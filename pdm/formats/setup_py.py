import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pdm.formats.base import array_of_inline_tables, make_array, make_inline_table
from pdm.project import Project


def check_fingerprint(project: Project, filename: Path) -> bool:
    return os.path.basename(filename) == "setup.py"


def convert(
    project: Project, filename: Path, options: Optional[Any]
) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    from pdm.models.in_process import parse_setup_py

    parsed = parse_setup_py(
        str(project.environment.interpreter.executable), str(filename)
    )
    metadata: Dict[str, Any] = {}
    settings: Dict[str, Any] = {}
    for name in [
        "name",
        "version",
        "description",
        "keywords",
        "urls",
        "readme",
    ]:
        if name in parsed:
            metadata[name] = parsed[name]
    if "authors" in parsed:
        metadata["authors"] = array_of_inline_tables(parsed["authors"])
    if "maintainers" in parsed:
        metadata["maintainers"] = array_of_inline_tables(parsed["maintainers"])
    if "classifiers" in parsed:
        metadata["classifiers"] = make_array(sorted(parsed["classifiers"]), True)
    if "python_requires" in parsed:
        metadata["requires-python"] = parsed["python_requires"]
    if "install_requires" in parsed:
        metadata["dependencies"] = make_array(sorted(parsed["install_requires"]), True)
    if "extras_require" in parsed:
        metadata["optional-dependencies"] = {
            k: make_array(sorted(v), True) for k, v in parsed["extras_require"].items()
        }
    if "license" in parsed:
        metadata["license"] = make_inline_table({"text": parsed["license"]})
    if "package_dir" in parsed:
        settings["package-dir"] = parsed["package_dir"]

    entry_points = parsed.get("entry_points", {})
    if "console_scripts" in entry_points:
        metadata["scripts"] = entry_points.pop("console_scripts")
    if "gui_scripts" in entry_points:
        metadata["gui-scripts"] = entry_points.pop("gui_scripts")
    if entry_points:
        metadata["entry-points"] = entry_points

    return metadata, settings


def export(project: Project, candidates: List, options: Optional[Any]) -> str:
    from pdm.pep517.base import Builder

    builder = Builder(project.root)
    return builder.format_setup_py()
