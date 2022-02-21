import json
import os
import subprocess
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory

from pdm.cli.actions import PEP582_PATH
from pdm.utils import cd


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
        [str(project.python.executable), "-c", "import click"], env=env
    )
    assert proc.returncode == 0

    result = invoke(["run", "python", "-c", "import click"], obj=project)
    if os.name != "nt":  # os.environ handling seems problematic on Windows
        assert result.exit_code != 0


def test_run_with_site_packages(project, invoke):
    project.tool_settings["scripts"] = {
        "foo": {"cmd": "python -c 'import click'", "site_packages": True}
    }
    project.write_pyproject()
    result = invoke(
        ["run", "--site-packages", "python", "-c", "import click"], obj=project
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


def test_run_expand_env_vars(project, invoke, capfd):
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
        os.environ["FOO"] = "bar"
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
            assert ret.exit_code == 0
            out, _ = capfd.readouterr()
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


def test_pre_and_post_hooks(project, invoke, capfd):
    project.tool_settings["scripts"] = {
        "pre_install": "python -c \"print('PRE INSTALL CALLED')\"",
        "post_install": "python -c \"print('POST INSTALL CALLED')\"",
    }
    project.write_pyproject()
    invoke(["install"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "PRE INSTALL CALLED" in out
    assert "POST INSTALL CALLED" in out


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
    invoke(["run", "test"], strict=True, obj=project)
    out, _ = capfd.readouterr()
    assert "PRE test CALLED" in out
    assert "IN test CALLED" in out
    assert "POST test CALLED" in out
