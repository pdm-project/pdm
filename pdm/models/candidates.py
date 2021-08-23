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
        environment: Environment,
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
        self.environment = environment
        self.name = name or self.req.project_name
        self.version = version or self.req.version
        if link is None and self.req:
            link = self.ireq.link
        self.link = link
        self.source_dir: str | None = None
        self.hashes: dict[str, str] | None = None
        self._requires_python: str | None = None

        self.wheel: str | None = None
        self._metadata_dir: str | None = None

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    @cached_property
    def ireq(self) -> pip_shims.InstallRequirement:
        rv = self.req.as_ireq()
        if rv.link:
            rv.link = pip_shims.Link(
                expand_env_vars_in_auth(
                    rv.link.url.replace(
                        "${PROJECT_ROOT}",
                        self.environment.project.root.as_posix().lstrip(  # type: ignore
                            "/"
                        ),
                    )
                )
            )
            if rv.source_dir:
                rv.source_dir = os.path.normpath(os.path.abspath(rv.link.file_path))
            if rv.local_file_path:
                rv.local_file_path = rv.link.file_path
        return rv

    def identify(self) -> str:
        return self.req.identify()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Candidate):
            return False
        if self.req.is_named:
            return self.name == other.name and self.version == other.version
        return self.name == other.name and self.link == other.link

    @cached_property
    def revision(self) -> str:
        if not self.req.is_vcs:
            raise AttributeError("Non-VCS candidate doesn't have revision attribute")
        if self.req.revision:  # type: ignore
            return self.req.revision  # type: ignore
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
                    "url": url_without_fragments(req.url),
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
            with self.environment.get_finder() as finder:
                hash_cache = self.environment.project.make_hash_cache()
                hash_cache.session = finder.session  # type: ignore
                return _filter_none(
                    {
                        "url": url_without_fragments(req.url),
                        "archive_info": {
                            "hash": hash_cache.get_hash(
                                pip_shims.Link(req.url)
                            ).replace(":", "=")
                        },
                        "subdirectory": req.subdirectory,
                    }
                )
        else:
            return None

    def prepare(self, allow_all: bool = False) -> None:
        """Fetch the link of the candidate and unpack to local if necessary.

        :param allow_all: If true, don't validate the wheel tag nor hashes
        """
        if (
            self.source_dir
            or self.wheel
            and self._wheel_compatible(self.wheel, allow_all)
        ):
            return
        ireq = self.ireq
        if not allow_all and self.hashes:
            ireq.hash_options = convert_hashes(self.hashes)
        with self.environment.get_finder(ignore_requires_python=True) as finder:
            if (
                not self.link
                or self.link.is_wheel
                and not self._wheel_compatible(self.link.filename, allow_all)
            ):
                self.link = ireq.link = None
                with allow_all_wheels(allow_all):
                    self.link = populate_link(finder, ireq, False)
                if not self.link:
                    raise CandidateNotFound("No candidate is found for %s", self)
            if allow_all and not self.req.editable:
                cached = self._get_cached_wheel()
                if cached:
                    self.wheel = cached.file_path
                    return
            downloader = pip_shims.Downloader(finder.session, "off")  # type: ignore
            self._populate_source_dir(ireq)
            if not self.link.is_existing_dir():
                assert ireq.source_dir
                downloaded = pip_shims.unpack_url(
                    self.link,
                    ireq.source_dir,
                    downloader,
                    hashes=ireq.hashes(False),
                )
                if self.link.is_wheel:
                    assert downloaded
                    self.wheel = downloaded.path
                    return
            self.source_dir = ireq.unpacked_source_directory

    @cached_property
    def metadata(self) -> Distribution:
        """Get the metadata of the candidate.
        Will call the prepare_metadata_* hooks behind the scene
        """
        self.prepare(True)
        metadir_parent = create_tracked_tempdir(prefix="pdm-meta-")
        if self.wheel:
            self._metadata_dir = _get_wheel_metadata_from_wheel(
                self.wheel, metadir_parent
            )
            result: Distribution = PathDistribution(Path(self._metadata_dir))
        else:
            assert self.source_dir
            builder = EditableBuilder if self.req.editable else WheelBuilder
            try:
                self._metadata_dir = builder(
                    self.source_dir, self.environment
                ).prepare_metadata(metadir_parent)
            except BuildError:
                termui.logger.warn(
                    "Failed to build package, try parsing project files."
                )
                result = parse_metadata_from_source(self.source_dir)
            else:
                result = PathDistribution(Path(self._metadata_dir))
        if not self.name:
            self.name = str(result.metadata["Name"])  # type: ignore
            self.req.name = self.name
        if not self.version:
            self.version = result.version  # type: ignore
        self.requires_python = result.metadata.get("Requires-Python")
        return result

    def build(self) -> str:
        """Call PEP 517 build hook to build the candidate into a wheel"""
        self.prepare()
        if self.wheel:
            return self.wheel
        cached = self._get_cached_wheel()
        if cached:
            self.wheel = cached.file_path
            return self.wheel  # type: ignore
        assert self.source_dir, "Source directory isn't ready yet"
        builder_cls = EditableBuilder if self.req.editable else WheelBuilder
        builder = builder_cls(self.source_dir, self.environment)
        build_dir = self._get_wheel_dir()
        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        self.wheel = builder.build(build_dir, metadata_directory=self._metadata_dir)
        return self.wheel

    def __repr__(self) -> str:
        source = getattr(self.link, "comes_from", "unknown")
        return f"<Candidate {self.name} {self.version} from {source}>"

    @classmethod
    def from_installation_candidate(
        cls,
        candidate: pip_shims.InstallationCandidate,
        req: Requirement,
        environment: Environment,
    ) -> Candidate:
        """Build a candidate from pip's InstallationCandidate."""
        return cls(
            req,
            environment,
            name=candidate.name,
            version=str(candidate.version),
            link=candidate.link,
        )

    def get_dependencies_from_metadata(self) -> list[str]:
        """Get the dependencies of a candidate from metadata."""
        extras = self.req.extras or ()
        return filter_requirements_with_extras(
            self.metadata.requires or [], extras  # type: ignore
        )

    @property
    def requires_python(self) -> str:
        """The Python version constraint of the candidate."""
        if self._requires_python is not None:
            return self._requires_python
        assert self.link
        requires_python = self.link.requires_python
        if requires_python and requires_python.isdigit():
            requires_python = f">={requires_python},<{int(requires_python) + 1}"
            self._requires_python = requires_python
        return requires_python or ""

    @requires_python.setter
    def requires_python(self, value: str) -> None:
        self._requires_python = value

    @no_type_check
    def as_lockfile_entry(self) -> dict[str, Any]:
        """Build a lockfile entry dictionary for the candidate."""
        result = {
            "name": self.name,
            "version": str(self.version),
            "extras": sorted(self.req.extras or ()),
            "requires_python": str(self.requires_python),
            "editable": self.req.editable,
        }
        project_root = self.environment.project.root.as_posix()
        if self.req.is_vcs:
            result.update(
                {
                    self.req.vcs: self.req.repo,
                    "ref": self.req.ref,
                }
            )
            if not self.req.editable:
                result.update(revision=self.revision)
        elif not self.req.is_named:
            if self.req.is_file_or_url and self.req.is_local_dir:
                result.update(path=path_replace(project_root, ".", self.req.str_path))
            else:
                result.update(
                    url=path_replace(
                        project_root.lstrip("/"), "${PROJECT_ROOT}", self.req.url
                    )
                )
        return {k: v for k, v in result.items() if v}

    def format(self) -> str:
        """Format for output."""
        return (
            f"{termui.green(self.name, bold=True)} "
            f"{termui.yellow(str(self.version))}"
        )

    def _get_cached_wheel(self) -> pip_shims.Link | None:
        wheel_cache = self.environment.project.make_wheel_cache()
        supported_tags = pip_shims.get_supported(self.environment.interpreter.for_tag())
        assert self.link
        cache_entry = wheel_cache.get_cache_entry(
            self.link,
            self.req.project_name,  # type: ignore
            supported_tags,
        )
        if cache_entry is not None:
            termui.logger.debug("Using cached wheel link: %s", cache_entry.link)
            return cache_entry.link
        return None

    def _populate_source_dir(self, ireq: pip_shims.InstallRequirement) -> None:
        assert self.link
        if self.link.is_existing_dir():
            ireq.source_dir = self.link.file_path
        elif self.req.editable:
            if self.environment.packages_path:
                src_dir = self.environment.packages_path / "src"
            elif os.getenv("VIRTUAL_ENV"):
                src_dir = Path(os.environ["VIRTUAL_ENV"]) / "src"
            else:
                src_dir = Path("src")
            if not src_dir.is_dir():
                src_dir.mkdir()
            ireq.ensure_has_source_dir(str(src_dir))
        elif not ireq.source_dir:
            ireq.source_dir = create_tracked_tempdir(prefix="pdm-build-")

    def _wheel_compatible(self, wheel_file: str, allow_all: bool) -> bool:
        if allow_all:
            return True
        supported_tags = pip_shims.get_supported(self.environment.interpreter.for_tag())
        return pip_shims.PipWheel(os.path.basename(wheel_file)).supported(
            supported_tags
        )

    def _get_wheel_dir(self) -> str:
        should_cache = False
        wheel_cache = self.environment.project.make_wheel_cache()
        assert self.link
        if self.link.is_vcs and not self.req.editable:
            vcs = pip_shims.VcsSupport()
            vcs_backend = vcs.get_backend_for_scheme(self.link.scheme)
            if vcs_backend and vcs_backend.is_immutable_rev_checkout(
                self.link.url, cast(str, self.ireq.source_dir)
            ):
                should_cache = True
        elif not self.link.is_existing_dir():
            base, _ = self.link.splitext()
            if _egg_info_re.search(base) is not None:
                # Determine whether the string looks like an egg_info.
                should_cache = True
        if should_cache:
            return wheel_cache.get_path_for_link(self.link)
        else:
            return create_tracked_tempdir(prefix="pdm-wheel-")
