import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    dry_run_option,
    install_group,
    lockfile_option,
    packages_group,
    prerelease_option,
    save_strategy_group,
    skip_option,
    unconstrained_option,
    update_strategy_group,
)
from pdm.exceptions import PdmUsageError
from pdm.project import Project


class Command(BaseCommand):
    """Add package(s) to pyproject.toml and install them"""

    arguments = [
        *BaseCommand.arguments,
        lockfile_option,
        save_strategy_group,
        update_strategy_group,
        prerelease_option,
        unconstrained_option,
        packages_group,
        install_group,
        dry_run_option,
        skip_option,
    ]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="Add packages into dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to add into")
        parser.add_argument(
            "--no-sync",
            dest="sync",
            default=True,
            action="store_false",
            help="Only write pyproject.toml and do not sync the working set",
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.editables and options.no_editable:
            raise PdmUsageError("`--no-editable` cannot be used with `-e/--editable`")
        actions.do_add(
            project,
            dev=options.dev,
            group=options.group,
            sync=options.sync,
            save=options.save_strategy or project.config["strategy.save"],
            strategy=options.update_strategy or project.config["strategy.update"],
            editables=options.editables,
            packages=options.packages,
            unconstrained=options.unconstrained,
            no_editable=options.no_editable,
            no_self=options.no_self,
            dry_run=options.dry_run,
            prerelease=options.prerelease,
            hooks=HookManager(project, options.skip),
        )
