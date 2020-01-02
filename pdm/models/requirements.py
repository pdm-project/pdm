from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple
import urllib.parse as urlparse

from pkg_resources import (
    Requirement as PackageRequirement,
    RequirementParseError,
    safe_name,
)
from packaging.markers import InvalidMarker
from packaging.specifiers import SpecifierSet

from pdm.models.markers import get_marker
from pdm.models.candidates import (
    Candidate,
    FileCandidate,
    LocalDirCandidate,
    VcsCandidate,
)
from pdm.types import RequirementDict

VCS_SCHEMA = ("git", "hg", "svn", "bzr")


class RequirementError(ValueError):
    pass


def get_specifier(version_str: str) -> SpecifierSet:
    if not version_str or version_str == "*":
        return SpecifierSet()
    return SpecifierSet(version_str)


class Requirement:
    """Base class of a package requirement.
    A requirement is a (virtual) specification of a package which contains
    some constraints of version, python version, or other marker.
    """

    VCS_REQ = re.compile(
        rf"(?P<editable>-e[\t ]+)(?P<vcs>{'|'.join(VCS_SCHEMA)})\+"
        r"(?P<url>[^\s;]+)(?P<marker>[\t ]*;[^\n]+)?"
    )
    _PATH_START = r"(?:\.|/|[a-zA-Z]:[/\\])"
    FILE_REQ = re.compile(
        r"(?:(?P<url>\S+://[^\s;]+)|"
        rf"(?P<editable>-e[\t ]+)?(?P<path>{_PATH_START}(?:[^\s;]|\\ )*"
        rf"|'{_PATH_START}(?:[^']|\\')*'"
        rf"|\"{_PATH_START}(?:[^\"]|\\\")*\"))"
        r"(?P<marker>[\t ]*;[^\n]+)?"
    )
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
    )

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k == "marker":
                try:
                    v = get_marker(v)
                except InvalidMarker as e:
                    raise RequirementError("Invalid marker: %s" % str(e)) from None
            elif k == "specifier":
                v = get_specifier(v)
            setattr(self, k, v)
        if self.name and not self.project_name:
            self.project_name = safe_name(self.name)
            self.key = self.project_name.lower()

    def __getattr__(self, attr: str) -> Any:
        if attr in self.attributes:
            return None
        raise AttributeError(attr)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    @classmethod
    def from_line(cls, line: str) -> "Requirement":

        m = cls.VCS_REQ.match(line)
        if m is not None:
            return VcsRequirement.from_line(line, m.groupdict())
        m = cls.FILE_REQ.match(line)
        if m is not None:
            return FileRequirement.from_line(line, m.groupdict())
        try:
            r = NamedRequirement.from_line(line)
        except RequirementParseError as e:
            if line.strip().startswith("-e"):
                raise RequirementError(
                    "Editable requirement is only supported for "
                    "VCS url or local directory."
                ) from None
            else:
                raise RequirementError(str(e)) from None
        else:
            if r.url:
                r = FileRequirement(name=r.name, url=r.url, extras=r.extras)
            return r

    @classmethod
    def from_req_dict(cls, name: str, req_dict: RequirementDict) -> "Requirement":
        # TODO: validate req_dict
        if isinstance(req_dict, str):  # Version specifier only.
            return NamedRequirement(name=name, specifier=req_dict)
        for vcs in VCS_SCHEMA:
            if vcs in req_dict:
                repo = req_dict[vcs]
                url = VcsRequirement._build_url_from_req_dict(name, repo, req_dict)
                return VcsRequirement(name=name, vcs=vcs, url=url, **req_dict)
        specifier = req_dict.pop("version", None)
        if specifier is not None:
            return NamedRequirement(name=name, specifier=specifier, **req_dict)
        return FileRequirement(name=name, **req_dict)

    def as_req_dict(self) -> Tuple[str, RequirementDict]:
        r = {}
        if self.is_vcs:
            r[self.vcs] = self.repo
        elif self.url:
            r["url"] = self.url
        if self.editable:
            r["editable"] = True
        if self.extras:
            r["extras"] = sorted(self.extras)
        if self.path:
            r["path"] = self.str_path
        if self.marker:
            r["marker"] = str(self.marker)
        if self.specs:
            r["version"] = str(self.specifier)
        elif self.is_named:
            r["version"] = "*"
        if len(r) == 1 and next(iter(r), None) == "version":
            r = r["version"]
        return self.project_name, r

    @property
    def is_named(self) -> bool:
        return isinstance(self, NamedRequirement)

    @property
    def is_vcs(self) -> bool:
        return isinstance(self, VcsRequirement)

    @property
    def is_file_or_url(self) -> bool:
        return isinstance(self, FileRequirement)

    def as_line(self) -> str:
        raise NotImplementedError

    def _format_marker(self) -> None:
        if self.marker:
            return f";{str(self.marker)}"
        return ""


