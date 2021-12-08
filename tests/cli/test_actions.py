import os
import sys
from json import loads

import pytest

from pdm.cli import actions
from pdm.exceptions import InvalidPyVersion, PdmException, PdmUsageError
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet


@pytest.mark.usefixtures("repository", "working_set", "vcs")
def test_remove_both_normal_and_editable_packages(project, is_dev):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, is_dev, packages=["demo"])
    actions.do_add(
        project,
        is_dev,
        editables=["git+https://github.com/test-root/demo.git#egg=demo"],
    )
    group = (
        project.tool_settings["dev-dependencies"]["dev"]
        if is_dev
        else project.meta["dependencies"]
    )
    actions.do_remove(project, is_dev, packages=["demo"])
    assert not group
    assert "demo" not in project.locked_repository.all_candidates


@pytest.mark.usefixtures("repository")
def test_remove_package(project, working_set, is_dev):
    actions.do_add(project, dev=is_dev, packages=["requests", "pytz"])
    actions.do_remove(project, dev=is_dev, packages=["pytz"])
    locked_candidates = project.locked_repository.all_candidates
    assert "pytz" not in locked_candidates
    assert "pytz" not in working_set


@pytest.mark.usefixtures("repository")
def test_remove_package_with_dry_run(project, working_set, capsys):
    actions.do_add(project, packages=["requests"])
    actions.do_remove(project, packages=["requests"], dry_run=True)
    out, _ = capsys.readouterr()
    project._lockfile = None
    locked_candidates = project.locked_repository.all_candidates
    assert "urllib3" in locked_candidates
    assert "urllib3" in working_set
    assert "- urllib3 1.22" in out


@pytest.mark.usefixtures("repository")
def test_remove_package_no_sync(project, working_set):
    actions.do_add(project, packages=["requests", "pytz"])
    actions.do_remove(project, sync=False, packages=["pytz"])
    locked_candidates = project.locked_repository.all_candidates
    assert "pytz" not in locked_candidates
    assert "pytz" in working_set


@pytest.mark.usefixtures("repository", "working_set")
def test_remove_package_not_exist(project):
    actions.do_add(project, packages=["requests", "pytz"])
    with pytest.raises(PdmException):
        actions.do_remove(project, sync=False, packages=["django"])


@pytest.mark.usefixtures("repository")
def test_remove_package_exist_in_multi_groups(project, working_set):
    actions.do_add(project, packages=["requests"])
    actions.do_add(project, dev=True, packages=["urllib3"])
    actions.do_remove(project, dev=True, packages=["urllib3"])
    assert all(
        "urllib3" not in line
        for line in project.tool_settings["dev-dependencies"]["dev"]
    )
    assert "urllib3" in working_set
    assert "requests" in working_set


@pytest.mark.usefixtures("repository")
def test_add_remove_no_package(project):
    with pytest.raises(PdmUsageError):
        actions.do_add(project, packages=())

    with pytest.raises(PdmUsageError):
        actions.do_remove(project, packages=())


@pytest.mark.usefixtures("repository")
def test_lock_dependencies(project):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    assert project.lockfile_file.exists()
    locked = project.locked_repository.all_candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


def test_build_distributions(tmp_path, core):
    project = core.create_project()
    actions.do_build(project, dest=tmp_path.as_posix())
    wheel = next(tmp_path.glob("*.whl"))
    assert wheel.name.startswith("pdm-")
    tarball = next(tmp_path.glob("*.tar.gz"))
    assert tarball.exists()


def test_project_no_init_error(project_no_init):

    for handler in (
        actions.do_add,
        actions.do_list,
        actions.do_lock,
        actions.do_update,
    ):
        with pytest.raises(
            PdmException, match="The pyproject.toml has not been initialized yet"
        ):
            handler(project_no_init)


@pytest.mark.usefixtures("repository", "working_set")
def test_list_dependency_graph(project, capsys):
    actions.do_add(project, packages=["requests"])
    actions.do_list(project, graph=True)
    content, _ = capsys.readouterr()
    assert "└── urllib3 1.22 [ required: <1.24,>=1.21.1 ]" in content


