from pathlib import Path

import click

from pdm.context import context
from pdm.project import Project

pass_project = click.make_pass_decorator(Project, ensure=True)


def verbose_option(f):
    def callback(ctx, param, value):
        context.io.set_verbosity(value)
        return value

    return click.option(
        "-v",
        "--verbose",
        count=True,
        callback=callback,
        expose_value=False,
        help="-v for detailed output and -vv for more detailed.",
    )(f)


def dry_run_option(f):
    return click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Only prints actions without actually running them.",
    )(f)


def sections_option(f):
    name = f.__name__

    f = click.option(
        "-s",
        "--section",
        "sections",
        metavar="SECTIONS",
        multiple=True,
        help=f"Specify section(s) to {name}.",
    )(f)
    f = click.option(
        "-d",
        "--dev",
        default=False,
        is_flag=True,
        help=f"Also {name} dev dependencies.",
    )(f)
    f = click.option(
        "--no-default",
        "default",
        flag_value=False,
        default=True,
        help=f"Don't {name} dependencies from default seciton.",
    )(f)
    return f


def save_strategy_option(f):
    f = click.option(
        "--save-compatible",
        "save",
        flag_value="compatible",
        help="Save compatible version specifiers.",
        default=True,
    )(f)
    f = click.option(
        "--save-exact",
        "save",
        flag_value="exact",
        help="Save exactly pinned version specifiers.",
    )(f)
    f = click.option(
        "--save-wildcard",
        "save",
        flag_value="wildcard",
        help="Save wildcard unpinned version specifiers.",
    )(f)
    return f


def update_strategy_option(f):
    f = click.option(
        "--update-reuse",
        "strategy",
        flag_value="reuse",
        help="Reuse pinned versions already present in lock file if possible.",
    )(
        click.option(
            "--update-eager",
            "strategy",
            flag_value="eager",
            help="Try to update the packages and their dependencies recursively.",
        )(f)
    )
    return f


def global_option(f):
    def callback(ctx, param, value):
        if value:
            ctx.obj = Project.create_global()
        return value

    return click.option(
        "-g",
        "--global",
        default=False,
        expose_value=False,
        is_flag=True,
        callback=callback,
        is_eager=True,
        help="Use the global project",
    )(f)


def project_option(allow_global=True):
    def callback(ctx, param, value):
        if value:
            project = ctx.ensure_object(Project)
            project.root = Path(value).absolute()
            project.init_global_project()
        return value

    def decorator(f):
        f = pass_project(f)
        f = click.option(
            "-p",
            "--project",
            metavar="PROJECT",
            help="Specify a project root directory",
            expose_value=False,
            callback=callback,
        )(f)
        if allow_global:
            f = global_option(f)
        return f

    return decorator
