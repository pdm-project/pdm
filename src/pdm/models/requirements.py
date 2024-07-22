from __future__ import annotations

import dataclasses
import functools
import inspect
import json
import os
import posixpath
import re
import secrets
import urllib.parse as urlparse
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence, TypeVar, cast

from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement as PackageRequirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import parse_sdist_filename, parse_wheel_filename

from pdm.compat import Distribution
from pdm.exceptions import RequirementError
from pdm.models.backends import BuildBackend, get_relative_path
from pdm.models.markers import Marker, get_marker
from pdm.models.setup import Setup
from pdm.models.specifiers import PySpecSet, fix_legacy_specifier, get_specifier
from pdm.utils import (
    PACKAGING_22,
    add_ssh_scheme_to_git_uri,
    comparable_version,
    normalize_name,
    path_to_url,
    path_without_fragments,
    url_to_path,
    url_without_fragments,
)

if TYPE_CHECKING:
    from unearth import Link

    from pdm._types import RequirementDict


VCS_SCHEMA = ("git", "hg", "svn", "bzr")
_vcs_req_re = re.compile(
    rf"(?P<url>(?P<vcs>{'|'.join(VCS_SCHEMA)})\+[^\s;]+)(?P<marker>[\t ]*;[^\n]+)?",
    flags=re.IGNORECASE,
)
_file_req_re = re.compile(
    r"(?:(?P<url>\S+://[^\s\[\];]+)|"
    r"(?P<path>(?:[^\s;\[\]]|\\ )*"
    r"|'(?:[^']|\\')*'"
    r"|\"(?:[^\"]|\\\")*\"))"
    r"(?P<extras>\[[^\[\]]+\])?(?P<marker>[\t ]*;[^\n]+)?"
)
_egg_info_re = re.compile(r"([a-z0-9_.]+)-([a-z0-9_.!+-]+)", re.IGNORECASE)
T = TypeVar("T", bound="Requirement")
ALLOW_ANY = SpecifierSet()


def strip_extras(line: str) -> tuple[str, tuple[str, ...] | None]:
    match = re.match(r"^(.+?)(?:\[([^\]]+)\])?$", line)
    assert match is not None
    name, extras_str = match.groups()
    extras = tuple({e.strip() for e in extras_str.split(",")}) if extras_str else None
    return name, extras


@functools.lru_cache(maxsize=None)
def _get_random_key(req: Requirement) -> str:
    return f":empty:{secrets.token_urlsafe(8)}"


