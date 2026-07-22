from datetime import datetime
from pathlib import Path
from unittest.mock import ANY

import pytest
from unearth import Link

from pdm.cli import actions
from pdm.exceptions import PdmUsageError
from pdm.models.requirements import parse_requirement
from pdm.models.specifiers import PySpecSet
from pdm.project.lockfile import FLAG_CROSS_PLATFORM
from pdm.project.lockfile.base import Compatibility, LockInputsState
from pdm.project.lockfile.freshness import lock_inputs_match
from pdm.signals import pre_lock
from pdm.utils import parse_version
from tests import FIXTURES


def test_lock_command(project, pdm, mocker):
    m = mocker.patch.object(actions, "do_lock")
    pdm(["lock"], obj=project)
    m.assert_called_with(
        project,
        refresh=False,
        groups=["default"],
        hooks=ANY,
        strategy_change=None,
        strategy="all",
        append=False,
        env_spec=None,
    )


class FakeResolver:
    def __init__(self, *args, **kwargs):
        pass

    def resolve(self):
        return [], set()


def make_workspace_member(project, core):
    project.pyproject.settings["workspace"] = {"members": ["packages/*"]}
    project.pyproject.write()
    member_path = project.root / "packages" / "foo"
    member_path.mkdir(parents=True)
    member_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )
    return core.create_project(member_path, global_config=project.global_config.config_file.as_posix())


def make_workspace_members(project, core, members):
    project.pyproject.settings["workspace"] = {"members": ["packages/*"]}
    project.pyproject.write()
    for name, dependencies in members.items():
        member_path = project.root / "packages" / name
        member_path.mkdir(parents=True)
        dependency_lines = ", ".join(f'"{dependency}"' for dependency in dependencies)
        member_path.joinpath("pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "0.1.0"\ndependencies = [{dependency_lines}]\n',
            encoding="utf-8",
        )
    return core.create_project(project.root, global_config=project.global_config.config_file.as_posix())


def capture_pre_lock_requirements():
    captured = {}

    def capture_requirements(sender, requirements, **kwargs):
        captured["requirements"] = requirements

    pre_lock.connect(capture_requirements, weak=False)
    return captured, capture_requirements


def enable_lock_inputs(project):
    project.pyproject.open_for_write()
    project.pyproject.settings.setdefault("resolution", {})["lock_inputs"] = True
    project.pyproject.write(show_message=False)


def test_do_lock_adds_workspace_members_to_explicit_member_requirements(project, core, mocker):
    member_project = make_workspace_member(project, core)
    mocker.patch.object(member_project, "get_resolver", return_value=FakeResolver)
    captured, receiver = capture_pre_lock_requirements()

    try:
        actions.do_lock(
            member_project,
            requirements=[parse_requirement("requests")],
            groups=["default"],
            dry_run=True,
        )
    finally:
        pre_lock.disconnect(receiver)

    requirements = captured["requirements"]
    assert [req.identify() for req in requirements] == ["requests", "foo"]
    assert requirements[-1].editable
    assert requirements[-1].str_path == "./packages/foo"
    assert member_project.lockfile._path == project.root / "pdm.lock"


def test_do_lock_adds_workspace_members_to_member_resolved_requirements(project, core, mocker):
    member_project = make_workspace_member(project, core)
    mocker.patch.object(member_project, "get_resolver", return_value=FakeResolver)
    captured, receiver = capture_pre_lock_requirements()

    try:
        actions.do_lock(member_project, groups=["default"], dry_run=True)
    finally:
        pre_lock.disconnect(receiver)

    requirements = captured["requirements"]
    assert [req.identify() for req in requirements] == ["requests", "foo"]
    assert requirements[-1].editable
    assert requirements[-1].str_path == "./packages/foo"
    assert member_project.lockfile._path == project.root / "pdm.lock"


