from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import distlib.scripts
from pip._vendor.pkg_resources import EggInfoDistribution

from pdm import termui
from pdm.models import pip_shims
from pdm.models.builders import EnvBuilder
from pdm.models.requirements import parse_requirement

if TYPE_CHECKING:
    from distlib.wheel import Wheel
    from pip._vendor.pkg_resources import Distribution

    from pdm.models.candidates import Candidate
    from pdm.models.environment import Environment


def is_dist_editable(dist: Distribution) -> bool:
    return isinstance(dist, EggInfoDistribution) or getattr(dist, "editable", False)


def format_dist(dist: Distribution) -> str:
    formatter = "{version}{path}"
    path = ""
    if is_dist_editable(dist):
        path = f" (-e {dist.location})"
    return formatter.format(version=termui.yellow(dist.version), path=path)


class Installer:  # pragma: no cover
    """The installer that performs the installation and uninstallation actions."""

    def __init__(self, environment: Environment, auto_confirm: bool = True) -> None:
        self.environment = environment
        self.auto_confirm = auto_confirm
        # XXX: Patch pip to make it work under multi-thread mode
        pip_shims.pip_logging._log_state.indentation = 0

    def install(self, candidate: Candidate) -> None:
        candidate.get_metadata(allow_all_wheels=False, raising=True)
        if candidate.req.editable:
            self.install_editable(candidate.ireq)
        else:
            self.install_wheel(candidate.wheel)

    def install_wheel(self, wheel: Wheel) -> None:
        paths = self.environment.get_paths()
        maker = distlib.scripts.ScriptMaker(None, None)
        maker.variants = set(("",))
        maker.executable = self.environment.python_executable
        wheel.install(paths, maker)

    def install_editable(self, ireq: pip_shims.InstallRequirement) -> None:
        setup_path = ireq.setup_py_path
        paths = self.environment.get_paths()
        install_script = importlib.import_module(
            "pdm.installers._editable_install"
        ).__file__.rstrip("co")
        install_args = [
            self.environment.python_executable,
            "-u",
            install_script,
            setup_path,
            paths["prefix"],
            paths["purelib"],
            paths["scripts"],
        ]
        with EnvBuilder(ireq.unpacked_source_directory, self.environment) as builder:
            builder.install(["setuptools"])
            extra_env = {"INJECT_SITE": "1"} if not self.environment.is_global else None
            builder.subprocess_runner(
                install_args, ireq.unpacked_source_directory, extra_env
            )

    def uninstall(self, dist: Distribution) -> None:
        req = parse_requirement(dist.project_name)
        ireq = pip_shims.install_req_from_line(dist.project_name)
        ireq.req = req

        pathset = ireq.uninstall(auto_confirm=self.auto_confirm)
        if pathset:
            pathset.commit()
