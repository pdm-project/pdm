from __future__ import annotations

import dataclasses
from functools import cached_property
from typing import Collection, Iterable

from pdm import termui
from pdm.compat import Distribution
from pdm.environments import BaseEnvironment
from pdm.exceptions import BuildError
from pdm.installers.manager import InstallManager
from pdm.models.candidates import Candidate
from pdm.models.repositories import Package
from pdm.models.requirements import FileRequirement, Requirement, parse_requirement, strip_extras
from pdm.utils import is_editable, normalize_name


def editables_candidate(environment: BaseEnvironment) -> Candidate | None:
    """Return a candidate for `editables` package"""
    with environment.get_finder() as finder:
        best = finder.find_best_match("editables").best
    return None if best is None else Candidate.from_installation_candidate(best, parse_requirement("editables"))


class BaseSynchronizer:
    """Synchronize the working set with given installation candidates

    :param candidates: a dict of candidates to be installed
    :param environment: the environment associated with the project
    :param clean: clean unneeded packages
    :param dry_run: only prints summary but do not install or uninstall
    :param retry_times: retry times when installation failed
    :param install_self: whether to install self project
    :param no_editable: if True, override all editable installations,
        if a list, override editables with the given names
    :param use_install_cache: whether to use install cache
    :param reinstall: whether to reinstall all packages
    :param only_keep: If true, only keep the selected candidates
    :param fail_fast: If true, stop the installation on first error
    """

    SEQUENTIAL_PACKAGES = ("pip", "setuptools", "wheel")

    def __init__(
        self,
        environment: BaseEnvironment,
        candidates: dict[str, Candidate] | None = None,
        clean: bool = False,
        dry_run: bool = False,
        retry_times: int = 1,
        install_self: bool = False,
        no_editable: bool | Collection[str] = False,
        reinstall: bool = False,
        only_keep: bool = False,
        fail_fast: bool = False,
        use_install_cache: bool | None = None,
        packages: Iterable[Package] = (),
        requirements: Iterable[Requirement] = (),
    ) -> None:
        if candidates:  # pragma: no cover
            self.requested_candidates = candidates
        else:
            self.requested_candidates = {entry.candidate.identify(): entry.candidate for entry in packages}
        self.environment = environment
        self.clean = clean
        self.dry_run = dry_run
        self.retry_times = retry_times
        self.no_editable = no_editable
        self.install_self = install_self
        if use_install_cache is None:
            use_install_cache = bool(environment.project.config["install.cache"])
        self.use_install_cache = use_install_cache
        self.reinstall = reinstall
        self.only_keep = only_keep
        self.parallel = environment.project.config["install.parallel"]
        self.fail_fast = fail_fast

        self.working_set = environment.get_working_set()
        self.ui = environment.project.core.ui
        self._manager: InstallManager | None = None
        self.packages = packages
        self.requirements = list(requirements)

    @cached_property
    def self_candidate(self) -> Candidate:
        """Return the candidate for self project"""
        return self.environment.project.make_self_candidate(not self.no_editable)

    @cached_property
    def candidates(self) -> dict[str, Candidate]:
        """Return the candidates to be installed"""
        candidates = self.requested_candidates.copy()
        if isinstance(self.no_editable, Collection):
            keys = self.no_editable
        elif self.no_editable:
            keys = candidates.keys()
        else:
            keys = []
            if self.should_install_editables():
                # Install `editables` as well as required by self project
                editables = editables_candidate(self.environment)
                if editables is not None:
                    candidates["editables"] = editables
        for key in keys:
            if key in candidates and candidates[key].req.editable:
                candidate = candidates[key]
                # Create a new candidate with editable=False
                req = dataclasses.replace(candidate.req, editable=False)
                candidates[key] = candidate.copy_with(req)
        return candidates

    def should_install_editables(self) -> bool:
        """Return whether to add editables"""
        if not self.install_self or "editables" in self.requested_candidates:
            return False
        # As editables may be added by the backend, we need to check the metadata
        try:
            metadata = self.self_candidate.prepare(self.environment).metadata
        except BuildError:
            return False
        return any(req.startswith("editables") for req in metadata.requires or [])

    @property
    def manager(self) -> InstallManager:
        if not self._manager:
            self._manager = self.get_manager(rename_pth=True)
        return self._manager

    def get_manager(self, rename_pth: bool = False) -> InstallManager:
        return self.environment.project.core.install_manager_class(
            self.environment, use_install_cache=self.use_install_cache, rename_pth=rename_pth
        )

    @property
    def self_key(self) -> str | None:
        if not self.install_self:
            return None
        name = self.environment.project.name
        if name:
            return normalize_name(name)
        return name

    def _should_update(self, dist: Distribution, can: Candidate) -> bool:
        """Check if the candidate should be updated"""
        backend = self.environment.project.backend
        if self.reinstall or can.req.editable:  # Always update if incoming is editable
            return True
        if is_editable(dist):  # only update editable if no_editable is True
            return bool(self.no_editable)
        if not can.req.is_named:
            dreq = Requirement.from_dist(dist)
            if not isinstance(dreq, FileRequirement):
                return True
            url = dreq.get_full_url()
            if dreq.is_local_dir:
                # We don't know whether a local dir has been changed, always update
                return True
            assert can.link is not None
            return url != backend.expand_line(can.link.url_without_fragment)
        specifier = can.req.as_pinned_version(can.version).specifier
        return not specifier.contains(dist.version, prereleases=True)

    def compare_with_working_set(self) -> tuple[list[str], list[str], list[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.working_set
        candidates = self.candidates.copy()
        to_update: set[str] = set()
        to_remove: set[str] = set()
        to_add: set[str] = set()
        locked_repository = self.environment.project.get_locked_repository()
        all_candidate_keys = list(locked_repository.all_candidates)

        for key, dist in working_set.items():
            if key == self.self_key and self.install_self:
                continue
            if key in candidates:
                can = candidates.pop(key)
                if self._should_update(dist, can):
                    if working_set.is_owned(key):
                        to_update.add(key)
                    else:
                        to_add.add(key)
            elif (
                (self.only_keep or self.clean and key not in all_candidate_keys)
                and key not in self.SEQUENTIAL_PACKAGES
                and working_set.is_owned(key)
            ):
                # Remove package only if it is not required by any group
                # Packages for packaging will never be removed
                to_remove.add(key)
        to_add.update(
            strip_extras(name)[0]
            for name, _ in candidates.items()
            if name != self.self_key and strip_extras(name)[0] not in working_set
        )
        return (sorted(to_add), sorted(to_update), sorted(to_remove))

    def synchronize(self) -> None:
        """Synchronize the working set with pinned candidates."""
        to_add, to_update, to_remove = self.compare_with_working_set()
        manager = self.get_manager()
        for key in to_add:
            can = self.candidates[key]
            termui.logger.info("Installing %s@%s...", key, can.version)
            manager.install(can)
        for key in to_update:
            can = self.candidates[key]
            dist = self.working_set[strip_extras(key)[0]]
            dist_version = dist.version
            termui.logger.info("Updating %s@%s -> %s...", key, dist_version, can.version)
            manager.uninstall(dist)
            manager.install(can)
        for key in to_remove:
            dist = self.working_set[key]
            termui.logger.info("Removing %s@%s...", key, dist.version)
            manager.uninstall(dist)
        termui.logger.info("Synchronization complete.")
