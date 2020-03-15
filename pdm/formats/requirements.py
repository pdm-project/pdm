import argparse
import shlex
import hashlib

from pdm.models.requirements import parse_requirement
from pdm.iostream import stream


def get_req_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--requirement", dest="file")
    parser.add_argument("-i", "--index-url")
    parser.add_argument("--extra-index-url")
    parser.add_argument("-e", "--editable")
    parser.add_argument("--pre", action="store_true")
    parser.add_argument("requirement", nargs="?")
    return parser


def parse_requirement_file(filename):
    sources = {}
    requirements = []
    parser = get_req_parser()

    with open(filename, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            args, argv = parser.parse_known_args(shlex.split(line))
            if args.file:
                file_sources, file_requirements = parse_requirement_file(args.file)
                sources.update(file_sources)
                requirements.extend(file_requirements)
                continue
            if args.index_url:
                sources[args.index] = "pypi"
            if args.extra_index_url:
                sources[args.extra_index_url] = hashlib.sha1(
                    args.extra_index_url
                ).hexdigest()[:6]
            if args.requirement:
                req = parse_requirement(args.requirement)
            elif args.editable:
                req = parse_requirement(args.editable, True)
            else:
                continue
            if args.index_url or args.extra_index_url:
                req.index = sources[args.index_url or args.extra_index_url]
            req.allow_prereleases = args.pre
            requirements.append(req)
            if argv:
                stream.echo(
                    stream.yellow(
                        "WARNING: Arguments {} are not supported "
                        "and will be dropped in PDM.".format(argv)
                    ),
                    err=True,
                )
    return sources, requirements


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


def convert(filename):
    sources, requirements = parse_requirement_file(filename)

    data = {"dependencies": dict(req.to_req_dict() for req in requirements)}
    if sources:
        pyproject_sources = []
        for url, name in sources.items():
            pyproject_sources.append(
                {"url": url, "name": name, "verify_ssl": url.startswith("https://")}
            )
        data["source"] = pyproject_sources
    return data


if __name__ == "__main__":
    parser = get_req_parser()
    args, argv = parser.parse_known_args(["-v", "abcdef", "--hashes=12144"])
    print(args, argv)
