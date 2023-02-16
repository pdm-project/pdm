import json
import os
import pathlib
from unittest import mock

import pytest
from rich.box import ASCII

from pdm.cli import actions
from pdm.cli.commands.list import Command
from pdm.models.specifiers import PySpecSet
from pdm.pytest import Distribution
from tests import FIXTURES


def test_list_command(project, invoke, mocker):
    # Calls the correct handler within the Command
    m = mocker.patch.object(Command, "handle_list")
    invoke(["list"], obj=project)
    m.assert_called_once()


@pytest.mark.usefixtures("working_set")
def test_list_graph_command(project, invoke, mocker):
    # Calls the correct handler within the list command
    m = mocker.patch.object(Command, "handle_graph")
    invoke(["list", "--graph"], obj=project)
    m.assert_called_once()


@mock.patch("rich.console.ConsoleOptions.ascii_only", lambda: True)
@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph(project, invoke):
    # Shows a line that contains a sub requirement (any order).
    actions.do_add(project, packages=["requests"])
    result = invoke(["list", "--graph"], obj=project)
    expected = "-- urllib3 1.22 [ required: <1.24,>=1.21.1 ]" in result.outputs
    assert expected


@mock.patch("rich.console.ConsoleOptions.ascii_only", lambda: True)
@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph_include_exclude(project, invoke):
    # Just include dev packages in the graph
    project.environment.python_requires = PySpecSet(">=3.6")
    dep_path = FIXTURES.joinpath("projects/demo").as_posix()
    actions.do_add(
        project,
        dev=True,
        group="dev",
        editables=[f"{dep_path}[security]"],
    )

    # Output full graph
    result = invoke(["list", "--graph"], obj=project)
    expects = (
        "demo 0.0.1 [ Not required ]\n",
        "+-- chardet 3.0.4 [ required: Any ]\n" if os.name == "nt" else "",
        "`-- idna 2.7 [ required: Any ]\n",
        "requests 2.19.1 [ Not required ]\n",
        "+-- certifi 2018.11.17 [ required: >=2017.4.17 ]\n",
        "+-- chardet 3.0.4 [ required: <3.1.0,>=3.0.2 ]\n",
        "+-- idna 2.7 [ required: <2.8,>=2.5 ]\n",
        "`-- urllib3 1.22 [ required: <1.24,>=1.21.1 ]\n",
    )
    expects = "".join(expects)
    assert expects == result.outputs

    # Now exclude the dev dep.
    result = invoke(["list", "--graph", "--exclude", "dev"], obj=project)
    expects = ""
    assert expects == result.outputs

    # Only include the dev dep
    result = invoke(["list", "--graph", "--include", "dev", "--exclude", "*"], obj=project)
    expects = "demo[security] 0.0.1 [ required: Any ]\n"
    expects = "".join(expects)
    assert expects == result.outputs


@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph_with_circular_forward(project, invoke, repository):
    # shows a circular dependency
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo"])
    actions.do_add(project, packages=["foo"])
    result = invoke(["list", "--graph"], obj=project)
    circular_found = "foo [circular]" in result.outputs
    assert circular_found


@mock.patch("rich.console.ConsoleOptions.ascii_only", lambda: True)
@pytest.mark.usefixtures("working_set")
def test_list_dependency_graph_with_circular_reverse(project, invoke, repository):
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo", "baz"])
    repository.add_dependencies("baz", "0.1.0", [])
    actions.do_add(project, packages=["foo"])

    # --reverse flag shows packages reversed and with [circular]
    result = invoke(["list", "--graph", "--reverse"], obj=project)
    expected = (
        "baz 0.1.0 \n"
        "`-- foo-bar 0.1.0 [ requires: Any ]\n"
        "    `-- foo 0.1.0 [ requires: Any ]\n"
        "        +-- foo-bar [circular] [ requires: Any ]\n"
        "        `-- test-project 0.0.0 [ requires: ~=0.1 ]\n"
    )
    assert expected in result.outputs

    # -r flag shows packages reversed and with [circular]
    result = invoke(["list", "--graph", "-r"], obj=project)
    assert expected in result.outputs


def test_list_reverse_without_graph_flag(project, invoke):
    # results in PDMUsageError since --reverse needs --graph
    result = invoke(["list", "--reverse"], obj=project)
    assert "[PdmUsageError]" in result.stderr
    assert "--reverse cannot be used without --graph" in result.stderr

    result = invoke(["list", "-r"], obj=project)
    assert "[PdmUsageError]" in result.stderr
    assert "--reverse cannot be used without --graph" in result.stderr


