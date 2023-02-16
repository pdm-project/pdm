import argparse
from typing import Any, Mapping

from pdm import termui
from pdm.cli.commands.base import BaseCommand
from pdm.project import Project
from pdm.project.config import (
    DEFAULT_REPOSITORIES,
    REPOSITORY,
    Config,
    RegistryConfig,
    RepositoryConfig,
)


class Command(BaseCommand):
    """Display the current configuration"""

    ui: termui.UI

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-l",
            "--local",
            action="store_true",
            help="Set config in the project's local configuration file",
        )
        parser.add_argument("-d", "--delete", action="store_true", help="Unset a configuration key")
        parser.add_argument("key", help="Config key", nargs="?")
        parser.add_argument("value", help="Config value", nargs="?")

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        if options.delete:
            self._delete_config(project, options)
        elif options.value:
            self._set_config(project, options)
        elif options.key:
            self._get_config(project, options)
        else:
            self._list_config(project, options)

    def _get_config(self, project: Project, options: argparse.Namespace) -> None:
        if options.key in project.project_config.deprecated:  # pragma: no cover
            project.core.ui.echo(
                f"DEPRECATED: the config has been renamed to {project.project_config.deprecated[options.key]}",
                style="warning",
                err=True,
            )
            options.key = project.project_config.deprecated[options.key]
        try:
            value = project.project_config[options.key]
        except KeyError:
            value = project.global_config[options.key]
        project.core.ui.echo(value)

    def _set_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        if options.key in config.deprecated:  # pragma: no cover
            project.core.ui.echo(
                f"DEPRECATED: the config has been renamed to {config.deprecated[options.key]}",
                style="warning",
                err=True,
            )
        config[options.key] = options.value

    def _show_config(self, config: Mapping[str, Any], supersedes: Mapping[str, Any]) -> None:
        assert Config.site is not None
        for key in sorted(config):
            deprecated = ""
            canonical_key = key
            superseded = key in supersedes
            if key in Config.site.deprecated:  # pragma: no cover
                canonical_key = Config.site.deprecated[key]
                if canonical_key in supersedes:
                    superseded = True
                deprecated = f"[error](deprecating: {key})[/]"
            elif key not in Config._config_map and not (key.startswith("pypi.") or key.startswith(REPOSITORY)):
                continue
            extra_style = "dim" if superseded else None
            if canonical_key not in Config._config_map:
                if key.startswith("pypi."):
                    index = key.split(".")[1]
                    self.ui.echo(
                        f"[warning]# Configuration of non-default Pypi index `{index}`",
                        style=extra_style,
                        verbosity=termui.Verbosity.DETAIL,
                    )
                    self.ui.echo(RegistryConfig(**config[key], config_prefix=key))
                elif key.startswith(REPOSITORY):
                    for item in config[key]:
                        self.ui.echo(
                            f"[warning]# Configuration of custom repository `{item}`",
                            style=extra_style,
                            verbosity=termui.Verbosity.DETAIL,
                        )
                        repository = dict(config[key][item])
                        if "url" not in repository and item in DEFAULT_REPOSITORIES:
                            repository["url"] = DEFAULT_REPOSITORIES[item].url
                        self.ui.echo(RepositoryConfig(**repository, config_prefix=f"{key}.{item}"))
                continue
            config_item = Config._config_map[canonical_key]
            self.ui.echo(
                f"[warning]# {config_item.description}",
                style=extra_style,
                verbosity=termui.Verbosity.DETAIL,
            )
            value = "[i]<hidden>[/]" if key.endswith("password") else config[key]
            self.ui.echo(
                f"[primary]{canonical_key}[/]{deprecated} = {value}",
                style=extra_style,
            )

    def _list_config(self, project: Project, options: argparse.Namespace) -> None:
        self.ui = project.core.ui
        assert Config.site is not None
        self.ui.echo(
            f"Site/default configuration ([success]{Config.site.config_file}[/]):",
            style="bold",
        )
        self._show_config(
            Config.get_defaults(),
            {**project.global_config.self_data, **project.project_config.self_data},
        )

        self.ui.echo(
            f"\nHome configuration ([success]{project.global_config.config_file}[/]):",
            style="bold",
        )
        self._show_config(project.global_config.self_data, project.project_config.self_data)

        self.ui.echo(
            f"\nProject configuration ([success]{project.project_config.config_file}[/]):",
            style="bold",
        )
        self._show_config(project.project_config.self_data, {})

    def _delete_config(self, project: Project, options: argparse.Namespace) -> None:
        config = project.project_config if options.local else project.global_config
        if options.key in config.deprecated:  # pragma: no cover
            project.core.ui.echo(
                f"DEPRECATED: the config has been renamed to {config.deprecated[options.key]}",
                style="warning",
                err=True,
            )
        del config[options.key]
