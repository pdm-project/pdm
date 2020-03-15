import hashlib
from pip._internal.req.req_file import parse_requirements

from pdm.models.requirements import Requirement
from pdm.utils import get_finder


def parse_requirement_file(filename):
    finder = get_finder([])
    ireqs = list(parse_requirements(filename, finder.session, finder))
    return ireqs, finder


def check_fingerprint(filename):
    import tomlkit

    with open(filename, encoding="utf-8") as fp:
        try:
            tomlkit.parse(fp.read())
        except ValueError:
            # the file should be a requirements.txt if it not a TOML document.
            return True
        else:
            return False


def convert_url_to_source(url, name=None):
    if not name:
        name = hashlib.sha1(url.encode("utf-8")).hexdigest[:6]
    return {"name": name, "url": url, "verify_ssl": url.startswith("https://")}


def convert(filename):
    ireqs, finder = parse_requirement_file(filename)
    reqs = []
    for ireq in ireqs:
        req = ireq.req
        req.marker = ireq.markers
        reqs.append(Requirement.from_pkg_requirement(req))

    data = {"dependencies": dict(req.to_req_dict() for req in reqs)}
    if finder.index_urls:
        sources = [convert_url_to_source(finder.index_urls[0], "pypi")]
        sources.extend(convert_url_to_source(url) for url in finder.index_urls[1:])
        data["source"] = sources

    return data
