import argparse
from typing import Any


class Option:
    """A reusable option object which delegates all arguments
    to parser.add_argument().
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(*self.args, **self.kwargs)

    def add_to_group(self, group: argparse._ArgumentGroup) -> None:
        group.add_argument(*self.args, **self.kwargs)


class ArgumentGroup:
    """A reusable argument group object which can call `add_argument()`
    to add more arguments. And itself will be registered to the parser later.
    """

    def __init__(
        self,
        name: str = None,
        parser: argparse.ArgumentParser = None,
        is_mutually_exclusive: bool = False,
        required: bool = None,
    ) -> None:
        self.name = name
        self.options = []
        self.parser = parser
        self.required = required
        self.is_mutually_exclusive = is_mutually_exclusive
        self.argument_group = None

    def add_argument(self, *args: Any, **kwargs: Any) -> None:
        self.options.append(Option(*args, **kwargs))

    def add_to_parser(self, parser: argparse.ArgumentParser) -> None:
        if self.is_mutually_exclusive:
            group = parser.add_mutually_exclusive_group(required=self.required)
        else:
            group = parser.add_argument_group(self.name)
        for option in self.options:
            option.add_to_group(group)
        self.argument_group = group
        self.parser = parser

    def add_to_group(self, group: argparse._ArgumentGroup) -> None:
        self.add_to_parser(group)


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

sections_group = ArgumentGroup("Dependencies selection")
sections_group.add_argument(
    "-s",
    "--section",
    dest="sections",
    metavar="SECTION",
    action="append",
    help="(MULTIPLE) Specify section(s) of optional-dependencies "
    "or dev-dependencies(with -d)",
    default=[],
)
sections_group.add_argument(
    "-d",
    "--dev",
    default=False,
    action="store_true",
    help="Select dev dependencies",
)
sections_group.add_argument(
    "--no-default",
    dest="default",
    action="store_false",
    default=True,
    help="Don't include dependencies from default section",
)


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
clean_group.add_argument("--clean", action="store_true", help="clean unused packages")
clean_group.add_argument(
    "--no-clean", action="store_false", help="don't clean unused packages"
)

sync_group = ArgumentGroup("sync", is_mutually_exclusive=True)
sync_group.add_argument("--sync", action="store_true", help="sync packages")
sync_group.add_argument("--no-sync", action="store_false", help="don't sync packages")

packages_group = ArgumentGroup("Packages")
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