@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph_with_circular_forward(project, capsys, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo"])
    actions.do_add(project, packages=["foo"])
    capsys.readouterr()
    actions.do_list(project, graph=True)
    content, _ = capsys.readouterr()
    assert "foo [circular]" in content


@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph_with_circular_reverse(project, capsys, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo", "baz"])
    repository.add_dependencies("baz", "0.1.0", [])
    actions.do_add(project, packages=["foo"])
    capsys.readouterr()
    actions.do_list(project, graph=True, reverse=True)
    content, _ = capsys.readouterr()
    expected = """
    └── foo 0.1.0 [ requires: Any ]
        ├── foo-bar [circular] [ requires: Any ]
        └── test-project 0.0.0 [ requires: ~=0.1 ]"""
    assert expected in content


@pytest.mark.usefixtures("repository", "working_set")
def test_freeze_dependencies_list(project, capsys, mocker):
    actions.do_add(project, packages=["requests"])
    capsys.readouterr()
    mocker.patch(
        "pdm.models.requirements.Requirement.from_dist",
        side_effect=lambda d: d.as_req(),
    )
    actions.do_list(project, freeze=True)
    content, _ = capsys.readouterr()
    assert "requests==2.19.1" in content
    assert "urllib3==1.22" in content


def test_list_reverse_without_graph_flag(project):
    with pytest.raises(PdmException):
        actions.do_list(project, reverse=True)


@pytest.mark.usefixtures("repository", "working_set")
def test_list_reverse_dependency_graph(project, capsys):
    actions.do_add(project, packages=["requests"])
    capsys.readouterr()
    actions.do_list(project, True, True)
    content, _ = capsys.readouterr()
    assert "└── requests 2.19.1 [ requires: <1.24,>=1.21.1 ]" in content


def test_list_json_without_graph_flag(project):
    with pytest.raises(PdmException):
        actions.do_list(project, json=True)


@pytest.mark.usefixtures("repository", "working_set")
def test_list_json(project, capsys):
    actions.do_add(project, packages=["requests"], no_self=True)
    content, _ = capsys.readouterr()
    actions.do_list(project, graph=True, json=True)
    content, _ = capsys.readouterr()
    expected = [
        {
            "package": "requests",
            "version": "2.19.1",
            "required": "~=2.19",
            "dependencies": [
                {
                    "package": "certifi",
                    "version": "2018.11.17",
                    "required": ">=2017.4.17",
                    "dependencies": [],
                },
                {
                    "package": "chardet",
                    "version": "3.0.4",
                    "required": "<3.1.0,>=3.0.2",
                    "dependencies": [],
                },
                {
                    "package": "idna",
                    "version": "2.7",
                    "required": "<2.8,>=2.5",
                    "dependencies": [],
                },
                {
                    "package": "urllib3",
                    "version": "1.22",
                    "required": "<1.24,>=1.21.1",
                    "dependencies": [],
                },
            ],
        }
    ]
    assert expected == loads(content)


@pytest.mark.usefixtures("repository", "working_set")
def test_list_json_reverse(project, capsys):
    actions.do_add(project, packages=["requests"], no_self=True)
    capsys.readouterr()
    actions.do_list(project, graph=True, reverse=True, json=True)
    content, _ = capsys.readouterr()
    expected = [
        {
            "package": "certifi",
            "version": "2018.11.17",
            "requires": None,
            "dependents": [
                {
                    "package": "requests",
                    "version": "2.19.1",
                    "requires": ">=2017.4.17",
                    "dependents": [],
                }
            ],
        },
        {
            "package": "chardet",
            "version": "3.0.4",
            "requires": None,
            "dependents": [
                {
                    "package": "requests",
                    "version": "2.19.1",
                    "requires": "<3.1.0,>=3.0.2",
                    "dependents": [],
                }
            ],
        },
        {
            "package": "idna",
            "version": "2.7",
            "requires": None,
            "dependents": [
                {
                    "package": "requests",
                    "version": "2.19.1",
                    "requires": "<2.8,>=2.5",
                    "dependents": [],
                }
            ],
        },
        {
            "package": "urllib3",
            "version": "1.22",
            "requires": None,
            "dependents": [
                {
                    "package": "requests",
                    "version": "2.19.1",
                    "requires": "<1.24,>=1.21.1",
                    "dependents": [],
                }
            ],
        },
    ]

    assert expected == loads(content)


@pytest.mark.usefixtures("working_set")
def test_list_json_with_circular_forward(project, capsys, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("baz", "0.1.0", ["foo"])
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo"])
    actions.do_add(project, packages=["baz"], no_self=True)
    capsys.readouterr()
    actions.do_list(project, graph=True, json=True)
    content, _ = capsys.readouterr()
    expected = [
        {
            "package": "baz",
            "version": "0.1.0",
            "required": "~=0.1",
            "dependencies": [
                {
                    "package": "foo",
                    "version": "0.1.0",
                    "required": "Any",
                    "dependencies": [
                        {
                            "package": "foo-bar",
                            "version": "0.1.0",
                            "required": "Any",
                            "dependencies": [
                                {
                                    "package": "foo",
                                    "version": "0.1.0",
                                    "required": "Any",
                                    "dependencies": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    ]
    assert expected == loads(content)


@pytest.mark.usefixtures("working_set")
def test_list_json_with_circular_reverse(project, capsys, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo", "baz"])
    repository.add_dependencies("baz", "0.1.0", [])
    actions.do_add(project, packages=["foo"], no_self=True)
    capsys.readouterr()
    actions.do_list(project, graph=True, json=True, reverse=True)
    content, _ = capsys.readouterr()
    expected = [
        {
            "package": "baz",
            "version": "0.1.0",
            "requires": None,
            "dependents": [
                {
                    "package": "foo-bar",
                    "version": "0.1.0",
                    "requires": "Any",
                    "dependents": [
                        {
                            "package": "foo",
                            "version": "0.1.0",
                            "requires": "Any",
                            "dependents": [
                                {
                                    "package": "foo-bar",
                                    "version": "0.1.0",
                                    "requires": "Any",
                                    "dependents": [],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    ]
    assert expected == loads(content)


def test_init_validate_python_requires(project_no_init):
    with pytest.raises(ValueError):
        actions.do_init(project_no_init, python_requires="3.7")


@pytest.mark.skipif(os.name != "posix", reason="Run on POSIX platforms only")
def test_use_wrapper_python(project):
    wrapper_script = """#!/bin/bash
exec "{}" "$@"
""".format(
        sys.executable
    )
    shim_path = project.root.joinpath("python_shim.sh")
    shim_path.write_text(wrapper_script)
    shim_path.chmod(0o755)

    actions.do_use(project, shim_path.as_posix())
    assert project.python.executable == sys.executable


@pytest.mark.skipif(os.name != "posix", reason="Run on POSIX platforms only")
def test_use_invalid_wrapper_python(project):
    wrapper_script = """#!/bin/bash
echo hello
"""
    shim_path = project.root.joinpath("python_shim.sh")
    shim_path.write_text(wrapper_script)
    shim_path.chmod(0o755)
    with pytest.raises(InvalidPyVersion):
        actions.do_use(project, shim_path.as_posix())