@dataclasses.dataclass(eq=False)
class Requirement:
    """Base class of a package requirement.
    A requirement is a (virtual) specification of a package which contains
    some constraints of version, python version, or other marker.
    """

    name: str | None = None
    marker: Marker | None = None
    extras: Sequence[str] | None = None
    specifier: SpecifierSet = ALLOW_ANY
    editable: bool = False
    prerelease: bool | None = None
    groups: list[str] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        self.requires_python = self.marker.split_pyspec()[1] if self.marker else PySpecSet()

    @property
    def project_name(self) -> str | None:
        return normalize_name(self.name, lowercase=False) if self.name else None

    @property
    def key(self) -> str | None:
        return self.project_name.lower() if self.project_name else None

    @property
    def is_pinned(self) -> bool:
        if len(self.specifier) != 1:
            return False

        sp = next(iter(self.specifier))
        return sp.operator == "===" or sp.operator == "==" and "*" not in sp.version

    def as_pinned_version(self: T, other_version: str | None) -> T:
        """Return a new requirement with the given pinned version."""
        if self.is_pinned or not other_version:
            return self
        normalized = comparable_version(other_version)
        return dataclasses.replace(self, specifier=get_specifier(f"=={normalized}"))

    def _hash_key(self) -> tuple:
        return (
            self.key,
            frozenset(self.extras) if self.extras else None,
            str(self.marker) if self.marker else None,
        )

    def __hash__(self) -> int:
        return hash(self._hash_key())

    def __eq__(self, o: object) -> bool:
        return isinstance(o, Requirement) and self._hash_key() == o._hash_key()

    def identify(self) -> str:
        if not self.key:
            return _get_random_key(self)
        extras = "[{}]".format(",".join(sorted(self.extras))) if self.extras else ""
        return self.key + extras

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.as_line()}>"

    def __str__(self) -> str:
        return self.as_line()

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        if "marker" in kwargs:
            kwargs["marker"] = get_marker(kwargs["marker"])
        if "extras" in kwargs and isinstance(kwargs["extras"], str):
            kwargs["extras"] = tuple(e.strip() for e in kwargs["extras"][1:-1].split(","))
        version = kwargs.pop("version", "")
        try:
            kwargs["specifier"] = get_specifier(version)
        except InvalidSpecifier as e:
            raise RequirementError(f'Invalid specifier for {kwargs.get("name")}: {version}: {e}') from None
        return cls(**{k: v for k, v in kwargs.items() if k in inspect.signature(cls).parameters})

    @classmethod
    def from_dist(cls, dist: Distribution) -> Requirement:
        direct_url_json = dist.read_text("direct_url.json")
        if direct_url_json is not None:
            direct_url = json.loads(direct_url_json)
            data = {
                "name": dist.metadata.get("Name"),
                "url": direct_url.get("url"),
                "editable": direct_url.get("dir_info", {}).get("editable"),
                "subdirectory": direct_url.get("subdirectory"),
            }
            if "vcs_info" in direct_url:
                vcs_info = direct_url["vcs_info"]
                data.update(
                    url=f"{vcs_info['vcs']}+{direct_url['url']}",
                    ref=vcs_info.get("requested_revision"),
                    revision=vcs_info.get("commit_id"),
                )
                return VcsRequirement.create(**data)
            return FileRequirement.create(**data)
        return NamedRequirement.create(name=dist.metadata["Name"], version=f"=={dist.version}")

    @classmethod
    def from_req_dict(cls, name: str, req_dict: RequirementDict, check_installable: bool = True) -> Requirement:
        if isinstance(req_dict, str):  # Version specifier only.
            return NamedRequirement.create(name=name, version=req_dict)
        for vcs in VCS_SCHEMA:
            if vcs in req_dict:
                repo = cast(str, req_dict.pop(vcs, None))
                url = f"{vcs}+{repo}"
                return VcsRequirement.create(name=name, vcs=vcs, url=url, **req_dict)
        if "path" in req_dict or "url" in req_dict:
            return FileRequirement.create(name=name, **req_dict, check_installable=check_installable)
        return NamedRequirement.create(name=name, **req_dict)

    @property
    def is_named(self) -> bool:
        return isinstance(self, NamedRequirement)

    @property
    def is_vcs(self) -> bool:
        return isinstance(self, VcsRequirement)

    @property
    def is_file_or_url(self) -> bool:
        return type(self) is FileRequirement

    def as_line(self) -> str:
        raise NotImplementedError

    def matches(self, line: str) -> bool:
        """Return whether the passed in PEP 508 string
        is the same requirement as this one.
        """
        req = parse_line(line)
        return (
            self.key == req.key
            or isinstance(self, FileRequirement)
            and isinstance(req, FileRequirement)
            and self.url == req.url
        )

    @classmethod
    def from_pkg_requirement(cls, req: PackageRequirement) -> Requirement:
        from unearth import Link

        kwargs = {
            "name": req.name,
            "extras": req.extras,
            "specifier": req.specifier,
            "marker": get_marker(req.marker),
        }
        if getattr(req, "url", None):
            link = Link(cast(str, req.url))
            klass = VcsRequirement if link.is_vcs else FileRequirement
            return klass(url=cast(str, req.url), **kwargs)
        else:
            return NamedRequirement(**kwargs)  # type: ignore[arg-type]

    def _format_marker(self) -> str:
        if self.marker:
            return f"; {self.marker!s}"
        return ""


@dataclasses.dataclass(eq=False)
class NamedRequirement(Requirement):
    def as_line(self) -> str:
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        return f"{self.project_name}{extras}{self.specifier or ''}{self._format_marker()}"


