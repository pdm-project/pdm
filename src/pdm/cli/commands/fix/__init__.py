from __future__ import annotations

import argparse

from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.fix.fixers import BaseFixer, PackageTypeFixer, ProjectConfigFixer
from pdm.exceptions import PdmUsageError
from pdm.project import Project
from pdm.termui import Emoji


class Command(BaseCommand):
    """Fix the project problems according to the latest version of PDM"""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("problem", nargs="?", help="Fix the specific problem, or all if not given")
        parser.add_argument("--dry-run", action="store_true", help="Only show the problems")

    @staticmethod
    def find_problems(project: Project) -> list[tuple[str, BaseFixer]]:
        """Get the problems in the project"""
        problems: list[tuple[str, BaseFixer]] = []
        for fixer in Command.get_fixers(project):
            if fixer.check():
                problems.append((fixer.identifier, fixer))
        return problems

    @staticmethod
    def check_problems(project: Project, strict: bool = True) -> None:
        """Check the problems in the project"""
        problems = Command.find_problems(project)
        if not problems:
            return
        breaking = False
        project.core.ui.warn("The following problems are found in your project:")
        for name, fixer in problems:
            project.core.ui.echo(f"  [b]{name}[/]: {fixer.get_message()}", err=True)
            if fixer.breaking:
                breaking = True
        extra_option = " -g" if project.is_global else ""
        project.core.ui.echo(
            f"Run [success]pdm fix{extra_option}[/] to fix all or [success]pdm fix{extra_option} <name>[/]"
            " to fix individual problem.",
            err=True,
        )
        if breaking and strict:
            raise SystemExit(1)

    @staticmethod
    def get_fixers(project: Project) -> list[BaseFixer]:
        """Return a list of fixers to check, the order matters"""
        return [ProjectConfigFixer(project), PackageTypeFixer(project)]

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.dry_run:
            return self.check_problems(project)
        problems = self.find_problems(project)
        if options.problem:
            fixer = next((fixer for name, fixer in problems if name == options.problem), None)
            if not fixer:
                raise PdmUsageError(
                    f"The problem doesn't exist: [success]{options.problem}[/], "
                    f"possible values are {[p[0] for p in problems]}",
                )
            project.core.ui.echo(f"Fixing [success]{fixer.identifier}[/]...", end=" ")
            fixer.fix()
            project.core.ui.echo(f"[success]{Emoji.SUCC}[/]")
            return
        if not problems:
            project.core.ui.echo("No problem is found, nothing to fix.")
            return
        for name, fixer in problems:
            project.core.ui.echo(f"Fixing [success]{name}[/]...", end=" ")
            fixer.fix()
            project.core.ui.echo(f"[success]{Emoji.SUCC}[/]")
