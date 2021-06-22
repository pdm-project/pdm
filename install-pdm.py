from __future__ import annotations

import argparse
import atexit
import dataclasses
import io
import json
import os
import platform
import shutil
import site
import subprocess
import sys
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

from pip import __file__ as pip_location

if sys.version_info < (3, 7):
    sys.exit("Python 3.7 or above is required to install PDM.")

_plat = platform.system()
MACOS = _plat == "Darwin"
WINDOWS = _plat == "Windows"
REPO = "https://github.com/pdm-project/pdm"
JSON_URL = "https://pypi.org/pypi/pdm/json"

FOREGROUND_COLORS = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}


def _call_subprocess(args: list[str]) -> int:
    try:
        return subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True
        ).returncode
    except subprocess.CalledProcessError as e:
        print(f"An error occurred when executing {args}:", file=sys.stderr)
        print(e.output.decode("utf-8"))
        sys.exit(e.returncode)


def _echo(text: str) -> None:
    sys.stdout.write(text + "\n")


def _get_win_folder_with_ctypes(csidl_name):
    import ctypes

    csidl_const = {
        "CSIDL_APPDATA": 26,
        "CSIDL_COMMON_APPDATA": 35,
        "CSIDL_LOCAL_APPDATA": 28,
    }[csidl_name]

    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl_const, None, 0, buf)

    # Downgrade to short path name if have highbit chars. See
    # <http://bugs.activestate.com/show_bug.cgi?id=85099>.
    has_high_char = False
    for c in buf:
        if ord(c) > 255:
            has_high_char = True
            break
    if has_high_char:
        buf2 = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(buf.value, buf2, 1024):
            buf = buf2

    return buf.value


def _get_win_folder_from_registry(csidl_name):
    """This is a fallback technique at best. I'm not sure if using the
    registry for this guarantees us the correct answer for all CSIDL_*
    names.
    """
    import winreg

    shell_folder_name = {
        "CSIDL_APPDATA": "AppData",
        "CSIDL_COMMON_APPDATA": "Common AppData",
        "CSIDL_LOCAL_APPDATA": "Local AppData",
    }[csidl_name]

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
    )
    dir, _ = winreg.QueryValueEx(key, shell_folder_name)
    return dir


if WINDOWS:
    try:
        from ctypes import windll  # noqa

        _get_win_folder = _get_win_folder_with_ctypes
    except ImportError:
        _get_win_folder = _get_win_folder_from_registry


def support_ansi() -> False:
    if WINDOWS:
        return (
            os.getenv("ANSICON") is not None
            or "ON" == os.getenv("ConEmuANSI")
            or "xterm" == os.getenv("Term")
        )

    if not hasattr(sys.stdout, "fileno"):
        return False

    try:
        return os.isatty(sys.stdout.fileno())
    except io.UnsupportedOperation:
        return False


def colored(color: str, text: str, bold: bool = False) -> str:
    if not support_ansi():
        return text
    codes = [FOREGROUND_COLORS[color]]
    if bold:
        codes.append(1)

    return "\x1b[{}m{}\x1b[0m".format(";".join(map(str, codes)), text)


