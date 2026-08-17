import shutil
from argparse import Namespace
from textwrap import dedent

import pytest

from pdm.compat import tomllib
from pdm.formats import MetaConvertError, flit, pipfile, poetry, requirements, setup_py
from pdm.formats.uv import uv_file_builder
from pdm.models.repositories import LockedRepository
from pdm.models.requirements import parse_requirement
from pdm.utils import cd
from tests import FIXTURES


def ns(**kwargs):
    default_options = {
        "dev": False,
        "group": None,
        "expandvars": False,
        "self": False,
        "editable_self": False,
        "hashes": True,
    }
    kwargs = {**default_options, **kwargs}
    self = kwargs.pop("self")
    rv = Namespace(**kwargs)
    rv.self = self
    return rv


def test_convert_pipfile(project):
    golden_file = FIXTURES / "Pipfile"
    assert pipfile.check_fingerprint(project, golden_file)
    result, settings = pipfile.convert(project, golden_file, None)

    assert settings["resolution"]["allow-prereleases"]
    assert result["requires-python"] == ">=3.6"

    assert not settings.get("dev-dependencies", {}).get("dev")

    assert "requests" in result["dependencies"]
    assert 'pywinusb; sys_platform == "win32"' in result["dependencies"]

    assert settings["source"][0]["url"] == "https://pypi.python.org/simple"


@pytest.mark.parametrize("is_dev", [True, False])
def test_convert_requirements_file(project, is_dev):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    options = ns(dev=is_dev)
    result, settings = requirements.convert(project, golden_file, options)
    group = settings["dev-dependencies"]["dev"] if is_dev else result["dependencies"]
    dev_group = settings["dev-dependencies"]["dev"]

    assert len(settings["source"]) == 2
    assert "webassets==2.0" in group
    assert 'whoosh==2.7.4; sys_platform == "win32"' in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" in dev_group
    if not is_dev:
        assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" not in group
    assert (
        "pep508-package @ git+https://github.com/techalchemy/test-project.git"
        "@master#subdirectory=parent_folder/pep508-package" in group
    )


@pytest.mark.parametrize(
    "line, expected",
    [
        ("requests==2.31.0\t# tab before comment", "requests==2.31.0"),
        ("requests==2.31.0 # space before comment", "requests==2.31.0"),
        ("requests==2.31.0\x0c# formfeed before comment", "requests==2.31.0"),
        ("requests==2.31.0   \t  # mixed whitespace", "requests==2.31.0"),
        ("# a whole-line comment", ""),
        ("   \t# an indented whole-line comment", ""),
        # A `#` not preceded by whitespace is part of the requirement, e.g. a URL fragment
        (
            "git+https://github.com/test-root/demo.git#egg=demo",
            "git+https://github.com/test-root/demo.git#egg=demo",
        ),
    ],
)
def test_requirements_clean_line_strips_comments(line, expected):
    parser = requirements.RequirementParser(None)
    assert parser._clean_line(line) == expected


def test_convert_requirements_file_with_tab_before_comment(project):
    req_file = project.root.joinpath("reqs.txt")
    req_file.write_text("webassets==2.0\t# a tab-separated comment\n", encoding="utf-8")
    result, _ = requirements.convert(project, str(req_file), ns())

    assert result["dependencies"] == ["webassets==2.0"]


@pytest.mark.parametrize(
    "reference,expected_url",
    [
        ("child.txt", "https://example.com/base/child.txt"),
        ("../child.txt", "https://example.com/child.txt"),
        ("https://other.example/child.txt", "https://other.example/child.txt"),
    ],
)
def test_remote_requirements_resolve_nested_reference(mocker, reference, expected_url):
    session = mocker.Mock()
    session.get.side_effect = [
        mocker.Mock(is_error=False, text=f"-r {reference}"),
        mocker.Mock(is_error=False, text="webassets==2.0"),
    ]
    parser = requirements.RequirementParser(session)

    parser.parse_file("https://example.com/base/requirements.txt")

    assert [call.args[0] for call in session.get.call_args_list] == [
        "https://example.com/base/requirements.txt",
        expected_url,
    ]
    assert [req.as_line() for req in parser.requirements] == ["webassets==2.0"]


def test_convert_requirements_file_without_name(project, vcs):
    req_file = project.root.joinpath("reqs.txt")
    project.root.joinpath("reqs.txt").write_text("git+https://github.com/test-root/demo.git\n")
    assert requirements.check_fingerprint(project, str(req_file))
    result, _ = requirements.convert(project, str(req_file), ns())

    assert result["dependencies"] == ["demo @ git+https://github.com/test-root/demo.git"]


