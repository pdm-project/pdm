import click

from pdm.cli.options import pass_project, project_option, verbose_option
from pdm.context import context


@click.group(invoke_without_command=True, name="config")
@verbose_option
@project_option()
@click.pass_context
def config_cmd(ctx, project):
    """Display the current configuration"""
    if ctx.invoked_subcommand:
        return

    context.io.echo(
        "Home configuration ({}):".format(project.global_config._config_file)
    )
    with context.io.indent("  "):
        for key in sorted(project.global_config):
            context.io.echo(
                context.io.yellow("# " + project.global_config.CONFIG_ITEMS[key][0]),
                verbosity=context.io.DETAIL,
            )
            context.io.echo(f"{context.io.cyan(key)} = {project.global_config[key]}")

    context.io.echo()
    context.io.echo(
        "Project configuration ({}):".format(project.project_config._config_file)
    )
    with context.io.indent("  "):
        for key in sorted(project.project_config):
            context.io.echo(
                context.io.yellow("# " + project.project_config.CONFIG_ITEMS[key][0]),
                verbosity=context.io.DETAIL,
            )
            context.io.echo(f"{context.io.cyan(key)} = {project.project_config[key]}")


@config_cmd.command()
@click.argument("name")
@pass_project
def get(project, name):
    """Show a configuration value"""
    context.io.echo(project.config[name])


@config_cmd.command(name="set")
@click.option(
    "-l",
    "--local",
    is_flag=True,
    help="Store the configuration into project config file.",
)
@click.argument("name")
@click.argument("value")
@pass_project
def set_config_item(project, local, name, value):
    """Set a configuration value"""
    config = project.project_config if local else project.global_config
    config[name] = value


@config_cmd.command(name="del")
@click.option(
    "-l",
    "--local",
    is_flag=True,
    help="Delete the configuration item from project config file.",
)
@click.argument("name")
@pass_project
def del_config_item(project, local, name):
    """Delete a configuration value"""
    config = project.project_config if local else project.global_config
    del config[name]
