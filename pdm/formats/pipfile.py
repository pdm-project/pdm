import functools
import operator
import os
from argparse import Namespace
from os import PathLike
from typing import Any, Dict, List, Optional, Tuple

import toml
from packaging.markers import default_environment

from pdm._types import RequirementDict
from pdm.formats.base import make_array
from pdm.models.markers import Marker
from pdm.models.requirements import Requirement
from pdm.project import Project

MARKER_KEYS = list(default_environment().keys())


def convert_pipfile_requirement(name: str, req: RequirementDict) -> str:
    markers = []

    if "markers" in req:
        markers.append(Marker(req["markers"]))
    for key in MARKER_KEYS:
        if key in req:
            marker = Marker(f"{key}{req[key]}")
            markers.append(marker)
            del req[key]

    if markers:
        marker = functools.reduce(operator.and_, markers)
        req["marker"] = str(marker).replace('"', "'")
    return Requirement.from_req_dict(name, req).as_line()


def check_fingerprint(project: Project, filename: PathLike) -> bool:
    return os.path.basename(filename) == "Pipfile"


def convert(
    project: Project, filename: PathLike, options: Optional[Namespace]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    with open(filename, encoding="utf-8") as fp:
        data = toml.load(fp)
    result = {}
    settings = {}
    if "pipenv" in data:
        settings["allow_prereleases"] = data["pipenv"].get("allow_prereleases", False)
    if "requires" in data:
        python_version = data["requires"].get("python_full_version") or data[
            "requires"
        ].get("python_version")
        result["requires-python"] = f">={python_version}"
    if "source" in data:
        settings["source"] = data["source"]
    result["dependencies"] = make_array(
        [
            convert_pipfile_requirement(k, req)
            for k, req in data.get("packages", {}).items()
        ],
        True,
    )
    settings["dev-dependencies"] = {
        "dev": make_array(
            [
                convert_pipfile_requirement(k, req)
                for k, req in data.get("dev-packages", {}).items()
            ],
            True,
        )
    }
    return result, settings


def export(project: Project, candidates: List, options: Optional[Any]) -> None:
    raise NotImplementedError()
