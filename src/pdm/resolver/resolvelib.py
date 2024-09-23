from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, cast

from pdm import termui
from pdm.models.candidates import Candidate
from pdm.models.markers import get_marker
from pdm.models.requirements import FileRequirement, Requirement, strip_extras
from pdm.models.specifiers import PySpecSet
from pdm.project.lockfile import FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA
from pdm.resolver.base import Resolution, Resolver
from pdm.resolver.graph import merge_markers, populate_groups
from pdm.resolver.python import PythonRequirement
from pdm.resolver.reporters import LockReporter, RichLockReporter
from pdm.utils import normalize_name


@dataclass
class RLResolver(Resolver):
    def __post_init__(self) -> None:
        if self.locked_repository is None:
            self.locked_repository = self.project.get_locked_repository()
        supports_env_spec = "env_spec" in inspect.signature(self.project.get_provider).parameters
        if supports_env_spec:
            provider = self.project.get_provider(
                self.update_strategy,
                self.tracked_names,
                direct_minimal_versions=FLAG_DIRECT_MINIMAL_VERSIONS in self.strategies,
                env_spec=self.target,
                locked_repository=self.locked_repository,
            )
        else:  # pragma: no cover
            provider = self.project.get_provider(
                self.update_strategy,
                self.tracked_names,
                direct_minimal_versions=FLAG_DIRECT_MINIMAL_VERSIONS in self.strategies,
                ignore_compatibility=self.target.is_allow_all(),
            )
        if isinstance(self.reporter, LockReporter):
            provider.repository.reporter = self.reporter
        self.provider = provider

    def resolve(self) -> Resolution:
        from pdm.models.repositories import Package

        mapping = self._do_resolve()
        if self.project.enable_write_lockfile:  # type: ignore[has-type]
            if isinstance(self.reporter, RichLockReporter):
                self.reporter.update(info="Fetching hashes for resolved packages")
            self.provider.repository.fetch_hashes(mapping.values())
        if not (env_python := PySpecSet(self.target.requires_python)).is_superset(self.environment.python_requires):
            python_marker = get_marker(env_python.as_marker_string())
            for candidate in mapping.values():
                marker = candidate.req.marker or get_marker("")
                candidate.req = replace(candidate.req, marker=marker & python_marker)
        backend = self.project.backend
        packages: list[Package] = []
        for candidate in mapping.values():
            deps: list[str] = []
            for r in self.provider.fetched_dependencies[candidate.dep_key]:
                if isinstance(r, FileRequirement) and r.path:
                    try:
                        if r.path.is_absolute():
                            r.path = Path(os.path.normpath(r.path)).relative_to(os.path.normpath(self.project.root))
                    except ValueError:
                        pass
                    else:
                        r.url = backend.relative_path_to_url(r.path.as_posix())
                deps.append(r.as_line())
            packages.append(Package(candidate, deps, candidate.summary))
        return Resolution(packages, self.provider.repository.collected_groups)

    def _do_resolve(self) -> dict[str, Candidate]:
        from resolvelib import Resolver as _Resolver

        resolver_class = cast("type[_Resolver]", getattr(self.project.core, "resolver_class", _Resolver))
        resolver = resolver_class(self.provider, self.reporter)
        provider = self.provider
        repository = self.provider.repository
        target = self.target
        python_req = PythonRequirement.from_pyspec_set(PySpecSet(target.requires_python))
        requirements: list[Requirement] = [python_req, *self.requirements]
        max_rounds = self.project.config["strategy.resolve_max_rounds"]
        result = resolver.resolve(requirements, max_rounds)

        if repository.has_warnings:
            self.project.core.ui.info(
                "Use `-q/--quiet` to suppress these warnings, or ignore them per-package with "
                r"`ignore_package_warnings` config in \[tool.pdm] table.",
                verbosity=termui.Verbosity.NORMAL,
            )

        mapping = cast(Dict[str, Candidate], result.mapping)
        mapping.pop("python", None)

        local_name = normalize_name(self.project.name) if self.project.is_distribution else None
        for key, candidate in list(mapping.items()):
            if key is None:
                continue
            # For source distribution whose name can only be determined after it is built,
            # the key in the resolution map and criteria should be updated.
            if key.startswith(":empty:"):
                new_key = provider.identify(candidate)
                mapping[new_key] = mapping.pop(key)
                result.criteria[new_key] = result.criteria.pop(key)  # type: ignore[attr-defined]

        if FLAG_INHERIT_METADATA in self.strategies:
            all_markers = merge_markers(result)
            populate_groups(result)
        else:
            all_markers = {}

        for key, candidate in list(mapping.items()):
            if key in all_markers:
                marker = all_markers[key]
                if marker.is_empty():
                    del mapping[key]
                    continue
                candidate.req = replace(candidate.req, marker=None if marker.is_any() else marker)

            if not self.keep_self and strip_extras(key)[0] == local_name:
                del mapping[key]

        return mapping
