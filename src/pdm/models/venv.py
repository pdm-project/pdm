from __future__ import annotations

import dataclasses as dc
import sys
from functools import cached_property
from pathlib import Path

from pdm.models.in_process import get_sys_config_paths
from pdm.utils import find_python_in_path, get_venv_like_prefix

IS_WIN = sys.platform == "win32"
BIN_DIR = "Scripts" if IS_WIN else "bin"


def get_venv_python(venv: Path) -> Path:
    """Get the interpreter path inside the given venv."""
    suffix = ".exe" if IS_WIN else ""
    result = venv / BIN_DIR / f"python{suffix}"
    if IS_WIN and not result.exists():
        result = venv / "bin" / f"python{suffix}"  # for mingw64/msys2
        if result.exists():
            return result
        else:
            return venv / "python.exe"  # for conda
    return result


def is_conda_venv(root: Path) -> bool:
    return (root / "conda-meta").exists()


@dc.dataclass(frozen=True)
class VirtualEnv:
    root: Path
    is_conda: bool
    interpreter: Path

    @classmethod
    def get(cls, root: Path) -> VirtualEnv | None:
        path = get_venv_python(root)
        if not path.exists():
            return None
        return cls(root, is_conda_venv(root), path)

    @classmethod
    def from_interpreter(cls, interpreter: Path) -> VirtualEnv | None:
        root, is_conda = get_venv_like_prefix(interpreter)
        if root is not None:
            return cls(root, is_conda, interpreter)
        return None

    def env_vars(self) -> dict[str, str]:
        key = "CONDA_PREFIX" if self.is_conda else "VIRTUAL_ENV"
        return {key: str(self.root)}

    @cached_property
    def venv_config(self) -> dict[str, str]:
        venv_cfg = self.root / "pyvenv.cfg"
        if not venv_cfg.exists():
            return {}
        parsed: dict[str, str] = {}
        with venv_cfg.open(encoding="utf-8") as fp:
            for line in fp:
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if k == "include-system-site-packages":
                        v = v.lower()
                    parsed[k] = v
        return parsed

    @property
    def include_system_site_packages(self) -> bool:
        return self.venv_config.get("include-system-site-packages") == "true"

    @cached_property
    def base_paths(self) -> list[str]:
        home = Path(self.venv_config["home"])
        base_executable = find_python_in_path(home) or find_python_in_path(home.parent)
        assert base_executable is not None
        paths = get_sys_config_paths(str(base_executable))
        return [paths["purelib"], paths["platlib"]]
