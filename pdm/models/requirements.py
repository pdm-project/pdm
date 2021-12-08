from __future__ import annotations

import dataclasses
import functools
import json
import os
import re
import secrets
import sys
import urllib.parse as urlparse
import warnings
from pathlib import Path
from typing import Any, Sequence, Type, TypeVar, cast

from pip._vendor.packaging.markers import InvalidMarker
from pip._vendor.packaging.requirements import InvalidRequirement
from pip._vendor.packaging.specifiers import SpecifierSet
from pip._vendor.pkg_resources import Requirement as PackageRequirement
from pip._vendor.pkg_resources import RequirementParseError, safe_name

from pdm._types import RequirementDict
from pdm.exceptions import ExtrasError, RequirementError
from pdm.models.markers import Marker, get_marker, split_marker_extras
from pdm.models.pip_shims import (
    InstallRequirement,
    Link,
    install_req_from_editable,
    install_req_from_line,
    path_to_url,
    url_to_path,
)
from pdm.models.setup import Setup
from pdm.models.specifiers import PySpecSet, get_specifier
from pdm.utils import (
    add_ssh_scheme_to_git_uri,
    parse_name_version_from_wheel,
    url_without_fragments,
)

if sys.version_info >= (3, 8):
    from importlib.metadata import Distribution
else:
    from importlib_metadata import Distribution

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


def strip_extras(line: str) -> tuple[str, tuple[str, ...] | None]:
    match = re.match(r"^(.+?)(?:\[([^\]]+)\])?$", line)
    assert match is not None
    name, extras_str = match.groups()
    extras = (
        tuple(set(e.strip() for e in extras_str.split(","))) if extras_str else None
    )
    return name, extras


