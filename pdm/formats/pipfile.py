import functools
import operator
import os

import toml
from packaging.markers import default_environment

from pdm.formats.base import make_array
from pdm.models.markers import Marker
from pdm.models.requirements import Requirement

MARKER_KEYS = list(default_environment().keys())


def convert_pipfile_requirement(name, req):
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


def check_fingerprint(project, filename):
    return os.path.basename(filename) == "Pipfile"


def convert(project, filename):
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
    result["dev-dependencies"] = make_array(
        [
            convert_pipfile_requirement(k, req)
            for k, req in data.get("dev-packages", {}).items()
        ],
        True,
    )
    return result, settings


def export(project, candidates, options):
    raise NotImplementedError()
