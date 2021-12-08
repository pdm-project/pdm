from __future__ import annotations

import argparse
import os
from typing import Any, Callable, Sequence

from click import secho

from pdm._types import Protocol


class ActionCallback(Protocol):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None,
    ) -> None:
        ...


class Option:
    """A reusable option object which delegates all arguments
    to parser.add_argument().
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def add_to_parser(self, parser: argparse._ActionsContainer) -> None:
        parser.add_argument(*self.args, **self.kwargs)

    def add_to_group(self, group: argparse._ArgumentGroup) -> None:
        group.add_argument(*self.args, **self.kwargs)


class CallbackAction(argparse.Action):
    def __init__(self, *args: Any, callback: ActionCallback, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.callback = callback

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        return self.callback(parser, namespace, values, option_string=option_string)


class ArgumentGroup(Option):
    """A reusable argument group object which can call `add_argument()`
    to add more arguments. And itself will be registered to the parser later.
    """

    def __init__(
        self,
        name: str = None,
        is_mutually_exclusive: bool = False,
        required: bool = None,
    ) -> None:
        self.name = name
        self.options: list[Option] = []
        self.required = required
        self.is_mutually_exclusive = is_mutually_exclusive

    def add_argument(self, *args: Any, **kwargs: Any) -> None:
        if args and isinstance(args[0], Option):
            self.options.append(args[0])
        else:
            self.options.append(Option(*args, **kwargs))

    def add_to_parser(self, parser: argparse._ActionsContainer) -> None:
        group: argparse._ArgumentGroup
        if self.is_mutually_exclusive:
            group = parser.add_mutually_exclusive_group(required=self.required)
        else:
            group = parser.add_argument_group(self.name)
        for option in self.options:
            option.add_to_group(group)

    def add_to_group(self, group: argparse._ArgumentGroup) -> None:
        self.add_to_parser(group)


def deprecated(message: str, type_: type = str) -> Callable[[Any], Any]:
    """Prints deprecation message for the argument"""

    def wrapped_type(obj: Any) -> Any:
        secho(f"DEPRECATED: {message}", fg="red", err=True)
        return type_(obj)

    return wrapped_type


verbose_option = Option(
    "-v",
    "--verbose",
    action="count",
    default=0,
    help="-v for detailed output and -vv for more detailed",
)


dry_run_option = Option(
    "--dry-run",
    action="store_true",
    default=False,
    help="Show the difference only and don't perform any action",
)


pep582_option = Option(
    "--pep582",
    const="AUTO",
    metavar="SHELL",
    nargs="?",
    help="Print the command line to be eval'd by the shell",
)

install_group = ArgumentGroup("Install options")
install_group.add_argument(
    "--no-editable",
    action="store_true",
    dest="no_editable",
    help="Install non-editable versions for all packages",
)
install_group.add_argument(
    "--no-self",
    action="store_true",
    dest="no_self",
    help="Don't install the project itself",
)


def no_isolation_callback(
    parser: argparse.ArgumentParser,
    namespace: argparse.Namespace,
    values: str | Sequence[Any] | None,
    option_string: str | None,
) -> None:
    os.environ["PDM_BUILD_ISOLATION"] = "no"


no_isolation_option = Option(
    "--no-isolation",
    dest="build_isolation",
    action=CallbackAction,
    nargs=0,
    help="Do not isolate the build in a clean environment",
    callback=no_isolation_callback,
)
install_group.options.append(no_isolation_option)

groups_group = ArgumentGroup("Dependencies selection")
groups_group.add_argument(
    "-G",
    "--group",
    dest="groups",
    metavar="GROUP",
    action="append",
    help="Select group of optional-dependencies "
    "or dev-dependencies(with -d). Can be supplied multiple times, "
    'use ":all" to include all groups under the same species.',
    default=[],
)
groups_group.add_argument(
    "--no-default",
    dest="default",
    action="store_false",
    default=True,
    help="Don't include dependencies from the default group",
)

dev_group = ArgumentGroup("dev", is_mutually_exclusive=True)
dev_group.add_argument(
    "-d",
    "--dev",
    default=True,
    dest="dev",
    action="store_true",
    help="Select dev dependencies",
)
dev_group.add_argument(
    "--prod",
    "--production",
    dest="dev",
    action="store_false",
    help="Unselect dev dependencies",
)
groups_group.options.append(dev_group)

save_strategy_group = ArgumentGroup("save_strategy", is_mutually_exclusive=True)
save_strategy_group.add_argument(
    "--save-compatible",
    action="store_const",
    dest="save_strategy",
    const="compatible",
    help="Save compatible version specifiers",
)
save_strategy_group.add_argument(
    "--save-wildcard",
    action="store_const",
    dest="save_strategy",
    const="wildcard",
    help="Save wildcard version specifiers",
)
save_strategy_group.add_argument(
    "--save-exact",
    action="store_const",
    dest="save_strategy",
    const="exact",
    help="Save exact version specifiers",
)
save_strategy_group.add_argument(
    "--save-minimum",
    action="store_const",
    dest="save_strategy",
    const="minimum",
    help="Save minimum version specifiers",
)

update_strategy_group = ArgumentGroup("update_strategy", is_mutually_exclusive=True)
update_strategy_group.add_argument(
    "--update-reuse",
    action="store_const",
    dest="update_strategy",
    const="reuse",
    help="Reuse pinned versions already present in lock file if possible",
)
update_strategy_group.add_argument(
    "--update-eager",
    action="store_const",
    dest="update_strategy",
    const="eager",
    help="Try to update the packages and their dependencies recursively",
)

project_option = Option(
    "-p",
    "--project",
    dest="project_path",
    help="Specify another path as the project root, "
    "which changes the base of pyproject.toml and __pypackages__",
)


global_option = Option(
    "-g",
    "--global",
    dest="global_project",
    action="store_true",
    help="Use the global project, supply the project root with `-p` option",
)

clean_group = ArgumentGroup("clean", is_mutually_exclusive=True)
clean_group.add_argument(
    "--clean", action="store_true", dest="clean", help="clean unused packages"
)
clean_group.add_argument(
    "--no-clean", action="store_false", dest="clean", help="don't clean unused packages"
)

sync_group = ArgumentGroup("sync", is_mutually_exclusive=True)
sync_group.add_argument(
    "--sync", action="store_true", dest="sync", help="sync packages"
)
sync_group.add_argument(
    "--no-sync", action="store_false", dest="sync", help="don't sync packages"
)

packages_group = ArgumentGroup("Package Arguments")
packages_group.add_argument(
    "-e",
    "--editable",
    dest="editables",
    action="append",
    help="Specify editable packages",
    default=[],
)
packages_group.add_argument("packages", nargs="*", help="Specify packages")

ignore_python_option = Option(
    "-I",
    "--ignore-python",
    action="store_true",
    help="Ignore the Python path saved in the pdm.toml config",
)

prerelease_option = Option(
    "--pre",
    "--prerelease",
    action="store_true",
    dest="prerelease",
    help="Allow prereleases to be pinned",
)
unconstrained_option = Option(
    "-u",
    "--unconstrained",
    action="store_true",
    default=False,
    help="Ignore the version constraint of packages",
)
