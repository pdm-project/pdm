from __future__ import annotations

import argparse
import os

import requests
from rich.progress import (
    BarColumn,
    DownloadColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from pdm.cli import actions
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.publish.package import PackageFile
from pdm.cli.commands.publish.repository import Repository
from pdm.cli.hooks import HookManager
from pdm.cli.options import project_option, skip_option, verbose_option
from pdm.exceptions import PdmUsageError, PublishError
from pdm.project import Project
from pdm.termui import logger


class Command(BaseCommand):
    """Build and publish the project to PyPI"""

    arguments = [verbose_option, project_option, skip_option]

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-r",
            "--repository",
            help="The repository name or url to publish the package to [env var: PDM_PUBLISH_REPO]",
        )
        parser.add_argument(
            "-u",
            "--username",
            help="The username to access the repository [env var: PDM_PUBLISH_USERNAME]",
        )
        parser.add_argument(
            "-P",
            "--password",
            help="The password to access the repository [env var: PDM_PUBLISH_PASSWORD]",
        )
        parser.add_argument(
            "-S",
            "--sign",
            action="store_true",
            help="Upload the package with PGP signature",
        )
        parser.add_argument(
            "-i",
            "--identity",
            help="GPG identity used to sign files.",
        )
        parser.add_argument(
            "-c",
            "--comment",
            help="The comment to include with the distribution file.",
        )
        parser.add_argument(
            "--no-build",
            action="store_false",
            dest="build",
            help="Don't build the package before publishing",
        )
        parser.add_argument(
            "--ca-certs",
            dest="ca_certs",
            help="The path to a PEM-encoded Certificate Authority bundle to use"
            " for publish server validation [env var: PDM_PUBLISH_CA_CERTS]",
        )

    @staticmethod
    def _make_package(filename: str, signatures: dict[str, str], options: argparse.Namespace) -> PackageFile:
        p = PackageFile.from_filename(filename, options.comment)
        if p.base_filename in signatures:
            p.add_gpg_signature(signatures[p.base_filename], p.base_filename + ".asc")
        elif options.sign:
            p.sign(options.identity)
        return p

    @staticmethod
    def _check_response(response: requests.Response) -> None:
        message = ""
        if response.status_code == 410 and "pypi.python.org" in response.url:
            message = (
                "Uploading to these sites is deprecated. "
                "Try using https://upload.pypi.org/legacy/ "
                "(or https://test.pypi.org/legacy/) instead."
            )
        elif response.status_code == 405 and "pypi.org" in response.url:
            message = "It appears you're trying to upload to pypi.org but have an invalid URL."
        else:
            try:
                response.raise_for_status()
            except requests.HTTPError as err:
                message = str(err)
        if message:
            raise PublishError(message)

    @staticmethod
    def get_repository(project: Project, options: argparse.Namespace) -> Repository:
        repository = options.repository or os.getenv("PDM_PUBLISH_REPO", "pypi")
        username = options.username or os.getenv("PDM_PUBLISH_USERNAME")
        password = options.password or os.getenv("PDM_PUBLISH_PASSWORD")
        ca_certs = options.ca_certs or os.getenv("PDM_PUBLISH_CA_CERTS")

        config = project.global_config.get_repository_config(repository)
        if config is None:
            raise PdmUsageError(f"Missing repository config of {repository}")
        if username is not None:
            config.username = username
        if password is not None:
            config.password = password
        if ca_certs is not None:
            config.ca_certs = ca_certs
        return Repository(project, config.url, config.username, config.password, config.ca_certs)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        hooks = HookManager(project, options.skip)

        hooks.try_emit("pre_publish")

        if options.build:
            actions.do_build(project, hooks=hooks)

        package_files = [str(p) for p in project.root.joinpath("dist").iterdir() if not p.name.endswith(".asc")]
        signatures = {p.stem: str(p) for p in project.root.joinpath("dist").iterdir() if p.name.endswith(".asc")}

        repository = self.get_repository(project, options)
        uploaded: list[PackageFile] = []
        with project.core.ui.make_progress(
            " [progress.percentage]{task.percentage:>3.0f}%",
            BarColumn(),
            DownloadColumn(),
            "•",
            TimeRemainingColumn(
                compact=True,
                elapsed_when_finished=True,
            ),
            "•",
            TransferSpeedColumn(),
        ) as progress, project.core.ui.logging("publish"):
            packages = sorted(
                (self._make_package(p, signatures, options) for p in package_files),
                # Upload wheels first if they exist.
                key=lambda p: not p.base_filename.endswith(".whl"),
            )
            for package in packages:
                resp = repository.upload(package, progress)
                logger.debug("Response from %s:\n%s %s", resp.url, resp.status_code, resp.reason)
                self._check_response(resp)
                uploaded.append(package)

        release_urls = repository.get_release_urls(uploaded)
        if release_urls:
            project.core.ui.echo("\n[success]View at:")
            for url in release_urls:
                project.core.ui.echo(url)

        hooks.try_emit("post_publish")