@dataclasses.dataclass(eq=False)
class FileRequirement(Requirement):
    url: str = ""
    path: Path | None = None
    subdirectory: str | None = None
    check_installable: bool = True
    _root: Path = dataclasses.field(default_factory=Path.cwd, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._parse_url()
        if self.is_local_dir and self.check_installable:
            self._check_installable()

    def _hash_key(self) -> tuple:
        return (*super()._hash_key(), self.get_full_url(), self.editable)

    def guess_name(self) -> str | None:
        filename = os.path.basename(urlparse.unquote(url_without_fragments(self.url))).rsplit("@", 1)[0]
        if self.is_vcs:
            if self.vcs == "git":  # type: ignore[attr-defined]
                name = filename
                if name.endswith(".git"):
                    name = name[:-4]
                return name
            elif self.vcs == "hg":  # type: ignore[attr-defined]
                return filename
            else:  # svn and bzr
                name, in_branch, _ = filename.rpartition("/branches/")
                if not in_branch and name.endswith("/trunk"):
                    return name[:-6]
                return name
        elif filename.endswith(".whl"):
            return parse_wheel_filename(filename)[0]
        else:
            try:
                return parse_sdist_filename(filename)[0]
            except ValueError:
                match = _egg_info_re.match(filename)
                # Filename is like `<name>-<version>.tar.gz`, where name will be
                # extracted and version will be left to be determined from
                # the metadata.
                if match:
                    return match.group(1)
        return None

    @classmethod
    def create(cls: type[T], **kwargs: Any) -> T:
        if kwargs.get("path"):
            kwargs["path"] = Path(kwargs["path"])
        return super().create(**kwargs)

    @property
    def str_path(self) -> str | None:
        if not self.path:
            return None
        if self.path.is_absolute():
            try:
                result = self.path.relative_to(self._root).as_posix()
            except ValueError:
                return self.path.as_posix()
        else:
            result = self.path.as_posix()
        result = posixpath.normpath(result)
        if not result.startswith(("./", "../")):
            result = "./" + result
        if result.startswith("./../"):
            result = result[2:]
        return result

    def _parse_url(self) -> None:
        if not self.url and self.path and self.path.is_absolute():
            self.url = path_to_url(self.path.as_posix())
        if not self.path:
            path = get_relative_path(self.url)
            if path is None:
                try:
                    self.path = path_without_fragments(url_to_path(self.url))
                except AssertionError:
                    pass
            else:
                self.path = path_without_fragments(path)
        if self.url:
            self._parse_name_from_url()

    def relocate(self, backend: BuildBackend) -> None:
        """Change the project root to the given path"""
        if self.path is None or self.path.is_absolute():
            return
        # self.path is relative
        self.path = path_without_fragments(os.path.relpath(self.path, backend.root))
        path = self.path.as_posix()
        if path == ".":
            path = ""
        self.url = backend.relative_path_to_url(path)
        self._root = backend.root

    @property
    def absolute_path(self) -> Path | None:
        return self._root.joinpath(self.path) if self.path else None

    @property
    def is_local(self) -> bool:
        return (path := self.absolute_path) is not None and path.exists()

    @property
    def is_local_dir(self) -> bool:
        return self.is_local and cast(Path, self.absolute_path).is_dir()

    def as_file_link(self) -> Link:
        from unearth import Link

        url = self.get_full_url()
        # only subdirectory is useful in a file link
        if self.subdirectory:
            url += f"#subdirectory={self.subdirectory}"
        return Link(url)

    def get_full_url(self) -> str:
        return url_without_fragments(self.url)

    def as_line(self) -> str:
        project_name = f"{self.project_name}" if self.project_name else ""
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras and self.project_name else ""
        marker = self._format_marker()
        if marker:
            marker = f" {marker}"
        url = self.get_full_url()
        fragments = []
        if self.subdirectory:
            fragments.append(f"subdirectory={self.subdirectory}")
        if self.editable:
            if project_name:
                fragments.insert(0, f"egg={project_name}{extras}")
            fragment_str = ("#" + "&".join(fragments)) if fragments else ""
            return f"-e {url}{fragment_str}{marker}"
        delimiter = " @ " if project_name else ""
        fragment_str = ("#" + "&".join(fragments)) if fragments else ""
        return f"{project_name}{extras}{delimiter}{url}{fragment_str}{marker}"

    def _parse_name_from_url(self) -> None:
        parsed = urlparse.urlparse(self.url)
        fragments = dict(urlparse.parse_qsl(parsed.fragment))
        if "egg" in fragments:
            egg_info = urlparse.unquote(fragments["egg"])
            name, extras = strip_extras(egg_info)
            self.name = name
            if not self.extras:
                self.extras = extras
        if not self.name and not self.is_vcs:
            self.name = self.guess_name()

    def _check_installable(self) -> None:
        assert self.path
        if not self.path.exists():
            return
        if not (self.path.joinpath("setup.py").exists() or self.path.joinpath("pyproject.toml").exists()):
            raise RequirementError(f"The local path '{self.path}' is not installable.")
        result = Setup.from_directory(self.path.absolute())
        if result.name:
            self.name = result.name


@dataclasses.dataclass(eq=False)
class VcsRequirement(FileRequirement):
    vcs: str = ""
    ref: str | None = None
    revision: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.vcs:
            self.vcs = self.url.split("+", 1)[0]

    def get_full_url(self) -> str:
        url = super().get_full_url()
        if self.revision and not self.editable:
            url += f"@{self.revision}"
        elif self.ref:
            url += f"@{self.ref}"
        return url

    def _parse_url(self) -> None:
        vcs, url_no_vcs = self.url.split("+", 1)
        if url_no_vcs.startswith("git@"):
            url_no_vcs = add_ssh_scheme_to_git_uri(url_no_vcs)
        if not self.name:
            self._parse_name_from_url()
        ref = self.ref
        parsed = urlparse.urlparse(url_no_vcs)
        path = parsed.path
        fragments = dict(urlparse.parse_qsl(parsed.fragment))
        if "subdirectory" in fragments:
            self.subdirectory = fragments["subdirectory"]
        if "@" in parsed.path:
            path, ref = parsed.path.split("@", 1)
        repo = urlparse.urlunparse(parsed._replace(path=path, fragment=""))
        self.url = f"{vcs}+{repo}"
        self.repo, self.ref = repo, ref


def filter_requirements_with_extras(
    requirement_lines: list[str], extras: Sequence[str], include_default: bool = False
) -> list[Requirement]:
    """Filter the requirements with extras.
    If extras are given, return those with matching extra markers.
    Otherwise, return those without extra markers.
    """
    result: list[Requirement] = []
    for req in requirement_lines:
        _r = parse_requirement(req)
        req_extras = get_marker("")
        if _r.marker:
            rest, req_extras = _r.marker.split_extras()
            _r.marker = rest if not rest.is_any() else None
            if not req_extras.evaluate({"extra": extras or ""}):
                continue
        # Add to the requirements if:
        # The requirement has no extras while requested extras are empty or include_default is True, or
        # The requirement has extras, in which case the `evaluate()` test must have been passed.
        if not req_extras.is_any() or include_default or not extras:
            result.append(_r)

    return result


def parse_as_pkg_requirement(line: str) -> PackageRequirement:
    """Parse a requirement line as packaging.requirement.Requirement"""
    try:
        return PackageRequirement(line)
    except InvalidRequirement:
        if not PACKAGING_22:  # We can't do anything, reraise the error.
            raise
        new_line = fix_legacy_specifier(line)
        return PackageRequirement(new_line)


def parse_line(line: str) -> Requirement:
    if line.startswith("-e "):
        return parse_requirement(line[3:].strip(), editable=True)
    return parse_requirement(line)


def parse_requirement(line: str, editable: bool = False) -> Requirement:
    m = _vcs_req_re.match(line)
    r: Requirement
    if m is not None:
        r = VcsRequirement.create(**m.groupdict())
    else:
        # Special handling for hatch local references:
        # https://hatch.pypa.io/latest/config/dependency/#local
        # We replace the {root.uri} temporarily with a dummy URL header
        # to make it pass through the packaging.requirement parser
        # and then revert it.
        root_url = path_to_url(Path().as_posix())
        replaced = "{root:uri}" in line
        if replaced:
            line = line.replace("{root:uri}", root_url)
        try:
            pkg_req = parse_as_pkg_requirement(line)
        except InvalidRequirement as e:
            m = _file_req_re.match(line)
            if m is None:
                raise RequirementError(f"{line}: {e}") from None
            args = m.groupdict()
            if not line.startswith(".") and not args["url"] and args["path"] and not os.path.exists(args["path"]):
                raise RequirementError(f"{line}: {e}") from None
            r = FileRequirement.create(**args)
        else:
            r = Requirement.from_pkg_requirement(pkg_req)
        if replaced:
            assert isinstance(r, FileRequirement)
            r.url = r.url.replace(root_url, "{root:uri}")
            r.path = Path(get_relative_path(r.url) or "")

    if editable:
        if r.is_vcs or r.is_file_or_url and r.is_local_dir:  # type: ignore[attr-defined]
            assert isinstance(r, FileRequirement)
            r.editable = True
        else:
            raise RequirementError(f"{line}: Editable requirement is only supported for VCS link or local directory.")
    return r
