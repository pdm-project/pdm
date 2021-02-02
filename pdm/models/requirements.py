import os
import re
import urllib.parse as urlparse
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from pip._vendor.packaging.markers import InvalidMarker
from pip._vendor.pkg_resources import Requirement as PackageRequirement
from pip._vendor.pkg_resources import RequirementParseError, safe_name

from pdm._types import RequirementDict
from pdm.exceptions import ExtrasError, RequirementError
from pdm.models.markers import Marker, get_marker, split_marker_extras
from pdm.models.pip_shims import (
    InstallRequirement,
    install_req_from_editable,
    install_req_from_line,
    path_to_url,
    url_to_path,
)
from pdm.models.readers import SetupReader
from pdm.models.specifiers import PySpecSet, get_specifier
from pdm.utils import (
    add_ssh_scheme_to_git_uri,
    is_readonly_property,
    parse_name_version_from_wheel,
    url_without_fragments,
)

VCS_SCHEMA = ("git", "hg", "svn", "bzr")
VCS_REQ = re.compile(
    rf"(?P<vcs>{'|'.join(VCS_SCHEMA)})\+" r"(?P<url>[^\s;]+)(?P<marker>[\t ]*;[^\n]+)?"
)
FILE_REQ = re.compile(
    r"(?:(?P<url>\S+://[^\s\[\];]+)|"
    r"(?P<path>(?:[^\s;\[\]]|\\ )*"
    r"|'(?:[^']|\\')*'"
    r"|\"(?:[^\"]|\\\")*\"))"
    r"(?P<extras>\[[^\[\]]+\])?(?P<marker>[\t ]*;[^\n]+)?"
)


def strip_extras(line):
    match = re.match(r"^(.+?)(?:\[([^\]]+)\])?$", line)
    assert match is not None
    name, extras = match.groups()
    if extras:
        extras = tuple(set(e.strip() for e in extras.split(",")))
    else:
        extras = None
    return name, extras


class Requirement:
    """Base class of a package requirement.
    A requirement is a (virtual) specification of a package which contains
    some constraints of version, python version, or other marker.
    """

    attributes = (
        "vcs",
        "editable",
        "name",
        "specifier",
        "specs",
        "marker",
        "extras",
        "key",
        "project_name",
        "url",
        "path",
        "ref",
        "index",
        "version",
        "allow_prereleases",
        "from_section",
    )

    def __init__(self, **kwargs):
        self._marker = None
        self.from_section = "default"
        self.marker_no_python = None  # type: Optional[Marker]
        self.requires_python = PySpecSet()  # type: PySpecSet
        for k, v in kwargs.items():
            if k == "specifier":
                v = get_specifier(v)
            setattr(self, k, v)
        if self.name and not self.project_name:
            self.project_name = safe_name(self.name)
            self.key = self.project_name.lower()

    def __hash__(self):
        hashCmp = (
            self.key,
            self.url,
            self.specifier,
            frozenset(self.extras) if self.extras else None,
            str(self.marker) if self.marker else None,
        )
        return hash(hashCmp)

    def __eq__(self, o: object) -> bool:
        return isinstance(o, Requirement) and hash(self) == hash(o)

    @property
    def marker(self) -> Optional[Marker]:
        return self._marker

    @marker.setter
    def marker(self, value) -> None:
        try:
            m = self._marker = get_marker(value)
            if not m:
                self.marker_no_python, self.requires_python = None, PySpecSet()
            else:
                self.marker_no_python, self.requires_python = m.split_pyspec()
        except InvalidMarker as e:
            raise RequirementError("Invalid marker: %s" % str(e)) from None

    def identify(self) -> Optional[str]:
        if not self.key:
            return None
        extras = "[{}]".format(",".join(sorted(self.extras))) if self.extras else ""
        return self.key + extras

    def __getattr__(self, attr: str) -> Any:
        if attr in self.attributes:
            return None
        raise AttributeError(attr)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.as_line()}>"

    def __str__(self) -> str:
        return self.as_line()

    @classmethod
    def from_req_dict(cls, name: str, req_dict: RequirementDict) -> "Requirement":
        # TODO: validate req_dict
        if isinstance(req_dict, str):  # Version specifier only.
            return NamedRequirement(name=name, specifier=req_dict)
        for vcs in VCS_SCHEMA:
            if vcs in req_dict:
                repo = req_dict[vcs]  # type: str
                url = VcsRequirement._build_url_from_req_dict(name, repo, req_dict)
                return VcsRequirement(name=name, vcs=vcs, url=url, **req_dict)
        if "path" in req_dict or "url" in req_dict:
            return FileRequirement(name=name, **req_dict)
        specifier = req_dict.pop("version", None)
        return NamedRequirement(name=name, specifier=specifier, **req_dict)

    def copy(self) -> "Requirement":
        kwargs = {
            k: getattr(self, k, None)
            for k in self.attributes
            if not is_readonly_property(self.__class__, k)
        }
        return self.__class__(**kwargs)

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

    def as_req_dict(self) -> Tuple[str, RequirementDict]:
        r = {}
        if self.editable:
            r["editable"] = True
        if self.extras:
            r["extras"] = sorted(self.extras)
        if self.is_vcs:
            r[self.vcs] = self.repo
        elif self.path and self.is_local_dir:
            r["path"] = self.str_path
        elif self.url:
            r["url"] = self.url
        if self.marker:
            r["marker"] = str(self.marker).replace('"', "'")
        if self.specifier:
            r["version"] = str(self.specifier)
        elif self.is_named:
            r["version"] = "*"
        if len(r) == 1 and next(iter(r), None) == "version":
            r = r["version"]
        for attr in ["index", "allow_prereleases", "ref"]:
            if getattr(self, attr) is not None:
                r[attr] = getattr(self, attr)
        return self.project_name, r

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

    def as_ireq(self, **kwargs) -> InstallRequirement:
        if self.is_file_or_url:
            line_for_req = self.as_line(True)
        else:
            line_for_req = self.as_line()
        if self.editable:
            line_for_req = line_for_req[3:].strip()
            ireq = install_req_from_editable(line_for_req, **kwargs)
        else:
            ireq = install_req_from_line(line_for_req, **kwargs)
        ireq.req = self
        return ireq

    @classmethod
    def from_pkg_requirement(cls, req: PackageRequirement) -> "Requirement":
        klass = FileRequirement if req.url else NamedRequirement
        return klass(
            name=req.name,
            extras=req.extras,
            url=req.url,
            specifier=req.specifier,
            marker=req.marker,
        )

    def _format_marker(self) -> str:
        if self.marker:
            return f"; {str(self.marker)}"
        return ""


