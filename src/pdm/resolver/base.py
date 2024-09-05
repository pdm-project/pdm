from __future__ import annotations

import abc
import typing as t
from dataclasses import dataclass, field

from resolvelib import BaseReporter

from pdm.models.candidates import Candidate
from pdm.models.repositories import LockedRepository

if t.TYPE_CHECKING:
    from pdm.environments import BaseEnvironment
    from pdm.models.markers import EnvSpec
    from pdm.models.repositories import Package
    from pdm.models.requirements import Requirement
    from pdm.project import Project


class Resolution(t.NamedTuple):
    """The resolution result."""

    packages: t.Iterable[Package]
    """The list of pinned packages with dependencies."""
    collected_groups: set[str]
    """The list of collected groups."""

    @property
    def candidates(self) -> dict[str, Candidate]:
        return {entry.candidate.identify(): entry.candidate for entry in self.packages}


@dataclass
class Resolver(abc.ABC):
    """The resolver class."""

    environment: BaseEnvironment
    """The environment instance."""
    requirements: list[Requirement]
    """The list of requirements to resolve."""
    update_strategy: str
    """The update strategy to use [all|reuse|eager|reuse-installed]."""
    strategies: set[str]
    """The list of strategies to use."""
    target: EnvSpec
    """The target environment specification."""
    tracked_names: t.Collection[str] = ()
    """The list of tracked names."""
    keep_self: bool = False
    """Whether to keep self dependencies."""
    locked_repository: LockedRepository | None = None
    """The repository with all locked dependencies."""
    reporter: BaseReporter = field(default_factory=BaseReporter)
    """The reporter to use."""

    @abc.abstractmethod
    def resolve(self) -> Resolution:
        """Resolve the requirements."""
        pass

    @property
    def project(self) -> Project:
        """The project instance."""
        return self.environment.project
