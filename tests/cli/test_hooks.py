import shlex
import sys
from collections import namedtuple
from textwrap import dedent

import pytest

from pdm.cli import actions
from pdm.cli.hooks import KNOWN_HOOKS
from pdm.cli.options import from_splitted_env
from pdm.models.requirements import parse_requirement

pytestmark = pytest.mark.usefixtures("repository", "working_set", "local_finder")


def test_pre_script_fail_fast(project, invoke, capfd, mocker):
    project.pyproject.settings["scripts"] = {
        "pre_install": "python -c \"print('PRE INSTALL CALLED'); exit(1)\"",
        "post_install": "python -c \"print('POST INSTALL CALLED')\"",
    }
    project.pyproject.write()
    synchronize = mocker.patch("pdm.installers.synchronizers.Synchronizer.synchronize")
    result = invoke(["install"], obj=project)
    assert result.exit_code == 1
    out, _ = capfd.readouterr()
    assert "PRE INSTALL CALLED" in out
    assert "POST INSTALL CALLED" not in out
    synchronize.assert_not_called()


def test_pre_and_post_scripts(project, invoke, capfd, _echo):
    project.pyproject.settings["scripts"] = {
        "pre_script": "python echo.py pre_script",
        "post_script": "python echo.py post_script",
        "pre_test": "python echo.py pre_test",
        "test": "python echo.py test",
        "post_test": "python echo.py post_test",
        "pre_run": "python echo.py pre_run",
        "post_run": "python echo.py post_run",
    }
    project.pyproject.write()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    expected = dedent(
        """
        pre_run CALLED
        pre_script CALLED
        pre_test CALLED
        test CALLED
        post_test CALLED
        post_script CALLED
        post_run CALLED
        """
    ).strip()
    assert out.strip() == expected


def test_composite_runs_all_hooks(project, invoke, capfd, _echo):
    project.pyproject.settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "python echo.py Pre-Test",
        "post_test": "python echo.py Post-Test",
        "first": "python echo.py First",
        "pre_first": "python echo.py Pre-First",
        "second": "python echo.py Second",
        "post_second": "python echo.py Post-Second",
        "pre_script": "python echo.py Pre-Script",
        "post_script": "python echo.py Post-Script",
        "pre_run": "python echo.py Pre-Run",
        "post_run": "python echo.py Post-Run",
    }
    project.pyproject.write()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    expected = dedent(
        """
        Pre-Run CALLED
        Pre-Script CALLED
        Pre-Test CALLED
        Pre-Script CALLED
        Pre-First CALLED
        First CALLED
        Post-Script CALLED
        Pre-Script CALLED
        Second CALLED
        Post-Second CALLED
        Post-Script CALLED
        Post-Test CALLED
        Post-Script CALLED
        Post-Run CALLED
        """
    ).strip()
    assert out.strip() == expected


