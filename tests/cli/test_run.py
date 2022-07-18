import json
import os
import subprocess
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pdm import termui
from pdm.cli import actions
from pdm.cli.actions import PEP582_PATH
from pdm.utils import cd


@pytest.fixture
def _args(project):
    (project.root / "args.py").write_text(
        textwrap.dedent(
            """
            import os
            import sys
            name = sys.argv[1]
            args = ", ".join(sys.argv[2:])
            print(f"{name} CALLED with {args}" if args else f"{name} CALLED")
            """
        )
    )


def test_pep582_launcher_for_python_interpreter(project, local_finder, invoke):
    project.root.joinpath("main.py").write_text(
        "import first;print(first.first([0, False, 1, 2]))\n"
    )
    result = invoke(["add", "first"], obj=project)
    assert result.exit_code == 0, result.stderr
    env = os.environ.copy()
    env.update({"PYTHONPATH": PEP582_PATH})
    output = subprocess.check_output(
        [str(project.python.executable), str(project.root.joinpath("main.py"))],
        env=env,
    )
    assert output.decode().strip() == "1"


def test_auto_isolate_site_packages(project, invoke):
    env = os.environ.copy()
    env.update({"PYTHONPATH": PEP582_PATH})
    proc = subprocess.run(
        [str(project.python.executable), "-c", "import sys;print(sys.path, sep='\\n')"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(project.root),
        check=True,
    )
    assert any("site-packages" in path for path in proc.stdout.splitlines())

    result = invoke(
        ["run", "python", "-c", "import sys;print(sys.path, sep='\\n')"],
        obj=project,
        strict=True,
    )
    assert not any("site-packages" in path for path in result.stdout.splitlines())


def test_run_with_site_packages(project, invoke):
    project.tool_settings["scripts"] = {
        "foo": {
            "cmd": ["python", "-c", "import sys;print(sys.path, sep='\\n')"],
            "site_packages": True,
        }
    }
    project.write_pyproject()
    result = invoke(
        [
            "run",
            "--site-packages",
            "python",
            "-c",
            "import sys;print(sys.path, sep='\\n')",
        ],
        obj=project,
    )
    assert result.exit_code == 0
    result = invoke(["run", "foo"], obj=project)
    assert result.exit_code == 0


def test_run_command_not_found(invoke):
    result = invoke(["run", "foobar"])
    assert "Command 'foobar' is not found on your PATH." in result.stderr
    assert result.exit_code == 1


def test_run_pass_exit_code(invoke):
    result = invoke(["run", "python", "-c", "1/0"])
    assert result.exit_code == 1


def test_run_cmd_script(project, invoke):
    project.tool_settings["scripts"] = {"test_script": "python -V"}
    project.write_pyproject()
    result = invoke(["run", "test_script"], obj=project)
    assert result.exit_code == 0


def test_run_cmd_script_with_array(project, invoke):
    project.tool_settings["scripts"] = {
        "test_script": ["python", "-c", "import sys; sys.exit(22)"]
    }
    project.write_pyproject()
    result = invoke(["run", "test_script"], obj=project)
    assert result.exit_code == 22


def test_run_script_pass_project_root(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "test_script": [
            "python",
            "-c",
            "import os;print(os.getenv('PDM_PROJECT_ROOT'))",
        ]
    }
    project.write_pyproject()
    capfd.readouterr()
    result = invoke(["run", "test_script"], obj=project)
    assert result.exit_code == 0
    out, _ = capfd.readouterr()
    assert Path(out.strip()) == project.root


def test_run_shell_script(project, invoke):
    project.tool_settings["scripts"] = {
        "test_script": {
            "shell": "echo hello > output.txt",
            "help": "test it won't fail",
        }
    }
    project.write_pyproject()
    with cd(project.root):
        result = invoke(["run", "test_script"], obj=project)
    assert result.exit_code == 0
    assert (project.root / "output.txt").read_text().strip() == "hello"


def test_run_call_script(project, invoke):
    (project.root / "test_script.py").write_text(
        textwrap.dedent(
            """
            import argparse
            import sys

            def main(argv=None):
                parser = argparse.ArgumentParser()
                parser.add_argument("-c", "--code", type=int)
                args = parser.parse_args(argv)
                sys.exit(args.code)
            """
        )
    )
    project.tool_settings["scripts"] = {
        "test_script": {"call": "test_script:main"},
        "test_script_with_args": {"call": "test_script:main(['-c', '9'])"},
    }
    project.write_pyproject()
    with cd(project.root):
        result = invoke(["run", "test_script", "-c", "8"], obj=project)
        assert result.exit_code == 8

        result = invoke(["run", "test_script_with_args"], obj=project)
        assert result.exit_code == 9


def test_run_script_with_extra_args(project, invoke, capfd):
    (project.root / "test_script.py").write_text(
        textwrap.dedent(
            """
            import sys
            print(*sys.argv[1:], sep='\\n')
            """
        )
    )
    project.tool_settings["scripts"] = {"test_script": "python test_script.py"}
    project.write_pyproject()
    with cd(project.root):
        invoke(["run", "test_script", "-a", "-b", "-c"], obj=project)
    out, _ = capfd.readouterr()
    assert out.splitlines()[-3:] == ["-a", "-b", "-c"]


def test_run_expand_env_vars(project, invoke, capfd, monkeypatch):
    (project.root / "test_script.py").write_text("import os; print(os.getenv('FOO'))")
    project.tool_settings["scripts"] = {
        "test_cmd": 'python -c "foo, bar = 0, 1;print($FOO)"',
        "test_cmd_no_expand": "python -c 'print($FOO)'",
        "test_script": "python test_script.py",
        "test_cmd_array": ["python", "test_script.py"],
        "test_shell": {"shell": "echo $FOO"},
    }
    project.write_pyproject()
    capfd.readouterr()
    with cd(project.root):
        monkeypatch.setenv("FOO", "bar")
        invoke(["run", "test_cmd"], obj=project)
        assert capfd.readouterr()[0].strip() == "1"

        result = invoke(["run", "test_cmd_no_expand"], obj=project)
        assert result.exit_code == 1

        invoke(["run", "test_script"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar"

        invoke(["run", "test_cmd_array"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar"

        invoke(["run", "test_shell"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar"


def test_run_script_with_env_defined(project, invoke, capfd):
    (project.root / "test_script.py").write_text("import os; print(os.getenv('FOO'))")
    project.tool_settings["scripts"] = {
        "test_script": {"cmd": "python test_script.py", "env": {"FOO": "bar"}}
    }
    project.write_pyproject()
    capfd.readouterr()
    with cd(project.root):
        invoke(["run", "test_script"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar"


def test_run_script_with_dotenv_file(project, invoke, capfd):
    (project.root / "test_script.py").write_text(
        "import os; print(os.getenv('FOO'), os.getenv('BAR'))"
    )
    project.tool_settings["scripts"] = {
        "_": {"env": {"BAR": "foo"}},
        "test_script": {"cmd": "python test_script.py", "env_file": ".env"},
    }
    project.write_pyproject()
    (project.root / ".env").write_text("FOO=bar\nBAR=override")
    capfd.readouterr()
    with cd(project.root):
        invoke(["run", "test_script"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar foo"


def test_run_script_override_global_env(project, invoke, capfd):
    (project.root / "test_script.py").write_text("import os; print(os.getenv('FOO'))")
    project.tool_settings["scripts"] = {
        "_": {"env": {"FOO": "bar"}},
        "test_env": {"cmd": "python test_script.py"},
        "test_env_override": {"cmd": "python test_script.py", "env": {"FOO": "foobar"}},
    }
    project.write_pyproject()
    capfd.readouterr()
    with cd(project.root):
        invoke(["run", "test_env"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar"
        invoke(["run", "test_env_override"], obj=project)
        assert capfd.readouterr()[0].strip() == "foobar"


def test_run_show_list_of_scripts(project, invoke):
    project.tool_settings["scripts"] = {
        "test_composite": {"composite": ["test_cmd", "test_script", "test_shell"]},
        "test_cmd": "flask db upgrade",
        "test_multi": """\
            I am a multilines
            command
        """,
        "test_script": {"call": "test_script:main", "help": "call a python function"},
        "test_shell": {"shell": "echo $FOO", "help": "shell command"},
    }
    project.write_pyproject()
    result = invoke(["run", "--list"], obj=project)
    result_lines = result.output.splitlines()[3:]
    assert (
        result_lines[0][1:-1].strip() == "test_cmd       │ cmd       │ flask db upgrade"
    )
    sep = termui.Emoji.ARROW_SEPARATOR
    assert (
        result_lines[1][1:-1].strip()
        == f"test_composite │ composite │ test_cmd {sep} test_script {sep} test_shell"
    )
    assert (
        result_lines[2][1:-1].strip()
        == f"test_multi     │ cmd       │ I am a multilines{termui.Emoji.ELLIPSIS}"
    )
    assert (
        result_lines[3][1:-1].strip()
        == "test_script    │ call      │ call a python function"
    )
    assert result_lines[4][1:-1].strip() == "test_shell     │ shell     │ shell command"


def test_run_with_another_project_root(project, local_finder, invoke, capfd):
    project.meta["requires-python"] = ">=3.6"
    project.write_pyproject()
    invoke(["add", "first"], obj=project)
    with TemporaryDirectory(prefix="pytest-run-") as tmp_dir:
        Path(tmp_dir).joinpath("main.py").write_text(
            "import first;print(first.first([0, False, 1, 2]))\n"
        )
        capfd.readouterr()
        with cd(tmp_dir):
            ret = invoke(["run", "-p", str(project.root), "python", "main.py"])
            out, err = capfd.readouterr()
            assert ret.exit_code == 0, err
            assert out.strip() == "1"


def test_import_another_sitecustomize(project, invoke, capfd):
    project.meta["requires-python"] = ">=2.7"
    project.write_pyproject()
    # a script for checking another sitecustomize is imported
    project.root.joinpath("foo.py").write_text("import os;print(os.getenv('FOO'))")
    # ensure there have at least one sitecustomize can be imported
    # there may have more than one sitecustomize.py in sys.path
    project.root.joinpath("sitecustomize.py").write_text(
        "import os;os.environ['FOO'] = 'foo'"
    )
    env = os.environ.copy()
    paths = env.get("PYTHONPATH")
    this_path = str(project.root)
    new_paths = [this_path] if not paths else [this_path, paths]
    env["PYTHONPATH"] = os.pathsep.join(new_paths)
    project._environment = None
    capfd.readouterr()
    with cd(project.root):
        result = invoke(["run", "python", "foo.py"], env=env)
    assert result.exit_code == 0, result.stderr
    out, _ = capfd.readouterr()
    assert out.strip() == "foo"


def test_run_with_patched_sysconfig(project, invoke, capfd):
    project.root.joinpath("script.py").write_text(
        """\
import sysconfig
import json
print(json.dumps(sysconfig.get_paths()))
"""
    )
    capfd.readouterr()
    with cd(project.root):
        result = invoke(["run", "python", "script.py"], obj=project)
    assert result.exit_code == 0
    out = json.loads(capfd.readouterr()[0])
    assert "__pypackages__" in out["purelib"]


def test_run_composite(project, invoke, capfd, _echo):
    project.tool_settings["scripts"] = {
        "first": "python echo.py First",
        "second": "python echo.py Second",
        "test": {"composite": ["first", "second"]},
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "First CALLED" in out
    assert "Second CALLED" in out


def test_composite_stops_on_first_failure(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "first": {"cmd": ["python", "-c", "print('First CALLED')"]},
        "fail": "python -c 'raise Exception'",
        "second": "echo 'Second CALLED'",
        "test": {"composite": ["first", "fail", "second"]},
    }
    project.write_pyproject()
    capfd.readouterr()
    result = invoke(["run", "test"], obj=project)
    assert result.exit_code == 1
    out, _ = capfd.readouterr()
    assert "First CALLED" in out
    assert "Second CALLED" not in out


def test_composite_inherit_env(project, invoke, capfd, _echo):
    project.tool_settings["scripts"] = {
        "first": {
            "cmd": "python echo.py First VAR",
            "env": {"VAR": "42"},
        },
        "second": {
            "cmd": "python echo.py Second VAR",
            "env": {"VAR": "42"},
        },
        "test": {"composite": ["first", "second"], "env": {"VAR": "overriden"}},
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "First CALLED with VAR=overriden" in out
    assert "Second CALLED with VAR=overriden" in out


def test_composite_fail_on_first_missing_task(project, invoke, capfd, _echo):
    project.tool_settings["scripts"] = {
        "first": "python echo.py First",
        "second": "python echo.py Second",
        "test": {"composite": ["first", "fail", "second"]},
    }
    project.write_pyproject()
    capfd.readouterr()
    result = invoke(["run", "test"], obj=project)
    assert result.exit_code == 1
    out, _ = capfd.readouterr()
    assert "First CALLED" in out
    assert "Second CALLED" not in out


def test_composite_runs_all_hooks(project, invoke, capfd, _echo):
    project.tool_settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "python echo.py Pre-Test",
        "post_test": "python echo.py Post-Test",
        "first": "python echo.py First",
        "pre_first": "python echo.py Pre-First",
        "second": "python echo.py Second",
        "post_second": "python echo.py Post-Second",
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


def test_composite_pass_parameters_to_subtasks(project, invoke, capfd, _args):
    project.tool_settings["scripts"] = {
        "test": {"composite": ["first", "second"]},
        "pre_test": "python args.py Pre-Test",
        "post_test": "python args.py Post-Test",
        "first": "python args.py First",
        "pre_first": "python args.py Pre-First",
        "second": "python args.py Second",
        "post_second": "python args.py Post-Second",
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test", "param=value"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Test CALLED" in out
    assert "Pre-First CALLED" in out
    assert "First CALLED with param=value" in out
    assert "Second CALLED with param=value" in out
    assert "Post-Second CALLED" in out
    assert "Post-Test CALLED" in out


def test_composite_can_pass_parameters(project, invoke, capfd, _args):
    project.tool_settings["scripts"] = {
        "test": {"composite": ["first param=first", "second param=second"]},
        "pre_test": "python args.py Pre-Test",
        "post_test": "python args.py Post-Test",
        "first": "python args.py First",
        "pre_first": "python args.py Pre-First",
        "second": "python args.py Second",
        "post_second": "python args.py Post-Second",
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Test CALLED" in out
    assert "Pre-First CALLED" in out
    assert "First CALLED with param=first" in out
    assert "Second CALLED with param=second" in out
    assert "Post-Second CALLED" in out
    assert "Post-Test CALLED" in out


def test_composite_hooks_inherit_env(project, invoke, capfd, _echo):
    project.tool_settings["scripts"] = {
        "pre_task": {"cmd": "python echo.py Pre-Task VAR", "env": {"VAR": "42"}},
        "task": "python echo.py Task",
        "post_task": {"cmd": "python echo.py Post-Task VAR", "env": {"VAR": "42"}},
        "test": {"composite": ["task"], "env": {"VAR": "overriden"}},
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Task CALLED with VAR=overriden" in out
    assert "Task CALLED" in out
    assert "Post-Task CALLED with VAR=overriden" in out


def test_composite_inherit_env_in_cascade(project, invoke, capfd, _echo):
    project.tool_settings["scripts"] = {
        "_": {"env": {"FOO": "BAR", "TIK": "TOK"}},
        "pre_task": {
            "cmd": "python echo.py Pre-Task VAR FOO TIK",
            "env": {"VAR": "42", "FOO": "foobar"},
        },
        "task": {
            "cmd": "python echo.py Task VAR FOO TIK",
            "env": {"VAR": "42", "FOO": "foobar"},
        },
        "post_task": {
            "cmd": "python echo.py Post-Task VAR FOO TIK",
            "env": {"VAR": "42", "FOO": "foobar"},
        },
        "test": {"composite": ["task"], "env": {"VAR": "overriden"}},
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Task CALLED with VAR=overriden FOO=foobar TIK=TOK" in out
    assert "Task CALLED with VAR=overriden FOO=foobar TIK=TOK" in out
    assert "Post-Task CALLED with VAR=overriden FOO=foobar TIK=TOK" in out


def test_composite_inherit_dotfile(project, invoke, capfd, _echo):
    (project.root / ".env").write_text("VAR=42")
    (project.root / "override.env").write_text("VAR=overriden")
    project.tool_settings["scripts"] = {
        "pre_task": {"cmd": "python echo.py Pre-Task VAR", "env_file": ".env"},
        "task": {"cmd": "python echo.py Task VAR", "env_file": ".env"},
        "post_task": {"cmd": "python echo.py Post-Task VAR", "env_file": ".env"},
        "test": {"composite": ["task"], "env_file": "override.env"},
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Pre-Task CALLED with VAR=overriden" in out
    assert "Task CALLED with VAR=overriden" in out
    assert "Post-Task CALLED with VAR=overriden" in out


def test_composite_can_have_commands(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "task": {"cmd": ["python", "-c", 'print("Task CALLED")']},
        "test": {"composite": ["task", "python -c 'print(\"Command CALLED\")'"]},
    }
    project.write_pyproject()
    capfd.readouterr()
    invoke(["run", "-v", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "Task CALLED" in out
    assert "Command CALLED" in out


def test_run_shortcut(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "test": "echo 'Everything is fine'",
    }
    project.write_pyproject()
    capfd.readouterr()
    result = invoke(["test"], obj=project, strict=True)
    assert result.exit_code == 0
    out, _ = capfd.readouterr()
    assert "Everything is fine" in out


def test_run_shortcuts_dont_override_commands(project, invoke, capfd, mocker):
    do_lock = mocker.patch.object(actions, "do_lock")
    do_sync = mocker.patch.object(actions, "do_sync")
    project.tool_settings["scripts"] = {
        "install": "echo 'Should not run'",
    }
    project.write_pyproject()
    capfd.readouterr()
    result = invoke(["install"], obj=project, strict=True)
    assert result.exit_code == 0
    out, _ = capfd.readouterr()
    assert "Should not run" not in out
    do_lock.assert_called_once()
    do_sync.assert_called_once()


def test_run_shortcut_fail_with_usage_if_script_not_found(project, invoke):
    result = invoke(["whatever"], obj=project)
    assert result.exit_code != 0
    assert "Command unknown: whatever" in result.stderr
    assert "Usage" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        pytest.param([], id="no args"),
        pytest.param(["-ko"], id="unknown param"),
        pytest.param(["pip", "--version"], id="not an user script"),
    ],
)
def test_empty_positionnal_args_still_display_usage(project, invoke, args):
    result = invoke(args, obj=project)
    assert result.exit_code != 0
    assert "Usage" in result.stderr
