import json
import os
import subprocess
import textwrap

import pytest

from pdm.cli.actions import PEP582_PATH
from pdm.utils import cd, temp_environ


def test_pep582_not_loading_site_packages(project, invoke, capfd):
    with cd(project.root):
        invoke(["install"], obj=project)
        invoke(
            ["run", "python", "-c", "import sys,json;print(json.dumps(sys.path))"],
            obj=project,
        )
    sys_path = json.loads(capfd.readouterr()[0])
    assert not any("site-packages" in p for p in sys_path)
    assert str(project.environment.packages_path / "lib") in sys_path


@pytest.mark.pypi
def test_pep582_launcher_for_python_interpreter(project, invoke):
    project.tool_settings["python_requires"] = ">=3.6"
    project.write_pyproject()
    project.root.joinpath("main.py").write_text(
        "import requests\nprint(requests.__version__)\n"
    )
    invoke(["add", "requests==2.24.0"], obj=project)
    env = os.environ.copy()
    env.update({"PYTHONPATH": PEP582_PATH})
    output = subprocess.check_output(
        [project.environment.python_executable, str(project.root.joinpath("main.py"))],
        env=env,
    )
    assert output.decode().strip() == "2.24.0"


def test_pep582_launcher_with_system_site_packages(project, invoke):
    with cd(project.root):
        invoke(["install"], obj=project)
        result = invoke(["run", "python", "-c", "import resolvelib"], obj=project)
        assert result.exit_code != 0

        result = invoke(["run", "-s", "python", "-c", "import resolvelib"], obj=project)
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


def test_run_shell_script(project, invoke):
    project.tool_settings["scripts"] = {
        "test_script": {"shell": "echo hello > output.txt"}
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


def test_run_expand_env_vars(project, invoke, capfd):
    (project.root / "test_script.py").write_text("import os; print(os.getenv('FOO'))")
    project.tool_settings["scripts"] = {
        "test_cmd": 'python -c "foo, bar = 0, 1;print($FOO)"',
        "test_cmd_no_expand": "python -c 'print($FOO)'",
        "test_script": "python test_script.py",
        "test_shell": {"shell": "echo $FOO"},
    }
    project.write_pyproject()
    capfd.readouterr()
    with cd(project.root), temp_environ():
        os.environ["FOO"] = "bar"
        invoke(["run", "test_cmd"], obj=project)
        assert capfd.readouterr()[0].strip() == "1"

        result = invoke(["run", "test_cmd_no_expand"], obj=project)
        assert result.exit_code == 1

        invoke(["run", "test_script"], obj=project)
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
    (project.root / "test_script.py").write_text("import os; print(os.getenv('FOO'))")
    project.tool_settings["scripts"] = {
        "test_script": {"cmd": "python test_script.py", "env_file": ".env"}
    }
    project.write_pyproject()
    (project.root / ".env").write_text("FOO=bar")
    capfd.readouterr()
    with cd(project.root):
        invoke(["run", "test_script"], obj=project)
        assert capfd.readouterr()[0].strip() == "bar"


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
        "test_cmd": "flask db upgrade",
        "test_script": {"call": "test_script:main", "help": "call a python function"},
        "test_shell": {"shell": "echo $FOO", "help": "shell command"},
    }
    project.write_pyproject()
    result = invoke(["run", "--list"], obj=project)
    result_lines = result.output.splitlines()[2:]
    assert result_lines[0].strip() == "test_cmd    cmd   flask db upgrade"
    assert (
        result_lines[1].strip()
        == "test_script call  test_script:main call a python function"
    )
    assert result_lines[2].strip() == "test_shell  shell echo $FOO        shell command"