@pytest.mark.parametrize("option", [":all", ":pre,:post"])
def test_skip_all_hooks_option(project, invoke, capfd, option: str, _echo):
    project.pyproject.settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "python echo.py Pre-Test",
        "post_test": "python echo.py Post-Test",
        "first": "python echo.py First",
        "pre_first": "python echo.py Pre-First",
        "post_first": "python echo.py Post-First",
        "second": "python echo.py Second",
        "pre_second": "python echo.py Pre-Second",
        "post_second": "python echo.py Post-Second",
        "pre_script": "python echo.py Pre-Script",
        "post_script": "python echo.py Post-Script",
        "pre_run": "python echo.py Pre-Run",
        "post_run": "python echo.py Post-Run",
    }
    project.pyproject.write()
    capfd.readouterr()
    invoke(["run", f"--skip={option}", "first"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-First CALLED" not in out
    assert "First CALLED" in out
    assert "Post-First CALLED" not in out
    assert "Pre-Script CALLED" not in out
    assert "Post-Script CALLED" not in out
    capfd.readouterr()
    invoke(["run", f"--skip={option}", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Test CALLED" not in out
    assert "Pre-First CALLED" not in out
    assert "First CALLED" in out
    assert "Post-First CALLED" not in out
    assert "Pre-Second CALLED" not in out
    assert "Second CALLED" in out
    assert "Post-Second CALLED" not in out
    assert "Post-Test CALLED" not in out
    assert "Pre-Script CALLED" not in out
    assert "Post-Script CALLED" not in out
    assert "Pre-Run CALLED" not in out
    assert "Post-Run CALLED" not in out


@pytest.mark.parametrize(
    "args",
    [
        "--skip pre_test,post_first,second",
        "-k pre_test,post_first,second",
        "--skip pre_test --skip post_first --skip second",
        "-k pre_test -k post_first -k second",
        "--skip pre_test --skip post_first,second",
        "-k pre_test -k post_first,second",
    ],
)
def test_skip_option(project, invoke, capfd, args, _echo):
    project.pyproject.settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "python echo.py Pre-Test",
        "post_test": "python echo.py Post-Test",
        "first": "python echo.py First",
        "pre_first": "python echo.py Pre-First",
        "post_first": "python echo.py Post-First",
        "second": "python echo.py Second",
        "pre_second": "python echo.py Pre-Second",
        "post_second": "python echo.py Post-Second",
    }
    project.pyproject.write()
    capfd.readouterr()
    invoke(["run", *shlex.split(args), "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Test CALLED" not in out
    assert "Pre-First CALLED" in out
    assert "First CALLED" in out
    assert "Post-First CALLED" not in out
    assert "Pre-Second CALLED" not in out
    assert "Second CALLED" not in out
    assert "Post-Second CALLED" not in out
    assert "Post-Test CALLED" in out


@pytest.mark.parametrize(
    "env, expected",
    [
        ("pre_test", ["pre_test"]),
        ("pre_test,post_test", ["pre_test", "post_test"]),
        ("pre_test , post_test", ["pre_test", "post_test"]),
        (None, None),
        (" ", None),
        (" , ", None),
    ],
)
def test_skip_option_default_from_env(env, expected, monkeypatch):
    if env is not None:
        monkeypatch.setenv("PDM_SKIP_HOOKS", env)

    # Default value is set once and not easily testable
    # so we test the function generating this default value
    assert from_splitted_env("PDM_SKIP_HOOKS", ",") == expected


HookSpecs = namedtuple("HookSpecs", ["command", "hooks", "fixtures"])
this_python_version = f"{sys.version_info[0]}.{sys.version_info[1]}"

KNOWN_COMMAND_HOOKS = (
    ("add", "add requests", ("pre_lock", "post_lock"), ["working_set"]),
    ("build", "build", ("pre_build", "post_build"), []),
    ("init", "init --non-interactive", ("post_init",), []),
    (
        "install",
        "install",
        ("pre_install", "post_install", "pre_lock", "post_lock"),
        ["repository"],
    ),
    ("lock", "lock", ("pre_lock", "post_lock"), []),
    (
        "publish",
        "publish --username abc --password 123",
        ("pre_publish", "pre_build", "post_build", "post_publish"),
        ["mock_publish"],
    ),
    ("remove", "remove requests", ("pre_lock", "post_lock"), ["lock"]),
    ("sync", "sync", ("pre_install", "post_install"), ["lock"]),
    ("update", "update", ("pre_install", "post_install", "pre_lock", "post_lock"), []),
    ("use", f"use -f {this_python_version}", ("post_use",), []),
)

parametrize_with_commands = pytest.mark.parametrize(
    "specs",
    [pytest.param(HookSpecs(command, hooks, fixtures), id=id) for id, command, hooks, fixtures in KNOWN_COMMAND_HOOKS],
)

parametrize_with_hooks = pytest.mark.parametrize(
    "specs,hook",
    [
        pytest.param(HookSpecs(command, hooks, fixtures), hook, id=f"{id}-{hook}")
        for id, command, hooks, fixtures in KNOWN_COMMAND_HOOKS
        for hook in hooks
    ],
)


@pytest.fixture
def hooked_project(project, capfd, specs, request):
    project.pyproject.settings["scripts"] = {hook: f"python -c \"print('{hook} CALLED')\"" for hook in KNOWN_HOOKS}
    project.pyproject.write()
    for fixture in specs.fixtures:
        request.getfixturevalue(fixture)
    capfd.readouterr()
    return project


@pytest.fixture
def lock(project, capfd):
    project.add_dependencies({"requests": parse_requirement("requests")})
    actions.do_lock(project)
    capfd.readouterr()


@parametrize_with_commands
def test_hooks(hooked_project, invoke, capfd, specs: HookSpecs):
    invoke(shlex.split(specs.command), strict=True, obj=hooked_project)
    out, _ = capfd.readouterr()
    for hook in specs.hooks:
        assert f"{hook} CALLED" in out


@parametrize_with_hooks  # Iterate over hooks as we need a clean slate for each run
def test_skip_option_from_signal(hooked_project, invoke, capfd, specs: HookSpecs, hook: str):
    invoke([*shlex.split(specs.command), f"--skip={hook}"], strict=True, obj=hooked_project)
    out, _ = capfd.readouterr()
    assert f"{hook} CALLED" not in out
    for known_hook in specs.hooks:
        if known_hook != hook:
            assert f"{known_hook} CALLED" in out


@parametrize_with_commands
@pytest.mark.parametrize("option", [":all", ":pre,:post"])
def test_skip_all_option_from_signal(hooked_project, invoke, capfd, specs: HookSpecs, option: str):
    invoke(
        [*shlex.split(specs.command), f"--skip={option}"],
        strict=True,
        obj=hooked_project,
    )
    out, _ = capfd.readouterr()
    for hook in KNOWN_HOOKS:
        assert f"{hook} CALLED" not in out


@parametrize_with_commands
@pytest.mark.parametrize("prefix", ["pre", "post"])
def test_skip_pre_post_option_from_signal(hooked_project, invoke, capfd, specs: HookSpecs, prefix: str):
    invoke(
        [*shlex.split(specs.command), f"--skip=:{prefix}"],
        strict=True,
        obj=hooked_project,
    )
    out, _ = capfd.readouterr()
    for hook in specs.hooks:
        if hook.startswith(prefix):
            assert f"{hook} CALLED" not in out
        else:
            assert f"{hook} CALLED" in out
