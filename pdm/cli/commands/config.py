import argparse

from pdm.cli.commands.base import BaseCommand
from pdm.context import context
from pdm.project import Project


class Command(BaseCommand):
    """Display the current configuration"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        subparsers = parser.add_subparsers()
        GetCommand.register_to(subparsers, "get")
        SetCommand.register_to(subparsers, "set")
        DeleteCommand.register_to(subparsers, "del")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        context.io.echo(
            "Home configuration ({}):".format(project.global_config._config_file)
        )
        with context.io.indent("  "):
            for key in sorted(project.global_config):
                context.io.echo(
                    context.io.yellow(
                        "# " + project.global_config._config_map[key].description
                    ),
                    verbosity=context.io.DETAIL,
                )
                context.io.echo(
                    f"{context.io.cyan(key)} = {project.global_config[key]}"
                )

        context.io.echo()
        context.io.echo(
            "Project configuration ({}):".format(project.project_config._config_file)
        )
        with context.io.indent("  "):
            for key in sorted(project.project_config):
                context.io.echo(
                    context.io.yellow(
                        "# " + project.project_config._config_map[key].description
                    ),
                    verbosity=context.io.DETAIL,
                )
                context.io.echo(
                    f"{context.io.cyan(key)} = {project.project_config[key]}"
                )


class GetCommand(BaseCommand):
    """Show a configuration value"""

    arguments = []

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("name", help="Config name")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        context.io.echo(project.config[options.name])


class SetCommand(BaseCommand):
    """Set a configuration value"""

    arguments = []

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--local",
            action="store_true",
            help="Save to project configuration file",
        )
        parser.add_argument("name", help="Config name")
        parser.add_argument("value", help="Config value")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        config[options.name] = options.value


class DeleteCommand(BaseCommand):
    """Delete a configuration value"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--local",
            action="store_true",
            help="Delete from project configuration file",
        )
        parser.add_argument("name", help="Config name")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        del config[options.name]