def test_build_uv_pyproject_toml_with_workspace(project):
    project.pyproject.settings["workspace"] = {"members": ["packages/*"]}
    project.pyproject.write()
    for name in ("foo", "bar"):
        member_path = project.root / "packages" / name
        member_path.mkdir(parents=True)
        member_path.joinpath("pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
    req = parse_requirement("foo>=0.1")
    req.groups = ["default"]
    locked_repo = LockedRepository({}, project.sources, project.environment)

    with uv_file_builder(project, ">=3.10", project.with_workspace_dependencies([req]), locked_repo) as builder:
        path = builder.build_pyproject_toml()
        with path.open("rb") as fp:
            data = tomllib.load(fp)

    assert data["project"]["requires-python"] == ">=3.10"
    assert set(data["project"]["dependencies"]) == {"foo>=0.1", "bar"}
    assert data["tool"]["uv"]["workspace"]["members"] == ["packages/*"]
    assert data["tool"]["uv"]["sources"]["foo"] == {"workspace": True}
    assert data["tool"]["uv"]["sources"]["bar"] == {"workspace": True}


def test_build_uv_files_without_project_name_and_version(project):
    """uv requires project.name/version, so a placeholder is filled in for applications
    that declare neither. See issue #3421.
    """
    from pdm.formats.uv import PLACEHOLDER_NAME, PLACEHOLDER_VERSION

    del project.pyproject.metadata["name"]
    del project.pyproject.metadata["version"]
    project.pyproject.write()

    locked_repo = LockedRepository({}, project.sources, project.environment)
    with uv_file_builder(project, ">=3.10", [], locked_repo) as builder:
        pyproject_path = builder.build_pyproject_toml()
        with pyproject_path.open("rb") as fp:
            pyproject_data = tomllib.load(fp)
        lock_path = builder.build_uv_lock()
        with lock_path.open("rb") as fp:
            lock_data = tomllib.load(fp)

    # uv refuses to parse a pyproject.toml whose [project] table lacks either key
    assert pyproject_data["project"].get("name") == PLACEHOLDER_NAME
    assert pyproject_data["project"].get("version") == PLACEHOLDER_VERSION
    roots = [p for p in lock_data["package"] if p["name"] == PLACEHOLDER_NAME]
    assert len(roots) == 1
    assert roots[0]["version"] == PLACEHOLDER_VERSION
    assert roots[0]["source"] == {"virtual": "."}


def test_build_uv_lock_root_entry_groups_dependencies(project):
    """The root entry carries the requirements, split between `dependencies` and
    `optional-dependencies` by group. Covers the loop the placeholder fix de-indented."""
    from pdm.formats.uv import PLACEHOLDER_NAME
    from pdm.models.candidates import Candidate
    from pdm.models.repositories import Package

    del project.pyproject.metadata["name"]
    project.pyproject.write()

    locked_repo = LockedRepository({}, project.sources, project.environment)
    reqs = []
    for name, groups in [("first", ["default"]), ("second", ["tui"]), ("third", [])]:
        req = parse_requirement(name)
        req.groups = groups
        reqs.append(req)
        locked_repo.add_package(Package(Candidate(req, name=name, version="1.0"), [], ""))

    # not in the locked repository, so _make_dependency returns None and it is skipped
    unlocked = parse_requirement("nowhere")
    unlocked.groups = ["default"]
    reqs.append(unlocked)

    with uv_file_builder(project, ">=3.10", reqs, locked_repo) as builder:
        lock_path = builder.build_uv_lock()
        with lock_path.open("rb") as fp:
            lock_data = tomllib.load(fp)

    root = next(p for p in lock_data["package"] if p["name"] == PLACEHOLDER_NAME)
    assert [d["name"] for d in root["dependencies"]] == ["first"]
    assert [d["name"] for d in root["optional-dependencies"]["tui"]] == ["second"]
    # `third` belongs to no group and `nowhere` is not locked, so neither is listed
    listed = {d["name"] for d in root["dependencies"]}
    assert "third" not in listed and "nowhere" not in listed


def test_build_uv_pyproject_toml_keeps_dynamic_version(project):
    project.pyproject.metadata["dynamic"] = ["version"]
    del project.pyproject.metadata["version"]
    project.pyproject.write()

    locked_repo = LockedRepository({}, project.sources, project.environment)
    with uv_file_builder(project, ">=3.10", [], locked_repo) as builder:
        path = builder.build_pyproject_toml()
        with path.open("rb") as fp:
            data = tomllib.load(fp)

    assert "version" not in data["project"]
    assert data["project"]["dynamic"] == ["version"]


def test_build_uv_lock_with_local_path_wheel(project):
    from pdm.models.candidates import Candidate
    from pdm.models.repositories import Package
    from pdm.models.requirements import FileRequirement

    wheel_name = "first-2.0.2-py2.py3-none-any.whl"
    wheel_path = FIXTURES / "artifacts" / wheel_name
    req = FileRequirement.create(path=str(wheel_path), name="first")
    req.groups = ["default"]
    candidate = Candidate(req, name="first", version="2.0.2")
    candidate.hashes.append(
        {
            "url": wheel_name,
            "file": wheel_name,
            "hash": "sha256:dummy",
        }
    )
    package = Package(candidate, [], "")

    locked_repo = LockedRepository({}, project.sources, project.environment)
    locked_repo.add_package(package)

    with uv_file_builder(project, ">=3.8", [req], locked_repo) as builder:
        path = builder.build_uv_lock()
        with path.open("rb") as fp:
            data = tomllib.load(fp)

    pkg = next(p for p in data["package"] if p["name"] == "first")
    assert "path" in pkg["source"], "local wheel source should use 'path', not 'url'"
    assert "url" not in pkg["source"]
    wheel_entry = pkg["wheels"][0]
    assert "filename" in wheel_entry, "local wheel entry should use 'filename', not 'url'"
    assert "url" not in wheel_entry
    assert wheel_entry["filename"] == wheel_name
    assert wheel_entry["hash"] == "sha256:dummy"


def test_convert_poetry(project):
    golden_file = FIXTURES / "pyproject.toml"
    assert poetry.check_fingerprint(project, golden_file)
    with cd(FIXTURES):
        result, settings = poetry.convert(project, golden_file, ns())

    assert result["authors"] == [
        {
            "name": "Sébastien Eustace",
            "email": "sebastien@eustace.io",
        },
        {
            "name": "Example, Inc.",
            "email": "inc@example.com",
        },
    ]
    assert result["name"] == "poetry"
    assert result["version"] == "1.0.0"
    assert result["license"] == {"text": "MIT"}
    assert "repository" in result["urls"]
    assert result["requires-python"] == "!=3.0.*,!=3.1.*,!=3.2.*,!=3.3.*,<4.0,>=2.7"
    assert 'cleo<0.8.0,>=0.7.6; python_version ~= "2.7"' in result["dependencies"]
    assert 'cachecontrol[filecache]<0.13.0,>=0.12.4; python_version ~= "3.4"' in result["dependencies"]
    assert "babel==2.9.0" in result["dependencies"]
    assert "mysql" in result["optional-dependencies"]
    assert "psycopg2<3.0,>=2.7" in result["optional-dependencies"]["pgsql"]
    assert len(settings["dev-dependencies"]["dev"]) == 2

    assert result["scripts"] == {"poetry": "poetry.console:run"}
    assert result["entry-points"]["blogtool.parsers"] == {".rst": "some_module:SomeClass"}
    build = settings["build"]
    assert build["includes"] == ["lib/my_package", "tests", "CHANGELOG.md"]
    assert build["excludes"] == ["my_package/excluded.py"]


def test_convert_poetry_optional_dependency_in_multiple_extras(project):
    golden_file = FIXTURES / "pyproject.toml"
    with cd(FIXTURES):
        result, _ = poetry.convert(project, golden_file, ns())

    assert result["optional-dependencies"]["mysql"] == ["mysqlclient<2.0,>=1.3"]
    assert result["optional-dependencies"]["pgsql"] == ["psycopg2<3.0,>=2.7"]
    assert result["optional-dependencies"]["all"] == ["psycopg2<3.0,>=2.7", "mysqlclient<2.0,>=1.3"]


@pytest.mark.parametrize(
    "constraint,expected",
    [
        # Poetry's caret keeps the leftmost non-zero component unchanged.
        ("^1.2.3", "<2.0.0,>=1.2.3"),
        ("^1.2", "<2.0,>=1.2"),
        ("^1", "<2,>=1"),
        ("^0.2.3", "<0.3.0,>=0.2.3"),
        ("^0.0.3", "<0.0.4,>=0.0.3"),
        ("^0.0", "<0.1,>=0.0"),
        ("^0", "<1,>=0"),
    ],
)
def test_convert_poetry_caret_constraint(project, constraint, expected):
    pyproject = project.root / "pyproject.toml"
    pyproject.write_text(
        f'[tool.poetry]\nname = "demo"\nversion = "0.1.0"\n[tool.poetry.dependencies]\nfoo = "{constraint}"\n',
        encoding="utf-8",
    )
    result, _ = poetry.convert(project, pyproject, ns())

    assert result["dependencies"] == [f"foo{expected}"]


def test_convert_poetry_12(project):
    golden_file = FIXTURES / "poetry-new.toml"
    with cd(FIXTURES):
        result, settings = poetry.convert(project, golden_file, ns())

    assert result["dependencies"] == ["httpx", "pendulum"]
    assert settings["dev-dependencies"]["test"] == ["pytest<7.0.0,>=6.0.0", "pytest-mock"]


def test_convert_flit(project):
    golden_file = FIXTURES / "projects/flit-demo/pyproject.toml"
    assert flit.check_fingerprint(project, golden_file)
    result, settings = flit.convert(project, golden_file, None)

    assert result["name"] == "pyflit"
    assert result["version"] == "0.1.0"
    assert result["description"] == "An awesome flit demo"
    assert "classifiers" in result["dynamic"]
    assert result["authors"][0] == {
        "name": "Thomas Kluyver",
        "email": "thomas@kluyver.me.uk",
    }
    assert result["urls"]["homepage"] == "https://github.com/takluyver/flit"
    assert result["requires-python"] == ">=3.5"
    assert result["readme"] == "README.rst"
    assert result["urls"]["Documentation"] == "https://flit.readthedocs.io/en/latest/"
    assert result["dependencies"] == [
        "requests>=2.6",
        'configparser; python_version == "2.7"',
    ]

    assert result["optional-dependencies"]["test"] == [
        "pytest >=2.7.3",
        "pytest-cov",
    ]

    assert result["scripts"]["flit"] == "flit:main"
    assert result["entry-points"]["pygments.lexers"]["dogelang"] == "dogelang.lexer:DogeLexer"
    build = settings["build"]
    assert build["includes"] == ["doc/"]
    assert build["excludes"] == ["doc/*.html"]


def test_convert_flit_author_and_maintainer_without_email(project, tmp_path):
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        '[tool.flit.metadata]\nmodule = "flit"\nauthor = "Thomas Kluyver"\nmaintainer = "Frost Ming"\n',
        encoding="utf-8",
    )
    result, _ = flit.convert(project, pyproject_file, None)

    assert result["authors"] == [{"name": "Thomas Kluyver"}]
    assert result["maintainers"] == [{"name": "Frost Ming"}]


