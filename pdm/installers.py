import importlib
import subprocess
from typing import Dict, List, Tuple

import distlib.scripts
from distlib.wheel import Wheel
from pip._vendor.pkg_resources import Distribution, EggInfoDistribution, safe_name
from pip_shims import shims
from vistir import cd

from pdm.context import context
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment
from pdm.models.requirements import parse_requirement, strip_extras


def _is_dist_editable(dist: Distribution) -> bool:
    return isinstance(dist, EggInfoDistribution)


def format_dist(dist: Distribution) -> str:
    formatter = "{version}{path}"
    path = ""
    if _is_dist_editable(dist):
        path = f" (-e {dist.location})"
    return formatter.format(version=context.io.yellow(dist.version), path=path)


def _print_list_information(word, items, dry=False):
    if dry:
        word = "to be " + word
    template = "{count} package{suffix} {word}: {items}"
    suffix = "s" if len(items) > 1 else ""
    count = len(items)
    items = ", ".join(str(context.io.green(item, bold=True)) for item in items)
    print(template.format(count=count, suffix=suffix, word=word, items=items))


class Installer:  # pragma: no cover
    """The installer that performs the installation and uninstallation actions."""

    def __init__(self, environment: Environment, auto_confirm: bool = True) -> None:
        self.environment = environment
        self.auto_confirm = auto_confirm

    def install(self, candidate: Candidate) -> None:
        candidate.get_metadata()
        if candidate.req.editable:
            self.install_editable(candidate.ireq)
        else:
            self.install_wheel(candidate.wheel)

    def install_wheel(self, wheel: Wheel) -> None:
        paths = self.environment.get_paths()
        scripts = distlib.scripts.ScriptMaker(None, None)
        scripts.executable = self.environment.python_executable
        scripts.script_template = scripts.script_template.replace(
            "import sys",
            "import sys\nsys.path.insert(0, {!r})".format(paths["platlib"]),
        )
        wheel.install(paths, scripts)

    def install_editable(self, ireq: shims.InstallRequirement) -> None:
        setup_path = ireq.setup_py_path
        paths = self.environment.get_paths()
        install_script = importlib.import_module(
            "pdm._editable_install"
        ).__file__.rstrip("co")
        install_args = [
            self.environment.python_executable,
            "-u",
            install_script,
            setup_path,
            paths["prefix"],
        ]
        with self.environment.activate(), cd(ireq.unpacked_source_directory):
            try:
                result = subprocess.run(install_args, capture_output=True, check=True)
            except subprocess.CalledProcessError as ex:
                result = ex
        context.io.echo(result.stdout, verbosity=context.io.DETAIL)
        if result.stderr:
            context.io.echo(result.stderr, err=True, verbosity=context.io.DETAIL)
        if result.returncode:
            raise result from None

    def uninstall(self, dist: Distribution) -> None:
        req = parse_requirement(dist.project_name)
        if _is_dist_editable(dist):
            ireq = shims.install_req_from_editable(dist.location)
        else:
            ireq = shims.install_req_from_line(dist.project_name)
        ireq.req = req

        with self.environment.activate():
            pathset = ireq.uninstall(auto_confirm=self.auto_confirm)
            if pathset:
                pathset.commit()


class Synchronizer:
    """Synchronize the working set with given installation candidates"""

    def __init__(
        self, candidates: Dict[str, Candidate], environment: Environment
    ) -> None:
        self.candidates = candidates
        self.environment = environment

    def get_installer(self) -> Installer:
        return Installer(self.environment)

    def compare_with_working_set(self) -> Tuple[List[str], List[str], List[str]]:
        """Compares the candidates and return (to_add, to_update, to_remove)"""
        working_set = self.environment.get_working_set()
        to_update, to_remove = [], []
        candidates = self.candidates.copy()
        environment = self.environment.marker_environment
        for key, dist in working_set.items():
            if key not in candidates:
                to_remove.append(key)
            else:
                can = candidates.pop(key)
                if can.marker and not can.marker.evaluate(environment):
                    to_remove.append(key)
                elif not _is_dist_editable(dist) and dist.version != can.version:
                    # XXX: An editable distribution is always considered as consistent.
                    to_update.append(key)
        to_add = list(
            {
                strip_extras(name)[0]
                for name, can in candidates.items()
                if not (can.marker and not can.marker.evaluate(environment))
                and strip_extras(name)[0] not in working_set
            }
        )
        return to_add, to_update, to_remove

    def install_candidates(
        self, candidates: List[Candidate], update: bool = False
    ) -> None:
        """Install candidates.

        :param candidates: a list of candidates to be installed.
        :param update: whether to remove existed packages.
        """
        installer = self.get_installer()
        working_set = self.environment.get_working_set()
        for can in candidates:
            if update:
                dist = working_set[safe_name(can.name).lower()]
                context.io.echo(
                    f"Updating {context.io.green(can.name, bold=True)} "
                    f"{context.io.yellow(dist.version)} -> "
                    f"{context.io.yellow(can.version)}"
                )
                installer.uninstall(dist)
            else:
                context.io.echo(f"Installing {can.format()}...")
            installer.install(can)

    def remove_distributions(self, distributions: List[str]) -> None:
        """Remove distributions with given names.

        :param distributions: a list of names to be removed.
        """
        installer = self.get_installer()
        working_set = self.environment.get_working_set()
        for name in distributions:
            dist = working_set[name]
            context.io.echo(
                f"Uninstalling: {context.io.green(name, bold=True)} "
                f"{context.io.yellow(dist.version)}"
            )
            installer.uninstall(dist)

    def synchronize(self, clean: bool = True, dry_run: bool = False) -> None:
        """Synchronize the working set with pinned candidates.

        :param clean: Whether to remove unneeded packages, defaults to True.
        :param dry_run: If set to True, only prints actions without actually do them.
        """
        to_add, to_update, to_remove = self.compare_with_working_set()
        lists_to_check = [to_add, to_update]
        if clean:
            lists_to_check.append(to_remove)
        if not any(lists_to_check):
            context.io.echo("All packages are synced to date, nothing to do.")
            return
        if to_add and not dry_run:
            self.install_candidates(
                [can for k, can in self.candidates.items() if k in to_add]
            )
        if to_update and not dry_run:
            self.install_candidates(
                [can for k, can in self.candidates.items() if k in to_update],
                update=True,
            )
        if clean and to_remove and not dry_run:
            self.remove_distributions(to_remove)
        context.io.echo()
        if to_add:
            _print_list_information("added", to_add, dry_run)
        if to_update:
            _print_list_information("updated", to_update, dry_run)
        if clean and to_remove:
            _print_list_information("removed", to_remove, dry_run)
