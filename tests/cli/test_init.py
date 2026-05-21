import argparse
import sys
from textwrap import dedent
from unittest.mock import ANY

import pytest

from pdm.cli.commands.init import Command
from pdm.compat import tomllib
from pdm.models.python import PythonInfo
from pdm.utils import cd

PYTHON_VERSION = f"{sys.version_info[0]}.{sys.version_info[1]}"


@pytest.fixture(autouse=True)
def enable_interactive_mode(mocker):
    from rich import get_console

    console = get_console()
    mocker.patch.object(console, "is_interactive", True)


def test_init_validate_python_requires(project_no_init, pdm):
    result = pdm(["init"], input="\n\n\n\n\n\n\n3.7\n", obj=project_no_init)
    assert result.exit_code != 0
    assert "InvalidSpecifier" in result.stderr


def test_init_command(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    pdm(["init"], input="\ntest-project\n\n\n\n\n\n\n\n", strict=True, obj=project_no_init)
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Default template for PDM package",
            "license": {"text": "MIT"},
            "name": "test-project",
            "requires-python": f"=={python_version}.*",
            "readme": "README.md",
            "version": "0.1.0",
        },
        "tool": {"pdm": {"distribution": False}},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_uses_existing_pyproject_values_as_defaults(project_no_init, mocker):
    project_no_init.pyproject._path.write_text(
        dedent(
            """
            [project]
            name = "existing-project"
            version = "2.1.0"
            description = "Existing description"
            authors = [{name = "Existing Author", email = "author@example.org"}]
            license = {text = "Apache-2.0"}
            requires-python = ">=3.10"

            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [tool.pdm]
            distribution = true
            """
        )
    )
    project_no_init.pyproject.reload()
    defaults = {}

    def ask_with_default(question, default, **kwargs):
        defaults[question] = default
        return default

    mocker.patch("pdm.cli.commands.init.termui.ask", side_effect=ask_with_default)
    confirm = mocker.patch(
        "pdm.cli.commands.init.termui.confirm", side_effect=lambda *args, **kwargs: kwargs["default"]
    )
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Git User", "git@example.org"),
    )
    command = Command()
    options = argparse.Namespace(
        name=None,
        project_version=None,
        dist=False,
        backend=None,
        license=None,
    )

    command.get_metadata_from_input(project_no_init, options)

    assert defaults == {
        "Project name": "existing-project",
        "Project version": "2.1.0",
        "Project description": "Existing description",
        "Please select": 3,
        "License(SPDX name)": "Apache-2.0",
        "Author name": "Existing Author",
        "Author email": "author@example.org",
        "Python requires('*' to allow any)": ">=3.10",
    }
    confirm.assert_called_once_with(
        "Do you want to build this project for distribution(such as wheel)?\n"
        "If yes, it will be installed by default when running `pdm install`.",
        default=True,
    )


def test_init_preserves_existing_pyproject_values(project_no_init, pdm, mocker):
    project_no_init.pyproject._path.write_text(
        dedent(
            """
            [project]
            name = "existing-project"
            version = "2.1.0"
            description = "Existing description"
            authors = [{name = "Existing Author", email = "author@example.org"}]
            license = {text = "Apache-2.0"}
            requires-python = ">=3.10"
            dependencies = ["requests"]

            [build-system]
            requires = ["hatchling"]
            build-backend = "hatchling.build"

            [tool.pdm]
            distribution = false
            """
        )
    )
    project_no_init.pyproject.reload()
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )

    result = pdm(["init"], input="\n\n\n\n\n\n\n\n\n", obj=project_no_init)

    assert result.exit_code == 0
    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        data = tomllib.load(fp)
    assert data["project"]["name"] == "existing-project"
    assert data["project"]["version"] == "2.1.0"
    assert data["project"]["description"] == "Existing description"
    assert data["project"]["authors"] == [{"name": "Existing Author", "email": "author@example.org"}]
    assert data["project"]["license"] == {"text": "Apache-2.0"}
    assert data["project"]["requires-python"] == ">=3.10"
    assert data["project"]["dependencies"] == ["requests"]
    assert data["build-system"] == {"requires": ["hatchling"], "build-backend": "hatchling.build"}
    assert data["tool"]["pdm"]["distribution"] is False


