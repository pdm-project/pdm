import time

from resolvelib.reporters import BaseReporter


class SimpleReporter(BaseReporter):
    def __init__(self, requirements):
        self.requirements = requirements
        self.start_at = None

    @staticmethod
    def _print_title(title):
        print("=" * 20 + " " + title + " " + "=" * 20)

    def starting(self):
        """Called before the resolution actually starts.
        """
        self._print_title("Start resolving requirements...")
        self.start_at = time.time()
        for r in self.requirements:
            print(r.as_line())

    def ending_round(self, index, state):
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        self._print_title(f"Ending ROUND {index}")

    def ending(self, state):
        """Called before the resolution ends successfully.
        """
        print("End resolving...")
        elapsed = time.time() - self.start_at
        print("Cost time:", elapsed)
