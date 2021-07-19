from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

import distlib.scripts
from distlib.wheel import Wheel
from pip._vendor.pkg_resources import EggInfoDistribution

from pdm import termui
from pdm.models import pip_shims
from pdm.models.requirements import parse_requirement

if TYPE_CHECKING:
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
        if candidate.req.editable:
            self.install_editable(candidate.ireq)
        else:
            built = candidate.build()
            self.install_wheel(Wheel(built))

    def install_wheel(self, wheel: Wheel) -> None:
        paths = self.environment.get_paths()
        maker = distlib.scripts.ScriptMaker(None, None)
        maker.variants = set(("",))
        enquoted_executable = distlib.scripts.enquote_executable(
            self.environment.interpreter.executable
        )
        maker.executable = enquoted_executable
        wheel.install(paths, maker)

    def install_editable(self, ireq: pip_shims.InstallRequirement) -> None:
        from pdm.builders import EditableBuilder

        builder = EditableBuilder(ireq.unpacked_source_directory, self.environment)
        setup_path = builder.ensure_setup_py()
        paths = self.environment.get_paths()
        install_script = pathlib.Path(__file__).with_name("_editable_install.py")
        install_args = [
            self.environment.interpreter.executable,
            "-u",
            str(install_script),
            setup_path,
            paths["prefix"],
            paths["purelib"],
            paths["scripts"],
        ]
        builder.install(["setuptools"])
        builder.subprocess_runner(install_args, ireq.unpacked_source_directory)

    def uninstall(self, dist: Distribution) -> None:
        req = parse_requirement(dist.project_name)
        ireq = pip_shims.install_req_from_line(dist.project_name)
        ireq.req = req  # type: ignore

        pathset = ireq.uninstall(auto_confirm=self.auto_confirm)
        if pathset:
            pathset.commit()