@mock.patch("rich.console.ConsoleOptions.ascii_only", lambda: True)
@pytest.mark.usefixtures("working_set")
def test_list_reverse_dependency_graph(project, invoke):
    # requests visible on leaf node
    actions.do_add(project, packages=["requests"])
    result = invoke(["list", "--graph", "--reverse"], obj=project)
    assert "`-- requests 2.19.1 [ requires: <1.24,>=1.21.1 ]" in result.outputs


@pytest.mark.usefixtures("working_set")
def test_list_json(project, invoke):
    # check json output matches graph output
    actions.do_add(project, packages=["requests"], no_self=True)
    result = invoke(["list", "--graph", "--json"], obj=project)

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
    assert expected == json.loads(result.outputs)


@pytest.mark.usefixtures("working_set")
def test_list_json_reverse(project, invoke):
    # check json output matches reversed graph
    actions.do_add(project, packages=["requests"], no_self=True)
    result = invoke(["list", "--graph", "--reverse", "--json"], obj=project)
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

    assert expected == json.loads(result.outputs)


@pytest.mark.usefixtures("working_set")
def test_list_json_with_circular_forward(project, invoke, repository):
    # circulars are handled in json exports
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("baz", "0.1.0", ["foo"])
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo"])
    actions.do_add(project, packages=["baz"], no_self=True)
    result = invoke(["list", "--graph", "--json"], obj=project)
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
    assert expected == json.loads(result.outputs)


@pytest.mark.usefixtures("working_set")
def test_list_json_with_circular_reverse(project, invoke, repository):
    # circulars are handled in reversed json exports
    repository.add_candidate("foo", "0.1.0")
    repository.add_candidate("foo-bar", "0.1.0")
    repository.add_candidate("baz", "0.1.0")
    repository.add_dependencies("foo", "0.1.0", ["foo-bar"])
    repository.add_dependencies("foo-bar", "0.1.0", ["foo", "baz"])
    repository.add_dependencies("baz", "0.1.0", [])
    actions.do_add(project, packages=["foo"], no_self=True)
    result = invoke(["list", "--graph", "--reverse", "--json"], obj=project)
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
    assert expected == json.loads(result.outputs)


def test_list_field_unknown(project, invoke):
    # unknown list fields flagged to user
    result = invoke(["list", "--fields", "notvalid"], obj=project)
    assert "[PdmUsageError]" in result.stderr
    assert "--fields must specify one or more of:" in result.stderr


def test_list_sort_unknown(project, invoke):
    # unknown sort fields flagged to user
    result = invoke(["list", "--sort", "notvalid"], obj=project)
    assert "[PdmUsageError]" in result.stderr
    assert "--sort key must be one of:" in result.stderr


def test_list_freeze_banned_options(project, invoke):
    # other flags cannot be used with --freeze
    result = invoke(["list", "--freeze", "--graph"], obj=project)
    expected = "--graph cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--reverse"], obj=project)
    expected = "--reverse cannot be used without --graph"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "-r"], obj=project)
    expected = "--reverse cannot be used without --graph"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--fields", "name"], obj=project)
    expected = "--fields cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--resolve"], obj=project)
    expected = "--resolve cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--sort", "name"], obj=project)
    expected = "--sort cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--csv"], obj=project)
    expected = "--csv cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--json"], obj=project)
    expected = "--json cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--markdown"], obj=project)
    expected = "--markdown cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--include", "dev"], obj=project)
    expected = "--include/--exclude cannot be used with --freeze"
    assert expected in result.outputs

    result = invoke(["list", "--freeze", "--exclude", "dev"], obj=project)
    expected = "--include/--exclude cannot be used with --freeze"
    assert expected in result.outputs


