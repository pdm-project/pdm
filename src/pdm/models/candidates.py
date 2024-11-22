from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import warnings
from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, cast, no_type_check
from zipfile import ZipFile

from packaging.version import InvalidVersion

from pdm import termui
from pdm.builders import EditableBuilder, WheelBuilder
from pdm.compat import importlib_metadata as im
from pdm.exceptions import BuildError, CandidateNotFound, InvalidPyVersion, PDMWarning, RequirementError
from pdm.models.backends import get_backend, get_backend_by_spec
from pdm.models.reporter import CandidateReporter
from pdm.models.requirements import (
    FileRequirement,
    Requirement,
    VcsRequirement,
    _egg_info_re,
    filter_requirements_with_extras,
)
from pdm.models.setup import Setup
from pdm.models.specifiers import PySpecSet
from pdm.utils import (
    comparable_version,
    convert_hashes,
    filtered_sources,
    get_rev_from_url,
    normalize_name,
    path_to_url,
    url_without_fragments,
)

if TYPE_CHECKING:
    from importlib.metadata import _SimplePath

    from unearth import Link, Package, PackageFinder

    from pdm._types import FileHash
    from pdm.environments import BaseEnvironment


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


def _find_best_match_link(finder: PackageFinder, req: Requirement, files: list[FileHash]) -> Link | None:
    """Get the best matching link for a requirement"""

    # This function is called when a lock file candidate is given or incompatible wheel
    # In this case, the requirement must be pinned, so no need to pass allow_prereleases
    # If links are not empty, find the best match from the links, otherwise find from
    # the package sources.
    from unearth import Link

    links = [Link(f["url"]) for f in files if "url" in f]
    hashes = convert_hashes(files)

    if not links:
        best = finder.find_best_match(req.as_line(), hashes=hashes).best
    else:
        # this branch won't be executed twice if ignore_compatibility is True
        evaluator = finder.build_evaluator(req.name)
        packages = finder._evaluate_links(links, evaluator)
        best = max(packages, key=finder._sort_key, default=None)
    return best.link if best is not None else None


