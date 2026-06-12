import abc
import re
import shutil
from pathlib import Path

from pdm.project import Config, Project
from pdm.project.lockfile import FLAG_CROSS_PLATFORM
from pdm.termui import Verbosity
from pdm.utils import parse_version


class BaseFixer(abc.ABC):
    """Base class for fixers"""

    # A unique identifier for the fixer
    identifier: str
    # A boolean flag to indicate if the problem is breaking
    breaking: bool = False

    def __init__(self, project: Project) -> None:
        self.project = project

    def log(self, message: str, verbosity: Verbosity = Verbosity.DETAIL) -> None:
        self.project.core.ui.echo(message, verbosity=verbosity)

    @abc.abstractmethod
    def get_message(self) -> str:
        """Return a description of the problem"""

    @abc.abstractmethod
    def fix(self) -> None:
        """Perform the fix"""

    @abc.abstractmethod
    def check(self) -> bool:
        """Check if the problem exists"""


class ProjectConfigFixer(BaseFixer):
    """Fix the project config"""

    identifier = "project-config"

    def get_message(self) -> str:
        return (
            "[success]python.path[/] config needs to be moved to [info].pdm-python[/] and "
            "[info].pdm.toml[/] needs to be renamed to [info]pdm.toml[/]"
        )

    def _fix_gitignore(self) -> None:
        gitignore = self.project.root.joinpath(".gitignore")
        if not gitignore.exists():
            return
        content = gitignore.read_text("utf8")
        if ".pdm-python" not in content:
            content = re.sub(r"^\.pdm\.toml$", ".pdm-python", content, flags=re.M)
            gitignore.write_text(content, "utf8")

    def fix(self) -> None:
        old_file = self.project.root.joinpath(".pdm.toml")
        config = Config(old_file).self_data
        if not self.project.root.joinpath(".pdm-python").exists() and config.get("python.path"):
            self.log("Creating .pdm-python...", verbosity=Verbosity.DETAIL)
            self.project.root.joinpath(".pdm-python").write_text(config["python.path"])
        self.project.project_config  # access the project config to move the config items
        self.log("Moving .pdm.toml to pdm.toml...", verbosity=Verbosity.DETAIL)
        old_file.unlink()
        self.log("Fixing .gitignore...", verbosity=Verbosity.DETAIL)
        self._fix_gitignore()

    def check(self) -> bool:
        return self.project.root.joinpath(".pdm.toml").exists()


class ProjectPluginFixer(BaseFixer):
    """Move project plugins to the cache directory."""

    identifier = "project-plugins"

    @property
    def old_plugin_dir(self) -> Path:
        return self.project.root / ".pdm-plugins"

    def get_message(self) -> str:
        return "Project plugins need to be moved from [info].pdm-plugins[/] to the PDM cache directory."

    def check(self) -> bool:
        return self.old_plugin_dir.is_dir()

    def fix(self) -> None:
        plugin_root = self.project.project_plugins_dir
        self.log(
            f"Moving .pdm-plugins to {plugin_root.as_posix()}...",
            verbosity=Verbosity.DETAIL,
        )
        plugin_root.parent.mkdir(parents=True, exist_ok=True)
        if plugin_root.exists():
            if plugin_root.is_dir():
                shutil.rmtree(plugin_root)
            else:
                plugin_root.unlink()
        shutil.move(self.old_plugin_dir, plugin_root)


class PackageTypeFixer(BaseFixer):  # pragma: no cover
    identifier = "package-type"

    def get_message(self) -> str:
        package_type = self.project.pyproject.settings["package-type"]  # type: ignore[typeddict-item]
        dist = str(package_type == "library").lower()
        return (
            rf'[success]package-type = "{package_type}"[/] has been renamed to '
            rf"[info]distribution = {dist}[/] under \[tool.pdm] table"
        )

    def check(self) -> bool:
        return "package-type" in self.project.pyproject.settings

    def fix(self) -> None:
        # Copy the project settings
        self.project.pyproject.open_for_write()
        settings = self.project.pyproject.settings.copy()

        # Pop the package type and convert it to a distribution type
        package_type = settings.pop("package-type")  # type: ignore[typeddict-item]
        dist = package_type == "library"
        settings["distribution"] = dist

        # Update the project settings with the new distribution type
        self.project.pyproject._data["tool"].pop("pdm")
        self.project.pyproject.settings.update(settings)

        # Write the updated settings back to the project
        self.project.pyproject.write(False)


class LockStrategyFixer(BaseFixer):
    identifier = "deprecated-cross-platform"

    def get_message(self) -> str:
        return "Lock strategy [success]`cross_platform`[/] has been deprecated in favor of lock targets."

    def check(self) -> bool:
        from pdm.project.lockfile import PDMLock

        lockfile = self.project.lockfile
        if not isinstance(lockfile, PDMLock):  # pragma: no cover
            return False
        lockfile_version = lockfile.file_version
        if not lockfile_version or parse_version(lockfile_version) < parse_version("4.5.0"):
            return False
        return FLAG_CROSS_PLATFORM in lockfile.strategy

    def fix(self) -> None:
        strategies = self.project.lockfile.strategy - {FLAG_CROSS_PLATFORM}
        lockfile = self.project.lockfile.open_for_write()
        lockfile["metadata"]["strategy"] = sorted(strategies)
        self.project.lockfile.write(False)
        self.log("Lock strategy [success]`cross_platform` has been removed.", verbosity=Verbosity.DETAIL)
