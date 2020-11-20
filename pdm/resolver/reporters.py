from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from resolvelib import BaseReporter

from pdm.iostream import stream

if TYPE_CHECKING:
    from resolvelib.resolvers import State

    from pdm._vendor import halo
    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement


def log_title(title):
    stream.logger.info("=" * 8 + " " + title + " " + "=" * 8)


class SpinnerReporter(BaseReporter):
    def __init__(self, spinner: halo.Halo, requirements: List[Requirement]) -> None:
        self.spinner = spinner
        self.requirements = requirements
        self._previous = None  # type: Optional[Dict[str, Candidate]]

    def starting_round(self, index: int) -> None:
        # self.spinner.hide_and_write(f"Resolving ROUND {index}")
        pass

    def starting(self) -> None:
        """Called before the resolution actually starts."""
        log_title("Start resolving requirements")
        for req in self.requirements:
            stream.logger.info("\t" + req.as_line())

    def ending_round(self, index: int, state: State) -> None:
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        log_title("Ending round {}".format(index))

    def ending(self, state: State) -> None:
        """Called before the resolution ends successfully."""
        self.spinner.stop_and_persist(text="Finish resolving")

        log_title("Resolution Result")
        stream.logger.info("Stable pins:")
        if state.mapping:
            column_width = max(map(len, state.mapping.keys()))
            for k, can in state.mapping.items():
                stream.logger.info(f"  {k.rjust(column_width)} {can.version}")

    def extract_metadata(self):
        self.spinner.start("Extracting package metadata")

    def adding_requirement(self, requirement: Requirement, parent: Candidate) -> None:
        """Called when adding a new requirement into the resolve criteria.

        :param requirement: The additional requirement to be applied to filter
            the available candidaites.
        :param parent: The candidate that requires ``requirement`` as a
            dependency, or None if ``requirement`` is one of the root
            requirements passed in from ``Resolver.resolve()``.
        """
        parent_line = f"(from {parent.name} {parent.version})" if parent else ""
        stream.logger.info(f"\tAdding requirement {requirement.as_line()}{parent_line}")

    def backtracking(self, candidate: Candidate) -> None:
        """Called when rejecting a candidate during backtracking."""
        stream.logger.info(f"Candidate rejected: {candidate.name} {candidate.version}")
        stream.logger.info("Backtracking...")

    def pinning(self, candidate: Candidate) -> None:
        """Called when adding a candidate to the potential solution."""
        self.spinner.text = "Resolving: " + candidate.format()
        stream.logger.info(f"\tNew pin: {candidate.name} {candidate.version}")
