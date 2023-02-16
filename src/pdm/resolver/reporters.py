from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from resolvelib import BaseReporter

from pdm import termui

if TYPE_CHECKING:
    from resolvelib.resolvers import Criterion, RequirementInformation, State

    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement


logger = logging.getLogger("pdm.termui")


def log_title(title: str) -> None:
    logger.info("=" * 8 + " " + title + " " + "=" * 8)


class SpinnerReporter(BaseReporter):
    def __init__(self, spinner: termui.Spinner, requirements: list[Requirement]) -> None:
        self.spinner = spinner
        self.requirements = requirements
        self._previous: dict[str, Candidate] | None = None

    def starting_round(self, index: int) -> None:
        log_title(f"Starting round {index}")

    def starting(self) -> None:
        """Called before the resolution actually starts."""
        log_title("Start resolving requirements")
        for req in self.requirements:
            logger.info("  " + req.as_line())

    def ending_round(self, index: int, state: State) -> None:
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        log_title(f"Ending round {index}")

    def ending(self, state: State) -> None:
        """Called before the resolution ends successfully."""
        log_title("Resolution Result")
        logger.info("Stable pins:")
        if state.mapping:
            column_width = max(map(len, state.mapping.keys()))
            for k, can in state.mapping.items():
                if not can.req.is_named:
                    can_info = can.req.url
                    if can.req.is_vcs:
                        can_info = f"{can_info}@{can.get_revision()}"
                else:
                    can_info = can.version
                logger.info(f"  {k.rjust(column_width)} {can_info}")

    def adding_requirement(self, requirement: Requirement, parent: Candidate) -> None:
        """Called when adding a new requirement into the resolve criteria.

        :param requirement: The additional requirement to be applied to filter
            the available candidates.
        :param parent: The candidate that requires ``requirement`` as a
            dependency, or None if ``requirement`` is one of the root
            requirements passed in from ``Resolver.resolve()``.
        """
        parent_line = f"(from {parent.name} {parent.version})" if parent else ""
        logger.info("  Adding requirement %s%s", requirement.as_line(), parent_line)

    def rejecting_candidate(self, criterion: Criterion, candidate: Candidate) -> None:
        *others, last = criterion.information
        logger.info(
            "Candidate rejected: %s because it introduces a new requirement %s"
            " that conflicts with other requirements:\n  %s",
            candidate,
            last.requirement.as_line(),  # type: ignore[attr-defined]
            "  \n".join(f"  {req.as_line()} (from {parent if parent else 'project'})" for req, parent in others),
        )

    def pinning(self, candidate: Candidate) -> None:
        """Called when adding a candidate to the potential solution."""
        self.spinner.update(f"Resolving: new pin {candidate.format()}")
        logger.info("Pinning: %s %s", candidate.name, candidate.version)

    def resolving_conflicts(self, causes: list[RequirementInformation]) -> None:
        conflicts = [f"  {req.as_line()} (from {parent if parent else 'project'})" for req, parent in causes]
        logger.info("Conflicts detected: \n%s", "\n".join(conflicts))
