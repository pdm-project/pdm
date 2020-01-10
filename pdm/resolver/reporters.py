from resolvelib.reporters import BaseReporter


class SimpleReporter(BaseReporter):
    def starting(self):
        """Called before the resolution actually starts.
        """
        print("Start resolving...")

    def starting_round(self, index):
        """Called before each round of resolution starts.

        The index is zero-based.
        """
        print(f"Starting ROUND {index}")

    def ending_round(self, index, state):
        """Called before each round of resolution ends.

        This is NOT called if the resolution ends at this round. Use `ending`
        if you want to report finalization. The index is zero-based.
        """
        print(f"Ending ROUND {index}")

    def ending(self, state):
        """Called before the resolution ends successfully.
        """
        print("End resolving...")
