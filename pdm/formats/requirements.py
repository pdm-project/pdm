import hashlib
import urllib.parse
from argparse import Namespace
from os import PathLike
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union, cast

from distlib.wheel import Wheel
from pip._vendor.packaging.requirements import Requirement as PRequirement

from pdm.formats.base import make_array
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.markers import Marker
from pdm.models.pip_shims import InstallRequirement, PackageFinder, parse_requirements
from pdm.models.requirements import Requirement, parse_requirement
from pdm.project import Project
from pdm.utils import get_finder


def _requirement_to_str_lowercase_name(requirement: PRequirement) -> str:
    """Formats a packaging.requirements.Requirement with a lowercase name."""
    parts = [requirement.name.lower()]

    if requirement.extras:
        parts.append("[{0}]".format(",".join(sorted(requirement.extras))))

    if requirement.specifier:
        parts.append(str(requirement.specifier))

    if requirement.url:
        parts.append("@ {0}".format(requirement.url))

    if requirement.marker:
        parts.append("; {0}".format(requirement.marker))

    return "".join(parts)


def ireq_as_line(ireq: InstallRequirement, environment: Environment) -> str:
    """Formats an `InstallRequirement` instance as a
    PEP 508 dependency string.

    Generic formatter for pretty printing InstallRequirements to the terminal
    in a less verbose way than using its `__str__` method.

    :param :class:`InstallRequirement` ireq: A pip **InstallRequirement** instance.
    :return: A formatted string for prettyprinting
    :rtype: str
    """
    if ireq.editable:
        line = "-e {}".format(ireq.link)
    else:
        if not ireq.req:
            ireq.req = parse_requirement("dummy @" + ireq.link.url)
            wheel = Wheel(environment.build(ireq))
            ireq.req.name = wheel.name

        line = _requirement_to_str_lowercase_name(ireq.req)

    if str(ireq.req.marker) != str(ireq.markers):
        if not ireq.req.marker:
            line = "{}; {}".format(line, ireq.markers)
        else:
            name, markers = line.split(";", 1)
            markers = Marker(markers) & ireq.markers
            line = "{}; {}".format(name, markers)

    return line


def parse_requirement_file(
    filename: str,
) -> Tuple[List[InstallRequirement], PackageFinder]:
    from pdm.models.pip_shims import install_req_from_parsed_requirement

    finder = get_finder([])
    ireqs = [
        install_req_from_parsed_requirement(pr)
        for pr in parse_requirements(filename, finder.session, finder)
    ]
    return ireqs, finder


def check_fingerprint(project: Project, filename: PathLike) -> bool:
    import tomlkit

    with open(filename, encoding="utf-8") as fp:
        try:
            tomlkit.parse(fp.read())
        except ValueError:
            # the file should be a requirements.txt if it not a TOML document.
            return True
        else:
            return False


def convert_url_to_source(url: str, name: Optional[str] = None) -> Dict[str, Any]:
    if not name:
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:6]
    return {"name": name, "url": url, "verify_ssl": url.startswith("https://")}


def convert(
    project: Project, filename: PathLike, options: Namespace
) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    ireqs, finder = parse_requirement_file(str(filename))
    with project.core.ui.logging("build"):
        reqs = [ireq_as_line(ireq, project.environment) for ireq in ireqs]

    deps = make_array(reqs, True)
    data: Dict[str, Any] = {}
    settings: Dict[str, Any] = {}
    if options.dev:
        settings["dev-dependencies"] = {options.section or "dev": deps}
    elif options.section:
        data["optional-dependencies"] = {options.section: deps}
    else:
        data["dependencies"] = deps
    if finder.index_urls:
        sources = [convert_url_to_source(finder.index_urls[0], "pypi")]
        sources.extend(convert_url_to_source(url) for url in finder.index_urls[1:])
        settings["source"] = sources

    return data, settings


def export(
    project: Project,
    candidates: Union[List[Candidate], List[Requirement]],
    options: Namespace,
) -> str:
    lines = []
    for candidate in candidates:
        req = getattr(candidate, "req", candidate).as_line()
        lines.append(req)
        if options.hashes and getattr(candidate, "hashes", None):
            for item in cast(Dict[str, str], candidate.hashes).values():
                lines.append(f" \\\n    --hash={item}")
        lines.append("\n")
    sources = project.tool_settings.get("source", [])
    for source in sources:
        url = source["url"]
        prefix = "--index-url" if source["name"] == "pypi" else "--extra-index-url"
        lines.append(f"{prefix} {url}\n")
        if not source["verify_ssl"]:
            host = urllib.parse.urlparse(url).hostname
            lines.append(f"--trusted-host {host}\n")
    return "".join(lines)
