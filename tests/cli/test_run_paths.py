import pytest

from pdm.utils import cd


@pytest.mark.parametrize("inline_metadata", [False, True])
@pytest.mark.parametrize(
    "script",
    [
        pytest.param("task.py", id="command-string"),
        pytest.param(["task.py"], id="command-array"),
        pytest.param({"composite": ["task.py"]}, id="composite"),
    ],
)
def test_named_python_script_from_subdirectory(project, pdm, capfd, script, inline_metadata):
    metadata = '# /// script\n# requires-python = ">=3.9"\n# ///\n' if inline_metadata else ""
    (project.root / "task.py").write_text(metadata + 'print("from project root")\n')
    caller = project.root / "sub dir"
    caller.mkdir()
    project.pyproject.settings["scripts"] = {"task": script}
    project.pyproject.write()
    capfd.readouterr()

    with cd(caller):
        result = pdm(["run", "task"], obj=project)

    assert result.exit_code == 0, result.stderr
    assert capfd.readouterr()[0].strip() == "from project root"


def test_direct_python_script_keeps_caller_working_directory(project, pdm, capfd):
    (project.root / "task.py").write_text('print("from project root")\n')
    caller = project.root / "sub dir"
    caller.mkdir()
    (caller / "task.py").write_text('print("from caller directory")\n')
    capfd.readouterr()

    with cd(caller):
        result = pdm(["run", "task.py"], obj=project)

    assert result.exit_code == 0, result.stderr
    assert capfd.readouterr()[0].strip() == "from caller directory"


def test_absolute_named_python_script_from_subdirectory(project, pdm, capfd):
    script = project.root / "task.py"
    script.write_text('print("absolute script")\n')
    caller = project.root / "sub dir"
    caller.mkdir()
    project.pyproject.settings["scripts"] = {"task": [script.as_posix()]}
    project.pyproject.write()
    capfd.readouterr()

    with cd(caller):
        result = pdm(["run", "task"], obj=project)

    assert result.exit_code == 0, result.stderr
    assert capfd.readouterr()[0].strip() == "absolute script"