@pytest.mark.parametrize(
    "sdist_table,expected_build",
    [
        ('include = ["doc/"]', {"includes": ["doc/"]}),
        ('exclude = ["doc/*.html"]', {"excludes": ["doc/*.html"]}),
    ],
)
def test_convert_flit_sdist_with_one_of_include_and_exclude(project, tmp_path, sdist_table, expected_build):
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(
        '[tool.flit.metadata]\nmodule = "flit"\nauthor = "Thomas Kluyver"\n'
        'author-email = "thomas@kluyver.me.uk"\n\n'
        f"[tool.flit.sdist]\n{sdist_table}\n",
        encoding="utf-8",
    )
    _, settings = flit.convert(project, pyproject_file, None)

    assert settings["build"] == expected_build


def test_convert_error_preserve_metadata(project):
    pyproject_file = FIXTURES / "poetry-error.toml"
    try:
        poetry.convert(project, pyproject_file, ns())
    except MetaConvertError as e:
        assert e.data["name"] == "test-poetry"
        assert "dependencies: Invalid specifier" in str(e)
    else:
        pytest.fail("Should raise MetaConvertError")


def test_import_requirements_with_group(project):
    golden_file = FIXTURES / "requirements.txt"
    assert requirements.check_fingerprint(project, golden_file)
    result, settings = requirements.convert(project, golden_file, ns(group="test"))

    group = result["optional-dependencies"]["test"]
    dev_group = settings["dev-dependencies"]["dev"]
    assert "webassets==2.0" in group
    assert 'whoosh==2.7.4; sys_platform == "win32"' in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" not in group
    assert "-e git+https://github.com/pypa/pip.git@main#egg=pip" in dev_group
    assert not result.get("dependencies")


