import sys
from pathlib import Path

import pytest


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


def test_fix_project_plugins(project, pdm):
    old_plugin_dir = project.root / ".pdm-plugins"
    old_plugin_dir.mkdir()
    old_plugin_dir.joinpath("plugin.py").write_text("value = 1\n")

    pdm(["fix", "project-plugins"], obj=project, strict=True)

    assert not old_plugin_dir.exists()
    assert project.project_plugins_dir.joinpath("plugin.py").read_text() == "value = 1\n"


def test_fix_project_plugins_replaces_existing_cache_dir(project, pdm):
    old_plugin_dir = project.root / ".pdm-plugins"
    old_plugin_dir.mkdir()
    old_plugin_dir.joinpath("plugin.py").write_text("value = 1\n")
    project.project_plugins_dir.mkdir(parents=True)
    project.project_plugins_dir.joinpath("stale.py").write_text("value = 0\n")

    pdm(["fix", "project-plugins"], obj=project, strict=True)

    assert not old_plugin_dir.exists()
    assert not project.project_plugins_dir.joinpath("stale.py").exists()
    assert project.project_plugins_dir.joinpath("plugin.py").read_text() == "value = 1\n"


def _make_symlink(path: Path, target: Path) -> None:
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError) as e:  # pragma: no cover
        pytest.skip(f"symlink is not supported: {e}")


def test_fix_project_config_refuses_symlinked_pdm_python(project, pdm, tmp_path):
    """A repo-planted `.pdm-python` symlink must not redirect the write out of the project."""
    project._saved_python = None
    old_config = project.root / ".pdm.toml"
    old_config.write_text('[python]\nuse_pyenv = false\npath = "ATTACKER_CONTROLLED_CONTENT"\n')

    target = tmp_path / "outside" / "victim-file"
    target.parent.mkdir(parents=True)
    symlink_path = project.root / ".pdm-python"
    _make_symlink(symlink_path, target)
    assert symlink_path.is_symlink()
    assert not symlink_path.exists()  # dangling, so the vulnerable `exists()` check passed

    result = pdm(["fix", "project-config"], obj=project)

    assert result.exit_code != 0
    assert not target.exists(), "the write followed the symlink out of the project"
    assert symlink_path.is_symlink()
    assert old_config.exists(), "`.pdm.toml` must survive so the fix can be retried"


def test_fix_project_config_refuses_symlinked_gitignore(project, pdm, tmp_path):
    """`_fix_gitignore()` writes `.gitignore` too, so it needs the same guard."""
    project._saved_python = None
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')

    target = tmp_path / "outside" / "gitignore"
    target.parent.mkdir(parents=True)
    target.write_text(".pdm.toml\n")
    symlink_path = project.root / ".gitignore"
    _make_symlink(symlink_path, target)

    result = pdm(["fix", "project-config"], obj=project)

    assert result.exit_code != 0
    assert target.read_text() == ".pdm.toml\n", "the write followed the symlink out of the project"
    assert symlink_path.is_symlink()


def test_fix_project_config_symlink_refusal_keeps_migration_intact(project, pdm, tmp_path):
    """A refused `.gitignore` write must not leave `.pdm.toml` already deleted."""
    project._saved_python = None
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')

    target = tmp_path / "outside" / "gitignore"
    target.parent.mkdir(parents=True)
    target.write_text(".pdm.toml\n")
    _make_symlink(project.root / ".gitignore", target)

    result = pdm(["fix", "project-config"], obj=project)

    assert result.exit_code != 0
    assert old_config.exists(), "`.pdm.toml` was deleted before the rejected write"
    # `.pdm-python` may already be created by then; that is idempotent and the
    # retry will skip it, so only the survival of `.pdm.toml` matters here.


def test_fix_project_config_keeps_pdm_toml_ignored_after_refusal(project, pdm, tmp_path):
    """A refused `.pdm-python` write must not leave `.pdm.toml` no longer ignored.

    `.gitignore` is rewritten by the same fixer, so rewriting it before the
    `.pdm-python` write can fail would surface the legacy config as an untracked file.
    """
    project._saved_python = None
    old_config = project.root / ".pdm.toml"
    old_config.write_text(f'[python]\nuse_pyenv = false\npath = "{Path(sys.executable).as_posix()}"\n')
    gitignore = project.root / ".gitignore"
    gitignore.write_text(".pdm.toml\n")

    target = tmp_path / "outside" / "victim-file"
    target.parent.mkdir(parents=True)
    _make_symlink(project.root / ".pdm-python", target)

    result = pdm(["fix", "project-config"], obj=project)

    assert result.exit_code != 0
    assert old_config.exists()
    assert gitignore.read_text() == ".pdm.toml\n", "`.pdm.toml` was left un-ignored after the refusal"
