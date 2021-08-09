import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import deprecated, install_group
from pdm.project import Project


class Command(BaseCommand):
    """Remove packages from pyproject.toml"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        install_group.add_to_parser(parser)
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Remove packages from dev dependencies",
        )
        parser.add_argument(
            "-s",
            "--section",
            dest="group",
            help="(DEPRECATED) Alias of `-G/--group`",
            type=deprecated(
                "`-s/--section` is deprecated in favor of `-G/--groups` "
                "and will be removed in the next minor release."
            ),
        )
        parser.add_argument(
            "-G", "--group", help="Specify the target dependency group to remove from"
        )
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not uninstall packages",
        )
        parser.add_argument(
            "packages", nargs="+", help="Specify the packages to remove"
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_remove(
            project,
            dev=options.dev,
            group=options.group,
            sync=options.sync,
            packages=options.packages,
            no_editable=options.no_editable,
            no_self=options.no_self,
        )