def test_list_multiple_export_formats(project, invoke):
    # export formats cannot be used with each other
    result = invoke(["list", "--csv", "--markdown"], obj=project)
    expected = "--markdown: not allowed with argument --csv"
    assert expected in result.outputs

    result = invoke(["list", "--csv", "--json"], obj=project)
    expected = "--json: not allowed with argument --csv"
    assert expected in result.outputs

    result = invoke(["list", "--markdown", "--csv"], obj=project)
    expected = "--csv: not allowed with argument --markdown"
    assert expected in result.outputs

    result = invoke(["list", "--markdown", "--json"], obj=project)
    expected = "--json: not allowed with argument --markdown"
    assert expected in result.outputs

    result = invoke(["list", "--json", "--markdown"], obj=project)
    expected = "--markdown: not allowed with argument --json"
    assert expected in result.outputs

    result = invoke(["list", "--json", "--csv"], obj=project)
    expected = "--csv: not allowed with argument --json"
    assert expected in result.outputs


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("working_set")
def test_list_bare(project, invoke):
    actions.do_add(project, packages=["requests"])
    result = invoke(["list"], obj=project)
    # Ordering can be different on different platforms
    # and python versions.
    assert "| name         | version    | location |\n" in result.output
    assert "| certifi      | 2018.11.17 |          |\n" in result.output
    assert "| chardet      | 3.0.4      |          |\n" in result.output
    assert "| idna         | 2.7        |          |\n" in result.output
    assert "| requests     | 2.19.1     |          |\n" in result.output
    assert "| urllib3      | 1.22       |          |\n" in result.output
    assert "| test-project | 0.0.0      |          |\n" in result.output


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("working_set")
def test_list_bare_sorted_name(project, invoke):
    actions.do_add(project, packages=["requests"])
    result = invoke(["list", "--sort", "name"], obj=project)
    expected = (
        "+--------------------------------------+\n"
        "| name         | version    | location |\n"
        "|--------------+------------+----------|\n"
        "| certifi      | 2018.11.17 |          |\n"
        "| chardet      | 3.0.4      |          |\n"
        "| idna         | 2.7        |          |\n"
        "| requests     | 2.19.1     |          |\n"
        "| test-project | 0.0.0      |          |\n"
        "| urllib3      | 1.22       |          |\n"
        "+--------------------------------------+\n"
    )
    assert expected == result.output


@pytest.fixture()
def fake_working_set(working_set):
    """Create fake packages with license data
    for testing.
    """

    class _MockPackagePath(pathlib.PurePosixPath):
        def read_text(self, *args, **kwargs):
            return self.license_text

    # Foo package.
    foo = Distribution("foo", "0.1.0", metadata={"License": "A License"})
    foo_l = _MockPackagePath("foo-0.1.0.dist-info", "LICENSE")
    foo_l.license_text = "license text for foo here"
    foo.files = [foo_l]

    # Bar package.
    bar = Distribution("bar", "3.0.1", metadata={"License": "B License"})
    bar_l = _MockPackagePath("bar-3.0.1.dist-info", "LICENSE")
    bar_l.license_text = "license text for bar here"
    bar.files = [bar_l]

    # Baz package.
    baz = Distribution("baz", "2.7", metadata={"License": "C License"})
    baz_l = _MockPackagePath("bar-2.7.dist-info", "LICENSE")
    baz_l.license_text = "license text for baz here"
    baz.files = [baz_l]

    # missing package- License is set to UNKNOWN, text saved in COPYING
    unknown = Distribution(
        "unknown",
        "1.0",
        metadata={
            "License": "UNKNOWN",
            "Classifier": "License :: OSI Approved :: Apache Software License",
        },
    )
    unknown_l = _MockPackagePath("unknown-1.0.dist-info", "COPYING")
    unknown_l.license_text = "license text for UNKNOWN here"
    unknown.files = [unknown_l]

    # missing package- License is set to UNKNOWN, text saved in LICENCE
    # using UK spelling
    classifier = Distribution("classifier", "1.0", metadata={"Classifier": "License :: PDM TEST D"})
    classifier_l = _MockPackagePath("classifier-1.0.dist-info", "LICENCE")
    classifier_l.license_text = "license text for CLASSIFIER here"
    classifier_l.read_text = lambda *a, **kw: 1 / 0  # make it throw an error
    classifier.files = [classifier_l]

    # Place our fake packages in the working set.
    for candidate in [foo, bar, baz, unknown, classifier]:
        working_set.add_distribution(candidate)
    return working_set