def test_export_requirements_with_self(project):
    result = requirements.export(project, [], ns(self=True, hashes=False))
    assert result.strip().splitlines()[-1] == ".  # this package"


def test_export_requirements_with_editable_self(project):
    result = requirements.export(project, [], ns(editable_self=True, hashes=False))
    assert result.strip().splitlines()[-1] == "-e .  # this package"


def test_keep_env_vars_in_source(project, monkeypatch):
    monkeypatch.setenv("USER", "foo")
    monkeypatch.setenv("PASSWORD", "bar")
    project.pyproject.settings["source"] = [{"url": "https://${USER}:${PASSWORD}@test.pypi.org/simple", "name": "pypi"}]
    result = requirements.export(project, [], ns())
    assert result.strip().splitlines()[-1] == "--index-url https://${USER}:${PASSWORD}@test.pypi.org/simple"


def test_expand_env_vars_in_source(project, monkeypatch):
    monkeypatch.setenv("USER", "foo")
    monkeypatch.setenv("PASSWORD", "bar")
    project.pyproject.settings["source"] = [{"url": "https://foo:bar@test.pypi.org/simple", "name": "pypi"}]
    result = requirements.export(project, [], ns(expandvars=True))
    assert result.strip().splitlines()[-1] == "--index-url https://foo:bar@test.pypi.org/simple"


