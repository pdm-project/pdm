from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pdm import termui
from pdm.compat import Distribution
from pdm.exceptions import UninstallError
from pdm.installers.installers import install_wheel
from pdm.installers.uninstallers import BaseRemovePaths, StashedRemovePaths

if TYPE_CHECKING:
    from pdm.environments import BaseEnvironment
    from pdm.models.candidates import Candidate


class InstallManager:
    """The manager that performs the installation and uninstallation actions."""

    # The packages below are needed to load paths and thus should not be cached.
    NO_CACHE_PACKAGES = ("editables",)

    def __init__(
        self, environment: BaseEnvironment, *, use_install_cache: bool = False, rename_pth: bool = False
    ) -> None:
        self.environment = environment
        self.use_install_cache = use_install_cache
        self.rename_pth = rename_pth

    def install(self, candidate: Candidate) -> Distribution:
        """Install a candidate into the environment, return the distribution"""
        prepared = candidate.prepare(self.environment)
        wheel = prepared.build()
        additional_metadata: dict[str, bytes] = {}
        if direct_url := prepared.direct_url():
            additional_metadata["direct_url.json"] = json.dumps(direct_url, indent=2).encode("utf-8")
        elif provenance_url := prepared.provenance_url():
            additional_metadata["provenance_url.json"] = json.dumps(provenance_url, indent=2).encode("utf-8")
        dist_info = install_wheel(
            wheel,
            self.environment,
            additional_metadata=additional_metadata,
            install_links=self.use_install_cache and not candidate.req.editable,
            rename_pth=self.rename_pth,
        )
        return Distribution.at(dist_info)

    def get_paths_to_remove(self, dist: Distribution) -> BaseRemovePaths:
        """Get the path collection to be removed from the disk"""
        return StashedRemovePaths.from_dist(dist, environment=self.environment)

    def uninstall(self, dist: Distribution) -> None:
        """Perform the uninstallation for a given distribution"""
        remove_path = self.get_paths_to_remove(dist)
        dist_name = dist.metadata.get("Name")
        termui.logger.info("Removing distribution %s", dist_name)
        try:
            remove_path.remove()
            remove_path.commit()
        except OSError as e:
            termui.logger.warn("Error occurred during uninstallation, roll back the changes now.")
            remove_path.rollback()
            raise UninstallError(e) from e

    def overwrite(self, dist: Distribution, candidate: Candidate) -> None:
        """An in-place update to overwrite the distribution with a new candidate"""
        paths_to_remove = self.get_paths_to_remove(dist)
        termui.logger.info("Overwriting distribution %s", dist.metadata.get("Name"))
        installed = self.install(candidate)
        installed_paths = self.get_paths_to_remove(installed)
        # Remove the paths that are in the new distribution
        paths_to_remove.difference_update(installed_paths)
        try:
            paths_to_remove.remove()
            paths_to_remove.commit()
        except OSError as e:
            termui.logger.warn("Error occurred during overwriting, roll back the changes now.")
            paths_to_remove.rollback()
            raise UninstallError(e) from e
