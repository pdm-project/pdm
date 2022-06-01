import argparse

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project
from pdm.project.config import Config


class Command(BaseCommand):
    """Display the current configuration"""

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

    def _show_config(self, config: Config, ui: termui.UI) -> None:
        for key in sorted(config):
            config_item = config._config_map[key]
            deprecated = ""
            if config_item.replace and config_item.replace in config._data:
                deprecated = f"[red](deprecating: {config_item.replace})[/]"
            ui.echo(
                f"# {config_item.description}",
                style="yellow",
                verbosity=termui.Verbosity.DETAIL,
            )
            ui.echo(f"[cyan]{key}[/]{deprecated} = {config[key]}")

    def _list_config(self, project: Project, options: argparse.Namespace) -> None:
        ui = project.core.ui
        ui.echo(
            "Home configuration ([green]{}[/]):".format(
                project.global_config.config_file
            ),
            style="bold",
        )
        self._show_config(project.global_config, ui)

        ui.echo()
        ui.echo(
            "Project configuration ([green]{}[/]):".format(
                project.project_config.config_file
            ),
            style="bold",
        )
        self._show_config(project.project_config, ui)

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
