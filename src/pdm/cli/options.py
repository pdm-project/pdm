from __future__ import annotations

import argparse
import os
import sys
from functools import partial
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Any, Protocol, Sequence

    from pdm.project import Project

    class ActionCallback(Protocol):
        def __call__(
            self,
            project: Project,
            namespace: argparse.Namespace,
            values: Any,
            option_string: str | None = None,
        ) -> None: ...


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

    def __call__(self, func: ActionCallback) -> Option:
        self.kwargs.update(action=CallbackAction, callback=func)
        return self


class CallbackAction(argparse.Action):
    def __init__(self, *args: Any, callback: ActionCallback, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.callback = callback

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if not hasattr(namespace, "callbacks"):
            namespace.callbacks = []
        callback = partial(self.callback, values=values, option_string=option_string)
        namespace.callbacks.append(callback)


class ExtendMapAction(argparse._AppendAction):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        assert isinstance(values, str)
        k, _, v = values.partition("=")
        mapping = getattr(namespace, self.dest, None) or {}
        if k in mapping:
            if not isinstance(mapping[k], list):
                mapping[k] = [mapping[k]]
            mapping[k].append(v)
        else:
            mapping[k] = v
        setattr(namespace, self.dest, mapping)


class ArgumentGroup(Option):
    """A reusable argument group object which can call `add_argument()`
    to add more arguments. And itself will be registered to the parser later.
    """

    def __init__(self, name: str, is_mutually_exclusive: bool = False, required: bool = False) -> None:
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


def split_lists(separator: str) -> type[argparse.Action]:
    """
    Works the same as `append` except each argument
    is considered a `separator`-separated list.
    """

    class SplitList(argparse.Action):
        def __call__(
            self,
            parser: argparse.ArgumentParser,
            args: argparse.Namespace,
            values: Any,
            option_string: str | None = None,
        ) -> None:
            if not isinstance(values, str):
                return
            split = getattr(args, self.dest) or []
            split.extend(value.strip() for value in values.split(separator) if value.strip())
            setattr(args, self.dest, split)

    return SplitList


def from_splitted_env(name: str, separator: str) -> list[str] | None:
    """
    Parse a `separator`-separated list from a `name` environment variable if present.
    """
    value = os.getenv(name)
    if not value:
        return None
    return [v.strip() for v in value.split(separator) if v.strip()] or None


verbose_option = ArgumentGroup("Verbosity options", is_mutually_exclusive=True)
verbose_option.add_argument(
    "-v",
    "--verbose",
    action="count",
    default=0,
    help="Use `-v` for detailed output and `-vv` for more detailed",
)
verbose_option.add_argument("-q", "--quiet", action="store_const", const=-1, dest="verbose", help="Suppress output")

no_cache_option = Option(
    "--no-cache",
    action="store_true",
    default=os.getenv("PDM_NO_CACHE"),
    help="Disable the cache for the current command. [env var: PDM_NO_CACHE]",
)

dry_run_option = Option(
    "--dry-run",
    action="store_true",
    default=False,
    help="Show the difference only and don't perform any action",
)


lockfile_option = Option(
    "-L",
    "--lockfile",
    default=os.getenv("PDM_LOCKFILE"),
    help="Specify another lockfile path. Default: pdm.lock. [env var: PDM_LOCKFILE]",
)


@Option(
    "--frozen-lockfile",
    "--no-lock",
    nargs=0,
    help="Don't try to create or update the lockfile. [env var: PDM_FROZEN_LOCKFILE]",
)
def frozen_lockfile_option(
    project: Project,
    namespace: argparse.Namespace,
    values: str | Sequence[Any] | None,
    option_string: str | None = None,
) -> None:
    if option_string == "--no-lock":
        project.core.ui.warn("--no-lock is deprecated, use --frozen-lockfile instead.")
    project.enable_write_lockfile = False  # type: ignore[has-type]


@Option(
    "--pep582",
    const="AUTO",
    metavar="SHELL",
    nargs="?",
    help="Print the command line to be eval'd by the shell for PEP 582",
)
def pep582_option(
    project: Project,
    namespace: argparse.Namespace,
    values: str | Sequence[Any] | None,
    option_string: str | None = None,
) -> None:
    from pdm.cli.actions import print_pep582_command

    print_pep582_command(project, cast(str, values))
    sys.exit(0)


install_group = ArgumentGroup("Install options")
install_group.add_argument(
    "--no-editable",
    action="store_true",
    default=bool(os.getenv("PDM_NO_EDITABLE")),
    dest="no_editable",
    help="Install non-editable versions for all packages. [env var: PDM_NO_EDITABLE]",
)
install_group.add_argument(
    "--no-self",
    action="store_true",
    default=bool(os.getenv("PDM_NO_SELF")),
    dest="no_self",
    help="Don't install the project itself. [env var: PDM_NO_SELF]",
)
install_group.add_argument("--fail-fast", "-x", action="store_true", help="Abort on first installation error")


@Option(
    "--no-isolation",
    dest="build_isolation",
    nargs=0,
    help="Disable isolation when building a source distribution that follows PEP 517, "
    "as in: build dependencies specified by PEP 518 must be already installed if this option is used.",
)
def no_isolation_option(
    project: Project,
    namespace: argparse.Namespace,
    values: str | Sequence[Any] | None,
    option_string: str | None = None,
) -> None:
    project.core.state.build_isolation = False


install_group.options.append(no_isolation_option)

groups_group = ArgumentGroup("Dependencies Selection")
groups_group.add_argument(
    "-G",
    "--group",
    "--with",
    dest="groups",
    metavar="GROUP",
    action=split_lists(","),
    help="Select group of optional-dependencies separated by comma "
    "or dev-dependencies (with `-d`). Can be supplied multiple times, "
    'use ":all" to include all groups under the same species.',
    default=[],
)
groups_group.add_argument(
    "--without",
    dest="excluded_groups",
    metavar="",
    action=split_lists(","),
    help="Exclude groups of optional-dependencies or dev-dependencies",
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
    default=None,
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

save_strategy_group = ArgumentGroup("Save Strategy")
_save_sub_group = ArgumentGroup("save_strategy", is_mutually_exclusive=True)
_save_sub_group.add_argument(
    "--save-compatible",
    action="store_const",
    dest="save_strategy",
    const="compatible",
    help="Save compatible version specifiers",
)
_save_sub_group.add_argument(
    "--save-wildcard",
    action="store_const",
    dest="save_strategy",
    const="wildcard",
    help="Save wildcard version specifiers",
)
_save_sub_group.add_argument(
    "--save-exact",
    action="store_const",
    dest="save_strategy",
    const="exact",
    help="Save exact version specifiers",
)
_save_sub_group.add_argument(
    "--save-minimum",
    action="store_const",
    dest="save_strategy",
    const="minimum",
    help="Save minimum version specifiers",
)
save_strategy_group.add_argument(_save_sub_group)

skip_option = Option(
    "-k",
    "--skip",
    dest="skip",
    action=split_lists(","),
    help="Skip some tasks and/or hooks by their comma-separated names."
    " Can be supplied multiple times."
    ' Use ":all" to skip all hooks.'
    ' Use ":pre" and ":post" to skip all pre or post hooks.',
    default=from_splitted_env("PDM_SKIP_HOOKS", ","),
)

update_strategy_group = ArgumentGroup("Update Strategy")
_update_sub_group = ArgumentGroup("update_strategy", is_mutually_exclusive=True)
_update_sub_group.add_argument(
    "--update-reuse",
    action="store_const",
    dest="update_strategy",
    const="reuse",
    help="Reuse pinned versions already present in lock file if possible",
)
_update_sub_group.add_argument(
    "--update-eager",
    action="store_const",
    dest="update_strategy",
    const="eager",
    help="Try to update the packages and their dependencies recursively",
)
_update_sub_group.add_argument(
    "--update-all",
    action="store_const",
    dest="update_strategy",
    const="all",
    help="Update all dependencies and sub-dependencies",
)
_update_sub_group.add_argument(
    "--update-reuse-installed",
    action="store_const",
    dest="update_strategy",
    const="reuse-installed",
    help="Reuse installed packages if possible",
)
update_strategy_group.add_argument(_update_sub_group)

project_option = Option(
    "-p",
    "--project",
    dest="project_path",
    help="Specify another path as the project root, which changes the base of pyproject.toml "
    "and __pypackages__ [env var: PDM_PROJECT]",
    default=os.getenv("PDM_PROJECT"),
)


global_option = Option(
    "-g",
    "--global",
    dest="global_project",
    action="store_true",
    help="Use the global project, supply the project root with `-p` option",
)

clean_group = ArgumentGroup("clean", is_mutually_exclusive=True)
clean_group.add_argument("--clean", action="store_true", help="Clean packages not in the lockfile")
clean_group.add_argument(
    "--only-keep", "--clean-unselected", action="store_true", help="Only keep the selected packages"
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


@Option(
    "-I",
    "--ignore-python",
    nargs=0,
    help="Ignore the Python path saved in .pdm-python. [env var: PDM_IGNORE_SAVED_PYTHON]",
)
def ignore_python_option(
    project: Project,
    namespace: argparse.Namespace,
    values: str | Sequence[Any] | None,
    option_string: str | None = None,
) -> None:
    os.environ.update({"PDM_IGNORE_SAVED_PYTHON": "1"})


@Option(
    "-n",
    "--non-interactive",
    nargs=0,
    dest="_non_interactive",
    help="Don't show interactive prompts but use defaults. [env var: PDM_NON_INTERACTIVE]",
)
def non_interactive_option(
    project: Project,
    namespace: argparse.Namespace,
    values: str | Sequence[Any] | None,
    option_string: str | None = None,
) -> None:
    os.environ.update({"PDM_NON_INTERACTIVE": "1"})


prerelease_option = ArgumentGroup("prerelease", is_mutually_exclusive=True)
prerelease_option.add_argument(
    "--pre",
    "--prerelease",
    action="store_true",
    dest="prerelease",
    default=None,
    help="Allow prereleases to be pinned",
)
prerelease_option.add_argument(
    "--stable", action="store_false", dest="prerelease", help="Only allow stable versions to be pinned"
)
unconstrained_option = Option(
    "-u",
    "--unconstrained",
    action="store_true",
    default=False,
    help="Ignore the version constraints in pyproject.toml and overwrite with new ones from the resolution result",
)


venv_option = Option(
    "--venv",
    dest="use_venv",
    metavar="NAME",
    nargs="?",
    const="in-project",
    help="Run the command in the virtual environment with the given key. [env var: PDM_IN_VENV]",
    default=os.getenv("PDM_IN_VENV"),
)


lock_strategy_group = ArgumentGroup("Lock Strategy")
lock_strategy_group.add_argument(
    "--strategy",
    "-S",
    dest="strategy_change",
    metavar="STRATEGY",
    action=split_lists(","),
    help="Specify lock strategy (cross_platform, static_urls, direct_minimal_versions, inherit_metadata). "
    "Add 'no_' prefix to disable. Can be supplied multiple times or split by comma.",
)
lock_strategy_group.add_argument(
    "--no-cross-platform",
    action="append_const",
    dest="strategy_change",
    const="no_cross_platform",
    help="[DEPRECATED] Only lock packages for the current platform",
)
lock_strategy_group.add_argument(
    "--static-urls",
    action="append_const",
    dest="strategy_change",
    help="[DEPRECATED] Store static file URLs in the lockfile",
    const="static_urls",
)
lock_strategy_group.add_argument(
    "--no-static-urls",
    action="append_const",
    dest="strategy_change",
    help="[DEPRECATED] Do not store static file URLs in the lockfile",
    const="no_static_urls",
)

config_setting_option = Option(
    "--config-setting",
    "-C",
    action=ExtendMapAction,
    help="Pass options to the builder. options with a value must be "
    'specified after "=": `--config-setting=key(=value)` '
    "or `-Ckey(=value)`",
)
install_group.options.append(config_setting_option)

override_option = Option(
    "--override",
    default=os.getenv("PDM_OVERRIDE"),
    action="append",
    help="Use the constraint file in pip-requirements format for overriding. [env var: PDM_OVERRIDE] "
    "This option can be used multiple times. "
    "See https://pip.pypa.io/en/stable/user_guide/#constraints-files",
)
