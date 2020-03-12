import argparse
import os
import sys
from typing import List, Optional

from pdm.cli.options import Option, global_option, verbose_option
from pdm.cli.utils import PdmFormatter
from pdm.project import Project


class BaseCommand(object):
    """A CLI subcommand"""

    name = None  # type: str
    description = None  # type: str
    arguments = [verbose_option, global_option]  # type: List[Option]

    def __init__(self, parser: Optional[argparse.ArgumentParser] = None) -> None:
        if not parser:
            parser = argparse.ArgumentParser(
                prog=os.path.basename(sys.argv[0]),
                description="Base argument parser for passa",
            )
        for arg in self.arguments:
            arg.add_to_parser(parser)
        self.add_arguments(parser)

    @classmethod
    def register_to(cls, subparsers, name=None):
        help_text = cls.description or cls.__doc__
        parser = subparsers.add_parser(
            name or cls.name,
            description=help_text,
            help=help_text,
            formatter_class=PdmFormatter,
        )
        command = cls(parser)
        parser.set_defaults(handler=command.handle)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        raise NotImplementedError
