import argparse
from typing import Any, Mapping

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project
from pdm.project.config import Config


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
        parser.add_argument(
            "-d", "--delete", action="store_true", help="Unset a configuration key"
        )
        parser.add_argument("key", help="Config key", nargs="?")
        parser.add_argument("value", help="Config value", nargs="?")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.delete:
            self._delete_config(project, options)
        elif options.value:
            self._set_config(project, options)
        elif options.key:
            self._get_config(project, options)
        else:
            self._list_config(project, options)

    def _get_config(self, project: Project, options: argparse.Namespace) -> None:
        if options.key in project.project_config.deprecated:
            project.core.ui.echo(
                "DEPRECATED: the config has been renamed to "
                f"{project.project_config.deprecated[options.key]}",
                style="yellow",
                err=True,
            )
            options.key = project.project_config.deprecated[options.key]
        if options.key.split(".")[0] == "repository":
            value = project.global_config[options.key]
        else:
            value = project.config[options.key]
        project.core.ui.echo(value)

    def _set_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        if options.key in config.deprecated:
            project.core.ui.echo(
                "DEPRECATED: the config has been renamed to "
                f"{config.deprecated[options.key]}",
                style="yellow",
                err=True,
            )
        config[options.key] = options.value

    def _show_config(
        self, config: Mapping[str, Any], supersedes: Mapping[str, Any]
    ) -> None:
        assert Config.site is not None
        for key in sorted(config):
            deprecated = ""
            canonical_key = key
            superseded = key in supersedes
            if key in Config.site.deprecated:
                canonical_key = Config.site.deprecated[key]
                if canonical_key in supersedes:
                    superseded = True
                deprecated = f"[red](deprecating: {key})[/]"
            elif key not in Config._config_map:
                continue
            extra_style = " dim" if superseded else ""
            config_item = Config._config_map[canonical_key]
            self.ui.echo(
                f"# {config_item.description}",
                style=f"yellow{extra_style}",
                verbosity=termui.Verbosity.DETAIL,
            )
            self.ui.echo(
                f"[cyan]{canonical_key}[/]{deprecated} = {config[key]}",
                style=extra_style or None,
            )

    def _list_config(self, project: Project, options: argparse.Namespace) -> None:
        self.ui = project.core.ui
        assert Config.site is not None
        self.ui.echo(
            f"Site/default configuration ([green]{Config.site.config_file}[/]):",
            style="bold",
        )
        self._show_config(
            Config.get_defaults(),
            {**project.global_config.self_data, **project.project_config.self_data},
        )

        self.ui.echo(
            f"\nHome configuration ([green]{project.global_config.config_file}[/]):",
            style="bold",
        )
        self._show_config(
            project.global_config.self_data, project.project_config.self_data
        )

        self.ui.echo(
            "\nProject configuration ([green]"
            f"{project.project_config.config_file}[/]):",
            style="bold",
        )
        self._show_config(project.project_config.self_data, {})

    def _delete_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        if options.key in config.deprecated:
            project.core.ui.echo(
                "DEPRECATED: the config has been renamed to "
                f"{config.deprecated[options.key]}",
                style="yellow",
                err=True,
            )
        del config[options.key]
