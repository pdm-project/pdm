from __future__ import annotations

from typing import TYPE_CHECKING

from pdm import termui
from pdm.exceptions import UninstallError
from pdm.installers.installers import (
    install_editable,
    install_wheel,
    install_wheel_with_cache,
)
from pdm.installers.uninstallers import BaseRemovePaths, StashedRemovePaths
from pdm.utils import is_dist_editable

if TYPE_CHECKING:
    from pip._vendor.pkg_resources import Distribution

    from pdm.models.candidates import Candidate
    from pdm.models.environment import Environment


def format_dist(dist: Distribution) -> str:
    formatter = "{version}{path}"
    path = ""
    if is_dist_editable(dist):
        path = f" (-e {dist.location})"
    return formatter.format(version=termui.yellow(dist.version), path=path)


class InstallManager:
    """The manager that performs the installation and uninstallation actions."""

    def __init__(
        self, environment: Environment, *, use_install_cache: bool = False
    ) -> None:
        self.environment = environment
        self.use_install_cache = use_install_cache

    def install(self, candidate: Candidate) -> None:
        if candidate.req.editable:
            installer = install_editable
        elif self.use_install_cache and candidate.req.is_named:
            # Only cache wheels from PyPI
            installer = install_wheel_with_cache
        else:
            installer = install_wheel
        installer(candidate)

    def get_paths_to_remove(self, dist: Distribution) -> BaseRemovePaths:
        """Get the path collection to be removed from the disk"""
        return StashedRemovePaths.from_dist(dist, envrionment=self.environment)

    def uninstall(self, dist: Distribution) -> None:
        """Perform the uninstallation for a given distribution"""
        remove_path = self.get_paths_to_remove(dist)
        try:
            remove_path.remove()
            remove_path.commit()
        except OSError as e:
            termui.logger.info(
                "Error occurred during uninstallation, roll back the changes now."
            )
            remove_path.rollback()
            raise UninstallError(e) from e