def test_lock_workspace_members_depend_on_each_other(project, core, repository):
    workspace_project = make_workspace_members(project, core, {"foo": ["bar"], "bar": []})

    actions.do_lock(workspace_project)

    locked_candidates = workspace_project.get_locked_repository().candidates
    assert locked_candidates["foo"].req.editable
    assert locked_candidates["bar"].req.editable
    assert locked_candidates["foo"].req.str_path == "./packages/foo"
    assert locked_candidates["bar"].req.str_path == "./packages/bar"


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_hash_tracks_workspace_member_pyproject(project, core, lock_format):
    project.project_config["lock.format"] = lock_format
    workspace_project = make_workspace_members(project, core, {"foo": []})

    actions.do_lock(workspace_project)

    assert workspace_project.is_lockfile_hash_match()
    assert workspace_project.is_lockfile_fresh()

    member_pyproject = workspace_project.root / "packages" / "foo" / "pyproject.toml"
    member_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )
    fresh_project = core.create_project(
        workspace_project.root, global_config=workspace_project.global_config.config_file.as_posix()
    )
    fresh_member_project = core.create_project(
        member_pyproject.parent, global_config=workspace_project.global_config.config_file.as_posix()
    )

    assert not fresh_project.is_lockfile_hash_match()
    assert not fresh_member_project.is_lockfile_hash_match()
    assert not fresh_project.is_lockfile_fresh()
    assert not fresh_member_project.is_lockfile_fresh()

    actions.do_lock(fresh_project)

    assert fresh_project.is_lockfile_hash_match()


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_inputs_track_workspace_member_version(project, core, pdm, lock_format):
    project.project_config["lock.format"] = lock_format
    workspace_project = make_workspace_members(project, core, {"foo": []})
    enable_lock_inputs(workspace_project)
    actions.do_lock(workspace_project)

    member_pyproject = workspace_project.root / "packages" / "foo" / "pyproject.toml"
    member_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.2.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    fresh_project = core.create_project(
        workspace_project.root, global_config=workspace_project.global_config.config_file.as_posix()
    )

    assert not fresh_project.is_lockfile_hash_match()
    assert not fresh_project.is_lockfile_fresh()
    result = pdm(["lock", "--check"], obj=fresh_project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
@pytest.mark.parametrize("dependency_kind", ["direct-url", "editable-url"])
def test_lock_inputs_track_local_directory_dependencies(project, lock_format, dependency_kind):
    project.project_config["lock.format"] = lock_format
    local_path = project.root / "local" / "foo"
    local_path.mkdir(parents=True)
    local_pyproject = local_path / "pyproject.toml"
    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    dependency = "file:///${PROJECT_ROOT}/local/foo"
    if dependency_kind == "direct-url":
        project.add_dependencies([f"foo @ {dependency}"])
    else:
        project.add_dependencies([f"-e {dependency}"], to_group="dev", dev=True)
    enable_lock_inputs(project)
    actions.do_lock(project)
    project.lockfile.reload()

    assert project.is_lockfile_fresh()
    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )

    assert not project.is_lockfile_hash_match()
    assert not project.is_lockfile_fresh()


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_validates_local_project_specifiers(project, lock_format):
    project.project_config["lock.format"] = lock_format
    local_path = project.root / "local" / "foo"
    local_path.mkdir(parents=True)
    local_pyproject = local_path / "pyproject.toml"
    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )
    project.add_dependencies(["foo @ file:///${PROJECT_ROOT}/local/foo"])
    enable_lock_inputs(project)
    actions.do_lock(project)
    project.lockfile.reload()

    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests>=2"]\n',
        encoding="utf-8",
    )
    assert project.is_lockfile_fresh()

    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests<2"]\n',
        encoding="utf-8",
    )
    assert not project.is_lockfile_fresh()


def test_lock_inputs_track_relative_editable_directory(project):
    local_path = project.root / "local" / "foo"
    local_path.mkdir(parents=True)
    local_pyproject = local_path / "pyproject.toml"
    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    project.pyproject.settings["dev-dependencies"] = {"dev": ["-e ./local/foo"]}
    project.pyproject.write(show_message=False)
    previous_inputs = project.lock_inputs()

    local_pyproject.write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )

    assert project.lock_inputs() != previous_inputs