@pytest.fixture()
def fake_metadata(mocker, repository):
    def prepare_metadata(self):
        can = self.candidate
        dist = Distribution(can.name, can.version, can.req.editable)
        dist.dependencies = repository.get_raw_dependencies(can)
        return dist

    return mocker.patch(
        "pdm.models.candidates.PreparedCandidate.prepare_metadata",
        prepare_metadata,
    )


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("working_set")
def test_list_freeze(project, invoke):
    actions.do_add(project, packages=["requests"])
    result = invoke(["list", "--freeze"], obj=project)
    expected = (
        "certifi==2018.11.17\n"
        "chardet==3.0.4\n"
        "idna==2.7\n"
        "requests==2.19.1\n"
        "test-project==0.0.0\n"
        "urllib3==1.22\n"
    )
    assert expected == result.output


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("working_set")
def test_list_bare_sorted_version(project, invoke):
    actions.do_add(project, packages=["requests"])
    result = invoke(["list", "--sort", "version"], obj=project)
    expected = (
        "+--------------------------------------+\n"
        "| name         | version    | location |\n"
        "|--------------+------------+----------|\n"
        "| test-project | 0.0.0      |          |\n"
        "| urllib3      | 1.22       |          |\n"
        "| requests     | 2.19.1     |          |\n"
        "| idna         | 2.7        |          |\n"
        "| certifi      | 2018.11.17 |          |\n"
        "| chardet      | 3.0.4      |          |\n"
        "+--------------------------------------+\n"
    )
    assert expected == result.output


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("fake_metadata")
def test_list_bare_sorted_version_resolve(project, invoke, working_set):
    project.environment.python_requires = PySpecSet(">=3.6")
    actions.do_add(project, packages=["requests"], sync=False)

    result = invoke(["list", "--sort", "version", "--resolve"], obj=project, strict=True)
    assert "requests" not in working_set
    expected = (
        "+----------------------------------+\n"
        "| name     | version    | location |\n"
        "|----------+------------+----------|\n"
        "| urllib3  | 1.22       |          |\n"
        "| requests | 2.19.1     |          |\n"
        "| idna     | 2.7        |          |\n"
        "| certifi  | 2018.11.17 |          |\n"
        "| chardet  | 3.0.4      |          |\n"
        "+----------------------------------+\n"
    )
    assert expected == result.outputs, result.outputs


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("fake_working_set")
def test_list_bare_fields_licences(project, invoke):
    result = invoke(["list", "--fields", "name,version,groups,licenses"], obj=project)
    expected = (
        "+---------------------------------------------------------+\n"
        "| name       | version | groups | licenses                |\n"
        "|------------+---------+--------+-------------------------|\n"
        "| foo        | 0.1.0   | :sub   | A License               |\n"
        "| bar        | 3.0.1   | :sub   | B License               |\n"
        "| baz        | 2.7     | :sub   | C License               |\n"
        "| unknown    | 1.0     | :sub   | Apache Software License |\n"
        "| classifier | 1.0     | :sub   | PDM TEST D              |\n"
        "+---------------------------------------------------------+\n"
    )
    assert expected == result.output


@pytest.mark.usefixtures("fake_working_set")
def test_list_csv_fields_licences(project, invoke):
    result = invoke(["list", "--csv", "--fields", "name,version,licenses"], obj=project)
    expected = (
        "name,version,licenses\n"
        "foo,0.1.0,A License\n"
        "bar,3.0.1,B License\n"
        "baz,2.7,C License\n"
        "unknown,1.0,Apache Software License\n"
        "classifier,1.0,PDM TEST D\n"
    )
    assert expected == result.output


@pytest.mark.usefixtures("fake_working_set")
def test_list_json_fields_licences(project, invoke):
    result = invoke(["list", "--json", "--fields", "name,version,licenses"], obj=project)
    expected = [
        {"name": "foo", "version": "0.1.0", "licenses": "A License"},
        {"name": "bar", "version": "3.0.1", "licenses": "B License"},
        {"name": "baz", "version": "2.7", "licenses": "C License"},
        {"name": "unknown", "version": "1.0", "licenses": "Apache Software License"},
        {"name": "classifier", "version": "1.0", "licenses": "PDM TEST D"},
    ]

    assert expected == json.loads(result.outputs)


