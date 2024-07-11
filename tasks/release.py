from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import parver
from rich.console import Console

if TYPE_CHECKING:
    from parver._typing import PreTag

_console = Console(highlight=False)
_err_console = Console(stderr=True, highlight=False)


def echo(*args: str, err: bool = False, **kwargs: Any):
    if err:
        _err_console.print(*args, **kwargs)
    else:
        _console.print(*args, **kwargs)


PROJECT_DIR = Path(__file__).parent.parent


def get_current_version() -> str:
    return subprocess.check_output(["git", "describe", "--abbrev=0", "--tags"], cwd=PROJECT_DIR).decode().strip()


def bump_version(pre: str | None = None, major: bool = False, minor: bool = False) -> str:
    if major and minor:
        echo("Only one option should be provided among (--major, --minor)", style="red", err=True)
        sys.exit(1)
    current_version = parver.Version.parse(get_current_version())
    if major or minor:
        version_idx = [major, minor].index(True)
        version = current_version.bump_release(index=version_idx)
    elif pre is not None and current_version.is_prerelease:
        version = current_version
    else:
        version = current_version.bump_release(index=2)
    if pre is not None:
        if version.pre_tag != pre:
            version = version.replace(pre_tag=cast("PreTag", pre), pre=0)
        else:
            version = version.bump_pre()
    else:
        version = version.replace(pre=None, post=None)
    version = version.replace(local=None, dev=None)
    return str(version)


def release(
    dry_run: bool = False, commit: bool = True, pre: str | None = None, major: bool = False, minor: bool = False
) -> None:
    new_version = bump_version(pre, major, minor)
    echo(f"Bump version to: {new_version}", style="yellow")
    if dry_run:
        subprocess.check_call(["towncrier", "build", "--version", new_version, "--draft"])
    else:
        subprocess.check_call(["towncrier", "build", "--yes", "--version", new_version])
        subprocess.check_call(["git", "add", "."])
        if commit:
            subprocess.check_call(["git", "commit", "-m", f"chore: Release {new_version}"])
            subprocess.check_call(["git", "tag", "-a", new_version, "-m", f"v{new_version}"])
            subprocess.check_call(["git", "push"])
            subprocess.check_call(["git", "push", "--tags"])


def parse_args(argv=None):
    parser = argparse.ArgumentParser("release.py")

    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument(
        "--no-commit",
        action="store_false",
        dest="commit",
        default=True,
        help="Do not commit to Git",
    )
    group = parser.add_argument_group(title="version part")
    group.add_argument("--pre", help="Bump with the pre tag", choices=["a", "b", "rc"])
    group.add_argument("--major", action="store_true", help="Bump major version")
    group.add_argument("--minor", action="store_true", help="Bump minor version")

    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    release(args.dry_run, args.commit, args.pre, args.major, args.minor)
