from __future__ import annotations

import dataclasses
import os
import re
import warnings
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Iterable, cast, no_type_check
from zipfile import ZipFile

from packaging.utils import parse_wheel_filename
from unearth import Link, vcs_support

from pdm import termui
from pdm.builders import EditableBuilder, WheelBuilder
from pdm.compat import cached_property
from pdm.compat import importlib_metadata as im
from pdm.exceptions import BuildError, CandidateNotFound, InvalidPyVersion
from pdm.models.backends import get_backend, get_backend_by_spec
from pdm.models.requirements import (
    FileRequirement,
    Requirement,
    VcsRequirement,
    _egg_info_re,
    filter_requirements_with_extras,
)
from pdm.models.setup import Setup
from pdm.models.specifiers import PySpecSet
from pdm.project.project_file import PyProject
from pdm.utils import (
    cd,
    convert_hashes,
    create_tracked_tempdir,
    get_rev_from_url,
    get_venv_like_prefix,
    normalize_name,
    path_to_url,
    url_without_fragments,
)

if TYPE_CHECKING:
    from unearth import Package, PackageFinder

    from pdm.models.environment import Environment


def _dist_info_files(whl_zip: ZipFile) -> list[str]:
    """Identify the .dist-info folder inside a wheel ZipFile."""
    res = []
    for path in whl_zip.namelist():
        m = re.match(r"[^/\\]+-[^/\\]+\.dist-info/", path)
        if m:
            res.append(path)
    if res:
        return res
    raise Exception("No .dist-info folder found in wheel")


def _get_wheel_metadata_from_wheel(whl_file: Path, metadata_directory: str) -> str:
    """Extract the metadata from a wheel.
    Fallback for when the build backend does not
    define the 'get_wheel_metadata' hook.
    """
    with ZipFile(whl_file) as zipf:
        dist_info = _dist_info_files(zipf)
        zipf.extractall(path=metadata_directory, members=dist_info)
    return os.path.join(metadata_directory, dist_info[0].split("/")[0])