def test_export_find_links(project, monkeypatch):
    url = "https://storage.googleapis.com/jax-releases/jax_cuda_releases.html"
    project.pyproject.settings["source"] = [{"url": url, "name": "jax", "type": "find_links"}]
    result = requirements.export(project, [], ns())
    assert result.strip().splitlines()[-1] == f"--find-links {url}"


@pytest.mark.parametrize(
    "url,trusted_host",
    [
        # A port in the trusted host must not be lost when matching.
        ("https://mirror.example.org:8443/simple", "mirror.example.org:8443"),
        # Credentials in the index URL are not part of the host.
        ("https://user:pw@mirror.example.org:8443/simple", "mirror.example.org:8443"),
        ("https://user@mirror.example.org/simple", "mirror.example.org"),
        # A trusted host without a port matches whatever port the URL uses.
        ("https://mirror.example.org:8443/simple", "mirror.example.org"),
        # Host comparison is case-insensitive.
        ("https://Mirror.Example.ORG/simple", "mirror.example.org"),
        # IPv6 literals stay bracketed.
        ("https://[::1]:8443/simple", "[::1]:8443"),
    ],
)
def test_import_requirements_trusted_host(project, tmp_path, url, trusted_host):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(f"--index-url {url}\n--trusted-host {trusted_host}\n", encoding="utf-8")
    _, settings = requirements.convert(project, req_file, ns())
    assert settings["source"] == [{"name": "pypi", "url": url, "verify_ssl": False}]


@pytest.mark.parametrize(
    "url,trusted_host",
    [
        ("https://mirror.example.org:8443/simple", "mirror.example.org:8443"),
        ("https://user:pw@mirror.example.org:8443/simple", "mirror.example.org:8443"),
        ("https://mirror.example.org/simple", "mirror.example.org"),
        ("https://[::1]:8443/simple", "[::1]:8443"),
    ],
)
def test_export_trusted_host_keeps_port(project, url, trusted_host):
    project.pyproject.settings["source"] = [{"url": url, "name": "pypi", "verify_ssl": False}]
    result = requirements.export(project, [], ns())
    assert result.strip().splitlines()[-1] == f"--trusted-host {trusted_host}"


@pytest.mark.parametrize(
    "url,trusted_host",
    [
        # A different port is not covered by the trusted host.
        ("https://mirror.example.org:8443/simple", "mirror.example.org:9999"),
        ("https://mirror.example.org/simple", "mirror.example.org:8443"),
        ("https://other.example.org:8443/simple", "mirror.example.org:8443"),
    ],
)
def test_import_requirements_untrusted_host(project, tmp_path, url, trusted_host):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(f"--index-url {url}\n--trusted-host {trusted_host}\n", encoding="utf-8")
    _, settings = requirements.convert(project, req_file, ns())
    assert settings["source"] == [{"name": "pypi", "url": url, "verify_ssl": True}]


def test_export_replace_project_root(project):
    artifact = FIXTURES / "artifacts/first-2.0.2-py2.py3-none-any.whl"
    shutil.copy2(artifact, project.root)
    with cd(project.root):
        req = parse_requirement(f"./{artifact.name}")
    result = requirements.export(project, [req], ns(hashes=False))
    assert "${PROJECT_ROOT}" not in result


