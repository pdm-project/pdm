import shlex
from collections import namedtuple

import pytest

from pdm.cli import actions
from pdm.cli.hooks import KNOWN_HOOKS
from pdm.models.requirements import parse_requirement


def test_pre_script_fail_fast(project, invoke, capfd, mocker):
    project.tool_settings["scripts"] = {
        "pre_install": "python -c \"print('PRE INSTALL CALLED'); exit(1)\"",
        "post_install": "python -c \"print('POST INSTALL CALLED')\"",
    }
    project.write_pyproject()
    synchronize = mocker.patch("pdm.installers.synchronizers.Synchronizer.synchronize")
    result = invoke(["install"], obj=project)
    assert result.exit_code == 1
    out, _ = capfd.readouterr()
    assert "PRE INSTALL CALLED" in out
    assert "POST INSTALL CALLED" not in out
    synchronize.assert_not_called()


def test_pre_and_post_scripts(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "pre_test": "python -c \"print('PRE test CALLED')\"",
        "test": "python -c \"print('IN test CALLED')\"",
        "post_test": "python -c \"print('POST test CALLED')\"",
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "PRE test CALLED" in out
    assert "IN test CALLED" in out
    assert "POST test CALLED" in out


def test_composite_runs_all_hooks(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "echo 'Pre-Test CALLED'",
        "post_test": "echo 'Post-Test CALLED'",
        "first": "echo 'First CALLED'",
        "pre_first": "echo 'Pre-First CALLED'",
        "second": "echo 'Second CALLED'",
        "post_second": "echo 'Post-Second CALLED'",
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Test CALLED" in out
    assert "Pre-First CALLED" in out
    assert "First CALLED" in out
    assert "Second CALLED" in out
    assert "Post-Second CALLED" in out
    assert "Post-Test CALLED" in out


@pytest.mark.parametrize("option", [":all", ":pre,:post"])
def test_skip_all_hooks_option(project, invoke, capfd, option: str):
    project.tool_settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "echo 'Pre-Test CALLED'",
        "post_test": "echo 'Post-Test CALLED'",
        "first": "echo 'First CALLED'",
        "pre_first": "echo 'Pre-First CALLED'",
        "post_first": "echo 'Post-First CALLED'",
        "second": "echo 'Second CALLED'",
        "pre_second": "echo 'Pre-Second CALLED'",
        "post_second": "echo 'Post-Second CALLED'",
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", f"--skip={option}", "first"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-First CALLED" not in out
    assert "First CALLED" in out
    assert "Post-First CALLED" not in out
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
def test_skip_option(project, invoke, capfd, args):
    project.tool_settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "echo 'Pre-Test CALLED'",
        "post_test": "echo 'Post-Test CALLED'",
        "first": "echo 'First CALLED'",
        "pre_first": "echo 'Pre-First CALLED'",
        "post_first": "echo 'Post-First CALLED'",
        "second": "echo 'Second CALLED'",
        "pre_second": "echo 'Pre-Second CALLED'",
        "post_second": "echo 'Post-Second CALLED'",
    }
    project.write_pyproject()
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


HookSpecs = namedtuple("HookSpecs", ["command", "hooks", "fixtures"])

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
    ("publish", "publish", ("pre_build", "post_build"), ["mock_publish"]),
    ("remove", "remove requests", ("pre_lock", "post_lock"), ["lock"]),
    ("sync", "sync", ("pre_install", "post_install"), ["lock"]),
    ("update", "update", ("pre_install", "post_install", "pre_lock", "post_lock"), []),
)

parametrize_with_commands = pytest.mark.parametrize(
    "specs",
    [
        pytest.param(HookSpecs(command, hooks, fixtures), id=id)
        for id, command, hooks, fixtures in KNOWN_COMMAND_HOOKS
    ],
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
    project.tool_settings["scripts"] = {
        hook: f"python -c \"print('{hook} CALLED')\"" for hook in KNOWN_HOOKS
    }
    project.write_pyproject()
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
def test_skip_option_from_signal(
    hooked_project, invoke, capfd, specs: HookSpecs, hook: str
):
    invoke(
        [*shlex.split(specs.command), f"--skip={hook}"], strict=True, obj=hooked_project
    )
    out, _ = capfd.readouterr()
    assert f"{hook} CALLED" not in out
    for known_hook in specs.hooks:
        if known_hook != hook:
            assert f"{known_hook} CALLED" in out


@parametrize_with_commands
@pytest.mark.parametrize("option", [":all", ":pre,:post"])
def test_skip_all_option_from_signal(
    hooked_project, invoke, capfd, specs: HookSpecs, option: str
):
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
def test_skip_pre_post_option_from_signal(
    hooked_project, invoke, capfd, specs: HookSpecs, prefix: str
):
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