class MetadataDistribution(im.Distribution):
    """A wrapper around a single METADATA file to provide the Distribution interface"""

    def __init__(self, text: str) -> None:
        self.text = text

    def locate_file(self, path: str | os.PathLike[str]) -> _SimplePath:
        return Path()

    def read_text(self, filename: str) -> str | None:
        if filename != "":
            return None
        return self.text


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
        "_revision",
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
            link = cast("Link", req.as_file_link())  # type: ignore[attr-defined]
        self.link = link
        self.summary = ""
        self.hashes: list[FileHash] = []

        self._requires_python: str | None = None
        self._prepared: PreparedCandidate | None = None
        self._revision = getattr(req, "revision", None)

    def identify(self) -> str:
        return self.req.identify()

    def copy_with(self, requirement: Requirement) -> Candidate:
        can = Candidate(requirement, name=self.name, version=self.version, link=self.link)
        can.summary = self.summary
        can.hashes = self.hashes
        can._requires_python = self._requires_python
        can._prepared = self._prepared
        can._revision = self._revision
        if can._prepared:
            can._prepared.req = requirement
        return can

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
        if self._revision:
            return self._revision
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
        try:  # ensure the specifier is valid
            PySpecSet(value)
        except InvalidPyVersion:
            return
        self._requires_python = value

    @no_type_check
    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        """Build a lockfile entry dictionary for the candidate."""
        version = str(self.version)
        if not self.req.is_pinned:
            try:
                version = str(comparable_version(version))
            except InvalidVersion as e:
                raise RequirementError(f"Invalid version for {self.req.as_line()}: {e}") from None
        result = {
            "name": normalize_name(self.name),
            "version": version,
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
            if self.req.is_file_or_url and self.req.is_local:
                result.update(path=self.req.str_path)
            else:
                result.update(url=self.req.url)
        return {k: v for k, v in result.items() if v}

    def format(self) -> str:
        """Format for output."""
        return f"[req]{self.name}[/] [warning]{self.version}[/]"

    def prepare(self, environment: BaseEnvironment, reporter: CandidateReporter | None = None) -> PreparedCandidate:
        """Prepare the candidate for installation."""
        if self._prepared is None:
            self._prepared = PreparedCandidate(self, environment, reporter=reporter or CandidateReporter())
        else:
            self._prepared.environment = environment
            if reporter is not None:
                self._prepared.reporter = reporter
        return self._prepared


@dataclasses.dataclass
class PreparedCandidate:
    """A candidate that has been prepared for installation.
    The metadata and built wheel are available.
    """

    candidate: Candidate
    environment: BaseEnvironment
    reporter: CandidateReporter = dataclasses.field(default_factory=CandidateReporter)

    def __post_init__(self) -> None:
        self.req = self.candidate.req
        self.link = self._replace_url_vars(self.candidate.link)

        self._cached: Path | None = None
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
        from unearth import vcs_support

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
            hash_cache = self.environment.project.make_hash_cache()
            return _filter_none(
                {
                    "url": self.link.url_without_fragment,
                    "archive_info": {
                        "hash": hash_cache.get_hash(self.link, self.environment.session).replace(":", "=")
                    },
                    "subdirectory": req.subdirectory,
                }
            )
        else:
            return None

    def build(self) -> Path:
        """Call PEP 517 build hook to build the candidate into a wheel"""
        self._obtain(allow_all=False)
        if self._cached:
            return self._cached
        if not self.req.editable:
            cached = self._get_build_cache()
            if cached:
                return cached
        assert self._source_dir, "Source directory isn't ready yet"
        builder_cls = EditableBuilder if self.req.editable else WheelBuilder
        builder = builder_cls(str(self._unpacked_dir), self.environment)
        build_dir = self._get_wheel_dir()
        os.makedirs(build_dir, exist_ok=True)
        termui.logger.info("Running PEP 517 backend to build a wheel for %s", self.link)
        self.reporter.report_build_start(self.link.filename)  # type: ignore[union-attr]
        self._cached = Path(builder.build(build_dir, metadata_directory=self._metadata_dir))
        self.reporter.report_build_end(self.link.filename)  # type: ignore[union-attr]
        return self._cached

    def _obtain(self, allow_all: bool = False, unpack: bool = True) -> None:
        """Fetch the link of the candidate and unpack to local if necessary.

        :param allow_all: If true, don't validate the wheel tag nor hashes
        :param unpack: Whether to download and unpack the link if it's not local
        """
        if self._cached and self._wheel_compatible(self._cached.name, allow_all):
            return

        if self._source_dir and self._source_dir.exists():
            return

        sources = filtered_sources(self.environment.project.sources, self.req.key)
        env_spec = self.environment.allow_all_spec if allow_all else self.environment.spec
        with self.environment.get_finder(sources, env_spec=env_spec) as finder:
            if not self.link or self.link.is_wheel and not self._wheel_compatible(self.link.filename, allow_all):
                if self.req.is_file_or_url:
                    raise CandidateNotFound(f"The URL requirement {self.req.as_line()} is a wheel but incompatible")
                self.link = self._cached = None  # reset the incompatible wheel
                self.link = _find_best_match_link(
                    finder, self.req.as_pinned_version(self.candidate.version), self.candidate.hashes
                )
                if not self.link:
                    raise CandidateNotFound(
                        f"No candidate is found for `{self.req.project_name}` that matches the environment or hashes"
                    )
                if not self.candidate.link:
                    self.candidate.link = self.link
        # find if there is any build cache for the candidate
        if not self.req.editable:
            cached = self._get_build_cache()
            if cached and self._wheel_compatible(cached.name, allow_all):
                self._cached = cached
                return
        # If not, download and unpack the link
        if unpack:
            self._unpack(validate_hashes=not allow_all)

    def _unpack(self, validate_hashes: bool = False) -> None:
        hash_options = None
        if validate_hashes and self.candidate.hashes:
            hash_options = convert_hashes(self.candidate.hashes)
        assert self.link is not None
        with self.environment.get_finder() as finder:
            with TemporaryDirectory(prefix="pdm-download-") as tmpdir:
                build_dir = self._get_build_dir()
                if self.link.is_wheel:
                    download_dir = build_dir
                else:
                    download_dir = tmpdir
                result = finder.download_and_unpack(
                    self.link,
                    build_dir,
                    download_dir,
                    hash_options,
                    download_reporter=self.reporter.report_download,
                    unpack_reporter=self.reporter.report_unpack,
                )
        if self.link.is_wheel:
            self._cached = result
        else:
            self._source_dir = Path(build_dir)
            self._unpacked_dir = result

    def prepare_metadata(self, force_build: bool = False) -> im.Distribution:
        self._obtain(allow_all=True, unpack=False)
        if self._metadata_dir:
            return im.PathDistribution(Path(self._metadata_dir))

        if self._cached:
            return self._get_metadata_from_wheel(self._cached)

        assert self.link is not None
        if self.link.dist_info_metadata:
            assert self.link.dist_info_link
            dist = self._get_metadata_from_metadata_link(self.link.dist_info_link, self.link.dist_info_metadata)
            if dist is not None:
                return dist

        self._unpack(validate_hashes=False)
        if self._cached:  # check again if the wheel is downloaded to local
            return self._get_metadata_from_wheel(self._cached)

        assert self._unpacked_dir, "Source directory isn't ready yet"
        pyproject_toml = self._unpacked_dir / "pyproject.toml"
        if not force_build and pyproject_toml.exists():
            dist = self._get_metadata_from_project(pyproject_toml)
            if dist is not None:
                return dist

        # If all fail, try building the source to get the metadata
        metadata_parent = self.environment.project.core.create_temp_dir(prefix="pdm-meta-")
        return self._get_metadata_from_build(self._unpacked_dir, metadata_parent)

    def _get_metadata_from_metadata_link(
        self, link: Link, medata_hash: bool | dict[str, str] | None
    ) -> im.Distribution | None:
        resp = self.environment.session.get(link.normalized)
        if isinstance(medata_hash, dict):
            hash_name, hash_value = next(iter(medata_hash.items()))
            if hashlib.new(hash_name, resp.content).hexdigest() != hash_value:
                termui.logger.warning("Metadata hash mismatch for %s, ignoring the metadata", link)
                return None
        return MetadataDistribution(resp.text)

    def _get_metadata_from_wheel(self, wheel: Path) -> im.Distribution:
        # Get metadata from METADATA inside the wheel
        metadata_parent = self.environment.project.core.create_temp_dir(prefix="pdm-meta-")
        dist_info = self._metadata_dir = _get_wheel_metadata_from_wheel(wheel, metadata_parent)
        return im.PathDistribution(Path(dist_info))

    def _get_metadata_from_project(self, pyproject_toml: Path) -> im.Distribution | None:
        # Try getting from PEP 621 metadata
        from pdm.formats import MetaConvertError
        from pdm.project.project_file import PyProject

        try:
            pyproject = PyProject(pyproject_toml, ui=self.environment.project.core.ui)
        except MetaConvertError as e:
            termui.logger.warning("Failed to parse pyproject.toml: %s", e)
            return None
        metadata = pyproject.metadata.unwrap()
        if not metadata:
            termui.logger.warning("Failed to parse pyproject.toml")
            return None

        dynamic_fields = metadata.get("dynamic", [])
        # Use the parse result only when all are static
        if not set(dynamic_fields).isdisjoint(
            {
                "name",
                "version",
                "dependencies",
                "optional-dependencies",
                "requires-python",
            }
        ):
            return None

        try:
            backend_cls = get_backend_by_spec(pyproject.build_system)
        except Exception:
            # no variable expansion
            backend_cls = get_backend("setuptools")
        backend = backend_cls(pyproject_toml.parent)
        if "name" not in metadata:
            termui.logger.warning("Failed to parse pyproject.toml, name is required")
            return None
        setup = Setup(
            name=metadata.get("name"),
            summary=metadata.get("description"),
            version=metadata.get("version", "0.0.0"),
            install_requires=list(
                map(
                    backend.expand_line,
                    metadata.get("dependencies", []),
                )
            ),
            extras_require={
                k: list(map(backend.expand_line, v)) for k, v in metadata.get("optional-dependencies", {}).items()
            },
            python_requires=metadata.get("requires-python"),
        )
        return setup.as_dist()

    def _get_metadata_from_build(self, source_dir: Path, metadata_parent: str) -> im.Distribution:
        builder = EditableBuilder if self.req.editable else WheelBuilder
        try:
            termui.logger.info("Running PEP 517 backend to get metadata for %s", self.link)
            self.reporter.report_build_start(self.link.filename)  # type: ignore[union-attr]
            self._metadata_dir = builder(source_dir, self.environment).prepare_metadata(metadata_parent)
            self.reporter.report_build_end(self.link.filename)  # type: ignore[union-attr]
        except BuildError:
            termui.logger.warning("Failed to build package, try parsing project files.")
            try:
                setup = Setup.from_directory(source_dir)
            except Exception:
                message = "Failed to parse the project files, dependencies may be missing"
                termui.logger.warning(message)
                warnings.warn(message, PDMWarning, stacklevel=1)
                setup = Setup()
            return setup.as_dist()
        else:
            return im.PathDistribution(Path(cast(str, self._metadata_dir)))

    @property
    def metadata(self) -> im.Distribution:
        if self._metadata is None:
            result = self.prepare_metadata()
            if not self.candidate.name:
                self.req.name = self.candidate.name = cast(str, result.metadata.get("Name"))
            if not self.candidate.version and result.metadata.get("Version"):
                self.candidate.version = result.version
            if not self.candidate.requires_python:
                self.candidate.requires_python = result.metadata.get("Requires-Python", "")
            self._metadata = result
        return self._metadata

    def get_dependencies_from_metadata(self) -> list[Requirement]:
        """Get the dependencies of a candidate from metadata."""
        extras = self.req.extras or ()
        return filter_requirements_with_extras(self.metadata.requires or [], extras)

    def should_cache(self) -> bool:
        """Determine whether to cache the dependencies and built wheel."""
        from unearth import vcs_support

        if not self.environment.project.core.state.enable_cache:
            return False

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

    def _get_build_cache(self) -> Path | None:
        if not self.environment.project.core.state.enable_cache:
            return None
        wheel_cache = self.environment.project.make_wheel_cache()
        assert self.candidate.link
        cache_entry = wheel_cache.get(self.candidate.link, self.candidate.name, self.environment.spec)
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
            prefix: Path | None = None
            if self.environment.is_local:
                prefix = self.environment.packages_path  # type: ignore[attr-defined]
            else:
                venv = self.environment.interpreter.get_venv()
                if venv is not None:
                    prefix = venv.root
            if prefix is not None:
                src_dir = prefix / "src"
            else:
                src_dir = Path("src")
            src_dir.mkdir(exist_ok=True, parents=True)
            dirname = self.candidate.name or self.req.name
            if not dirname:
                dirname, _ = os.path.splitext(original_link.filename)
            return str(src_dir / str(dirname))
        # Otherwise, for source dists, they will be unpacked into a *temp* directory.
        return self.environment.project.core.create_temp_dir(prefix="pdm-build-")

    def _wheel_compatible(self, wheel_file: str, allow_all: bool = False) -> bool:
        env_spec = self.environment.allow_all_spec if allow_all else self.environment.spec
        return env_spec.wheel_compatibility(wheel_file) is not None

    def _get_wheel_dir(self) -> str:
        assert self.candidate.link
        wheel_cache = self.environment.project.make_wheel_cache()
        if self.should_cache():
            termui.logger.info("Saving wheel to cache: %s", self.candidate.link)
            return wheel_cache.get_path_for_link(self.candidate.link, self.environment.spec).as_posix()
        else:
            return wheel_cache.get_ephemeral_path_for_link(self.candidate.link, self.environment.spec).as_posix()
