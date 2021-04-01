import argparse

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project


class Command(BaseCommand):
    """Display the current configuration"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--local",
            action="store_true",
            help="Set config in the project's local configuration filie",
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
        project.core.ui.echo(project.config[options.key])

    def _set_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        config[options.key] = options.value

    def _list_config(self, project: Project, options: argparse.Namespace) -> None:
        ui = project.core.ui
        ui.echo("Home configuration ({}):".format(project.global_config._config_file))
        with ui.indent("  "):
            for key in sorted(project.global_config):
                ui.echo(
                    termui.yellow(
                        "# " + project.global_config._config_map[key].description
                    ),
                    verbosity=termui.DETAIL,
                )
                ui.echo(f"{termui.cyan(key)} = {project.global_config[key]}")

        ui.echo()
        ui.echo(
            "Project configuration ({}):".format(project.project_config._config_file)
        )
        with ui.indent("  "):
            for key in sorted(project.project_config):
                ui.echo(
                    termui.yellow(
                        "# " + project.project_config._config_map[key].description
                    ),
                    verbosity=termui.DETAIL,
                )
                ui.echo(f"{termui.cyan(key)} = {project.project_config[key]}")

    def _delete_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        del config[options.key]
