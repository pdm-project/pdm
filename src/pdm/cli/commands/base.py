from __future__ import annotations

import argparse
import inspect
from argparse import _SubParsersAction
from typing import Any, Sequence, TypeVar

from pdm.cli.options import Option, global_option, project_option, verbose_option
from pdm.project import Project
from pdm.utils import deprecation_warning

C = TypeVar("C", bound="BaseCommand")


class BaseCommand:
    """A CLI subcommand"""

    # The subcommand's name
    name: str | None = None
    # The subcommand's help string, if not given, __doc__ will be used.
    description: str | None = None
    # A list of pre-defined options which will be loaded on initializing
    # Rewrite this if you don't want the default ones
    arguments: Sequence[Option] = (verbose_option, global_option, project_option)

    def __init__(self, parser: argparse.ArgumentParser | None = None) -> None:
        """For compatibility, the parser is optional and won't be used."""

    @classmethod
    def init_parser(cls: type[C], parser: argparse.ArgumentParser) -> C:
        args = inspect.signature(cls).parameters
        if "parser" in args and args["parser"].default is inspect._empty:
            deprecation_warning(
                f"The `parser` argument of `{cls.__name__}.__init__()` is deprecated. It won't be used."
            )
            cmd = cls(parser)  # type: ignore[call-arg]
        else:
            cmd = cls()
        for arg in cmd.arguments:
            arg.add_to_parser(parser)
        cmd.add_arguments(parser)
        return cmd

    @classmethod
    def register_to(cls, subparsers: _SubParsersAction, name: str | None = None, **kwargs: Any) -> None:
        """Register a subcommand to the subparsers,
        with an optional name of the subcommand.
        """
        help_text = cls.description or cls.__doc__
        name = name or cls.name or ""
        # Remove the existing subparser as it will raise an error on Python 3.11+
        subparsers._name_parser_map.pop(name, None)
        subactions = subparsers._get_subactions()
        subactions[:] = [action for action in subactions if action.dest != name]
        parser = subparsers.add_parser(
            name,
            description=help_text,
            help=help_text,
            **kwargs,
        )
        command = cls.init_parser(parser)
        command.name = name
        # Store the command instance in the parsed args. See pdm/core.py for more details
        parser.set_defaults(command=command)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Manipulate the argument parser to add more arguments"""
        pass

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        """The command handler function.

        :param project: the pdm project instance
        :param options: the parsed Namespace object
        """
        raise NotImplementedError