@dataclasses.dataclass
class Installer:
    location: str | None = None
    version: str | None = None
    prerelease: bool = False
    additional_deps: Sequence[str] = ()

    def __post_init__(self):
        self._path = self._decide_path()
        self._path.mkdir(parents=True, exist_ok=True)
        if self.version is None:
            self.version = self._get_latest_version()

    def _get_latest_version(self) -> str:
        resp = urllib.request.urlopen(JSON_URL)
        metadata = json.load(resp)

        def is_stable(v: str) -> bool:
            return all(p.isdigit() for p in v.split("."))

        def sort_version(v: str) -> tuple:
            return tuple(int(p) for p in v.split("."))

        releases = sorted(
            filter(is_stable, metadata["releases"]), key=sort_version, reverse=True
        )

        return releases[0]

    def _decide_path(self) -> Path:
        if self.location is not None:
            return Path(self.location).expanduser().resolve()

        if WINDOWS:
            const = "CSIDL_APPDATA"
            path = os.path.normpath(_get_win_folder(const))
            path = os.path.join(path, "pdm")
        elif MACOS:
            path = os.path.expanduser("~/Library/Application Support/pdm")
        else:
            path = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
            path = os.path.join(path, "pdm")

        return Path(path)

    def _make_env(self) -> Path:
        venv_path = self._path / "venv"

        _echo(
            "Installing {} ({}): {}".format(
                colored("green", "PDM", bold=True),
                colored("yellow", self.version),
                colored("cyan", "Creating virtual environment"),
            )
        )

        try:
            import venv
        except ModuleNotFoundError:
            try:
                import virtualenv
            except ModuleNotFoundError:
                tmpdir = TemporaryDirectory()
                atexit.register(tmpdir.cleanup)

                _call_subprocess(
                    [
                        sys.executable,
                        os.path.dirname(pip_location),
                        "install",
                        "virtualenv",
                        "-t",
                        tmpdir.name,
                    ]
                )
                sys.path.insert(0, tmpdir.name)
                import virtualenv

                virtualenv.cli_run([str(venv_path), "--clear"])
        else:
            venv.create(venv_path, clear=True, with_pip=True)

        return venv_path

    def _install(self, venv_path: Path) -> None:
        _echo(
            "Installing {} ({}): {}".format(
                colored("green", "PDM", bold=True),
                colored("yellow", self.version),
                colored("cyan", "Installing PDM and dependencies"),
            )
        )

        if WINDOWS:
            venv_python = venv_path / "Scripts/python.exe"
        else:
            venv_python = venv_path / "bin/python"

        if self.version:
            if self.version.upper() == "HEAD":
                req = f"git+{REPO}.git@main#egg=pdm"
            else:
                req = f"pdm=={self.version}"
        else:
            req = "pdm"
        args = [req] + [d for d in self.additional_deps if d]
        if self.prerelease:
            args.insert(0, "--pre")
        pip_cmd = [venv_python, "-m", "pip", "install"] + args
        _call_subprocess(pip_cmd)

    def _make_bin(self, venv_path: Path) -> Path:
        if self.location:
            bin_path = self._path / "bin"
        else:
            userbase = Path(site.getuserbase())
            bin_path = userbase / ("Scripts" if WINDOWS else "bin")

        _echo(
            "Installing {} ({}): {} {}".format(
                colored("green", "PDM", bold=True),
                colored("yellow", self.version),
                colored("cyan", "Making binary at"),
                colored("green", str(bin_path)),
            )
        )
        bin_path.mkdir(parents=True, exist_ok=True)
        if WINDOWS:
            script = bin_path / "pdm.exe"
            target = venv_path / "Scripts" / "pdm.exe"
        else:
            script = bin_path / "pdm"
            target = venv_path / "bin" / "pdm"

        if script.exists():
            script.unlink()
        try:
            script.symlink_to(target)
        except OSError:
            shutil.copy(target, script)
        return bin_path

    def _add_to_path(self, target: Path) -> None:
        value = os.path.normcase(target)

        if WINDOWS:

            import winreg

            with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as root:
                with winreg.OpenKey(
                    root, "Environment", 0, winreg.KEY_ALL_ACCESS
                ) as env_key:
                    try:
                        old_value, type_ = winreg.QueryValueEx(env_key, "PATH")
                        if value in [
                            os.path.normcase(item)
                            for item in old_value.split(os.pathsep)
                        ]:
                            return
                    except FileNotFoundError:
                        old_value, type_ = "", winreg.REG_EXPAND_SZ
                    new_value = (
                        os.pathsep.join([old_value, value]) if old_value else value
                    )
                    winreg.SetValueEx(env_key, "PATH", 0, type_, new_value)

            _echo(
                "Post-install: {} is added to PATH env, please restart your terminal "
                "to take effect".format(colored("green", value))
            )
        else:
            paths = [
                os.path.normcase(p) for p in os.getenv("PATH", "").split(os.pathsep)
            ]
            if value in paths:
                return
            _echo(
                "Post-install: Please add {} to PATH by executing:\n    {}".format(
                    colored("green", value),
                    colored("cyan", f"export PATH={value}:$PATH"),
                )
            )

    def _remove_path_windows(self, target: Path) -> None:
        value = os.path.normcase(target)

        import winreg

        with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as root:
            with winreg.OpenKey(
                root, "Environment", 0, winreg.KEY_ALL_ACCESS
            ) as env_key:
                try:
                    old_value, type_ = winreg.QueryValueEx(env_key, "PATH")
                    paths = [
                        os.path.normcase(item) for item in old_value.split(os.pathsep)
                    ]
                    if value not in paths:
                        return

                    new_value = os.pathsep.join(p for p in paths if p != value)
                    winreg.SetValueEx(env_key, "PATH", 0, type_, new_value)
                except FileNotFoundError:
                    return

    def _post_install(self, venv_path: Path, bin_path: Path) -> None:
        if WINDOWS:
            script = bin_path / "pdm.exe"
        else:
            script = bin_path / "pdm"
        subprocess.check_call([script, "--help"])
        print()
        _echo(
            "Successfully installed: {} ({}) at {}".format(
                colored("green", "PDM", bold=True),
                colored("yellow", self.version),
                colored("cyan", str(script)),
            )
        )
        self._add_to_path(bin_path)

    def install(self) -> None:
        venv = self._make_env()
        self._install(venv)
        bin = self._make_bin(venv)
        self._post_install(venv, bin)

    def uninstall(self) -> None:
        _echo(
            "Uninstalling {}: {}".format(
                colored("green", "PDM", bold=True),
                colored("cyan", "Removing venv and script"),
            )
        )
        if self.location:
            bin_path = self._path / "bin"
        else:
            userbase = Path(site.getuserbase())
            bin_path = userbase / ("Scripts" if WINDOWS else "bin")

        if WINDOWS:
            script = bin_path / "pdm.exe"
        else:
            script = bin_path / "pdm"

        shutil.rmtree(self._path / "venv")
        script.unlink()

        if WINDOWS:
            self._remove_path_windows(bin_path)

        print()
        _echo("Successfully uninstalled")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        "--version",
        help="Specify the version to be installed, "
        "or HEAD to install from the main branch",
        default=os.getenv("PDM_VERSION"),
    )
    parser.add_argument(
        "--prerelease",
        action="store_true",
        help="Allow prereleases to be installed",
        default=os.getenv("PDM_PRERELEASE"),
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the PDM installation",
        default=os.getenv("PDM_REMOVE"),
    )
    parser.add_argument(
        "-p",
        "--path",
        help="Specify the location to install PDM",
        default=os.getenv("PDM_HOME"),
    )
    parser.add_argument(
        "-d",
        "--dep",
        action="append",
        default=os.getenv("PDM_DEPS", "").split(","),
        help="Specify additional dependencies, can be given multiple times",
    )

    options = parser.parse_args()
    installer = Installer(
        options.path, options.version, options.prerelease, options.dep
    )
    if options.remove:
        installer.uninstall()
    else:
        installer.install()


if __name__ == "__main__":
    main()
