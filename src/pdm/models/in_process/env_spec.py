import json
import platform
import sys
import sysconfig


class EnvError(Exception):
    pass


def get_arch() -> str:
    arch = platform.machine().lower()
    if arch in ("i386", "i686"):
        return "x86"
    if arch == "amd64":
        if platform.architecture()[0] == "32bit":
            return "x86"
        return "x86_64"
    if arch == "arm64":
        return "aarch64"
    return arch


def get_platform() -> str:
    """Return the current platform."""

    system = platform.system()
    arch = get_arch()
    if system == "Linux":
        libc_ver = platform.libc_ver()[1]
        if libc_ver:
            parts = libc_ver.split(".")
            return f"manylinux_{parts[0]}_{parts[1]}_{arch}"
        else:  # musl
            # There is no easy way to retrieve the musl version, so we just assume it's 1.2
            return f"musllinux_1_2_{arch}"
    elif system == "Windows":
        if arch == "aarch64":
            return "windows_arm64"
        if arch == "x86_64":
            return "windows_amd64"
        return f"windows_{arch}"
    elif system == "Darwin":
        mac_ver = platform.mac_ver()[0].split(".")
        if arch == "aarch64":
            arch = "arm64"
        major, minor = int(mac_ver[0]), int(mac_ver[1])
        if major >= 11:
            minor = 0
        return f"macos_{major}_{minor}_{arch}"
    else:
        raise EnvError("Unsupported platform")


def get_current_env_spec():
    python_version = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    return {
        "requires_python": f"=={python_version}",
        "platform": get_platform(),
        "implementation": platform.python_implementation().lower(),
        "gil_disabled": sysconfig.get_config_var("Py_GIL_DISABLED") or False,
    }


if __name__ == "__main__":
    print(json.dumps(get_current_env_spec(), indent=2))
