import contextlib
import functools
import os
import traceback
from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Dict, List, Tuple

from click import progressbar
from pip._vendor.pkg_resources import Distribution, safe_name

from pdm.exceptions import InstallationError
from pdm.installers.installers import Installer, is_dist_editable
from pdm.iostream import stream
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.requirements import strip_extras


class DummyFuture:
    _NOT_SET = object()

    def __init__(self):
        self._result = self._NOT_SET
        self._exc = None

    def set_result(self, result):
        self._result = result

    def set_exception(self, exc):
        self._exc = exc

    def result(self):
        return self._result

    def exception(self):
        return self._exc

    def add_done_callback(self, func):
        func(self)


class DummyExecutor:
    """A synchronous pool class to mimick ProcessPoolExecuter's interface.
    functions are called and awaited for the result
    """

    def submit(self, func, *args, **kwargs):
        future = DummyFuture()
        try:
            future.set_result(func(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        return


class Synchronizer:
    """Synchronize the working set with given installation candidates"""

    BAR_FILLED_CHAR = "=" if os.name == "nt" else "▉"
    BAR_EMPTY_CHAR = " "
    RETRY_TIMES = 1
    SEQUENTIAL_PACKAGES = ("pip", "setuptools", "wheel")

    def __init__(
        self, candidates: Dict[str, Candidate], environment: Environment,
    ) -> None:
        self.candidates = candidates
        self.environment = environment
        self.parallel = environment.project.config["parallel_install"]
        self.all_candidates = environment.project.get_locked_candidates("__all__")
        self.working_set = environment.get_working_set()

    @contextlib.contextmanager
    def progressbar(self, label: str, total: int):
        bar = progressbar(
            length=total,
            fill_char=stream.green(self.BAR_FILLED_CHAR),
            empty_char=self.BAR_EMPTY_CHAR,
            show_percent=False,
            show_pos=True,
            label=label,
            bar_template="%(label)s %(bar)s %(info)s",
        )
        if self.parallel:
            executor = ThreadPoolExecutor()
        else:
            executor = DummyExecutor()
        with executor:
            try:
                yield bar, executor
            except KeyboardInterrupt:
                pass

    def get_installer(self) -> Installer:
        return Installer(self.environment)

    def compare_with_working_set(self) -> Tuple[List[str], List[str], List[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.working_set
        to_update, to_remove = [], []
        candidates = self.candidates.copy()
        environment = self.environment.marker_environment
        for key, dist in working_set.items():
            if key in candidates:
                can = candidates.pop(key)
                if can.marker and not can.marker.evaluate(environment):
                    to_remove.append(key)
                elif not is_dist_editable(dist) and dist.version != can.version:
                    # XXX: An editable distribution is always considered as consistent.
                    to_update.append(key)
            elif key not in self.all_candidates and key != "wheel":
                # Remove package only if it is not required by any section
                to_remove.append(key)
        to_add = list(
            {
                strip_extras(name)[0]
                for name, can in candidates.items()
                if not (can.marker and not can.marker.evaluate(environment))
                and strip_extras(name)[0] not in working_set
            }
        )
        return to_add, to_update, to_remove

    def install_candidate(self, key: str) -> Candidate:
        """Install candidate"""
        can = self.candidates[key]
        installer = self.get_installer()
        installer.install(can)
        return can

    def update_candidate(self, key: str) -> Tuple[Distribution, Candidate]:
        """Update candidate"""
        can = self.candidates[key]
        dist = self.working_set[safe_name(can.name).lower()]
        installer = self.get_installer()
        installer.uninstall(dist)
        installer.install(can)
        return dist, can

    def remove_distribution(self, key: str) -> Distribution:
        """Remove distributions with given names.

        :param distributions: a list of names to be removed.
        """
        installer = self.get_installer()
        dist = self.working_set[key]
        installer.uninstall(dist)
        return dist

    def _print_section_title(
        self, action: str, number_of_packages: int, dry_run: bool
    ) -> None:
        plural = "s" if number_of_packages > 1 else ""
        verb = "will be" if dry_run else "are" if plural else "is"
        stream.echo(f"{number_of_packages} package{plural} {verb} {action}:")

    def summarize(self, result, dry_run=False):
        added, updated, removed = result["add"], result["update"], result["remove"]
        if added:
            stream.echo("\n")
            self._print_section_title("installed", len(added), dry_run)
            for item in sorted(added, key=lambda x: x.name):
                stream.echo(f"  - {item.format()}")
        if updated:
            stream.echo("\n")
            self._print_section_title("updated", len(updated), dry_run)
            for old, can in sorted(updated, key=lambda x: x[1].name):
                stream.echo(
                    f"  - {stream.green(can.name, bold=True)} "
                    f"{stream.yellow(old.version)} "
                    f"-> {stream.yellow(can.version)}"
                )
        if removed:
            stream.echo("\n")
            self._print_section_title("removed", len(removed), dry_run)
            for dist in sorted(removed, key=lambda x: x.key):
                stream.echo(
                    f"  - {stream.green(dist.key, bold=True)} "
                    f"{stream.yellow(dist.version)}"
                )

    def synchronize(self, clean: bool = True, dry_run: bool = False) -> None:
        """Synchronize the working set with pinned candidates.

        :param clean: Whether to remove unneeded packages, defaults to True.
        :param dry_run: If set to True, only prints actions without actually do them.
        """
        to_add, to_update, to_remove = self.compare_with_working_set()
        if not clean:
            to_remove = []
        lists_to_check = [to_add, to_update, to_remove]
        if not any(lists_to_check):
            stream.echo("All packages are synced to date, nothing to do.")
            return

        if dry_run:
            result = dict(
                add=[self.candidates[key] for key in to_add],
                update=[
                    (self.working_set[key], self.candidates[key]) for key in to_update
                ],
                remove=[self.working_set[key] for key in to_remove],
            )
            self.summarize(result, dry_run)
            return

        handlers = {
            "add": self.install_candidate,
            "update": self.update_candidate,
            "remove": self.remove_distribution,
        }

        result = defaultdict(list)
        failed = defaultdict(list)
        to_do = {"add": to_add, "update": to_update, "remove": to_remove}
        # Keep track of exceptions
        errors = []

        def update_progress(future, section, key, bar):
            if future.exception():
                failed[section].append(key)
                errors.append(future.exception())
            else:
                result[section].append(future.result())
            bar.update(1)

        with stream.logging("install"):
            with self.progressbar(
                "Synchronizing:", sum(len(l) for l in to_do.values())
            ) as (bar, pool):
                # First update packages, then remove and add
                for section in sorted(to_do, reverse=True):
                    # setup toolkits are installed sequentially before other packages.
                    for key in sorted(
                        to_do[section], key=lambda x: x not in self.SEQUENTIAL_PACKAGES
                    ):
                        future = pool.submit(handlers[section], key)
                        future.add_done_callback(
                            functools.partial(
                                update_progress, section=section, key=key, bar=bar
                            )
                        )
                        if key in self.SEQUENTIAL_PACKAGES:
                            future.result()

            # Retry for failed items
            for i in range(self.RETRY_TIMES):
                if not any(failed.values()):
                    break
                stream.echo(
                    stream.yellow("\nSome packages failed to install, retrying...")
                )
                to_do = failed
                failed = defaultdict(list)
                errors.clear()
                with self.progressbar(
                    f"Retrying ({i + 1}/{self.RETRY_TIMES}):",
                    sum(len(l) for l in to_do.values()),
                ) as (bar, pool):

                    for section in sorted(to_do, reverse=True):
                        for key in sorted(
                            to_do[section],
                            key=lambda x: x not in self.SEQUENTIAL_PACKAGES,
                        ):
                            future = pool.submit(handlers[section], key)
                            future.add_done_callback(
                                functools.partial(
                                    update_progress, section=section, key=key, bar=bar
                                )
                            )
                            if key in self.SEQUENTIAL_PACKAGES:
                                future.result()
            # End installation
            self.summarize(result)
            if not any(failed.values()):
                return
            stream.echo("\n")
            error_msg = []
            if failed["add"] + failed["update"]:
                error_msg.append(
                    "Installation failed: "
                    f"{', '.join(failed['add'] + failed['update'])}"
                )
            if failed["remove"]:
                error_msg.append(f"Removal failed: {', '.join(failed['remove'])}")
            for error in errors:
                stream.echo(
                    "".join(
                        traceback.format_exception(
                            type(error), error, error.__traceback__
                        )
                    ),
                    verbosity=stream.DEBUG,
                )
            raise InstallationError("\n" + "\n".join(error_msg))
