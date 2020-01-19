import click


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