class FileRequirement(Requirement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.path = (
            Path(str(self.path).replace("${PROJECT_ROOT}", ".")) if self.path else None
        )
        self.version = None
        self._parse_url()
        if self.path and not self.path.exists():
            raise RequirementError(f"The local path {self.path} does not exist.")
        if self.is_local_dir:
            self._check_installable()

    @property
    def str_path(self) -> Optional[str]:
        if not self.path:
            return None
        result = self.path.as_posix()
        if not self.path.is_absolute():
            result = "./" + result
        return result

    @classmethod
    def parse(cls, line: str, parsed: Dict[str, str]) -> "FileRequirement":
        extras = parsed.get("extras")
        if extras:
            extras = tuple(e.strip() for e in extras[1:-1].split(","))
        r = cls(
            url=parsed.get("url"),
            path=parsed.get("path"),
            marker=parsed.get("marker"),
            extras=extras,
        )
        return r

    def _parse_url(self) -> None:
        if not self.url:
            if self.path:
                self.url = path_to_url(
                    self.path.as_posix().replace("${PROJECT_ROOT}", ".")
                )
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
        return self.path and self.path.exists()

    @property
    def is_local_dir(self) -> bool:
        return self.is_local and self.path.is_dir()

    @property
    def project_name(self) -> Optional[str]:
        return safe_name(self.name) if self.name else None

    @property
    def key(self) -> Optional[str]:
        return self.project_name.lower() if self.project_name else None

    def as_line(self, for_ireq: bool = False) -> str:
        editable = "-e " if self.editable else ""
        project_name = f"{self.project_name}" if self.project_name else ""
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        if self.path and not for_ireq and self.editable and not project_name:
            location = self.str_path
        else:
            location = self.url
        marker = self._format_marker()
        if for_ireq and project_name:
            return f"{editable}{location}#egg={project_name}{extras}{marker}"
        else:
            delimiter = " @ " if project_name else ""
            return f"{editable}{project_name}{extras}{delimiter}{location}{marker}"

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

    def _check_installable(self) -> None:
        if not (
            self.path.joinpath("setup.py").exists()
            or self.path.joinpath("pyproject.toml").exists()
        ):
            raise RequirementError(f"The local path '{self.path}' is not installable.")
        result = SetupReader.read_from_directory(self.path.absolute().as_posix())
        # TODO: Assign a temp name for PEP 517 local package.
        self.name = result["name"]


class NamedRequirement(Requirement, PackageRequirement):
    @classmethod
    def parse(
        cls, line: str, parsed: Optional[Dict[str, Optional[str]]] = None
    ) -> "NamedRequirement":
        r = cls()
        try:
            PackageRequirement.__init__(r, line)
            r.marker = get_marker(r.marker)
        except InvalidMarker as e:
            raise RequirementError("Invalid marker: %s" % str(e)) from None
        return r

    def as_line(self) -> str:
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        return f"{self.project_name}{extras}{self.specifier}{self._format_marker()}"


class VcsRequirement(FileRequirement):
    def __init__(self, **kwargs):
        self.repo = None
        super().__init__(**kwargs)

    @classmethod
    def parse(cls, line: str, parsed: Dict[str, str]) -> "VcsRequirement":
        r = cls(
            url=parsed.get("url"), vcs=parsed.get("vcs"), marker=parsed.get("marker")
        )
        return r

    def as_line(self) -> str:
        editable = "-e " if self.editable else ""
        return f"{editable}{self.vcs}+{self.url}{self._format_marker()}"

    def _parse_url(self) -> None:
        if self.url.startswith("git@"):
            self.url = add_ssh_scheme_to_git_uri(self.url)
        if not self.name:
            self._parse_name_from_url()
        repo = url_without_fragments(self.url)
        ref = None
        parsed = urlparse.urlparse(repo)
        if "@" in parsed.path:
            path, ref = parsed.path.split("@", 1)
            repo = urlparse.urlunparse(parsed._replace(path=path))
        self.repo, self.ref = repo, ref

    @staticmethod
    def _build_url_from_req_dict(name: str, url: str, req_dict: RequirementDict) -> str:
        ref = f"@{req_dict['ref']}" if "ref" in req_dict else ""
        fragments = f"#egg={urlparse.quote(name)}"
        if "subdirectory" in req_dict:
            fragments += f"&subdirectory={urlparse.quote(req_dict['subdirectory'])}"
        return f"{url}{ref}{fragments}"


def filter_requirements_with_extras(
    requirment_lines: List[Union[str, Dict[str, Union[str, List[str]]]]],
    extras: Sequence[str],
) -> List[str]:
    result = []
    extras_in_meta = []
    for req in requirment_lines:
        if isinstance(req, dict):
            if req.get("extra"):
                extras_in_meta.append(req["extra"])
            if not req.get("extra") or req.get("extra") in extras:
                marker = f"; {req['environment']}" if req.get("environment") else ""
                result.extend(f"{line}{marker}" for line in req.get("requires", []))
        else:
            _r = parse_requirement(req)
            if not _r.marker:
                result.append(req)
            else:
                elements, rest = split_marker_extras(_r.marker)
                extras_in_meta.extend(e for e in elements)
                _r.marker = rest
                if not elements or set(extras) & set(elements):
                    result.append(_r.as_line())

    extras_not_found = [e for e in extras if e not in extras_in_meta]
    if extras_not_found:
        warnings.warn(ExtrasError(extras_not_found), stacklevel=2)

    return result


def parse_requirement(line: str, editable: bool = False) -> Requirement:

    m = VCS_REQ.match(line)
    if m is not None:
        r = VcsRequirement.parse(line, m.groupdict())
    else:
        try:
            r = NamedRequirement.parse(line)  # type: Requirement
        except RequirementParseError as e:
            m = FILE_REQ.match(line)
            if m is not None:
                r = FileRequirement.parse(line, m.groupdict())
            else:
                raise RequirementError(str(e)) from None
        else:
            if r.url:
                r = FileRequirement(name=r.name, url=r.url, extras=r.extras)

    if editable:
        if r.is_vcs or r.is_file_or_url and r.is_local_dir:
            r.editable = True
        else:
            raise RequirementError(
                "Editable requirement is only supported for VCS link"
                " or local directory."
            )
    return r
