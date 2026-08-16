import os

import pytest

from pdm.cli.templates import ProjectTemplate
from pdm.exceptions import PdmException


@pytest.mark.parametrize(
    "url,expected",
    [
        # scp-like syntax, the userinfo must not be taken as a branch
        ("git@github.com:owner/repo.git", ("git@github.com:owner/repo.git", None)),
        ("git@github.com:owner/repo.git@dev", ("git@github.com:owner/repo.git", "dev")),
        # ssh:// and credentialed https:// URLs contain a userinfo part too
        ("ssh://git@github.com/owner/repo.git", ("ssh://git@github.com/owner/repo.git", None)),
        ("ssh://git@github.com/owner/repo.git@dev", ("ssh://git@github.com/owner/repo.git", "dev")),
        ("https://token@github.com/owner/repo.git", ("https://token@github.com/owner/repo.git", None)),
        ("https://github.com/owner/repo", ("https://github.com/owner/repo", None)),
        ("https://github.com/owner/repo@dev", ("https://github.com/owner/repo", "dev")),
    ],
)
def test_split_git_branch(url, expected):
    assert ProjectTemplate.split_git_branch(url) == expected


def test_non_pyproject_template_disallowed(project_no_init):
    with (
        ProjectTemplate("tests/fixtures/projects/demo_extras") as template,
        pytest.raises(PdmException, match=r"Template pyproject.toml not found"),
    ):
        template.generate(project_no_init.root, {"project": {"name": "foo"}})


def test_module_project_template(project_no_init):
    metadata = {
        "project": {"name": "foo", "version": "0.1.0", "requires-python": ">=3.10"},
        "build-system": {"requires": ["pdm-backend"], "build-backend": "pdm.backend"},
    }

    with ProjectTemplate("tests/fixtures/projects/demo") as template:
        template.generate(project_no_init.root, metadata)

    project_no_init.pyproject.reload()
    assert project_no_init.pyproject.metadata["name"] == "foo"
    assert project_no_init.pyproject.metadata["requires-python"] == ">=3.10"
    assert project_no_init.pyproject._data["build-system"] == metadata["build-system"]
    assert project_no_init.pyproject.metadata["dependencies"] == ["idna", "chardet; os_name=='nt'"]
    assert project_no_init.pyproject.metadata["optional-dependencies"]["tests"] == ["pytest"]
    assert (project_no_init.root / "foo.py").exists()
    assert os.access(project_no_init.root / "foo.py", os.W_OK)


def test_module_project_template_generate_application(project_no_init):
    metadata = {
        "project": {"name": "", "version": "", "requires-python": ">=3.10"},
    }

    with ProjectTemplate("tests/fixtures/projects/demo") as template:
        template.generate(project_no_init.root, metadata)

    project_no_init.pyproject.reload()
    assert project_no_init.pyproject.metadata["name"] == ""
    assert "build-system" not in project_no_init.pyproject._data
    assert project_no_init.pyproject.metadata["dependencies"] == ["idna", "chardet; os_name=='nt'"]
    assert (project_no_init.root / "demo.py").exists()


def test_package_project_template(project_no_init):
    metadata = {
        "project": {"name": "foo", "version": "0.1.0", "requires-python": ">=3.10"},
        "build-system": {"requires": ["pdm-backend"], "build-backend": "pdm.backend"},
    }

    with ProjectTemplate("tests/fixtures/projects/demo-package") as template:
        template.generate(project_no_init.root, metadata)

    project_no_init.pyproject.reload()
    assert project_no_init.pyproject.metadata["name"] == "foo"
    assert project_no_init.pyproject.metadata["requires-python"] == ">=3.10"
    assert project_no_init.pyproject._data["build-system"] == metadata["build-system"]
    assert (project_no_init.root / "foo").is_dir()
    assert (project_no_init.root / "foo/__init__.py").exists()
    assert project_no_init.pyproject.settings["version"] == {"path": "foo/__init__.py", "source": "file"}