class FileRequirement(Requirement):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.path = Path(self.path) if self.path else None
        self.str_path = self.path.as_posix() if self.path else None
        if self.path and not self.path.is_absolute():
            self.str_path = "./" + self.str_path
        self._parse_url()
        # TODO: Parse name from local dir.

    @classmethod
    def from_line(
        cls, line: str, parsed: Optional[Dict[str, Optional[str]]] = None
    ) -> "FileRequirement":
        r = cls(
            url=parsed.get("url"),
            path=parsed.get("path"),
            editable=bool(parsed.get("editable")) or None,
            marker=parsed.get("marker"),
        )
        return r

    def _parse_url(self) -> None:
        parsed = urlparse.urlparse(self.url)
        if parsed.scheme == "file" and not parsed.netloc:
            self.path = Path(parsed.path)

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

    def as_line(self) -> str:
        editable = "-e " if self.editable else ""
        project_name = f"{self.project_name}" if self.project_name else ""
        extras = f"[{','.join(sorted(self.extras))}]" if self.extras else ""
        delimiter = " @ " if project_name else ""
        if self.path:
            location = self.str_path
        else:
            location = self.url
        marker = self._format_marker()
        return f"{editable}{project_name}{extras}{delimiter}{location}{marker}"

    def as_candidate(self) -> Candidate:
        if self.is_local_dir:
            return LocalDirCandidate(self.path)
        elif self.path and self.path.exists() or self.url:
            return FileCandidate(self.path or self.url)
        else:
            raise RequirementError(
                "Invalid requirement: the local path does not exist."
            )


class NamedRequirement(Requirement, PackageRequirement):
    @classmethod
    def from_line(
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
        self._parse_name_from_url()

    @classmethod
    def from_line(
        cls, line: str, parsed: Optional[Dict[str, Optional[str]]] = None
    ) -> "VcsRequirement":
        r = cls(
            url=parsed.get("url"),
            vcs=parsed.get("vcs"),
            editable=bool(parsed.get("editable")) or None,
            marker=parsed.get("marker"),
        )
        return r

    def as_line(self) -> str:
        editable = "-e " if self.editable else ""
        return f"{editable}{self.vcs}+{self.url}{self._format_marker()}"

    def as_candidate(self) -> Candidate:
        return VcsCandidate(self.vcs, self.url)

    def _parse_name_from_url(self) -> None:
        if self.name and self.repo:
            return
        parsed = urlparse.urlparse(self.url)
        fragments = dict(urlparse.parse_qsl(parsed.fragment))
        if "egg" in fragments:
            self.name = urlparse.unquote(fragments["egg"])
        self.repo = urlparse.urlunparse(parsed._replace(fragment=""))

    @staticmethod
    def _build_url_from_req_dict(name: str, url: str, req_dict: RequirementDict) -> str:
        ref = f"@{req_dict['ref']}" if "ref" in req_dict else ""
        fragments = f"#egg={urlparse.quote(name)}"
        if "subdirectory" in req_dict:
            fragments += f"&subdirectory={urlparse.quote(req_dict['subdirectory'])}"
        return f"{url}{ref}{fragments}"
