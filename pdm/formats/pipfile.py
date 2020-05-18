import functools
import operator
import os

import tomlkit
from packaging.markers import default_environment

from pdm.models.markers import Marker

MARKER_KEYS = list(default_environment().keys())


def convert_pipfile_requirement(req):
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
    return req


def check_fingerprint(project, filename):
    return os.path.basename(filename) == "Pipfile"


def convert(project, filename):
    with open(filename, encoding="utf-8") as fp:
        data = tomlkit.parse(fp.read())
    result = {}
    if "pipenv" in data:
        result["allow_prereleases"] = data["pipenv"].get("allow_prereleases", False)
    if "requires" in data:
        python_version = data["requires"].get("python_full_version") or data[
            "requires"
        ].get("python_version")
        result["python_requires"] = f">={python_version}"
    if "source" in data:
        result["source"] = data["source"]
    result["dependencies"] = {
        k: convert_pipfile_requirement(req)
        for k, req in data.get("packages", {}).items()
    }
    result["dev-dependencies"] = {
        k: convert_pipfile_requirement(req)
        for k, req in data.get("dev-packages", {}).items()
    }
    return result


def export(project, candidates, options):
    raise NotImplementedError()