def test_init_asks_whether_to_initialize_git(project_no_init, pdm, mocker):
    initialize_git = mocker.patch("pdm.cli.commands.init.Command.initialize_git")

    result = pdm(["init"], input="\ntest-project\n\n\n\n\n\n\nn\n", obj=project_no_init)

    assert result.exit_code == 0
    initialize_git.assert_not_called()


def test_init_no_git_does_not_initialize_git(project_no_init, pdm, mocker):
    initialize_git = mocker.spy(Command, "initialize_git")

    result = pdm(["init", "--no-git"], input="\ntest-project\n\n\n\n\n\n\n", obj=project_no_init)

    assert result.exit_code == 0
    initialize_git.assert_not_called()


def test_init_non_interactive_initializes_git_by_default(project_no_init, pdm, mocker):
    initialize_git = mocker.patch("pdm.cli.commands.init.Command.initialize_git")
    confirm = mocker.patch("pdm.cli.commands.init.termui.confirm")
    mocker.patch("pdm.cli.commands.use.Command.do_use", return_value=PythonInfo.from_path(sys.executable))

    result = pdm(["init", "-n"], obj=project_no_init)

    assert result.exit_code == 0
    confirm.assert_not_called()
    initialize_git.assert_called_once_with(project_no_init)


def test_new_command(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    with cd(project_no_init.root):
        pdm(
            ["new", "--name", "test-project", "--python", sys.executable, "myproject"],
            input="\n\n\n\n\n\n\n",
            strict=True,
        )
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Default template for PDM package",
            "license": {"text": "MIT"},
            "name": "test-project",
            "requires-python": f"=={python_version}.*",
            "readme": "README.md",
            "version": "0.1.0",
        },
        "tool": {"pdm": {"distribution": False}},
    }

    with open(project_no_init.root.joinpath("myproject/pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_command_library(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    result = pdm(
        ["init"],
        input="\ntest-project\n\ny\nTest Project\n1\n\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Test Project",
            "license": {"text": "MIT"},
            "name": "test-project",
            "requires-python": f">={python_version}",
            "readme": "README.md",
            "version": "0.1.0",
        },
        "build-system": {"build-backend": "setuptools.build_meta", "requires": ["setuptools>=61"]},
        "tool": {"pdm": {"distribution": True}},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


@pytest.mark.parametrize(
    "backend_choice,merged_backend",
    [
        (0, {"build-backend": "pdm.backend", "requires": ["pdm-backend", "example"]}),
        (1, {"build-backend": "setuptools.build_meta", "requires": ["setuptools>=61"]}),
    ],
)
def test_init_template_build_system(tmp_path, project_no_init, pdm, mocker, backend_choice, merged_backend):
    template_with_backend = tmp_path / "backend-template"
    template_with_backend.mkdir()
    (template_with_backend / "pyproject.toml").write_text(
        dedent(
            """
            [project]
            dynamic = ["version"]
            name = "backend-template"

            [build-system]
            requires = ["pdm-backend", "example"]
            build-backend = "pdm.backend"
            """
        )
    )

    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    result = pdm(
        ["init", str(template_with_backend)],
        input=f"\ntest-project\n\ny\nTest Project\n{backend_choice}\n\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Test Project",
            "license": {"text": "MIT"},
            "name": "test-project",
            "requires-python": f">={python_version}",
            "dynamic": ["version"],
        },
        "build-system": merged_backend,
        "tool": {"pdm": {"distribution": True}},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_non_interactive(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_use = mocker.patch("pdm.cli.commands.use.Command.do_use", return_value=PythonInfo.from_path(sys.executable))
    result = pdm(["init", "-n"], obj=project_no_init)
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_use.assert_called_once_with(
        project_no_init,
        ANY,
        first=True,
        ignore_remembered=True,
        ignore_requires_python=True,
        save=False,
        hooks=ANY,
    )
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Default template for PDM package",
            "license": {"text": "MIT"},
            "name": project_no_init.root.name,
            "requires-python": f"=={python_version}.*",
            "readme": "README.md",
            "version": "0.1.0",
        },
        "tool": {"pdm": {"distribution": False}},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_auto_create_venv(project_no_init, pdm, mocker):
    mocker.patch("pdm.models.python.PythonInfo.get_venv", return_value=None)
    project_no_init.project_config["python.use_venv"] = True
    result = pdm(["init"], input="\ntest-project\n\ny\nTest Project\n1\n\n\n\n\n\n", obj=project_no_init)
    assert result.exit_code == 0
    assert project_no_init.python.executable.parent.parent == project_no_init.root / ".venv"
    assert ".pdm-python" in (project_no_init.root / ".gitignore").read_text()


def test_init_auto_create_venv_specify_python(project_no_init, pdm, mocker):
    mocker.patch("pdm.models.python.PythonInfo.get_venv", return_value=None)
    project_no_init.project_config["python.use_venv"] = True
    result = pdm(
        ["init", f"--python={PYTHON_VERSION}"],
        input="\n\n\n\n\n\n\n\n",
        obj=project_no_init,
    )
    assert result.exit_code == 0
    assert project_no_init.python.executable.parent.parent == project_no_init.root / ".venv"


def test_init_with_backend_default_library(project_no_init, pdm):
    pdm(["init", "--backend", "flit-core"], input="\n\n\n\n\n\n\n\n\n", obj=project_no_init)
    assert project_no_init.backend.__class__.__name__ == "FlitBackend"


def test_init_with_backend_default_library_non_interactive(project_no_init, pdm):
    pdm(["init", "-n", "--backend", "flit-core"], obj=project_no_init)
    assert project_no_init.backend.__class__.__name__ == "FlitBackend"


def test_init_with_license_non_interactive(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_use = mocker.patch("pdm.cli.commands.use.Command.do_use", return_value=PythonInfo.from_path(sys.executable))
    expected_license = "Proprietary"
    result = pdm(["init", "-n", "--license", expected_license], obj=project_no_init)
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_use.assert_called_once_with(
        project_no_init,
        ANY,
        first=True,
        ignore_remembered=True,
        ignore_requires_python=True,
        save=False,
        hooks=ANY,
    )
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Default template for PDM package",
            "license": {"text": f"{expected_license}"},
            "name": project_no_init.root.name,
            "requires-python": f"=={python_version}.*",
            "readme": "README.md",
            "version": "0.1.0",
        },
        "tool": {"pdm": {"distribution": False}},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data


def test_init_with_project_version_non_interactive(project_no_init, pdm, mocker):
    mocker.patch(
        "pdm.cli.commands.init.get_user_email_from_git",
        return_value=("Testing", "me@example.org"),
    )
    do_use = mocker.patch("pdm.cli.commands.use.Command.do_use", return_value=PythonInfo.from_path(sys.executable))
    expected_project_version = "2.0.42"
    result = pdm(["init", "-n", "--project-version", expected_project_version], obj=project_no_init)
    assert result.exit_code == 0
    python_version = f"{project_no_init.python.major}.{project_no_init.python.minor}"
    do_use.assert_called_once_with(
        project_no_init,
        ANY,
        first=True,
        ignore_remembered=True,
        ignore_requires_python=True,
        save=False,
        hooks=ANY,
    )
    data = {
        "project": {
            "authors": [{"email": "me@example.org", "name": "Testing"}],
            "dependencies": [],
            "description": "Default template for PDM package",
            "license": {"text": "MIT"},
            "name": project_no_init.root.name,
            "requires-python": f"=={python_version}.*",
            "readme": "README.md",
            "version": f"{expected_project_version}",
        },
        "tool": {"pdm": {"distribution": False}},
    }

    with open(project_no_init.root.joinpath("pyproject.toml"), "rb") as fp:
        assert tomllib.load(fp) == data
