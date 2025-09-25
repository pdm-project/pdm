import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from pdm.environments.local import PythonLocalEnvironment
from pdm.utils import pdm_scheme


@pytest.fixture()
def local_env(project):
    # Ensure we construct a fresh local environment for each test
    env = PythonLocalEnvironment(project)
    return env


def test_packages_path_compat_suffix_32(local_env, tmp_path, monkeypatch):
    # Simulate interpreter identifier ending with -32, and only non-"-32" directory exists
    monkeypatch.setattr(local_env, "_interpreter", SimpleNamespace(identifier="3.11-32"))
    base = local_env.project.root / "__pypackages__"
    compat_dir = base / "3.11"
    compat_dir.mkdir(parents=True, exist_ok=True)
    # Also ensure parent exists for side effects inside packages_path
    p = local_env.packages_path
    assert p.name == "3.11"
    assert p.parent == base


def test_local_get_paths_headers_override(local_env):
    paths = local_env.get_paths(dist_name="mypkg")
    # Ensure headers path is under include/mypkg (cross-platform path check)
    from pathlib import Path as _P

    assert _P(paths["headers"]).parts[-2:] == ("include", "mypkg")
    # Sanity: scheme base is pep582
    scheme = pdm_scheme(local_env.packages_path.as_posix())
    for k in ("purelib", "platlib", "scripts", "data"):
        assert paths[k].startswith(scheme[k])


def test_pip_command_uses_existing_module(monkeypatch, project):
    # Simulate: `python -Esm pip --version` fails, but host pip is compatible
    env = PythonLocalEnvironment(project)

    class DummyCompleted:
        returncode = 1

    monkeypatch.setattr("subprocess.run", lambda *a, **k: DummyCompleted())

    # Provide a dummy pip module with a file path
    dummy_pip = ModuleType("pip")
    dummy_dir = Path(project.core.create_temp_dir(prefix="pip-test-"))
    dummy_file = dummy_dir / "__init__.py"
    dummy_file.write_text("")
    dummy_pip.__file__ = str(dummy_file)
    monkeypatch.setitem(sys.modules, "pip", dummy_pip)

    # Make it considered compatible; patch the symbol used in BaseEnvironment
    monkeypatch.setattr("pdm.environments.base.is_pip_compatible_with_python", lambda v: True)

    cmd = env.pip_command
    assert cmd[:3] == [str(env.interpreter.executable), "-Es", str(dummy_dir)]


def test_pip_command_download_fallback(monkeypatch, project):
    # Simulate: `python -Esm pip --version` fails and host pip is unavailable/incompatible
    env = PythonLocalEnvironment(project)

    class DummyCompleted:
        returncode = 1

    monkeypatch.setattr("subprocess.run", lambda *a, **k: DummyCompleted())

    # Force importing pip to fail inside BaseEnvironment so pip_location is None
    import builtins as _builtins

    _real_import = _builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pip" or name.startswith("pip."):
            raise ImportError
        return _real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    # Also ensure compatibility check returns False on the symbol used in BaseEnvironment
    monkeypatch.setattr("pdm.environments.base.is_pip_compatible_with_python", lambda v: False)

    def fake_download(path):
        # Create the expected wheel path
        Path(path).write_text("")

    # Avoid network: stub out the download function to just create the file
    monkeypatch.setattr(type(env), "_download_pip_wheel", lambda self, p: fake_download(p))

    cmd = env.pip_command
    # Expect the -m form not used, fallback to the wheel's pip script
    assert cmd[0] == str(env.interpreter.executable)
    assert Path(cmd[1]).name == "pip"


def test_pip_command_installed(monkeypatch, project):
    # Simulate: `python -Esm pip --version` succeeds -> use it directly
    env = PythonLocalEnvironment(project)

    class DummyCompleted:
        returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *a, **k: DummyCompleted())

    cmd = env.pip_command
    assert cmd[:3] == [str(env.interpreter.executable), "-Esm", "pip"]


def test_script_kind_posix(local_env):
    # On non-Windows platforms, script_kind should be posix
    if os.name != "nt":
        assert local_env.script_kind == "posix"


def test_which_python_variants(local_env):
    # Should resolve to interpreter path when asking for pythonN or python
    exe = str(local_env.interpreter.executable)
    assert local_env.which("python") == exe
    # python3 matches the major version
    assert local_env.which(f"python{local_env.interpreter.version.major}") == exe


def test_process_env_includes_scripts_first(local_env):
    env = local_env.process_env
    scripts = local_env.get_paths()["scripts"]
    path_entries = env["PATH"].split(os.pathsep)
    assert path_entries[0] == scripts
