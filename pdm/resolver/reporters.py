from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from resolvelib import BaseReporter

from pdm import termui

if TYPE_CHECKING:
    from resolvelib.resolvers import RequirementInformation, State  # type: ignore

    from pdm._vendor import halo
    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement


logger = logging.getLogger("pdm.termui")


def log_title(title: str) -> None:
    logger.info("=" * 8 + " " + title + " " + "=" * 8)


class SpinnerReporter(BaseReporter):
    def __init__(
        self, spinner: halo.Halo | termui.DummySpinner, requirements: List[Requirement]
    ) -> None:
        self.spinner = spinner
        self.requirements = requirements
        self._previous: Optional[Dict[str, Candidate]] = None

    def starting_round(self, index: int) -> None:
        # self.spinner.hide_and_write(f"Resolving ROUND {index}")
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
                logger.info(f"  {k.rjust(column_width)} {can.version}")

    def adding_requirement(self, requirement: Requirement, parent: Candidate) -> None:
        """Called when adding a new requirement into the resolve criteria.

        :param requirement: The additional requirement to be applied to filter
            the available candidaites.
        :param parent: The candidate that requires ``requirement`` as a
            dependency, or None if ``requirement`` is one of the root
            requirements passed in from ``Resolver.resolve()``.
        """
        parent_line = f"(from {parent.name} {parent.version})" if parent else ""
        logger.info(f"  Adding requirement {requirement.as_line()}{parent_line}")

    def backtracking(self, candidate: Candidate) -> None:
        """Called when rejecting a candidate during backtracking."""
        logger.info(f"Candidate rejected: {candidate.name} {candidate.version}")

    def pinning(self, candidate: Candidate) -> None:
        """Called when adding a candidate to the potential solution."""
        self.spinner.text = f"Resolving: new pin {candidate.format()}"

    def resolving_conflicts(self, causes: list[RequirementInformation]) -> None:
        conflicts = [
            f"  {req.as_line()} (from {repr(parent) if parent else 'project'})"
            for req, parent in causes
        ]
        logger.info("Conflicts detected: ")
        logger.info("\n".join(conflicts))
