import sys
from pathlib import Path


def test_fix_non_existing_problem(project, pdm):
    result = pdm(["fix", "non-existing"], obj=project)
    assert result.exit_code == 1


def test_fix_individual_problem(project, pdm):
    project._saved_python = None
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')
    pdm(["fix", "project-config"], obj=project, strict=True)
    assert not old_config.exists()


def test_show_fix_command(project, pdm):
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')
    result = pdm(["info"], obj=project)
    assert "Run pdm fix to fix all" in result.stderr

    result = pdm(["fix", "-h"], obj=project)
    assert "Run pdm fix to fix all" not in result.stderr


def test_show_fix_command_global_project(core, pdm, project_no_init):
    project = core.create_project(None, True, project_no_init.global_config.config_file)
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')
    result = pdm(["info"], obj=project)
    assert "Run pdm fix -g to fix all" in result.stderr

    result = pdm(["fix", "-h"], obj=project)
    assert "Run pdm fix -g to fix all" not in result.stderr


def test_fix_project_config(project, pdm):
    project._saved_python = None
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')
    assert project.project_config["python.use_pyenv"] is False
    assert project._saved_python == Path(sys.executable).as_posix()
    pdm(["fix"], obj=project, strict=True)
    assert not old_config.exists()
    assert project.root.joinpath("pdm.toml").read_text() == "[python]\nuse_pyenv = false\n"
    assert project.root.joinpath(".pdm-python").read_text().strip() == Path(sys.executable).as_posix()