@pytest.mark.usefixtures("local_finder")
def test_convert_setup_py_project(project, pdm):
    project._saved_python = None
    project.project_config["python.use_venv"] = True
    pdm(["add", "setuptools"], obj=project)
    golden_file = FIXTURES / "projects/test-setuptools/setup.py"
    assert setup_py.check_fingerprint(project, golden_file)
    result, settings = setup_py.convert(project, golden_file, ns())
    assert result == {
        "name": "mymodule",
        "version": "0.1.0",
        "description": "A test module",
        "keywords": ["one", "two"],
        "readme": "README.md",
        "authors": [{"name": "frostming"}],
        "license": {"text": "MIT"},
        "classifiers": ["Framework :: Django", "Programming Language :: Python :: 3"],
        "requires-python": ">=3.5",
        "dependencies": ['importlib-metadata; python_version<"3.10"', "requests"],
        "scripts": {"mycli": "mymodule:main"},
    }
    assert settings == {"package-dir": "src"}


def test_convert_poetry_project_with_circular_dependency(project):
    parent_file = FIXTURES / "projects/poetry-with-circular-dep/pyproject.toml"
    child_file = FIXTURES / "projects/poetry-with-circular-dep/packages/child/pyproject.toml"

    _, settings = poetry.convert(project, parent_file, ns())
    assert settings["dev-dependencies"]["dev"] == ["child @ file:///${PROJECT_ROOT}/packages/child"]

    _, settings = poetry.convert(project, child_file, ns())
    assert settings["dev-dependencies"]["dev"] == ["parent @ file:///${PROJECT_ROOT}/../.."]


def test_export_pylock_toml(core, pdm):
    project = core.create_project(FIXTURES / "projects/demo")
    golden_file = FIXTURES / "projects/demo/pylock.toml"
    result = pdm(["export", "-f", "pylock"], obj=project, strict=True)
    assert result.stdout.strip() == golden_file.read_text(encoding="utf-8").strip()
    with cd(project.root):
        result = pdm(["export", "-f", "pylock", "-L", "pdm.no_groups.lock"])
    assert result.exit_code == 1
    assert "inherit_metadata strategy is required for pylock format" in result.stderr


def test_export_from_pylock_not_empty(core, pdm):
    """Test that exporting from pylock.toml produces non-empty output (fixes issue #3573)."""
    project = core.create_project(FIXTURES / "projects/demo")

    # Export from pylock.toml to requirements format
    with cd(project.root):
        result = pdm(["export", "-f", "requirements", "-L", "pylock.toml", "--no-hashes"], obj=project, strict=True)
        assert result.exit_code == 0

    # The output should not be empty (this was the original bug)
    output_lines = [
        line.strip() for line in result.stdout.strip().split("\n") if line.strip() and not line.strip().startswith("#")
    ]
    assert len(output_lines) > 0, "Export from pylock.toml should not be empty"

    # Should contain expected packages
    output = result.stdout
    assert any(pkg in output for pkg in ["chardet", "idna"]), "Expected at least some packages in output"


def test_parse_uv_lock_drops_the_placeholder_root(project):
    """A project with no name gets a placeholder in the generated pyproject.toml,
    so uv writes the root entry under that name. It must not become a dependency."""
    from pdm.formats.uv import PLACEHOLDER_NAME
    from pdm.resolver.uv import UvResolver

    project.pyproject._data.get("project", {}).pop("name", None)
    lock_path = project.root / "uv.lock"
    lock_path.write_text(
        dedent(
            f"""
            version = 1
            requires-python = ">=3.8"

            [[package]]
            name = "{PLACEHOLDER_NAME}"
            version = "0.0.0"
            source = {{ virtual = "." }}

            [[package]]
            name = "packaging"
            version = "24.0"
            source = {{ registry = "https://pypi.org/simple" }}
            sdist = {{ url = "https://example.invalid/packaging-24.0.tar.gz", hash = "sha256:abc" }}
            """
        ).strip(),
        encoding="utf-8",
    )

    resolver = UvResolver(
        project.environment,
        requirements=[],
        target=project.environment.spec,
        update_strategy="all",
        strategies=set(),
    )
    resolution = resolver._parse_uv_lock(lock_path)

    names = {p.candidate.name for p in resolution.packages}
    assert names == {"packaging"}, f"the placeholder root leaked into the resolution: {names}"
