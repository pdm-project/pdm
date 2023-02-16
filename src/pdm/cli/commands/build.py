import argparse

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.hooks import HookManager
from pdm.cli.options import (
    no_isolation_option,
    project_option,
    skip_option,
    verbose_option,
)
from pdm.project import Project


class Command(BaseCommand):
    """Build artifacts for distribution"""

    arguments = [verbose_option, project_option, no_isolation_option, skip_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--no-sdist",
            dest="sdist",
            default=True,
            action="store_false",
            help="Don't build source tarballs",
        )
        parser.add_argument(
            "--no-wheel",
            dest="wheel",
            default=True,
            action="store_false",
            help="Don't build wheels",
        )
        parser.add_argument("-d", "--dest", default="dist", help="Target directory to put artifacts")
        parser.add_argument(
            "--no-clean",
            dest="clean",
            default=True,
            action="store_false",
            help="Do not clean the target directory",
        )
        parser.add_argument(
            "--config-setting",
            "-C",
            action="append",
            help="Pass options to the backend. options with a value must be "
            'specified after "=": "--config-setting=--opt(=value)" '
            'or "-C--opt(=value)"',
        )

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        config_settings = None
        if options.config_setting:
            config_settings = {}
            for item in options.config_setting:
                name, _, value = item.partition("=")
                if name not in config_settings:
                    config_settings[name] = value
                else:
                    if not isinstance(config_settings[name], list):
                        config_settings[name] = [config_settings[name]]
                    config_settings[name].append(value)
        actions.do_build(
            project,
            sdist=options.sdist,
            wheel=options.wheel,
            dest=options.dest,
            clean=options.clean,
            config_settings=config_settings,
            hooks=HookManager(project, options.skip),
        )
