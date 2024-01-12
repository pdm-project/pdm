from __future__ import annotations

import functools
import operator
import os
from typing import TYPE_CHECKING, Any

from packaging.markers import default_environment

from pdm.compat import tomllib
from pdm.formats.base import make_array
from pdm.models.markers import Marker, get_marker
from pdm.models.requirements import FileRequirement, Requirement

if TYPE_CHECKING:
    from argparse import Namespace
    from os import PathLike

    from pdm._types import RequirementDict
    from pdm.models.backends import BuildBackend
    from pdm.project import Project

MARKER_KEYS = list(default_environment().keys())


def convert_pipfile_requirement(name: str, req: RequirementDict, backend: BuildBackend) -> str:
    if isinstance(req, dict):
        markers: list[Marker] = []
        if "markers" in req:
            markers.append(get_marker(req["markers"]))  # type: ignore[arg-type]
        for key in MARKER_KEYS:
            if key in req:
                marker = get_marker(f"{key}{req[key]}")
                markers.append(marker)
                del req[key]

        if markers:
            marker = functools.reduce(operator.and_, markers)
            req["marker"] = str(marker).replace('"', "'")
    r = Requirement.from_req_dict(name, req)
    if isinstance(r, FileRequirement):
        r.relocate(backend)
    return r.as_line()


def check_fingerprint(project: Project, filename: PathLike) -> bool:
    return os.path.basename(filename) == "Pipfile"


def convert(project: Project, filename: PathLike, options: Namespace | None) -> tuple[dict[str, Any], dict[str, Any]]:
    with open(filename, "rb") as fp:
        data = tomllib.load(fp)
    result = {}
    settings: dict[str, Any] = {}
    backend = project.backend
    if "pipenv" in data and "allow_prereleases" in data["pipenv"]:
        settings.setdefault("resolution", {})["allow-prereleases"] = data["pipenv"]["allow_prereleases"]
    if "requires" in data:
        python_version = data["requires"].get("python_full_version") or data["requires"].get("python_version")
        result["requires-python"] = f">={python_version}"
    if "source" in data:
        settings["source"] = data["source"]
    result["dependencies"] = make_array(  # type: ignore[assignment]
        [convert_pipfile_requirement(k, req, backend) for k, req in data.get("packages", {}).items()],
        True,
    )
    settings["dev-dependencies"] = {
        "dev": make_array(
            [convert_pipfile_requirement(k, req, backend) for k, req in data.get("dev-packages", {}).items()],
            True,
        )
    }
    return result, settings


def export(project: Project, candidates: list, options: Any) -> None:
    raise NotImplementedError()
