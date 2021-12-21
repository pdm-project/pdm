import json

import pytest

from pdm.cli import actions
from pdm.exceptions import PdmException


def test_list_command(project, invoke, mocker):
    do_list = mocker.patch.object(actions, "do_list")
    invoke(["list"], obj=project)
    do_list.assert_called_once()


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
    assert expected == json.loads(content)


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

    assert expected == json.loads(content)


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
    assert expected == json.loads(content)


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
    assert expected == json.loads(content)
