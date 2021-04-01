import argparse
from argparse import _SubParsersAction
from typing import List, Optional

from pdm.cli.options import Option, global_option, project_option, verbose_option
from pdm.cli.utils import PdmFormatter
from pdm.project import Project


class BaseCommand:
    """A CLI subcommand"""

    # The subcommand's name
    name: Optional[str] = None
    # The subcommand's help string, if not given, __doc__ will be used.
    description: Optional[str] = None
    # A list of pre-defined options which will be loaded on initailizing
    # Rewrite this if you don't want the default ones
    arguments: List[Option] = [verbose_option, global_option, project_option]

    def __init__(self, parser: argparse.ArgumentParser) -> None:
        for arg in self.arguments:
            arg.add_to_parser(parser)
        self.add_arguments(parser)

    @classmethod
    def register_to(cls, subparsers: _SubParsersAction, name: str = None) -> None:
        """Register a subcommand to the subparsers,
        with an optional name of the subcommand.
        """
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
        """Manipulate the argument parser to add more arguments"""
        pass

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        """The command handler function.

        :param project: the pdm project instance
        :param options: the parsed Namespace object
        """
        raise NotImplementedError
