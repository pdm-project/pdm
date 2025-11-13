import logging
import textwrap

import pytest

from pdm.exceptions import ProjectError
from pdm.formats import MetaConvertError
from pdm.models.setup import Setup


def test_setup_update_truthiness_semantics():
    base = Setup(name="foo", install_requires=["a"], summary=None)
    other = Setup(name=None, install_requires=[], summary="some desc")
    base.update(other)
    assert base.name == "foo"  # not overridden by falsy
    assert base.install_requires == ["a"]  # not overridden by empty list
    assert base.summary == "some desc"  # overridden by truthy


def test_parse_setup_py_with_kwargs_dict_and_variables(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        reqs = ['click', 'requests']
        extras_list = ['rich']
        extras = {'tui': extras_list}
        kwargs = dict(name='foo', version='0.1.0', install_requires=reqs,
                      python_requires='>=3.8', extras_require=extras)
        setup(**kwargs)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup(
        name="foo",
        version="0.1.0",
        install_requires=["click", "requests"],
        extras_require={"tui": ["rich"]},
        python_requires=">=3.8",
    )


def test_setup_as_dict():
    s = Setup(
        name="n", version="1", install_requires=["a"], extras_require={"x": ["b"]}, python_requires=">=3.8", summary="d"
    )
    d = s.as_dict()
    assert d["name"] == "n"
    assert d["version"] == "1"
    assert d["install_requires"] == ["a"]
    assert d["extras_require"] == {"x": ["b"]}
    assert d["python_requires"] == ">=3.8"
    assert d["summary"] == "d"


@pytest.mark.parametrize(
    "content",
    [
        # Last element is an if but not a Compare
        """
if True:
    pass
""",
        # Compare but left is Attribute not Name
        """
import pkg
if pkg.__name__ == "__main__":
    pass
""",
        # Compare left is Name but not __name__
        """
name = "x"
if name == "__main__":
    pass
""",
    ],
)
def test_parse_setup_py_no_setup_call_branches(tmp_path, content):
    tmp_path.joinpath("setup.py").write_text(textwrap.dedent(content))
    assert Setup.from_directory(tmp_path) == Setup()


def test_parse_setup_py_irrelevant_call_and_assignment(tmp_path):
    content = textwrap.dedent(
        """
        def foo():
            return 1
        x = 1
        foo()
        # no setup() call here
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup()


@pytest.mark.parametrize(
    "content, expected",
    [
        # No sections -> defaults (version defaults to "0.0.0")
        ("", Setup(version="0.0.0")),
        # Empty metadata section only
        ("[metadata]\n", Setup(version="0.0.0")),
        # Empty options section only
        ("[options]\n", Setup(version="0.0.0")),
        # Name only, version still defaults to 0.0.0
        ("[metadata]\nname = foo\n", Setup(name="foo", version="0.0.0")),
        # Version attr -> keep default 0.0.0
        ("[metadata]\nversion = attr:foo.__version__\n", Setup(version="0.0.0")),
    ],
)
def test_parse_setup_cfg_missing_sections_and_options(tmp_path, content, expected):
    tmp_path.joinpath("setup.cfg").write_text(content)
    assert Setup.from_directory(tmp_path) == expected


def test_find_setup_call_in_function_and_if_main(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup

        def inner():
            setup(name="foo", version="0.1.0")

        if __name__ == "__main__":
            inner()
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup(name="foo", version="0.1.0")


def test_if_main_direct_setup_hits_concat_body_return(tmp_path):
    content = textwrap.dedent(
        """
        if __name__ == "__main__":
            from setuptools import setup
            setup(name="foo2", version="0.3.0")
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup(name="foo2", version="0.3.0")


def test_from_directory_precedence_and_falsy_update(tmp_path):
    pyproject = textwrap.dedent(
        """
        [project]
        name = "name_py"
        version = "0.1.0"
        requires-python = ">=3.7"
        dependencies = ["a"]
        [project.optional-dependencies]
        tui = ["r1"]
        """
    )
    tmp_path.joinpath("pyproject.toml").write_text(pyproject)

    setup_cfg = textwrap.dedent(
        """
        [metadata]
        name = name_cfg
        version = 0.1.1

        [options]
        python_requires = >=3.8
        install_requires =
            b

        [options.extras_require]
        tui =
            r2
        """
    )
    tmp_path.joinpath("setup.cfg").write_text(setup_cfg)

    setup_py = textwrap.dedent(
        """
        from setuptools import setup
        setup(name='name_py', version='0.2.0', install_requires=[], extras_require={'tui': ['r3']})
        """
    )
    tmp_path.joinpath("setup.py").write_text(setup_py)

    result = Setup.from_directory(tmp_path)
    assert result.name == "name_py"  # from setup.py (last wins)
    assert result.version == "0.2.0"  # from setup.py
    assert result.install_requires == ["b"]  # not overridden by empty list in setup.py
    assert result.extras_require == {"tui": ["r3"]}  # overridden by setup.py (truthy)
    assert result.python_requires == ">=3.8"  # from setup.cfg (later non-empty vs pyproject)


def test_read_pyproject_toml_project_error_returns_empty(tmp_path, mocker):
    # Create a dummy PyProject that raises ProjectError on unwrap()
    import pdm.project.project_file as project_file

    mocker.patch.object(project_file.PyProject, "_convert_pyproject", side_effect=ProjectError("boom"))

    tmp_path.joinpath("pyproject.toml").write_text("[project]\nname='x'")
    assert Setup.from_directory(tmp_path) == Setup()  # empty due to ProjectError


def test_read_pyproject_toml_metaconverter_error_uses_partial_data_and_logs(tmp_path, mocker, caplog):
    partial = {
        "name": "foo",
        "version": "0.1.0",
        "description": "desc",
        "dependencies": ["a"],
        "optional-dependencies": {"tui": ["r"]},
        "requires-python": ">=3.8",
    }

    import pdm.project.project_file as project_file

    mocker.patch.object(
        project_file.PyProject, "_convert_pyproject", side_effect=MetaConvertError(["e1"], data=partial, settings={})
    )

    caplog.set_level("WARNING")
    logging.getLogger("pdm.termui").addHandler(caplog.handler)
    tmp_path.joinpath("pyproject.toml").write_text("[tool.other]\nfoo='bar'")
    result = Setup.from_directory(tmp_path)

    # Check fields are populated from partial data
    assert result.name == "foo"
    assert result.version == "0.1.0"
    assert result.summary == "desc"
    assert result.install_requires == ["a"]
    assert result.extras_require == {"tui": ["r"]}
    assert result.python_requires == ">=3.8"

    # Check a warning was logged
    assert any("Error parsing pyproject.toml" in message for message in caplog.messages)


def test_setup_distribution_metadata_and_requires_markers():
    dist = Setup(
        name="pack",
        version="1.0.0",
        summary="desc",
        python_requires=">=3.8",
        install_requires=["base>=1"],
        extras_require={
            "tui": [
                "rich",
                'foo; python_version >= "3.9"',
                'bar; python_version < "3.8" or sys_platform == "win32"',
            ]
        },
    ).as_dist()

    meta = dist.metadata
    assert meta == {
        "Name": "pack",
        "Version": "1.0.0",
        "Summary": "desc",
        "Requires-Python": ">=3.8",
    }

    reqs = dist.requires
    # Contains base
    assert any(r.startswith("base>=1") for r in reqs)
    # Extra-only requirement with no existing marker
    assert any(r.startswith("rich") and 'extra == "tui"' in r for r in reqs)
    # Existing marker combined without parentheses
    assert any(r.startswith("foo") and 'python_version >= "3.9" and extra == "tui"' in r for r in reqs)
    # Existing marker with OR and repeated extra markers (no parentheses)
    assert any(
        r.startswith("bar")
        and 'python_version < "3.8" and extra == "tui" or sys_platform == "win32" and extra == "tui"' in r
        for r in reqs
    )


def test_read_text_and_locate_file_smoke():
    dist = Setup(name="x", version="1").as_dist()
    assert dist.read_text("any") is None
    p = dist.locate_file("whatever")
    from pathlib import Path as _P

    assert isinstance(p, _P)


def test_find_setup_call_skips_non_call_expr_then_finds_setup(tmp_path):
    content = textwrap.dedent(
        """
        "module docstring"
        from setuptools import setup
        setup(name='d', version='0.1.0')
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup(name="d", version="0.1.0")


def test_find_setup_call_skips_non_functiondef_element_then_finds_setup(tmp_path):
    content = textwrap.dedent(
        """
        class X: pass
        from setuptools import setup
        setup(name='e', version='0.1.0')
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup(name="e", version="0.1.0")


def test_find_setup_call_skips_non_setup_call_then_finds_setup(tmp_path):
    content = textwrap.dedent(
        """
        def foo(): pass
        foo()
        from setuptools import setup
        setup(name='f', version='0.1.0')
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    assert Setup.from_directory(tmp_path) == Setup(name="f", version="0.1.0")


def test_install_requires_name_resolves_to_non_list(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        reqs = 'notalist'
        setup(name='g', version='0.1.0', install_requires=reqs)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    assert result.name == "g"
    assert result.install_requires == []


def test_extras_require_name_is_undefined_returns_empty(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        setup(name='h', version='0.1.0', extras_require=extras)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    assert result.extras_require == {}


def test_extras_require_name_resolves_to_non_dict(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        extras = ['x']
        setup(name='i', version='0.1.0', extras_require=extras)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    assert result.extras_require == {}


def test_single_string_name_variable_not_string(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        namev = 123
        setup(name=namev, version='0.1.0')
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    assert result.name is None


def test_extras_require_from_kwargs_non_dict_non_call_returns_empty(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        kwargs = "notadict"
        setup(**kwargs)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    assert result.extras_require == {}
    assert result.version == "0.0.0"


def test_extras_require_from_kwargs_call_func_is_attribute_returns_empty(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        class Obj:
            def build(self):
                return {}
        obj = Obj()
        kwargs = obj.build()
        setup(**kwargs)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    assert result.extras_require == {}


def test_extras_require_from_kwargs_call_func_name_not_dict_returns_empty(tmp_path):
    content = textwrap.dedent(
        """
        from setuptools import setup
        def make_kwargs(**kw):
            return kw
        kwargs = make_kwargs(name='n', version='0.1.0')
        setup(**kwargs)
        """
    )
    tmp_path.joinpath("setup.py").write_text(content)
    result = Setup.from_directory(tmp_path)
    # kwargs created by a function call that is not dict() won't be introspected
    assert result.name is None
    assert result.version == "0.0.0"
    assert result.extras_require == {}
