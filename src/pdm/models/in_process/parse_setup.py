import os
import sys
from typing import Any, Dict


def _parse_setup_cfg(path: str) -> Dict[str, Any]:
    import configparser

    setup_cfg = configparser.ConfigParser()
    setup_cfg.read(path, encoding="utf-8")

    result: Dict[str, Any] = {}
    if not setup_cfg.has_section("metadata"):
        return result

    metadata = setup_cfg["metadata"]

    if "name" in metadata:
        result["name"] = metadata["name"]

    if "description" in metadata:
        result["description"] = metadata["description"]

    if "license" in metadata:
        result["license"] = metadata["license"]

    if "author" in metadata:
        result["author"] = metadata["author"]

    if "author_email" in metadata:
        result["author_email"] = metadata["author_email"]

    if "maintainer" in metadata:
        result["maintainer"] = metadata["maintainer"]

    if "maintainer_email" in metadata:
        result["maintainer_email"] = metadata["maintainer_email"]

    if "keywords" in metadata:
        keywords = metadata["keywords"].strip().splitlines()
        result["keywords"] = keywords if len(keywords) > 1 else keywords[0]

    if "classifiers" in metadata:
        result["classifiers"] = metadata["classifiers"].strip().splitlines()

    if "url" in metadata:
        result["url"] = metadata["url"]

    if "download_url" in metadata:
        result["download_url"] = metadata["download_url"]

    if "project_urls" in metadata:
        result["project_urls"] = dict(
            [u.strip() for u in url.split("=", 1)] for url in metadata["project_urls"].strip().splitlines()
        )

    if "long_description" in metadata:
        long_description = metadata["long_description"].strip()
        if long_description.startswith("file:"):
            result["readme"] = long_description[5:].strip()

    if setup_cfg.has_section("options"):
        options = setup_cfg["options"]

        if "python_requires" in options:
            result["python_requires"] = options["python_requires"]

        if "install_requires" in options:
            result["install_requires"] = options["install_requires"].strip().splitlines()

        if "package_dir" in options:
            result["package_dir"] = dict(
                [p.strip() for p in d.split("=", 1)] for d in options["package_dir"].strip().splitlines()
            )

    if setup_cfg.has_section("options.extras_require"):
        result["extras_require"] = {
            feature: dependencies.strip().splitlines()
            for feature, dependencies in setup_cfg["options.extras_require"].items()
        }

    if setup_cfg.has_section("options.entry_points"):
        result["entry_points"] = {
            entry_point: definitions.strip().splitlines()
            for entry_point, definitions in setup_cfg["options.entry_points"].items()
        }

    return result


setup_kwargs = {}
SUPPORTED_ARGS = (
    "name",
    "version",
    "description",
    "license",
    "author",
    "author_email",
    "maintainer",
    "maintainer_email",
    "keywords",
    "classifiers",
    "url",
    "download_url",
    "project_urls",
    "python_requires",
    "install_requires",
    "extras_require",
    "entry_points",
    "package_dir",
)


def fake_setup(**kwargs):
    setup_kwargs.update((k, v) for k, v in kwargs.items() if k in SUPPORTED_ARGS)


def clean_metadata(metadata: Dict[str, Any]) -> None:
    author = {}
    if "author" in metadata:
        author["name"] = metadata.pop("author")
    if "author_email" in metadata:
        author["email"] = metadata.pop("author_email")
    if author:
        metadata["authors"] = [author]
    maintainer = {}
    if "maintainer" in metadata:
        maintainer["name"] = metadata.pop("maintainer")
    if "maintainer_email" in metadata:
        maintainer["email"] = metadata.pop("maintainer_email")
    if maintainer:
        metadata["maintainers"] = [maintainer]

    urls = {}
    if "url" in metadata:
        urls["Homepage"] = metadata.pop("url")
    if "download_url" in metadata:
        urls["Downloads"] = metadata.pop("download_url")
    if "project_urls" in metadata:
        urls.update(metadata.pop("project_urls"))
    if urls:
        metadata["urls"] = urls

    if "" in metadata.get("package_dir", {}):
        metadata["package_dir"] = metadata["package_dir"][""]

    if "keywords" in metadata:
        keywords = metadata["keywords"]
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",")]
        metadata["keywords"] = keywords

    if "entry_points" in metadata and isinstance(metadata["entry_points"], dict):
        entry_points = {}
        for entry_point, definitions in metadata["entry_points"].items():
            if isinstance(definitions, str):
                definitions = [definitions]
            definitions = dict(sorted(d.replace(" ", "").split("=", 1) for d in definitions))

            entry_points[entry_point] = definitions
        if entry_points:
            metadata["entry_points"] = dict(sorted(entry_points.items()))


def parse_setup(path: str) -> Dict[str, Any]:
    import tokenize

    import setuptools

    setuptools.setup = fake_setup

    parsed: Dict[str, Any] = {}
    path = os.path.abspath(path)
    project_path = os.path.dirname(path)
    os.chdir(project_path)
    if os.path.exists("setup.cfg"):
        parsed.update(_parse_setup_cfg("setup.cfg"))

    # Execute setup.py and get the kwargs
    __file__ = sys.argv[0] = path
    sys.path.insert(0, project_path)
    setup_kwargs.clear()

    with tokenize.open(path) as f:
        code = f.read()
    exec(
        compile(code, __file__, "exec"),
        {"__name__": "__main__", "__file__": __file__, "setup_kwargs": setup_kwargs},
    )
    parsed.update(setup_kwargs)

    if "readme" not in parsed:
        for readme_file in ("README.md", "README.rst", "README.txt"):
            readme_path = os.path.join(project_path, readme_file)
            if os.path.exists(readme_path):
                parsed["readme"] = readme_file
                break
    clean_metadata(parsed)
    return parsed


if __name__ == "__main__":
    import json

    print(json.dumps(parse_setup(sys.argv[1])))
