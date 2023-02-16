import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import dry_run_option, install_group, lockfile_option, skip_option
from pdm.project import Project


class Command(BaseCommand):
    """Remove packages from pyproject.toml"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        install_group.add_to_parser(parser)
        dry_run_option.add_to_parser(parser)
        lockfile_option.add_to_parser(parser)
        skip_option.add_to_parser(parser)
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Remove packages from dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to remove from")
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not uninstall packages",
        )
        parser.add_argument("packages", nargs="+", help="Specify the packages to remove")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        actions.do_remove(
            project,
            dev=options.dev,
            group=options.group,
            sync=options.sync,
            packages=options.packages,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            hooks=HookManager(project, options.skip),
        )
