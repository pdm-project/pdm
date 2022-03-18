from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast, no_type_check
from zipfile import ZipFile

from pdm import termui
from pdm.builders import EditableBuilder, WheelBuilder
from pdm.exceptions import BuildError, CandidateNotFound
from pdm.models import pip_shims
from pdm.models.requirements import (
    FileRequirement,
    Requirement,
    VcsRequirement,
    _egg_info_re,
    filter_requirements_with_extras,
    parse_metadata_from_source,
)
from pdm.utils import (
    allow_all_wheels,
    cached_property,
    convert_hashes,
    create_tracked_tempdir,
    expand_env_vars_in_auth,
    get_rev_from_url,
    get_venv_like_prefix,
    normalize_name,
    path_replace,
    populate_link,
    url_without_fragments,
)

if sys.version_info >= (3, 8):
    from importlib.metadata import Distribution, PathDistribution
else:
    from importlib_metadata import Distribution, PathDistribution

if TYPE_CHECKING:
    from pdm.models.environment import Environment

vcs = pip_shims.VcsSupport()


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


def _get_wheel_metadata_from_wheel(whl_file: str, metadata_directory: str) -> str:
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


class Candidate:
    """A concrete candidate that can be downloaded and installed.
    A candidate comes from the PyPI index of a package, or from the requirement itself
    (for file or VCS requirements). Each candidate has a name, version and several
    dependencies together with package metadata.
    """

    def __init__(
        self,
        req: Requirement,
        name: str | None = None,
        version: str | None = None,
        link: pip_shims.Link | None = None,
    ):
        """
        :param req: the requirement that produces this candidate.
        :param environment: the bound environment instance.
        :param name: the name of the candidate.
        :param version: the version of the candidate.
        :param link: the file link of the candidate.
        """
        self.req = req
        self.name = name or self.req.project_name
        self.version = version or self.req.version
        self.link = link
        self.summary = ""
        self.hashes: dict[str, str] | None = None

        self._requires_python: str | None = None
        self._prepared: PreparedCandidate | None = None

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def identify(self) -> str:
        return self.req.identify()

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
        if self.req.revision:  # type: ignore
            return self.req.revision  # type: ignore
        assert self._prepared
        return self._prepared.revision

    def __repr__(self) -> str:
        source = getattr(self.link, "comes_from", "unknown")
        return f"<Candidate {self.name} {self.version} from {source}>"

    @classmethod
    def from_installation_candidate(
        cls, candidate: pip_shims.InstallationCandidate, req: Requirement
    ) -> Candidate:
        """Build a candidate from pip's InstallationCandidate."""
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
            if requires_python and requires_python.isdigit():
                requires_python = f">={requires_python},<{int(requires_python) + 1}"
            self._requires_python = requires_python
        return self._requires_python or ""

    @requires_python.setter
    def requires_python(self, value: str) -> None:
        self._requires_python = value

    @no_type_check
    def as_lockfile_entry(self, project_root: Path) -> dict[str, Any]:
        """Build a lockfile entry dictionary for the candidate."""
        root_path = project_root.as_posix()
        result = {
            "name": normalize_name(self.name),
            "version": str(self.version),
            "extras": sorted(self.req.extras or ()),
            "requires_python": str(self.requires_python),
            "editable": self.req.editable,
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
            if self.req.is_file_or_url and self.req.is_local_dir:
                result.update(path=path_replace(root_path, ".", self.req.str_path))
            else:
                result.update(
                    url=path_replace(
                        root_path.lstrip("/"), "${PROJECT_ROOT}", self.req.url
                    )
                )
        return {k: v for k, v in result.items() if v}

    def format(self) -> str:
        """Format for output."""
        return (
            f"{termui.green(self.name, bold=True)} "
            f"{termui.yellow(str(self.version))}"
        )

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
        self.wheel: str | None = None
        self.req = candidate.req
        self.ireq = self.get_ireq()

        self._metadata_dir: str | None = None
        self._metadata: Distribution | None = None

    def get_ireq(self) -> pip_shims.InstallRequirement:
        rv, project = self.req.as_ireq(), self.environment.project
        if rv.link:
            rv.original_link = rv.link = pip_shims.Link(
                expand_env_vars_in_auth(
                    rv.link.url.replace(
                        "${PROJECT_ROOT}",
                        project.root.as_posix().lstrip("/"),  # type: ignore
                    )
                )
            )
            if rv.source_dir:
                rv.source_dir = os.path.normpath(os.path.abspath(rv.link.file_path))
            if rv.local_file_path:
                rv.local_file_path = rv.link.file_path
        elif self.candidate.link:
            rv.link = rv.original_link = self.candidate.link
        return rv

    @cached_property
    def revision(self) -> str:
        if not (self.ireq.source_dir and os.path.exists(self.ireq.source_dir)):
            # It happens because the cached wheel is hit and the source code isn't
            # pulled to local. In this case the link url must contain the full commit
            # hash which can be taken as the revision safely.
            # See more info at https://github.com/pdm-project/pdm/issues/349
            rev = get_rev_from_url(self.ireq.original_link.url)  # type: ignore
            if rev:
                return rev
        return vcs.get_backend(self.req.vcs).get_revision(  # type: ignore
            cast(str, self.ireq.source_dir)
        )

    def direct_url(self) -> dict[str, Any] | None:
        """PEP 610 direct_url.json data"""
        req = self.req
        if isinstance(req, VcsRequirement):
            if req.editable:
                assert self.ireq.source_dir
                return _filter_none(
                    {
                        "url": pip_shims.path_to_url(self.ireq.source_dir),
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
            if req.is_local_dir:
                return _filter_none(
                    {
                        "url": url_without_fragments(req.url),
                        "dir_info": _filter_none({"editable": req.editable or None}),
                        "subdirectory": req.subdirectory,
                    }
                )
            url = expand_env_vars_in_auth(
                req.url.replace(
                    "${PROJECT_ROOT}",
                    self.environment.project.root.as_posix().lstrip(  # type: ignore
                        "/"
                    ),
                )
            )
            with self.environment.get_finder() as finder:
                hash_cache = self.environment.project.make_hash_cache()
                hash_cache.session = finder.session  # type: ignore
                return _filter_none(
                    {
                        "url": url_without_fragments(url),
                        "archive_info": {
                            "hash": hash_cache.get_hash(pip_shims.Link(url)).replace(
                                ":", "="
                            )
                        },
                        "subdirectory": req.subdirectory,
                    }
                )
        else:
            return None

    def build(self) -> str:
        """Call PEP 517 build hook to build the candidate into a wheel"""
        self.obtain(allow_all=False)
        if self.wheel:
            return self.wheel
        cached = self._get_cached_wheel()
        if cached:
            self.wheel = cached.file_path
            return self.wheel  # type: ignore
        assert self.ireq.source_dir, "Source directory isn't ready yet"
        builder_cls = EditableBuilder if self.req.editable else WheelBuilder
        builder = builder_cls(self.ireq.unpacked_source_directory, self.environment)
        build_dir = self._get_wheel_dir()
        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        termui.logger.debug("Building wheel for %s", self.ireq.link)
        self.wheel = builder.build(build_dir, metadata_directory=self._metadata_dir)
        return self.wheel

    def obtain(self, allow_all: bool = False) -> None:
        """Fetch the link of the candidate and unpack to local if necessary.

        :param allow_all: If true, don't validate the wheel tag nor hashes
        """
        ireq = self.ireq
        if self.wheel:
            if self._wheel_compatible(self.wheel, allow_all):
                return
        elif ireq.source_dir:
            return

        if not allow_all and self.candidate.hashes:
            ireq.hash_options = convert_hashes(self.candidate.hashes)
        with self.environment.get_finder(ignore_requires_python=True) as finder:
            if (
                not ireq.link
                or ireq.link.is_wheel
                and not self._wheel_compatible(ireq.link.filename, allow_all)
            ):
                ireq.link = self.wheel = None  # reset the incompatible wheel
                with allow_all_wheels(allow_all):
                    ireq.link = populate_link(finder, ireq, False)
                if not ireq.link:
                    raise CandidateNotFound("No candidate is found for %s", self)
                if not ireq.original_link:
                    ireq.original_link = ireq.link
            if allow_all and not self.req.editable:
                cached = self._get_cached_wheel()
                if cached:
                    self.wheel = cached.file_path
                    return
            downloader = pip_shims.Downloader(finder.session, "off")  # type: ignore
            self._populate_source_dir()
            if not ireq.link.is_existing_dir():
                assert ireq.source_dir
                downloaded = pip_shims.unpack_url(  # type: ignore
                    ireq.link,
                    ireq.source_dir,
                    downloader,
                    hashes=ireq.hashes(False),
                )
                if ireq.link.is_wheel:
                    assert downloaded
                    self.wheel = downloaded.path
                    return

    def prepare_metadata(self) -> Distribution:
        """Prepare the metadata for the candidate.
        Will call the prepare_metadata_* hooks behind the scene
        """
        self.obtain(allow_all=True)
        metadir_parent = create_tracked_tempdir(prefix="pdm-meta-")
        result: Distribution
        if self.wheel:
            self._metadata_dir = _get_wheel_metadata_from_wheel(
                self.wheel, metadir_parent
            )
            result = PathDistribution(Path(self._metadata_dir))
        else:
            source_dir = self.ireq.unpacked_source_directory
            builder = EditableBuilder if self.req.editable else WheelBuilder
            try:
                self._metadata_dir = builder(
                    source_dir, self.environment
                ).prepare_metadata(metadir_parent)
            except BuildError:
                termui.logger.warn(
                    "Failed to build package, try parsing project files."
                )
                result = parse_metadata_from_source(source_dir)
            else:
                result = PathDistribution(Path(self._metadata_dir))
        if not self.candidate.name:
            self.req.name = self.candidate.name = cast(str, result.metadata["Name"])
        if not self.candidate.version:
            self.candidate.version = result.version
        if not self.candidate.requires_python:
            self.candidate.requires_python = cast(
                str, result.metadata.get("Requires-Python", "")
            )
        return result

    @property
    def metadata(self) -> Distribution:
        if self._metadata is None:
            self._metadata = self.prepare_metadata()
        return self._metadata

    def get_dependencies_from_metadata(self) -> list[str]:
        """Get the dependencies of a candidate from metadata."""
        extras = self.req.extras or ()
        return filter_requirements_with_extras(
            self.req.project_name, self.metadata.requires or [], extras  # type: ignore
        )

    def should_cache(self) -> bool:
        """Determine whether to cache the dependencies and built wheel."""
        link, source_dir = self.ireq.original_link, self.ireq.source_dir
        if self.req.is_vcs and not self.req.editable:
            if not source_dir:
                # If the candidate isn't prepared, we can't cache it
                return False
            vcs = pip_shims.VcsSupport()
            assert link
            vcs_backend = vcs.get_backend_for_scheme(link.scheme)
            return bool(
                vcs_backend
                and vcs_backend.is_immutable_rev_checkout(link.url, source_dir)
            )
        elif self.req.is_named:
            return True
        elif link and not link.is_existing_dir():
            base, _ = link.splitext()
            # Cache if the link contains egg-info like 'foo-1.0'
            return _egg_info_re.search(base) is not None
        return False

    def _get_cached_wheel(self) -> pip_shims.Link | None:
        wheel_cache = self.environment.project.make_wheel_cache()
        supported_tags = pip_shims.get_supported(self.environment.interpreter.for_tag())
        assert self.ireq.original_link
        cache_entry = wheel_cache.get_cache_entry(
            self.ireq.original_link, cast(str, self.req.project_name), supported_tags
        )
        if cache_entry is not None:
            termui.logger.debug("Using cached wheel link: %s", cache_entry.link)
            return cache_entry.link
        return None

    def _populate_source_dir(self) -> None:
        ireq = self.ireq
        assert ireq.original_link
        if ireq.original_link.is_existing_dir():
            ireq.source_dir = ireq.original_link.file_path
        elif self.req.editable:
            if self.environment.packages_path:
                src_dir = self.environment.packages_path / "src"
            else:
                venv_prefix = get_venv_like_prefix(
                    self.environment.interpreter.executable
                )
                if venv_prefix is not None:
                    src_dir = venv_prefix / "src"
                else:
                    src_dir = Path("src")
            if not src_dir.is_dir():
                src_dir.mkdir()
            ireq.ensure_has_source_dir(str(src_dir))
        elif not ireq.source_dir:
            ireq.source_dir = create_tracked_tempdir(prefix="pdm-build-")

    def _wheel_compatible(self, wheel_file: str, allow_all: bool = False) -> bool:
        if allow_all:
            return True
        supported_tags = pip_shims.get_supported(self.environment.interpreter.for_tag())
        return pip_shims.PipWheel(os.path.basename(wheel_file)).supported(
            supported_tags
        )

    def _get_wheel_dir(self) -> str:
        assert self.ireq.original_link
        if self.should_cache():
            wheel_cache = self.environment.project.make_wheel_cache()
            return wheel_cache.get_path_for_link(self.ireq.original_link)
        else:
            return create_tracked_tempdir(prefix="pdm-wheel-")
