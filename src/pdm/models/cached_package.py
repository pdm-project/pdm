from __future__ import annotations

import os
import shutil
from functools import cached_property
from pathlib import Path

from pdm.termui import logger


class CachedPackage:
    """A package cached in the central package store.
    The directory name is similar to wheel's filename:

        $PACKAGE_ROOT/<hash_part[:5]>/<dist_name>-<version>-<impl>-<abi>-<plat>/

    Under the directory there should be a text file named `referrers`.
    Each line of the file is a distribution path that refers to this package.
    *Only wheel installations will be cached*
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(os.path.normcase(os.path.expanduser(path))).resolve()
        self._referrers: set[str] | None = None

    @cached_property
    def dist_info(self) -> Path:
        """The dist-info directory of the wheel"""
        from installer.exceptions import InvalidWheelSource

        try:
            return next(self.path.glob("*.dist-info"))
        except StopIteration:
            raise InvalidWheelSource(f"The wheel doesn't contain metadata {self.path!r}") from None

    @property
    def referrers(self) -> set[str]:
        """A set of entries in referrers file"""
        if self._referrers is None:
            filepath = self.path / "referrers"
            if not filepath.is_file():
                return set()
            self._referrers = {
                line.strip()
                for line in filepath.read_text("utf8").splitlines()
                if line.strip() and os.path.exists(line.strip())
            }
        return self._referrers

    def add_referrer(self, path: str) -> None:
        """Add a new referrer"""
        path = os.path.normcase(os.path.expanduser(os.path.abspath(path)))
        referrers = self.referrers | {path}
        (self.path / "referrers").write_text("\n".join(sorted(referrers)) + "\n", "utf8")
        self._referrers = None

    def remove_referrer(self, path: str) -> None:
        """Remove a referrer"""
        path = os.path.normcase(os.path.expanduser(os.path.abspath(path)))
        referrers = self.referrers - {path}
        (self.path / "referrers").write_text("\n".join(referrers) + "\n", "utf8")
        self._referrers = None

    def cleanup(self) -> None:
        logger.info("Clean up cached package %s since it is not used by any project.", self.path)
        shutil.rmtree(self.path)
