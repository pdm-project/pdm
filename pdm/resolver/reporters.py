from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

import halo

from pdm.iostream import stream

if TYPE_CHECKING:
    from pdm.models.candidates import Candidate
    from pdm.models.requirements import Requirement
    from pdm.resolver.resolvers import State


def log_title(title):
    stream.logger.info("=" * 8 + title + "=" * 8)


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
        log_title("Start resolving requirements")
        for req in self.requirements:
            stream.logger.info("\t" + req.as_line())

    def ending_round(self, index: int, state: State) -> None:
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        log_title("Ending round {}".format(index))
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

        log_title("Resolution Result")
        stream.logger.info("Stable pins:")
        for k, can in state.mapping.items():
            stream.logger.info(f"\t{can.name}\t{can.version}")

    def pin_candidate(self, name, criterion, candidate, child_names):
        self.spinner.text = f"Resolved: {candidate.format()}"
        stream.logger.info("Package constraints:")
        for req, parent in criterion.information:
            stream.logger.info(
                f"\t{req.as_line()}\t<= {getattr(parent, 'name', parent)}"
            )
        stream.logger.info(f"Found candidate\t{candidate.name} {candidate.version}")

    def extract_metadata(self):
        self.spinner.start("Extracting package metadata")
