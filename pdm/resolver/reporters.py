from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

import halo

from pdm.iostream import stream

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement
    from pdm.resolver.resolvers import State


class SpinnerReporter:
    def __init__(self, spinner: halo.Halo, requirements: List[Requirement]) -> None:
        self.spinner = spinner
        self.requirements = requirements
        self._previous = None  # type: Optional[Dict[str, Candidate]]

    def starting_round(self, index: int) -> None:
        # self.spinner.hide_and_write(f"Resolving ROUND {index}")
        pass

    def starting(self) -> None:
        """Called before the resolution actually starts.
        """
        stream.logger.info("Start resolving requirements")
        stream.logger.info("============================")
        for req in self.requirements:
            stream.logger.info("\t" + req.as_line())

    def ending_round(self, index: int, state: State) -> None:
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        stream.logger.info("Ending round {}".format(index))
        stream.logger.info("===============")
        if not self._previous:
            added = state.mapping.values()
            changed = []
        else:
            added = [can for k, can in state.mapping.items() if k not in self._previous]
            changed = [
                (self._previous[k], can)
                for k, can in state.mapping.items()
                if k in self._previous and self._previous[k] != can
            ]
        if added:
            stream.logger.info("New pins:")
            for can in added:
                stream.logger.info(f"\t{can.name}\t{can.version}")
        if changed:
            stream.logger.info("Changed pins:")
            for (old, new) in changed:
                stream.logger.info(f"\t{new.name}\t{old.version} -> {new.version}")
        self._previous = state.mapping

    def ending(self, state: State) -> None:
        """Called before the resolution ends successfully.
        """
        self.spinner.stop_and_persist(text="Finish resolving")

        stream.logger.info("Resolution Result")
        stream.logger.info("=================")
        stream.logger.info("Stable pins:")
        for k, can in state.mapping.items():
            stream.logger.info(f"\t{can.name}\t{can.version}")

    def resolve_criteria(self, name):
        self.spinner.text = f"Resolving {stream.green(name, bold=True)}"
        stream.logger.info(f"\tResolving package\t{name}")

    def pin_candidate(self, name, criterion, candidate, child_names):
        self.spinner.text = f"Resolved: {candidate.format()}"
        stream.logger.info(f"\tFound candidate\t{candidate.name}\t{candidate.version}")

    def extract_metadata(self):
        self.spinner.start("Extracting package metadata")