def _filter_none(data: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict without None values"""
    return {k: v for k, v in data.items() if v is not None}


def _find_best_match_link(
    finder: PackageFinder,
    req: Requirement,
    links: Iterable[Link] | None = None,
    ignore_compatibility: bool = False,
) -> Link | None:
    """Get the best matching link for a requirement"""

    # This function is called when a lock file candidate is given or incompatible wheel
    # In this case, the requirement must be pinned, so no need to pass allow_prereleases
    # If links are not empty, find the best match from the links, otherwise find from
    # the package sources.
    def attempt_to_find() -> Link | None:
        if links is None:
            best = finder.find_best_match(req.as_line()).best
        else:
            # this branch won't be executed twice if ignore_compatibility is True
            evaluator = finder.build_evaluator(req.name)
            packages = finder._evaluate_links(links, evaluator)
            best = max(packages, key=finder._sort_key, default=None)
        return best.link if best is not None else None

    assert finder.ignore_compatibility is False
    found = attempt_to_find()
    if ignore_compatibility and (found is None or not found.is_wheel):
        # try to find a wheel for easy metadata extraction
        finder.ignore_compatibility = True
        new_found = attempt_to_find()
        if new_found is not None:
            found = new_found
        finder.ignore_compatibility = False
    return found


class Candidate:
    """A concrete candidate that can be downloaded and installed.
    A candidate comes from the PyPI index of a package, or from the requirement itself
    (for file or VCS requirements). Each candidate has a name, version and several
    dependencies together with package metadata.
    """

    __slots__ = (
        "req",
        "name",
        "version",
        "link",
        "summary",
        "hashes",
        "_prepared",
        "_requires_python",
        "_preferred",
    )

    def __init__(
        self,
        req: Requirement,
        name: str | None = None,
        version: str | None = None,
        link: Link | None = None,
    ):
        """
        :param req: the requirement that produces this candidate.
        :param name: the name of the candidate.
        :param version: the version of the candidate.
        :param link: the file link of the candidate.
        """
        self.req = req
        self.name = name or self.req.project_name
        self.version = version
        if link is None and not req.is_named:
            link = req.as_file_link()  # type: ignore[attr-defined]
        self.link = link
        self.summary = ""
        self.hashes: dict[Link, str] | None = None

        self._requires_python: str | None = None
        self._prepared: PreparedCandidate | None = None

    def identify(self) -> str:
        return self.req.identify()

    @property
    def dep_key(self) -> tuple[str, str | None]:
        """Key for retrieving and storing dependencies from the provider.

        Return a tuple of (name, version). For URL candidates, the version is None but
        there will be only one for the same name so it is also unique.
        """
        return (self.identify(), self.version)

    @property
    def prepared(self) -> PreparedCandidate | None:
        return self._prepared

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Candidate):
            return False
        if self.req.is_named:
            return self.name == other.name and self.version == other.version
        return self.name == other.name and self.link == other.link

    def get_revision(self) -> str:
        if not self.req.is_vcs:
            raise AttributeError("Non-VCS candidate doesn't have revision attribute")
        if self.req.revision:  # type: ignore[attr-defined]
            return self.req.revision  # type: ignore[attr-defined]
        return self._prepared.revision if self._prepared else "unknown"

    def __repr__(self) -> str:
        source = getattr(self.link, "comes_from", None)
        from_source = f" from {source}" if source else ""
        return f"<Candidate {self}{from_source}>"

    def __str__(self) -> str:
        if self.req.is_named:
            return f"{self.name}@{self.version}"
        assert self.link is not None
        return f"{self.name}@{self.link.url_without_fragment}"

    @classmethod
    def from_installation_candidate(cls, candidate: Package, req: Requirement) -> Candidate:
        """Build a candidate from unearth's find result."""
        return cls(
            req,
            name=candidate.name,
            version=str(candidate.version),
            link=candidate.link,
        )

    @property
    def requires_python(self) -> str:
        """The Python version constraint of the candidate."""
        if self._requires_python is not None:
            return self._requires_python
        if self.link:
            requires_python = self.link.requires_python
            if requires_python is not None:
                if requires_python.isdigit():
                    requires_python = f">={requires_python},<{int(requires_python) + 1}"
                try:  # ensure the specifier is valid
                    PySpecSet(requires_python)
                except InvalidPyVersion:
                    pass
                else:
                    self._requires_python = requires_python
        return self._requires_python or ""

    @requires_python.setter
    def requires_python(self, value: str) -> None:
        self._requires_python = value

    @no_type_check
    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        """Build a lockfile entry dictionary for the candidate."""
        result = {
            "name": normalize_name(self.name),
            "version": str(self.version),
            "extras": sorted(self.req.extras or ()),
            "requires_python": str(self.requires_python),
            "editable": self.req.editable,
            "subdirectory": getattr(self.req, "subdirectory", None),
        }
        if self.req.is_vcs:
            result.update(
                {
                    self.req.vcs: self.req.repo,
                    "ref": self.req.ref,
                }
            )
            if not self.req.editable:
                result.update(revision=self.get_revision())
        elif not self.req.is_named:
            with cd(project_root):
                if self.req.is_file_or_url and self.req.is_local:
                    result.update(path=self.req.str_path)
                else:
                    result.update(url=self.req.url)
        return {k: v for k, v in result.items() if v}

    def format(self) -> str:
        """Format for output."""
        return f"[req]{self.name}[/] [warning]{self.version}[/]"

    def prepare(self, environment: Environment) -> PreparedCandidate:
        """Prepare the candidate for installation."""
        if self._prepared is None:
            self._prepared = PreparedCandidate(self, environment)
        return self._prepared


class PreparedCandidate:
    """A candidate that has been prepared for installation.
    The metadata and built wheel are available.
    """

    def __init__(self, candidate: Candidate, environment: Environment) -> None:
        self.candidate = candidate
        self.environment = environment
        self.req = candidate.req

        self.wheel: Path | None = None
        self.link = self._replace_url_vars(self.candidate.link)

        self._source_dir: Path | None = None
        self._unpacked_dir: Path | None = None
        self._metadata_dir: str | None = None
        self._metadata: im.Distribution | None = None

        if self.link is not None and self.link.is_file and self.link.file_path.is_dir():
            self._source_dir = self.link.file_path
            self._unpacked_dir = self._source_dir / (self.link.subdirectory or "")

    def _replace_url_vars(self, link: Link | None) -> Link | None:
        if link is None:
            return None
        url = self.environment.project.backend.expand_line(link.normalized)
        return dataclasses.replace(link, url=url)

    @cached_property
    def revision(self) -> str:
        if not (self._source_dir and os.path.exists(self._source_dir)):
            # It happens because the cached wheel is hit and the source code isn't
            # pulled to local. In this case the link url must contain the full commit
            # hash which can be taken as the revision safely.
            # See more info at https://github.com/pdm-project/pdm/issues/349
            rev = get_rev_from_url(self.candidate.link.url)  # type: ignore[union-attr]
            if rev:
                return rev
        assert isinstance(self.req, VcsRequirement)
        return vcs_support.get_backend(self.req.vcs, self.environment.project.core.ui.verbosity).get_revision(
            cast(Path, self._source_dir)
        )

    def direct_url(self) -> dict[str, Any] | None:
        """PEP 610 direct_url.json data"""
        req = self.req
        if isinstance(req, VcsRequirement):
            if req.editable:
                assert self._source_dir
                return _filter_none(
                    {
                        "url": path_to_url(self._source_dir.as_posix()),
                        "dir_info": {"editable": True},
                        "subdirectory": req.subdirectory,
                    }
                )
            return _filter_none(
                {
                    "url": url_without_fragments(req.repo),
                    "vcs_info": _filter_none(
                        {
                            "vcs": req.vcs,
                            "requested_revision": req.ref,
                            "commit_id": self.revision,
                        }
                    ),
                    "subdirectory": req.subdirectory,
                }
            )
        elif isinstance(req, FileRequirement):
            assert self.link is not None
            if self.link.is_file and self.link.file_path.is_dir():
                return _filter_none(
                    {
                        "url": self.link.url_without_fragment,
                        "dir_info": _filter_none({"editable": req.editable or None}),
                        "subdirectory": req.subdirectory,
                    }
                )
            with self.environment.get_finder() as finder:
                hash_cache = self.environment.project.make_hash_cache()
                return _filter_none(
                    {
                        "url": self.link.url_without_fragment,
                        "archive_info": {"hash": hash_cache.get_hash(self.link, finder.session).replace(":", "=")},
                        "subdirectory": req.subdirectory,
                    }
                )
        else:
            return None

    def build(self) -> Path:
        """Call PEP 517 build hook to build the candidate into a wheel"""
        self.obtain(allow_all=False)
        if self.wheel:
            return self.wheel
        if not self.req.editable:
            cached = self._get_cached_wheel()
            if cached:
                self.wheel = cached
                return self.wheel
        assert self._source_dir, "Source directory isn't ready yet"
        builder_cls = EditableBuilder if self.req.editable else WheelBuilder
        builder = builder_cls(str(self._unpacked_dir), self.environment)
        build_dir = self._get_wheel_dir()
        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        termui.logger.info("Running PEP 517 backend to build a wheel for %s", self.link)
        self.wheel = Path(builder.build(build_dir, metadata_directory=self._metadata_dir))
        return self.wheel

    def obtain(self, allow_all: bool = False) -> None:
        """Fetch the link of the candidate and unpack to local if necessary.

        :param allow_all: If true, don't validate the wheel tag nor hashes
        """
        if self.wheel:
            if self._wheel_compatible(self.wheel.name, allow_all):
                return
        elif self._source_dir and self._source_dir.exists():
            return
        hash_options = None
        if not allow_all and self.candidate.hashes:
            hash_options = convert_hashes(self.candidate.hashes)
        with self.environment.get_finder() as finder:
            if not self.link or self.link.is_wheel and not self._wheel_compatible(self.link.filename, allow_all):
                if self.req.is_file_or_url:
                    raise CandidateNotFound(f"The URL requirement {self.req.as_line()} is a wheel but incompatible")
                self.link = self.wheel = None  # reset the incompatible wheel
                self.link = _find_best_match_link(
                    finder,
                    self.req.as_pinned_version(self.candidate.version),
                    self.candidate.hashes,
                    ignore_compatibility=allow_all,
                )
                if not self.link:
                    raise CandidateNotFound(
                        f"No candidate is found for `{self.req.project_name}` that matches the environment or hashes"
                    )
                if not self.candidate.link:
                    self.candidate.link = self.link
            if allow_all and not self.req.editable:
                cached = self._get_cached_wheel()
                if cached:
                    self.wheel = cached
                    return
            with TemporaryDirectory(prefix="pdm-download-") as tmpdir:
                build_dir = self._get_build_dir()
                if self.link.is_wheel:
                    download_dir = build_dir
                else:
                    download_dir = tmpdir
                result = finder.download_and_unpack(self.link, build_dir, download_dir, hash_options)
                if self.link.is_wheel:
                    self.wheel = result
                else:
                    self._source_dir = Path(build_dir)
                    self._unpacked_dir = result

    def prepare_metadata(self) -> im.Distribution:
        self.obtain(allow_all=True)
        metadir_parent = create_tracked_tempdir(prefix="pdm-meta-")
        if self.wheel:
            # Get metadata from METADATA inside the wheel
            self._metadata_dir = _get_wheel_metadata_from_wheel(self.wheel, metadir_parent)
            return im.PathDistribution(Path(self._metadata_dir))

        assert self._unpacked_dir, "Source directory isn't ready yet"
        # Try getting from PEP 621 metadata
        pyproject_toml = self._unpacked_dir / "pyproject.toml"
        if pyproject_toml.exists():
            pyproject = PyProject(pyproject_toml, ui=self.environment.project.core.ui)
            metadata = pyproject.metadata.unwrap()
            if not metadata:
                termui.logger.warn("Failed to parse pyproject.toml")
            else:
                dynamic_fields = metadata.get("dynamic", [])
                # Use the parse result only when all are static
                if set(dynamic_fields).isdisjoint(
                    {
                        "name",
                        "version",
                        "dependencies",
                        "optional-dependencies",
                        "requires-python",
                    }
                ):
                    try:
                        backend_cls = get_backend_by_spec(pyproject.build_system)
                    except Exception:
                        # no variable expansion
                        backend_cls = get_backend("setuptools")
                    backend = backend_cls(self._unpacked_dir)
                    setup = Setup(
                        name=metadata.get("name"),
                        summary=metadata.get("description"),
                        version=metadata.get("version"),
                        install_requires=list(
                            map(
                                backend.expand_line,
                                metadata.get("dependencies", []),
                            )
                        ),
                        extras_require={
                            k: list(map(backend.expand_line, v))
                            for k, v in metadata.get("optional-dependencies", {}).items()
                        },
                        python_requires=metadata.get("requires-python"),
                    )
                    return setup.as_dist()
        # If all fail, try building the source to get the metadata
        builder = EditableBuilder if self.req.editable else WheelBuilder
        try:
            termui.logger.info("Running PEP 517 backend to get metadata for %s", self.link)
            self._metadata_dir = builder(self._unpacked_dir, self.environment).prepare_metadata(metadir_parent)
        except BuildError:
            termui.logger.warn("Failed to build package, try parsing project files.")
            try:
                setup = Setup.from_directory(self._unpacked_dir)
            except Exception:
                message = "Failed to parse the project files, dependencies may be missing"
                termui.logger.warn(message)
                warnings.warn(message, RuntimeWarning)
                setup = Setup()
            return setup.as_dist()
        else:
            return im.PathDistribution(Path(cast(str, self._metadata_dir)))

    @property
    def metadata(self) -> im.Distribution:
        if self._metadata is None:
            result = self.prepare_metadata()
            if not self.candidate.name:
                self.req.name = self.candidate.name = cast(str, result.metadata["Name"])
            if not self.candidate.version:
                self.candidate.version = result.version
            if not self.candidate.requires_python:
                self.candidate.requires_python = cast(str, result.metadata["Requires-Python"] or "")
            self._metadata = result
        return self._metadata

    def get_dependencies_from_metadata(self) -> list[str]:
        """Get the dependencies of a candidate from metadata."""
        extras = self.req.extras or ()
        return filter_requirements_with_extras(
            self.req.project_name, self.metadata.requires or [], extras  # type: ignore[arg-type]
        )

    def should_cache(self) -> bool:
        """Determine whether to cache the dependencies and built wheel."""
        link, source_dir = self.candidate.link, self._source_dir
        if self.req.editable:
            return False
        if self.req.is_named:
            return True
        if self.req.is_vcs:
            if not source_dir:
                # If the candidate isn't prepared, we can't cache it
                return False
            assert link
            vcs_backend = vcs_support.get_backend(link.vcs, self.environment.project.core.ui.verbosity)
            return vcs_backend.is_immutable_revision(source_dir, link)
        if link and not (link.is_file and link.file_path.is_dir()):
            # Cache if the link contains egg-info like 'foo-1.0'
            return _egg_info_re.search(link.filename) is not None
        return False

    def _get_cached_wheel(self) -> Path | None:
        wheel_cache = self.environment.project.make_wheel_cache()
        assert self.candidate.link
        cache_entry = wheel_cache.get(self.candidate.link, self.candidate.name, self.environment.target_python)
        if cache_entry is not None:
            termui.logger.info("Using cached wheel: %s", cache_entry)
        return cache_entry

    def _get_build_dir(self) -> str:
        original_link = self.candidate.link
        assert original_link
        if original_link.is_file and original_link.file_path.is_dir():
            # Local directories are built in tree
            return str(original_link.file_path)
        if self.req.editable:
            # In this branch the requirement must be an editable VCS requirement.
            # The repository will be unpacked into a *persistent* src directory.
            if self.environment.packages_path:
                src_dir = self.environment.packages_path / "src"
            else:
                venv_prefix = get_venv_like_prefix(self.environment.interpreter.executable)
                if venv_prefix is not None:
                    src_dir = venv_prefix / "src"
                else:
                    src_dir = Path("src")
            src_dir.mkdir(exist_ok=True, parents=True)
            dirname = self.candidate.name or self.req.name
            if not dirname:
                dirname, _ = os.path.splitext(original_link.filename)
            return str(src_dir / str(dirname))
        # Otherwise, for source dists, they will be unpacked into a *temp* directory.
        return create_tracked_tempdir(prefix="pdm-build-")

    def _wheel_compatible(self, wheel_file: str, allow_all: bool = False) -> bool:
        if allow_all:
            return True
        supported_tags = self.environment.target_python.supported_tags()
        file_tags = parse_wheel_filename(wheel_file)[-1]
        return not file_tags.isdisjoint(supported_tags)

    def _get_wheel_dir(self) -> str:
        assert self.candidate.link
        if self.should_cache():
            termui.logger.info("Saving wheel to cache: %s", self.candidate.link)
            wheel_cache = self.environment.project.make_wheel_cache()
            return wheel_cache.get_path_for_link(self.candidate.link, self.environment.target_python).as_posix()
        else:
            return create_tracked_tempdir(prefix="pdm-wheel-")


@lru_cache(maxsize=None)
def make_candidate(
    req: Requirement,
    name: str | None = None,
    version: str | None = None,
    link: Link | None = None,
) -> Candidate:
    """Construct a candidate and cache it in memory"""
    return Candidate(req, name, version, link)
