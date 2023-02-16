from __future__ import annotations

import argparse
import sys
import textwrap
from shutil import get_terminal_size

from pdm import termui
from pdm._types import SearchResult
from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.models.environment import BareEnvironment, WorkingSet
from pdm.project import Project
from pdm.utils import normalize_name


def print_results(
    ui: termui.UI,
    hits: SearchResult,
    working_set: WorkingSet,
    terminal_width: int | None = None,
) -> None:
    if not hits:
        return
    name_column_width = max(len(hit.name) + len(hit.version or "") for hit in hits) + 4

    for hit in hits:
        name = hit.name
        summary = hit.summary or ""
        latest = hit.version or ""
        if terminal_width is not None:
            target_width = terminal_width - name_column_width - 5
            if target_width > 10:
                # wrap and indent summary to fit terminal
                summary = ("\n" + " " * (name_column_width + 2)).join(textwrap.wrap(summary, target_width))
        current_width = len(name) + len(latest) + 4
        spaces = " " * (name_column_width - current_width)
        line = f"[req]{name}[/] ([warning]{latest}[/]){spaces} - {summary}"
        try:
            ui.echo(line)
            if normalize_name(name) in working_set:
                dist = working_set[normalize_name(name)]
                if dist.version == latest:
                    ui.echo("  INSTALLED: %s (latest)" % dist.version)
                else:
                    ui.echo("  INSTALLED: %s" % dist.version)
                    ui.echo("  LATEST:    %s" % latest)
        except UnicodeEncodeError:
            pass


class Command(BaseCommand):
    """Search for PyPI packages"""

    arguments = [verbose_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("query", help="Query string to search")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        project.environment = BareEnvironment(project)
        result = project.get_repository().search(options.query)
        terminal_width = None
        if sys.stdout.isatty():
            terminal_width = get_terminal_size()[0]
        working_set = project.environment.get_working_set()
        print_results(project.core.ui, result, working_set, terminal_width)
