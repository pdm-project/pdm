import os
import subprocess
from typing import Dict, List, Tuple

from pip._vendor.pkg_resources import Distribution, WorkingSet
from pip_shims import shims

import distlib.scripts
from distlib.wheel import Wheel
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment

SETUPTOOLS_SHIM = (
    "import setuptools, tokenize;__file__=%r;"
    "f=getattr(tokenize, 'open', open)(__file__);"
    "code=f.read().replace('\\r\\n', '\\n');"
    "f.close();"
    "exec(compile(code, __file__, 'exec'))"
)


def _is_dist_editable(working_set: WorkingSet, dist: Distribution) -> bool:
    for entry in working_set.entries:
        if os.path.isfile(os.path.join(entry, dist.project_name + ".egg-link")):
            return True
    return False


def _print_list_information(word, items):
    template = "{count} package{suffix} {word}: {items}"
    suffix = "s" if len(items) > 1 else ""
    count = len(items)
    items = ", ".join(items)
    print(template.format(count=count, suffix=suffix, word=word, items=items))


class Installer:
    # TODO: Support PEP 517 builds

    def __init__(self, environment: Environment, auto_confirm: bool = True) -> None:
        self.environment = environment
        self.auto_confirm = auto_confirm

    def install(self, candidate: Candidate) -> None:
        print(f"Installing {candidate.name} {candidate.version}...")
        candidate.get_metadata()
        if candidate.wheel:
            self.install_wheel(candidate.wheel)
        else:
            self.install_editable(candidate.ireq)

    def install_wheel(self, wheel: Wheel) -> None:
        paths = self.environment.get_paths()
        scripts = distlib.scripts.ScriptMaker(None, None)
        scripts.executable = self.environment.python_executable
        scripts.script_template = scripts.script_template.replace(
            "import sys",
            "import sys; sys.path.insert(0, {!r})".format(paths["platlib"]),
        )
        wheel.install(paths, scripts)

    def install_editable(self, ireq: shims.InstallRequirement) -> None:
        setup_path = ireq.setup_py_path
        paths = self.environment.get_paths()
        old_pwd = os.getcwd()
        install_args = [
            self.environment.python_executable,
            "-u",
            "-c",
            SETUPTOOLS_SHIM % setup_path,
            "develop",
            "--install-dir={}".format(paths["platlib"]),
            "--no-deps",
            "--prefix={}".format(paths["prefix"]),
            "--script-dir={}".format(paths["scripts"]),
            "--site-dirs={}".format(paths["platlib"]),
        ]
        os.chdir(ireq.source_dir)
        try:
            with self.environment.activate():
                subprocess.check_call(install_args)
        finally:
            os.chdir(old_pwd)

    def uninstall(self, name: str) -> None:
        working_set = self.environment.get_working_set()
        ireq = shims.install_req_from_line(name)
        print(f"Uninstalling: {name} {working_set.by_key[name].version}")

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
        for dist in working_set:
            if dist.key not in candidates:
                to_remove.append(dist.key)
            else:
                can = candidates.pop(dist.key)
                if (
                    not _is_dist_editable(working_set, dist)
                    and dist.version != can.version
                ):
                    # XXX: An editable distribution is always considered as consistent.
                    to_update.append(dist.key)
        to_add = list(candidates)
        return to_add, to_update, to_remove

    def install_candidates(self, candidates: List[Candidate]) -> None:
        installer = self.get_installer()
        for can in candidates:
            installer.install(can)

    def remove_distributions(self, distributions: List[str]) -> None:
        installer = self.get_installer()
        for name in distributions:
            installer.uninstall(name)

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
            print("All packages are synced to date, nothing to do.")
            return
        if to_add and not dry_run:
            self.install_candidates(
                [can for k, can in self.candidates.items() if k in to_add]
            )
        if to_update and not dry_run:
            self.install_candidates(
                [can for k, can in self.candidates.items() if k in to_update]
            )
        if clean and to_remove and not dry_run:
            self.remove_distributions(to_remove)
        print()
        if to_add:
            _print_list_information("added", to_add)
        if to_update:
            _print_list_information("updated", to_update)
        if clean and to_remove:
            _print_list_information("removed", to_remove)
