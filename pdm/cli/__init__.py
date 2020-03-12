import importlib
import pkgutil
import sys
from typing import Type

from pdm.cli.commands.base import BaseCommand
from pdm.cli.options import verbose_option
from pdm.cli.utils import PdmFormatter, PdmParser
from pdm.context import context
from pdm.project import Project

COMMANDS_MODULE_PATH = importlib.import_module("pdm.cli.commands").__path__


def main(args=None, prog_name=None, obj=None, **extra):
    root_parser = PdmParser(
        prog="pdm",
        description="PDM - Python Development Master",
        formatter_class=PdmFormatter,
    )
    root_parser.is_root = True
    root_parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="{}, version {}".format(
            context.io._style("pdm", bold=True), context.version
        ),
        help="show the version and exit",
    )
    verbose_option.add_to_parser(root_parser)

    subparsers = root_parser.add_subparsers()
    for _, name, _ in pkgutil.iter_modules(COMMANDS_MODULE_PATH):
        module = importlib.import_module(f"pdm.cli.commands.{name}", __name__)
        try:
            klass = module.Command  # type: Type[BaseCommand]
        except AttributeError:
            continue
        klass.register_to(subparsers, name)

    options = root_parser.parse_args(args or None)
    if not getattr(options, "project", None):
        options.project = obj or Project()
    context.io.set_verbosity(options.verbose)

    try:
        f = options.handler
    except AttributeError:
        root_parser.print_help()
        sys.exit(1)
    else:
        try:
            f(options.project, options)
        except Exception:
            etype, err, traceback = sys.exc_info()
            if context.io.verbosity > context.io.NORMAL:
                raise err.with_traceback(traceback)
            context.io.echo("[{}]: {}".format(etype.__name__, err), err=True)
            sys.exit(1)