def test_dynamic_local_directory_is_volatile(project):
    local_path = project.root / "local" / "foo"
    local_path.mkdir(parents=True)
    local_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "foo"\ndynamic = ["version", "dependencies"]\n',
        encoding="utf-8",
    )
    project.add_dependencies(["foo @ file:///${PROJECT_ROOT}/local/foo"])
    lock_inputs = project.lock_inputs()

    assert not lock_inputs_match(project, lock_inputs)


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_inputs_track_local_file_content(project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    local_file = project.root / "demo-0.0.1-py2.py3-none-any.whl"
    local_file.write_bytes((FIXTURES / "artifacts" / "demo-0.0.1-py2.py3-none-any.whl").read_bytes())
    project.add_dependencies(["demo @ file:///${PROJECT_ROOT}/demo-0.0.1-py2.py3-none-any.whl"])
    enable_lock_inputs(project)
    actions.do_lock(project)
    project.lockfile.reload()

    assert project.is_lockfile_fresh()
    with local_file.open("ab") as file_handler:
        file_handler.write(b"changed")

    assert not project.is_lockfile_hash_match()
    assert not project.is_lockfile_fresh()


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_dependencies(project, lock_format):
    project.add_dependencies(["requests"])
    project.project_config["lock.format"] = lock_format
    actions.do_lock(project)
    assert project.lockfile.exists()
    assert project.lockfile._path.name == "pdm.lock" if lock_format == "pdm" else "pylock.toml"
    locked = project.get_locked_repository().candidates
    for package in ("requests", "idna", "chardet", "certifi"):
        assert package in locked


@pytest.mark.parametrize("args", [("-S", "static_urls"), ("--static-urls",)])
def test_lock_refresh(pdm, project, repository, args, core, mocker):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert not package.get("files")
    project.add_dependencies(["requests>=2.0"])
    url_hashes = {
        "http://example.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
        "http://example2.com/requests-2.19.1-py3-none-AMD64.whl": "sha256:abcdef123456",
        "http://example1.com/requests-2.19.1-py3-none-any.whl": "sha256:abcdef123456",
    }
    mocker.patch.object(
        core.repository_class,
        "get_hashes",
        side_effect=(
            lambda c: (
                [{"url": url, "file": Link(url).filename, "hash": hash} for url, hash in url_hashes.items()]
                if c.identify() == "requests"
                else []
            )
        ),
    )
    assert not project.is_lockfile_hash_match()
    result = pdm(["lock", "--refresh", "-v"], obj=project)
    assert result.exit_code == 0
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert package["files"] == [
        {"file": "requests-2.19.1-py3-none-AMD64.whl", "hash": "sha256:abcdef123456"},
        {"file": "requests-2.19.1-py3-none-any.whl", "hash": "sha256:abcdef123456"},
    ]
    assert project.is_lockfile_hash_match()
    result = pdm(["lock", "--refresh", *args, "-v"], obj=project)
    assert result.exit_code == 0
    package = next(p for p in project.lockfile["package"] if p["name"] == "requests")
    assert package["files"] == [{"url": url, "hash": hash} for url, hash in sorted(url_hashes.items())]


def test_lock_refresh_keep_consistent(pdm, project, repository):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()
    previous = project.lockfile._path.read_text()
    result = pdm(["lock", "--refresh"], obj=project)
    assert result.exit_code == 0
    assert project.lockfile._path.read_text() == previous


def test_pylock_refresh_preserves_dependency_group_markers(pdm, project, repository):
    project.project_config["lock.format"] = "pylock"
    project.add_dependencies(["requests"], to_group="dev", dev=True)
    result = pdm(["lock", "-G", "dev"], obj=project)
    assert result.exit_code == 0
    package = next(p for p in project.lockfile["packages"] if p["name"] == "requests")
    assert package["marker"] == '"dev" in dependency_groups'

    result = pdm(["lock", "--refresh"], obj=project)
    assert result.exit_code == 0
    package = next(p for p in project.lockfile["packages"] if p["name"] == "requests")
    assert package["marker"] == '"dev" in dependency_groups'


def test_lock_check_no_change_success(pdm, project, repository):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 0


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_uses_canonical_inputs(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests", "pytz"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    assert project.lockfile.lock_inputs == project.lock_inputs()
    assert project.lockfile.lock_inputs_state is LockInputsState.SUPPORTED
    if lock_format == "pdm":
        assert project.lockfile.file_version == str(project.lockfile.spec_version)
        assert "content_hash" not in project.lockfile._data["metadata"]
    else:
        assert "hashes" not in project.lockfile._data["tool"]["pdm"]
        assert "lock_inputs_version" not in project.lockfile._path.read_text(encoding="utf-8")
    project.pyproject.metadata["dependencies"] = ["pytz", "requests"]
    project.pyproject.write(show_message=False)
    project.lockfile.reload()

    assert not project.is_lockfile_hash_match()
    assert project.is_lockfile_fresh()
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 0


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_inputs_omit_named_specifiers(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests>=2"])
    enable_lock_inputs(project)

    pdm(["lock"], obj=project, strict=True)

    assert project.lockfile.lock_inputs["project"]["groups"]["default"] == ["requests"]


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_validates_only_locked_groups(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.pyproject.metadata["optional-dependencies"] = {"http": ["requests"]}
    enable_lock_inputs(project)

    pdm(["lock"], obj=project, strict=True)

    assert project.lockfile.groups == ["default"]
    assert "requests" not in project.get_locked_repository().candidates
    assert project.is_lockfile_fresh()
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 0


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_allows_compatible_specifier_change(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    project.add_dependencies(["requests>=2"])
    project.lockfile.reload()

    assert not project.is_lockfile_hash_match()
    assert project.is_lockfile_fresh()
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 0


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_rejects_incompatible_specifier_change(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    project.add_dependencies(["requests<2"])
    project.lockfile.reload()

    assert not project.is_lockfile_fresh()
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 1


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_always_validates_current_specifier(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests>=2"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    packages = project.lockfile._data["package"] if lock_format == "pdm" else project.lockfile._data["packages"]
    package = next(package for package in packages if package["name"] == "requests")
    package["version"] = "1.0.0"
    project.lockfile.write(show_message=False)
    project.lockfile.reload()

    assert project.lockfile.lock_inputs == project.lock_inputs()
    assert not project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_uses_effective_override_specifier(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.pyproject.settings["resolution"] = {
        "lock_inputs": True,
        "overrides": {"requests": "2.19.1"},
    }
    project.add_dependencies(["requests>=3"])

    pdm(["lock"], obj=project, strict=True)

    assert project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
@pytest.mark.parametrize("dependency_kind", ["direct", "override"])
@pytest.mark.parametrize("corruption", ["missing", "source"])
def test_lock_check_validates_effective_file_source(
    pdm,
    project,
    repository,
    lock_format,
    dependency_kind,
    corruption,
):
    project.project_config["lock.format"] = lock_format
    url = "http://fixtures.test/artifacts/demo-0.0.1-py2.py3-none-any.whl"
    if dependency_kind == "direct":
        project.add_dependencies([f"demo @ {url}"])
    else:
        project.pyproject.settings["resolution"] = {"overrides": {"demo": url}}
        project.add_dependencies(["demo"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    packages = project.lockfile._data["package"] if lock_format == "pdm" else project.lockfile._data["packages"]
    package = next(package for package in packages if package["name"] == "demo")
    if corruption == "missing":
        packages.remove(package)
    elif lock_format == "pdm":
        package["url"] = f"{url}?tampered=1"
    else:
        package["archive"]["url"] = f"{url}?tampered=1"
    project.lockfile.write(show_message=False)
    project.lockfile.reload()

    assert project.lockfile.lock_inputs == project.lock_inputs()
    assert not project.is_lockfile_fresh()


@pytest.mark.usefixtures("vcs")
@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_validates_vcs_source(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["demo @ git+https://github.com/test-root/demo.git@1234567890abcdef"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    assert project.is_lockfile_fresh()
    packages = project.lockfile._data["package"] if lock_format == "pdm" else project.lockfile._data["packages"]
    package = next(package for package in packages if package["name"] == "demo")
    if lock_format == "pdm":
        package["git"] = "https://github.com/test-root/demo-tampered.git"
    else:
        package["vcs"]["url"] = "https://github.com/test-root/demo-tampered.git"
    project.lockfile.write(show_message=False)
    project.lockfile.reload()

    assert project.lockfile.lock_inputs == project.lock_inputs()
    assert not project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_matches_specifiers_by_marker_context(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.pyproject.metadata["dependencies"] = [
        'django<2; sys_platform == "win32"',
        'django>=2; sys_platform != "win32"',
    ]
    project.pyproject.settings.setdefault("resolution", {})["lock_inputs"] = True
    project.pyproject.write(show_message=False)

    pdm(["lock", "--platform", "windows"], obj=project, strict=True)
    pdm(["lock", "--platform", "linux", "--append"], obj=project, strict=True)

    assert project.is_lockfile_fresh()
    project.pyproject.metadata["dependencies"][1] = 'django>=999; sys_platform != "win32"'
    project.pyproject.write(show_message=False)
    project.lockfile.reload()
    assert not project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_requires_candidate_coverage_for_all_targets(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    repository.add_candidate("forked", "1.0", "<3.11")
    repository.add_candidate("forked", "2.0", ">=3.11")
    project.add_dependencies(["forked"])
    enable_lock_inputs(project)

    pdm(["lock", "--python", ">=3.10,<3.11"], obj=project, strict=True)
    pdm(["lock", "--python", ">=3.12,<3.13", "--append"], obj=project, strict=True)

    packages = project.lockfile._data["package"] if lock_format == "pdm" else project.lockfile._data["packages"]
    candidates = [package for package in packages if package["name"] == "forked"]
    assert len(candidates) == 2
    assert project.is_lockfile_fresh()

    packages.remove(candidates[0])
    project.lockfile.write(show_message=False)
    project.lockfile.reload()

    assert project.lockfile.lock_inputs == project.lock_inputs()
    assert not project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_skips_excluded_named_dependency(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.pyproject.settings["resolution"] = {"excludes": ["requests"], "lock_inputs": True}
    local_path = project.root / "local" / "foo"
    local_path.mkdir(parents=True)
    local_path.joinpath("pyproject.toml").write_text(
        '[project]\nname = "foo"\nversion = "0.1.0"\ndependencies = ["requests>=999"]\n',
        encoding="utf-8",
    )
    project.add_dependencies(["foo @ file:///${PROJECT_ROOT}/local/foo"])

    pdm(["lock"], obj=project, strict=True)

    assert project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
@pytest.mark.parametrize("lock_inputs_setting", [None, False])
def test_lock_check_falls_back_to_legacy_hash(pdm, project, repository, lock_format, lock_inputs_setting):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    if lock_inputs_setting is not None:
        project.pyproject.open_for_write()
        project.pyproject.settings.setdefault("resolution", {})["lock_inputs"] = lock_inputs_setting
        project.pyproject.write(show_message=False)
    pdm(["lock"], obj=project, strict=True)

    assert project.lockfile.lock_inputs is None
    assert project.lockfile.lock_inputs_state is LockInputsState.LEGACY
    assert project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_inputs_setting_requires_regeneration(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    pdm(["lock"], obj=project, strict=True)

    enable_lock_inputs(project)
    project.lockfile.reload()

    assert not project.is_lockfile_hash_match()
    assert not project.is_lockfile_fresh()

    pdm(["lock"], obj=project, strict=True)

    assert project.lockfile.lock_inputs_state is LockInputsState.SUPPORTED
    assert project.lockfile.lock_inputs is not None
    assert "lock_inputs" not in project.lockfile.lock_inputs["project"]["resolution"]
    assert not project.is_lockfile_hash_match()
    assert project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_existing_lock_inputs_remain_enabled(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)

    project.pyproject.settings["resolution"].pop("lock_inputs")
    project.pyproject.write(show_message=False)
    project.lockfile.reload()

    assert not project.is_lockfile_hash_match()
    assert project.lock_inputs_enabled()
    assert project.is_lockfile_fresh()

    pdm(["lock"], obj=project, strict=True)

    assert project.lockfile.lock_inputs_state is LockInputsState.SUPPORTED
    assert project.lockfile.lock_inputs is not None
    assert not project.is_lockfile_hash_match()
    assert project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_version", ["", "4.5.0", "4.5.1", "4.5.2", "4.6.0"])
def test_pdmlock_uses_present_inputs_regardless_of_version(pdm, project, repository, lock_version):
    project.add_dependencies(["requests"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)
    project.lockfile._data["metadata"]["lock_version"] = lock_version
    project.pyproject.settings["resolution"].pop("lock_inputs")
    project.pyproject.write(show_message=False)

    assert project.lockfile.lock_inputs is not None
    assert project.lockfile.lock_inputs_state is LockInputsState.SUPPORTED
    assert not project.is_lockfile_hash_match()
    assert project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_lock_check_rejects_malformed_inputs(pdm, project, repository, lock_format):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)
    project.pyproject.settings["resolution"].pop("lock_inputs")
    project.pyproject.write(show_message=False)
    pdm(["lock"], obj=project, strict=True)
    if lock_format == "pdm":
        lock_inputs = project.lockfile._data["metadata"]["lock_inputs"]
    else:
        lock_inputs = project.lockfile._data["tool"]["pdm"]["lock_inputs"]
    lock_inputs["project"]["groups"]["default"] = [42]

    assert not project.is_lockfile_fresh()


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
@pytest.mark.parametrize("malformed_inputs", [{}, "invalid", datetime(2026, 1, 1)])
def test_lock_check_does_not_fallback_for_invalid_lock_inputs(pdm, project, repository, lock_format, malformed_inputs):
    project.project_config["lock.format"] = lock_format
    project.add_dependencies(["requests"])
    enable_lock_inputs(project)
    pdm(["lock"], obj=project, strict=True)
    project.pyproject.settings["resolution"].pop("lock_inputs")
    project.pyproject.write(show_message=False)
    pdm(["lock"], obj=project, strict=True)
    if lock_format == "pdm":
        project.lockfile._data["metadata"]["lock_inputs"] = malformed_inputs
    else:
        project.lockfile._data["tool"]["pdm"]["lock_inputs"] = malformed_inputs

    assert not project.is_lockfile_hash_match()
    assert not project.is_lockfile_fresh()


def test_lock_check_rejects_nested_temporal_value(project):
    timestamp = "2026-01-01T00:00:00"
    project.pyproject.settings["source"] = [{"name": timestamp, "url": "https://example.org/simple"}]
    lock_inputs = project.lock_inputs()
    lock_inputs["project"]["sources"][0]["name"] = datetime.fromisoformat(timestamp)

    assert not lock_inputs_match(project, lock_inputs)


def test_lock_inputs_redact_credentials(project):
    project.pyproject.settings["source"] = [
        {
            "name": "private",
            "url": "https://url-user:url-password@example.org/source-path-secret?token=source-query-secret",
            "username": "config-user",
            "password": "config-password",
        }
    ]
    project.pyproject.metadata["dependencies"] = [
        "demo @ https://dependency-user:dependency-password@example.org/dependency-path-secret/demo.whl"
        "?token=dependency-query-secret"
    ]
    project.pyproject.settings["resolution"] = {
        "overrides": {
            "demo": "https://example.org/override-path-secret/demo.whl?token=override-query-secret",
        }
    }

    lock_inputs = repr(project.lock_inputs())

    assert "url-user" not in lock_inputs
    assert "url-password" not in lock_inputs
    assert "config-user" not in lock_inputs
    assert "config-password" not in lock_inputs
    assert "dependency-user" not in lock_inputs
    assert "dependency-password" not in lock_inputs
    assert "source-path-secret" not in lock_inputs
    assert "source-query-secret" not in lock_inputs
    assert "dependency-path-secret" not in lock_inputs
    assert "dependency-query-secret" not in lock_inputs
    assert "override-path-secret" not in lock_inputs
    assert "override-query-secret" not in lock_inputs
    assert "sha256:" in lock_inputs


@pytest.mark.parametrize("lock_format", ["pdm", "pylock"])
def test_write_lockfile_does_not_add_lock_inputs(project, lock_format):
    project.project_config["lock.format"] = lock_format
    project.lockfile.open_for_write()

    project.write_lockfile(show_message=False)

    assert project.lockfile.lock_inputs is None


def test_lock_check_change_fails(pdm, project, repository):
    project.add_dependencies(["requests"])
    result = pdm(["lock"], obj=project)
    assert result.exit_code == 0
    assert project.is_lockfile_hash_match()

    project.add_dependencies(["pyyaml"])
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == 1


@pytest.mark.usefixtures("repository")
def test_innovations_with_specified_lockfile(pdm, project, working_set):
    project.add_dependencies(["requests"])
    lockfile = str(project.root / "mylock.lock")
    pdm(["lock", "--lockfile", lockfile], strict=True, obj=project)
    assert project.lockfile._path == project.root / "mylock.lock"
    assert project.is_lockfile_hash_match()
    locked = project.get_locked_repository().candidates
    assert "requests" in locked
    pdm(["sync", "--lockfile", lockfile], strict=True, obj=project)
    assert "requests" in working_set


@pytest.mark.usefixtures("repository", "vcs")
def test_skip_editable_dependencies_in_metadata(project, capsys):
    project.pyproject.metadata["dependencies"] = [
        "-e git+https://github.com/test-root/demo.git@1234567890abcdef#egg=demo"
    ]
    actions.do_lock(project)
    _, err = capsys.readouterr()
    assert "WARNING: Skipping editable dependency" in err
    assert not project.get_locked_repository().candidates


@pytest.mark.usefixtures("repository")
def test_lock_selected_groups(project, pdm):
    project.add_dependencies(["requests"], to_group="http")
    project.add_dependencies(["pytz"])
    pdm(["lock", "-G", "http", "--no-default"], obj=project, strict=True)
    assert project.lockfile.groups == ["http"]
    assert "requests" in project.get_locked_repository().candidates
    assert "pytz" not in project.get_locked_repository().candidates


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("to_dev", [True, False])
def test_lock_self_referencing_dev_groups(project, pdm, to_dev):
    name = project.name
    project.add_dependencies(["requests"], to_group="http", dev=to_dev)
    project.add_dependencies(
        {"pytz": parse_requirement("pytz"), f"{name}[http]": parse_requirement(f"{name}[http]")},
        to_group="dev",
        dev=True,
    )
    pdm(["lock", "-G", "dev"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "dev", "http"]
    packages = project.lockfile["package"]
    pytz = next(p for p in packages if p["name"] == "pytz")
    assert pytz["groups"] == ["dev"]
    requests = next(p for p in packages if p["name"] == "requests")
    assert requests["groups"] == ["dev", "http"]
    idna = next(p for p in packages if p["name"] == "idna")
    assert idna["groups"] == ["dev", "http"]


@pytest.mark.usefixtures("repository")
def test_lock_self_referencing_optional_groups(project, pdm):
    name = project.name
    project.add_dependencies(["requests"], to_group="http")
    project.add_dependencies(
        {"pytz": parse_requirement("pytz"), f"{name}[http]": parse_requirement(f"{name}[http]")},
        to_group="all",
    )
    pdm(["lock", "-G", "all"], obj=project, strict=True)
    assert project.lockfile.groups == ["default", "all", "http"]
    packages = project.lockfile["package"]
    pytz = next(p for p in packages if p["name"] == "pytz")
    assert pytz["groups"] == ["all"]
    requests = next(p for p in packages if p["name"] == "requests")
    assert requests["groups"] == ["all", "http"]
    idna = next(p for p in packages if p["name"] == "idna")
    assert idna["groups"] == ["all", "http"]


@pytest.mark.usefixtures("repository")
def test_lock_include_groups_not_allowed(project, pdm):
    project.pyproject.metadata["optional-dependencies"] = {"http": ["requests"]}
    project.pyproject.dependency_groups.update({"dev": ["pytest", {"include-group": "http"}]})
    project.pyproject.write()
    result = pdm(["lock", "-G", "all"], obj=project)
    assert result.exit_code != 0
    assert "Missing group 'http' in `include-group`" in result.stderr


@pytest.mark.usefixtures("repository")
def test_lock_optional_referencing_dev_group_not_allowed(project, pdm):
    name = project.name
    project.pyproject.metadata["optional-dependencies"] = {"http": ["requests", f"{name}[dev]"]}
    project.pyproject.dependency_groups.update({"dev": ["pytest"]})
    project.pyproject.write()
    result = pdm(["lock", "-G", "http"], obj=project)
    assert result.exit_code != 0
    assert "Optional dependency group 'http' cannot include non-existing extras" in result.stderr


@pytest.mark.usefixtures("local_finder")
def test_lock_multiple_platform_wheels(project, pdm):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies(["pdm-hello"])
    pdm(["lock"], obj=project, strict=True)
    package = next(p for p in project.lockfile["package"] if p["name"] == "pdm-hello")
    file_hashes = package["files"]
    assert len(file_hashes) == 2


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize("platform", ["linux", "macos", "windows"])
def test_lock_specific_platform_wheels(project, pdm, platform):
    project.environment.python_requires = PySpecSet(">=3.7")
    project.add_dependencies(["pdm-hello"])
    pdm(["lock", "--platform", platform], obj=project, strict=True)
    assert FLAG_CROSS_PLATFORM not in project.lockfile.strategy
    package = next(p for p in project.lockfile["package"] if p["name"] == "pdm-hello")
    file_hashes = package["files"]
    wheels_num = 2 if platform == "windows" else 1
    assert len(file_hashes) == wheels_num


def test_parse_lock_strategy_group_options(core):
    core.init_parser()
    parser = core.parser

    ns = parser.parse_args(["lock", "-S", "no_cross_platform"])
    assert ns.strategy_change == ["no_cross_platform"]
    ns = parser.parse_args(["lock", "-S", "no_cross_platform", "--static-urls"])
    assert ns.strategy_change == ["no_cross_platform", "static_urls"]
    ns = parser.parse_args(["lock", "-S", "no_cross_platform,direct_minimal_versions"])
    assert ns.strategy_change == ["no_cross_platform", "direct_minimal_versions"]


def test_apply_lock_strategy_changes(project):
    assert project.lockfile.apply_strategy_change(["no_cross_platform", "static_urls"]) == {
        "inherit_metadata",
        "static_urls",
    }
    assert project.lockfile.apply_strategy_change(["no_static_urls"]) == {"inherit_metadata"}
    assert project.lockfile.apply_strategy_change(["no_inherit_metadata"]) == set()


@pytest.mark.parametrize("strategy", [["abc"], ["no_abc", "static_urls"]])
def test_apply_lock_strategy_changes_invalid(project, strategy):
    with pytest.raises(PdmUsageError):
        project.lockfile.apply_strategy_change(strategy)


def test_lock_direct_minimal_versions(project, repository, pdm):
    project.add_dependencies(["django"])
    repository.add_candidate("pytz", "2019.6")
    pdm(["lock", "-S", "direct_minimal_versions"], obj=project, strict=True)
    assert project.lockfile.strategy == {"direct_minimal_versions", "inherit_metadata"}
    locked_repository = project.get_locked_repository()
    assert locked_repository.candidates["django"].version == "1.11.8"
    assert locked_repository.candidates["pytz"].version == "2019.6"


@pytest.mark.usefixtures("local_finder")
@pytest.mark.parametrize("args", [(), ("-S", "direct_minimal_versions")])
def test_lock_direct_minimal_versions_real(project, pdm, args):
    project.add_dependencies(["zipp"])
    pdm(["lock", *args], obj=project, strict=True)
    locked_candidate = project.get_locked_repository().candidates["zipp"]
    if args:
        assert locked_candidate.version == "3.6.0"
    else:
        assert locked_candidate.version == "3.7.0"


@pytest.mark.parametrize(
    "lock_version,expected",
    [
        ("4.1.0", Compatibility.BACKWARD),
        ("4.1.1", Compatibility.SAME),
        ("4.1.2", Compatibility.FORWARD),
        ("4.2", Compatibility.NONE),
        ("3.0", Compatibility.NONE),
        ("4.0.1", Compatibility.BACKWARD),
    ],
)
def test_lockfile_compatibility(project, monkeypatch, lock_version, expected, pdm):
    pdm(["lock"], obj=project, strict=True)
    monkeypatch.setattr("pdm.project.lockfile.PDMLock.spec_version", parse_version("4.1.1"))
    project.lockfile._data["metadata"]["lock_version"] = lock_version
    assert project.lockfile.compatibility() == expected
    result = pdm(["lock", "--check"], obj=project)
    assert result.exit_code == (1 if expected == Compatibility.NONE else 0)


def test_lock_default_inherit_metadata(project, pdm, mocker, working_set):
    project.add_dependencies(["requests"])
    pdm(["lock"], obj=project, strict=True)
    assert "inherit_metadata" in project.lockfile.strategy
    packages = project.lockfile["package"]
    assert all(package["groups"] == ["default"] for package in packages)

    resolver = mocker.patch.object(project, "get_resolver")
    pdm(["sync"], obj=project, strict=True)
    resolver.assert_not_called()
    for key in ("requests", "idna", "chardet", "urllib3"):
        assert key in working_set


def test_lock_inherit_metadata_strategy(project, pdm, mocker, working_set):
    project.add_dependencies(["requests"])
    pdm(["lock", "-S", "inherit_metadata"], obj=project, strict=True)
    assert "inherit_metadata" in project.lockfile.strategy
    packages = project.lockfile["package"]
    assert all(package["groups"] == ["default"] for package in packages)

    resolver = mocker.patch.object(project, "get_resolver")
    pdm(["sync"], obj=project, strict=True)
    resolver.assert_not_called()
    for key in ("requests", "idna", "chardet", "urllib3"):
        assert key in working_set


@pytest.mark.parametrize("source", ["cli", "pyproject", "config"])
def test_lock_exclude_newer(project, pdm, source):
    project.pyproject.metadata["requires-python"] = ">=3.9"
    project.project_config["pypi.url"] = "https://my.pypi.org/json"
    project.add_dependencies(["zipp"])
    pdm(["lock"], obj=project, strict=True, cleanup=False)
    assert project.get_locked_repository().candidates["zipp"].version == "3.7.0"

    cmd = ["lock", "--exclude-newer", "2024-01-01"]
    if source == "pyproject":
        project.pyproject.settings["resolution"] = {"exclude-newer": "2024-01-01"}
        cmd = ["lock"]
    elif source == "config":
        project.project_config["strategy.exclude-newer"] = "2024-01-01"
        cmd = ["lock"]

    pdm(cmd, obj=project, strict=True, cleanup=False)
    assert project.get_locked_repository().candidates["zipp"].version == "3.6.0"


@pytest.mark.parametrize("source", ["cli", "pyproject", "config"])
def test_lock_exclude_newer_accepts_relative_duration(project, pdm, monkeypatch, source):
    from datetime import datetime, timezone

    import pdm.utils as pdm_utils

    frozen_now = datetime(2024, 2, 9, 12, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return frozen_now

    monkeypatch.setattr(pdm_utils, "datetime", FrozenDateTime)

    cmd = ["lock", "--exclude-newer", "3w"]
    if source == "pyproject":
        project.pyproject.settings["resolution"] = {"exclude-newer": "3w"}
        cmd = ["lock"]
    elif source == "config":
        project.project_config["strategy.exclude-newer"] = "3w"
        cmd = ["lock"]

    project.pyproject.metadata["requires-python"] = ">=3.9"
    project.project_config["pypi.url"] = "https://my.pypi.org/json"
    project.add_dependencies(["zipp"])
    pdm(cmd, strict=True, obj=project, cleanup=False)
    assert project.get_locked_repository().candidates["zipp"].version == "3.6.0"


def test_pyproject_exclude_newer_overrides_config(project, pdm):
    project.pyproject.metadata["requires-python"] = ">=3.9"
    project.project_config["pypi.url"] = "https://my.pypi.org/json"
    project.project_config["strategy.exclude-newer"] = "2024-01-01"
    project.pyproject.settings["resolution"] = {"exclude-newer": "2025-01-01"}
    project.add_dependencies(["zipp"])

    pdm(["lock"], obj=project, strict=True, cleanup=False)
    assert project.get_locked_repository().candidates["zipp"].version == "3.7.0"


exclusion_cases = [
    pytest.param(("-G", ":all", "--without", "tz,ssl"), id="-G :all --without tz,ssl"),
    pytest.param(("-G", ":all", "--without", "tz", "--without", "ssl"), id="-G :all --without tz --without ssl"),
    pytest.param(("--with", ":all", "--without", "tz,ssl"), id="--with all --without tz,ssl"),
    pytest.param(("--with", ":all", "--without", "tz", "--without", "ssl"), id="--with all --without tz --without ssl"),
    pytest.param(("--without", "tz", "--without", "ssl"), id="--without tz --without ssl"),
    pytest.param(("--without", "tz,ssl"), id="--without tz,ssl"),
]


@pytest.mark.parametrize("args", exclusion_cases)
@pytest.mark.usefixtures("repository")
def test_lock_all_with_excluded_groups(project, pdm, args):
    project.add_dependencies(["urllib3"], "url")
    project.add_dependencies(["pytz"], "tz", True)
    project.add_dependencies(["pyopenssl"], "ssl")
    pdm(["lock", *args], obj=project, strict=True)
    assert "urllib3" in project.get_locked_repository().candidates
    assert "pytz" not in project.get_locked_repository().candidates
    assert "pyopenssl" not in project.get_locked_repository().candidates


@pytest.mark.parametrize(
    "args",
    [
        ("--append",),
        ("--python", "<3.6"),
        ("-S", "cross_platform", "--append", "--python", "3.10"),
        ("--platform", "linux", "--refresh"),
    ],
)
def test_forbidden_lock_target_options(project, pdm, args):
    result = pdm(["lock", *args], obj=project)
    assert result.exit_code != 0
    assert "PdmUsageError" in result.stderr


@pytest.mark.parametrize("nested", [False, True])
def test_lock_for_multiple_targets(project, pdm, repository, nested):
    deps = [
        'django<2; sys_platform == "win32"',
        'django>=2; sys_platform != "win32"',
    ]
    if nested:
        repository.add_candidate("foo", "0.1.0")
        repository.add_dependencies("foo", "0.1.0", deps)
        project.add_dependencies(["foo"])
    else:
        project.add_dependencies(deps)

    pdm(["lock", "--platform", "windows"], obj=project, strict=True)
    locked = project.get_locked_repository()
    candidates = locked.all_candidates
    assert len(candidates["django"]) == 1
    assert candidates["django"][0].version == "1.11.8"
    assert len(locked.targets) == 1
    pytz = candidates["pytz"][0]
    assert str(pytz.req.marker) == 'sys_platform == "win32"'

    result = pdm(["lock", "--platform", "windows", "--append"], obj=project, strict=True)
    assert "already exists, skip locking." in result.stdout

    pdm(["lock", "--platform", "linux", "--append"], obj=project, strict=True)
    locked = project.get_locked_repository()
    candidates = locked.all_candidates
    assert len(locked.targets) == 2
    assert sorted(c.version for c in candidates["django"]) == ["1.11.8", "2.2.9"]
    pytz = candidates["pytz"][0]
    assert not pytz.req.marker or pytz.req.marker.is_any()

    # not append but overwrite
    pdm(["lock", "--platform", "windows"], obj=project, strict=True)
    locked = project.get_locked_repository()
    candidates = locked.all_candidates
    assert len(candidates["django"]) == 1
    assert candidates["django"][0].version == "1.11.8"
    assert len(locked.targets) == 1
    pytz = candidates["pytz"][0]
    assert str(pytz.req.marker) == 'sys_platform == "win32"'


CONSTRAINT_FILE = str(FIXTURES / "constraints.txt")


@pytest.mark.usefixtures("repository")
@pytest.mark.parametrize("constraint", [CONSTRAINT_FILE, Path(CONSTRAINT_FILE).as_uri()])
def test_lock_with_override_file(project, pdm, constraint):
    project.add_dependencies(["requests"])
    pdm(["lock", "--override", constraint], obj=project, strict=True)
    candidates = project.get_locked_repository().candidates
    assert candidates["requests"].version == "2.20.0b1"
    assert candidates["urllib3"].version == "1.23b0"
    assert "django" not in candidates


def test_pylock_add_remove_strategy(project, pdm):
    project.project_config["lock.format"] = "pylock"
    pdm(["lock"], obj=project, strict=True)
    assert project.lockfile.strategy == {"inherit_metadata", "static_urls"}
    pdm(["lock", "-S", "static_urls"], obj=project, strict=True)
    pdm(["lock", "-S", "direct_minimal_versions"], obj=project, strict=True)
    assert project.lockfile.strategy == {"inherit_metadata", "static_urls", "direct_minimal_versions"}

    result = pdm(["lock", "-S", "no_static_urls"], obj=project)
    assert result.exit_code != 0
    result = pdm(["lock", "-S", "no_inherit_metadata"], obj=project)
    assert result.exit_code != 0


@pytest.mark.usefixtures("repository")
def test_lock_with_invalid_python_requirement(project, pdm):
    project.add_dependencies(["requests", "python>=3.6"])
    result = pdm(["lock", "-v"], obj=project, strict=True)
    assert "requests" in project.get_locked_repository().candidates
    assert "python" not in project.get_locked_repository().candidates
    assert "The 'python' requirement is not necessary and will be ignored." in result.stderr
