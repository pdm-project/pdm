import click

from pdm.cli.options import pass_project, verbose_option
from pdm.context import context


@click.group(invoke_without_command=True)
@verbose_option
@pass_project
@click.pass_context
def config(ctx, project):
    """Display the current configuration"""
    config_ins = project.config
    if ctx.invoked_subcommand:
        return
    global_keys = set(config_ins._global_config.keys()) | set(
        config_ins.DEFAULT_CONFIG.keys()
    )
    local_keys = set(config_ins._project_config.keys())
    context.io.echo("Home configuration ({}):".format(config_ins._global_config_file))
    with context.io.indent("  "):
        for key in sorted(global_keys):
            if key in config_ins._global_config:
                value = config_ins._global_config[key]
            else:
                value = config_ins[key]
            context.io.echo(
                context.io.yellow(config_ins.CONFIG_ITEMS[key]),
                verbosity=context.io.DETAIL,
            )
            context.io.echo(f"{context.io.cyan(key)} = {value}")

    context.io.echo()
    context.io.echo(
        "Project configuration ({}):".format(config_ins._project_config_file)
    )
    with context.io.indent("  "):
        for key in sorted(local_keys):
            context.io.echo(
                context.io.yellow(config_ins.CONFIG_ITEMS[key]),
                verbosity=context.io.DETAIL,
            )
            context.io.echo(f"{context.io.cyan(key)} = {config_ins[key]}")


@config.command()
@click.argument("name")
@pass_project
def get(project, name):
    """Show a configuration value"""
    context.io.echo(project.config[name])


@config.command(name="set")
@click.option(
    "-l", "--local", is_flag=True, help="Store the configuration into home config file."
)
@click.argument("name")
@click.argument("value")
@pass_project
def set_config_value(project, local, name, value):
    project.config[name] = value
    project.config.save_config(not local)