@pytest.mark.usefixtures("fake_working_set")
def test_list_markdown_fields_licences(project, invoke):
    result = invoke(["list", "--markdown", "--fields", "name,version,licenses"], obj=project)
    expected = (
        "# test_project licenses\n"
        "## foo\n\n"
        "| Name | foo |\n"
        "|----|----|\n"
        "| Version | 0.1.0 |\n"
        "| Licenses | A License |\n\n"
        "foo-0.1.0.dist-info/LICENSE\n\n\n"
        "````\n"
        "license text for foo here\n"
        "````\n\n\n"
        "## bar\n\n"
        "| Name | bar |\n"
        "|----|----|\n"
        "| Version | 3.0.1 |\n"
        "| Licenses | B License |\n\n"
        "bar-3.0.1.dist-info/LICENSE\n\n\n"
        "````\n"
        "license text for bar here\n"
        "````\n\n\n"
        "## baz\n\n"
        "| Name | baz |\n"
        "|----|----|\n"
        "| Version | 2.7 |\n"
        "| Licenses | C License |\n\n"
        "bar-2.7.dist-info/LICENSE\n\n\n"
        "````\n"
        "license text for baz here\n"
        "````\n\n\n"
        "## unknown\n\n"
        "| Name | unknown |\n"
        "|----|----|\n"
        "| Version | 1.0 |\n"
        "| Licenses | Apache Software License |\n\n"
        "unknown-1.0.dist-info/COPYING\n\n\n"
        "````\n"
        "license text for UNKNOWN here\n"
        "````\n\n\n"
        "## classifier\n\n"
        "| Name | classifier |\n"
        "|----|----|\n"
        "| Version | 1.0 |\n"
        "| Licenses | PDM TEST D |\n\n"
        "classifier-1.0.dist-info/LICENCE\n\n\n"
        "````\n"
        "Problem finding license text: division by zero\n"
        "````\n\n\n"
    )
    assert expected == result.output


@pytest.mark.usefixtures("working_set", "repository")
def test_list_csv_include_exclude_valid(project, invoke):
    project.environment.python_requires = PySpecSet(">=3.6")
    dep_path = FIXTURES.joinpath("projects/demo").as_posix()
    actions.do_add(
        project,
        dev=True,
        group="dev",
        editables=[f"{dep_path}[security]"],
    )
    result = invoke(
        [
            "list",
            "--csv",
            "--fields",
            "name,version,groups",
            "--sort",
            "name",
            "--include",
            "notexisting",
        ],
        obj=project,
    )
    assert "[PdmUsageError]" in result.outputs
    assert "--include groups must be selected from" in result.outputs
    assert "dev" in result.outputs
    assert "default" in result.outputs
    assert ":sub" in result.outputs


@pytest.mark.usefixtures("working_set", "repository")
def test_list_csv_include_exclude(project, invoke):
    project.environment.python_requires = PySpecSet(">=3.6")
    dep_path = FIXTURES.joinpath("projects/demo").as_posix()
    actions.do_add(
        project,
        dev=True,
        group="dev",
        editables=[f"{dep_path}[security]"],
    )

    # Show all groups.
    result = invoke(
        ["list", "--csv", "--fields", "name,version,groups", "--sort", "name"],
        obj=project,
    )
    expected = (
        "name,version,groups\n"
        "certifi,2018.11.17,:sub\n"
        "chardet,3.0.4,:sub\n"
        "demo,0.0.1,dev\n"
        "idna,2.7,:sub\n"
        "requests,2.19.1,:sub\n"
        "urllib3,1.22,:sub\n"
    )
    assert expected == result.output

    # Sub always included.
    result = invoke(
        [
            "list",
            "--csv",
            "--fields",
            "name,groups",
            "--sort",
            "name",
            "--include",
            "dev",
        ],
        obj=project,
    )
    expected = "name,groups\ncertifi,:sub\nchardet,:sub\ndemo,dev\nidna,:sub\nrequests,:sub\nurllib3,:sub\n"
    assert expected == result.output

    # Include all (default) except sub
    result = invoke(
        [
            "list",
            "--csv",
            "--fields",
            "name,groups",
            "--sort",
            "name",
            "--exclude",
            ":sub",
        ],
        obj=project,
    )
    expected = "name,groups\ndemo,dev\n"
    assert expected == result.output

    # Show just the dev group
    result = invoke(
        [
            "list",
            "--csv",
            "--fields",
            "name,version,groups",
            "--sort",
            "name",
            "--include",
            "dev",
            "--exclude",
            "*",
        ],
        obj=project,
    )
    expected = "name,version,groups\ndemo,0.0.1,dev\n"
    assert expected == result.output

    # Exclude the dev group.
    result = invoke(
        [
            "list",
            "--csv",
            "--fields",
            "name,version,groups",
            "--sort",
            "name",
            "--exclude",
            "dev",
        ],
        obj=project,
    )
    expected = "name,version,groups\n"
    assert expected == result.output