@dataclasses.dataclass
class Requirement:
    """Base class of a package requirement.
    A requirement is a (virtual) specification of a package which contains
    some constraints of version, python version, or other marker.
    """

    name: str | None = None
    marker: Marker | None = None
    extras: Sequence[str] | None = None
    specifier: SpecifierSet | None = None
    editable: bool = False
    prerelease: bool = False

    def __post_init__(self) -> None:
        self.requires_python = (
            self.marker.split_pyspec()[1] if self.marker else PySpecSet()
        )

    @property
    def project_name(self) -> str | None:
        return safe_name(self.name) if self.name else None  # type: ignore

    @property
    def key(self) -> str | None:
        return self.project_name.lower() if self.project_name else None

    @property
    def version(self) -> str | None:
        if not self.specifier:
            return None

        is_pinned = len(self.specifier) == 1 and next(
            iter(self.specifier)
        ).operator in (
            "==",
            "===",
        )
        if is_pinned:
            return next(iter(self.specifier)).version
        return None

    @version.setter
    def version(self, v: str) -> None:
        if not v or v == "*":
            self.specifier = SpecifierSet()
        else:
            self.specifier = get_specifier(f"=={v}")

    def _hash_key(self) -> tuple:
        return (
            self.key,
            frozenset(self.extras) if self.extras else None,
            str(self.marker) if self.marker else None,
        )

    def __hash__(self) -> int:
        return hash(self._hash_key())

    def __eq__(self, o: object) -> bool:
        return isinstance(o, Requirement) and hash(self) == hash(o)

    @functools.lru_cache(maxsize=None)
    def identify(self) -> str:
        if not self.key:
            return f":empty:{secrets.token_urlsafe(8)}"
        extras = "[{}]".format(",".join(sorted(self.extras))) if self.extras else ""
        return self.key + extras

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.as_line()}>"

    def __str__(self) -> str:
        return self.as_line()

    @classmethod
    def create(cls: Type[T], **kwargs: Any) -> T:
        if "marker" in kwargs:
            try:
                kwargs["marker"] = get_marker(kwargs["marker"])
            except InvalidMarker as e:
                raise RequirementError("Invalid marker: %s" % str(e)) from None
        if "extras" in kwargs and isinstance(kwargs["extras"], str):
            kwargs["extras"] = tuple(
                e.strip() for e in kwargs["extras"][1:-1].split(",")
            )
        version = kwargs.pop("version", None)
        if version:
            kwargs["specifier"] = get_specifier(version)
        return cls(**kwargs)

    @classmethod
    def from_dist(cls, dist: Distribution) -> "Requirement":
        direct_url_json = dist.read_text("direct_url.json")
        if direct_url_json is not None:
            direct_url = json.loads(direct_url_json)
            data = {
                "name": dist.metadata["Name"],
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
        return NamedRequirement.create(
            name=dist.metadata["Name"], version=f"=={dist.version}"
        )

    @classmethod
    def from_req_dict(cls, name: str, req_dict: RequirementDict) -> "Requirement":
        if isinstance(req_dict, str):  # Version specifier only.
            return NamedRequirement(name=name, specifier=get_specifier(req_dict))
        for vcs in VCS_SCHEMA:
            if vcs in req_dict:
                repo = cast(str, req_dict.pop(vcs, None))
                url = vcs + "+" + repo
                return VcsRequirement.create(name=name, vcs=vcs, url=url, **req_dict)
        if "path" in req_dict or "url" in req_dict:
            return FileRequirement.create(name=name, **req_dict)
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

    def matches(self, line: str, editable_match: bool = True) -> bool:
        """Return whether the passed in PEP 508 string
        is the same requirement as this one.
        """
        if line.strip().startswith("-e "):
            req = parse_requirement(line.split("-e ", 1)[-1], True)
        else:
            req = parse_requirement(line, False)
        return self.key == req.key and (
            not editable_match or self.editable == req.editable
        )

    def as_ireq(self, **kwargs: Any) -> InstallRequirement:
        line_for_req = self.as_line()
        if self.editable:
            line_for_req = line_for_req[3:].strip()
            ireq = install_req_from_editable(line_for_req, **kwargs)
        else:
            ireq = install_req_from_line(line_for_req, **kwargs)
        ireq.req = self  # type: ignore
        return ireq

    @classmethod
    def from_pkg_requirement(cls, req: PackageRequirement) -> "Requirement":
        kwargs = {
            "name": req.name,
            "extras": req.extras,
            "specifier": req.specifier,
            "marker": get_marker(req.marker),
        }
        if getattr(req, "url", None):
            link = Link(cast(str, req.url))
            klass = VcsRequirement if link.is_vcs else FileRequirement
            return klass(url=req.url, **kwargs)  # type: ignore
        else:
            return NamedRequirement(**kwargs)  # type: ignore

    def _format_marker(self) -> str:
        if self.marker:
            return f"; {str(self.marker)}"
        return ""


@dataclasses.dataclass
class NamedRequirement(Requirement):
    def __hash__(self) -> int:
        return hash(self._hash_key())

    def as_line(self) -> str:
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        return f"{self.project_name}{extras}{self.specifier}{self._format_marker()}"


@dataclasses.dataclass
class FileRequirement(Requirement):
    url: str = ""
    path: Path | None = None
    subdirectory: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self._parse_url()
        if self.path and not self.path.exists():
            raise RequirementError(f"The local path {self.path} does not exist.")
        if self.is_local_dir:
            self._check_installable()

    def _hash_key(self) -> tuple:
        return super()._hash_key() + (self.url, self.editable)

    def __hash__(self) -> int:
        return hash(self._hash_key())

    @classmethod
    def create(cls: Type[T], **kwargs: Any) -> T:
        if kwargs.get("path"):
            kwargs["path"] = Path(kwargs["path"].replace("${PROJECT_ROOT}", "."))
        return super().create(**kwargs)  # type: ignore

    @property
    def str_path(self) -> str | None:
        if not self.path:
            return None
        result = self.path.as_posix()
        if (
            not self.path.is_absolute()
            and not result.startswith("./")
            and not result.startswith("../")
        ):
            result = "./" + result
        return result

    def _parse_url(self) -> None:
        if not self.url:
            if self.path:
                self.url = path_to_url(self.path.resolve().as_posix())
                if not self.path.is_absolute():
                    project_root = Path(".").resolve().as_posix().lstrip("/")
                    self.url = self.url.replace(project_root, "${PROJECT_ROOT}")
        else:
            try:
                self.path = Path(
                    url_to_path(
                        self.url.replace(
                            "${PROJECT_ROOT}",
                            Path(".").absolute().as_posix().lstrip("/"),
                        )
                    )
                )
            except AssertionError:
                pass
        self._parse_name_from_url()

    @property
    def is_local(self) -> bool:
        return self.path and self.path.exists() or False

    @property
    def is_local_dir(self) -> bool:
        return self.is_local and cast(Path, self.path).is_dir()

    def as_line(self) -> str:
        project_name = f"{self.project_name}" if self.project_name else ""
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        marker = self._format_marker()
        url = url_without_fragments(self.url)
        if self.editable or self.subdirectory:
            fragments = f"egg={project_name}{extras}"
            if self.subdirectory:
                fragments = f"{fragments}&subdirectory={self.subdirectory}"
            return f"{'-e ' if self.editable else ''}{url}#{fragments}{marker}"
        delimiter = " @ " if project_name else ""
        return f"{project_name}{extras}{delimiter}{url}{marker}"

    def _parse_name_from_url(self) -> None:
        parsed = urlparse.urlparse(self.url)
        fragments = dict(urlparse.parse_qsl(parsed.fragment))
        if "egg" in fragments:
            egg_info = urlparse.unquote(fragments["egg"])
            name, extras = strip_extras(egg_info)
            self.name = name
            self.extras = extras
        if not self.name:
            filename = os.path.basename(url_without_fragments(self.url))
            if filename.endswith(".whl"):
                self.name, self.version = parse_name_version_from_wheel(filename)
            else:
                match = _egg_info_re.match(filename)
                # Filename is like `<name>-<version>.tar.gz`, where name will be
                # extracted and version will be left to be determined from the metadata.
                if match:
                    self.name = match.group(1)

    def _check_installable(self) -> None:
        assert self.path
        if not (
            self.path.joinpath("setup.py").exists()
            or self.path.joinpath("pyproject.toml").exists()
        ):
            raise RequirementError(f"The local path '{self.path}' is not installable.")
        result = Setup.from_directory(self.path.absolute())
        self.name = result.name


@dataclasses.dataclass
class VcsRequirement(FileRequirement):
    vcs: str = ""
    ref: str | None = None
    revision: str | None = None

    def __hash__(self) -> int:
        return hash(self._hash_key())

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.vcs:
            self.vcs = self.url.split("+", 1)[0]

    def as_line(self) -> str:
        project_name = f"{self.project_name}" if self.project_name else ""
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        marker = self._format_marker()
        url = url_without_fragments(self.url)
        if self.revision and not self.editable:
            url += f"@{self.revision}"
        elif self.ref:
            url += f"@{self.ref}"
        if self.editable or self.subdirectory:
            fragments = f"egg={project_name}{extras}"
            if self.subdirectory:
                fragments = f"{fragments}&subdirectory={self.subdirectory}"
            return f"{'-e ' if self.editable else ''}{url}#{fragments}{marker}"
        delimiter = " @ " if project_name else ""
        return f"{project_name}{extras}{delimiter}{url}{marker}"

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
        self.repo, self.ref = repo, ref  # type: ignore

    @staticmethod
    def _build_url_from_req_dict(name: str, url: str, req_dict: RequirementDict) -> str:
        assert not isinstance(req_dict, str)
        ref = f"@{req_dict['ref']}" if "ref" in req_dict else ""
        fragments = f"#egg={urlparse.quote(name)}"
        if "subdirectory" in req_dict:
            fragments += (
                "&subdirectory="  # type: ignore
                f"{urlparse.quote(req_dict.pop('subdirectory'))}"  # type: ignore
            )
        return f"{url}{ref}{fragments}"


def filter_requirements_with_extras(
    requirement_lines: list[str],
    extras: Sequence[str],
) -> list[str]:
    result: list[str] = []
    extras_in_meta: list[str] = []
    for req in requirement_lines:
        _r = parse_requirement(req)
        if not _r.marker:
            result.append(req)
        else:
            elements, rest = split_marker_extras(_r.marker)
            extras_in_meta.extend(elements)
            _r.marker = Marker(str(rest)) if rest else None
            if not elements or set(extras) & set(elements):
                result.append(_r.as_line())

    extras_not_found = [e for e in extras if e not in extras_in_meta]
    if extras_not_found:
        warnings.warn(ExtrasError(extras_not_found))

    return result


def parse_requirement(line: str, editable: bool = False) -> Requirement:

    m = _vcs_req_re.match(line)
    r: Requirement
    if m is not None:
        r = VcsRequirement.create(**m.groupdict())
    else:
        try:
            package_req = PackageRequirement(line)  # type: ignore
        except (RequirementParseError, InvalidRequirement) as e:
            m = _file_req_re.match(line)
            if m is None:
                raise RequirementError(str(e)) from None
            r = FileRequirement.create(**m.groupdict())
        else:
            r = Requirement.from_pkg_requirement(package_req)

    if editable:
        if r.is_vcs or r.is_file_or_url and r.is_local_dir:  # type: ignore
            assert isinstance(r, FileRequirement)
            r.editable = True
        else:
            raise RequirementError(
                "Editable requirement is only supported for VCS link"
                " or local directory."
            )
    return r


class MockDistribution(Distribution):
    def __init__(self, data: Setup) -> None:
        self._data = data

    def read_text(self, filename: str) -> str | None:
        return None

    def locate_file(self, path: os.PathLike[str] | str) -> os.PathLike[str]:
        return Path("")

    @property
    def metadata(self) -> dict[str, Any]:  # type: ignore
        return {
            "Name": self._data.name,
            "Version": self._data.version,
            "Summary": "UNKNOWN",
            "Requires-Python": self._data.python_requires,
        }

    @property
    def requires(self) -> list[str] | None:
        result = self._data.install_requires
        for extra, reqs in self._data.extras_require.items():
            extra_marker = f"extra == '{extra}'"
            for req in reqs:
                parsed = parse_requirement(req)
                old_marker = str(parsed.marker) if parsed.marker else None
                if old_marker:
                    if " or " in old_marker:
                        new_marker = f"({old_marker}) and {extra_marker}"
                    else:
                        new_marker = f"{old_marker} and {extra_marker}"
                else:
                    new_marker = extra_marker
                parsed.marker = Marker(new_marker)
                result.append(parsed.as_line())
        return result


def parse_metadata_from_source(src_dir: str) -> Distribution:
    setup = Setup.from_directory(Path(src_dir))
    return MockDistribution(setup)
