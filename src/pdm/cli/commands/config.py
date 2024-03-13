import argparse
import os
from pathlib import Path
from typing import Any, Mapping

from pdm import termui
from pdm._types import RepositoryConfig
from pdm.cli.commands.base import BaseCommand
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.project.config import DEFAULT_REPOSITORIES, REPOSITORY, SOURCE, Config


class Command(BaseCommand):
    """Display the current configuration"""

    ui: termui.UI

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--local",
            action="store_true",
            help="Set config in the project's local configuration file",
        )
        parser.add_argument("-d", "--delete", action="store_true", help="Unset a configuration key")
        parser.add_argument(
            "-e",
            "--edit",
            action="store_true",
            help="Edit the configuration file in the default editor(defined by EDITOR env var)",
        )
        parser.add_argument("key", help="Config key", nargs="?")
        parser.add_argument("value", help="Config value", nargs="?")

    @staticmethod
    def get_editor() -> str:
        for key in "VISUAL", "EDITOR":
            rv = os.getenv(key)
            if rv:
                return rv
        if os.name == "nt":
            return "notepad"
        for editor in "sensible-editor", "vim", "nano":
            if os.system(f"which {editor} >/dev/null 2>&1") == 0:
                return editor
        return "vi"

    def edit_file(self, path: Path) -> None:
        import subprocess

        editor = self.get_editor()
        proc = subprocess.Popen(f'{editor} "{path}"', shell=True)

        if proc.wait() != 0:
            raise PdmUsageError(f"Editor {editor} exited abnormally")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.ui = project.core.ui
        if options.edit:
            if options.key:
                raise PdmUsageError("Cannot specify an argument when `--edit` is given")
            if options.delete:
                raise PdmUsageError("`--delete` doesn't work when `--edit` is given")
            config = project.project_config if options.local else project.global_config
            return self.edit_file(config.config_file)
        if options.delete:
            self._delete_config(project, options)
        elif options.value:
            self._set_config(project, options)
        elif options.key:
            self._get_config(project, options)
        else:
            self._list_config(project, options)

    def _get_config(self, project: Project, options: argparse.Namespace) -> None:
        from findpython import ALL_PROVIDERS

        if options.key in project.project_config.deprecated:  # pragma: no cover
            project.core.ui.warn(
                f"[warning]DEPRECATED:[/] the config has been renamed to {project.project_config.deprecated[options.key]}",
            )
            options.key = project.project_config.deprecated[options.key]
        try:
            value = project.project_config[options.key]
        except KeyError:
            value = project.global_config[options.key]
        if options.key.endswith(".password"):
            value = "[i]<hidden>[/i]"
        elif options.key == "python.providers" and not value:
            value = ["venv", *ALL_PROVIDERS]
        project.core.ui.echo(value)

    def _set_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        if options.key in config.deprecated:  # pragma: no cover
            project.core.ui.warn(
                f"[warning]DEPRECATED:[/] the config has been renamed to {config.deprecated[options.key]}",
            )
        config[options.key] = options.value

    def _show_config(self, config: Mapping[str, Any], supersedes: Mapping[str, Any]) -> None:
        from findpython import ALL_PROVIDERS

        assert Config.site is not None
        for key in sorted(config):
            deprecated = ""
            canonical_key = key
            superseded = key in supersedes
            if key in Config.site.deprecated:  # pragma: no cover
                canonical_key = Config.site.deprecated[key]
                if canonical_key in supersedes:
                    superseded = True
                deprecated = f"[error](deprecating: {key})[/]"
            elif key not in Config._config_map and not (key.startswith("pypi.") or key.startswith(REPOSITORY)):
                continue
            extra_style = "dim" if superseded else None
            if canonical_key not in Config._config_map:
                prefix, name = key.split(".", 1)
                if prefix in (SOURCE, REPOSITORY):
                    title = "non-default PyPI index" if prefix == SOURCE else "custom repository"
                    self.ui.echo(
                        f"[warning]# Configuration of {title} `{name}`",
                        style=extra_style,
                        verbosity=termui.Verbosity.DETAIL,
                    )
                    repository = RepositoryConfig(**config[key], config_prefix=prefix, name=name)
                    if not repository.url and name in DEFAULT_REPOSITORIES:
                        repository.url = DEFAULT_REPOSITORIES[name]
                    self.ui.echo(repository)
                continue
            config_item = Config._config_map[canonical_key]
            self.ui.echo(
                f"[warning]# {config_item.description}",
                style=extra_style,
                verbosity=termui.Verbosity.DETAIL,
            )
            if key.endswith("password"):
                value: Any = "[i]<hidden>[/i]"
            else:
                value = config[key]
                if key == "python.providers" and not value:
                    value = ["venv", *ALL_PROVIDERS]
            self.ui.echo(
                f"[primary]{canonical_key}[/]{deprecated} = {value}",
                style=extra_style,
            )

    def _list_config(self, project: Project, options: argparse.Namespace) -> None:
        assert Config.site is not None
        self.ui.echo(
            f"Site/default configuration ([success]{Config.site.config_file}[/]):",
            style="bold",
        )
        self._show_config(
            Config.get_defaults(),
            {**project.global_config.self_data, **project.project_config.self_data},
        )

        if project.global_config.self_data:
            self.ui.echo(
                f"\nHome configuration ([success]{project.global_config.config_file}[/]):",
                style="bold",
            )
            self._show_config(project.global_config.self_data, project.project_config.self_data)

        if project.project_config.self_data:
            self.ui.echo(
                f"\nProject configuration ([success]{project.project_config.config_file}[/]):",
                style="bold",
            )
            self._show_config(project.project_config.self_data, {})

    def _delete_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        if options.key in config.deprecated:  # pragma: no cover
            project.core.ui.warn(
                f"[warning]DEPRECATED:[/] the config has been renamed to {config.deprecated[options.key]}",
            )
        del config[options.key]
