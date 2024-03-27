from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

from pdm.cli.commands import build
from pdm.cli.commands.base import BaseCommand
from pdm.cli.commands.publish.package import PackageFile
from pdm.cli.commands.publish.repository import Repository
from pdm.cli.hooks import HookManager
from pdm.cli.options import project_option, skip_option, verbose_option
from pdm.exceptions import PdmUsageError, PublishError
from pdm.termui import logger

if TYPE_CHECKING:
    from httpx import Response

    from pdm.project import Project


class Command(BaseCommand):
    """Build and publish the project to PyPI"""

    arguments = (verbose_option, project_option, skip_option)

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
            "-d",
            "--dest",
            help="The directory to upload the package from",
            default="dist",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip uploading files that already exist. This may not work with some repository implementations.",
        )
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--no-very-ssl", action="store_false", dest="verify_ssl", help="Disable SSL verification", default=None
        )
        group.add_argument(
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
    def _skip_upload(response: Response) -> bool:
        status = response.status_code
        reason = response.reason_phrase.lower()
        text = response.text.lower()

        # Borrowed from https://github.com/pypa/twine/blob/main/twine/commands/upload.py#L149
        return (
            # pypiserver (https://pypi.org/project/pypiserver)
            status == 409
            # PyPI / TestPyPI / GCP Artifact Registry
            or (status == 400 and any("already exist" in x for x in [reason, text]))
            # Nexus Repository OSS (https://www.sonatype.com/nexus-repository-oss)
            or (status == 400 and any("updating asset" in x for x in [reason, text]))
            # Artifactory (https://jfrog.com/artifactory/)
            or (status == 403 and "overwrite artifact" in text)
            # Gitlab Enterprise Edition (https://about.gitlab.com)
            or (status == 400 and "already been taken" in text)
        )

    @staticmethod
    def _check_response(response: Response) -> None:
        import httpx

        message = ""
        if response.status_code == 410 and "pypi.python.org" in str(response.url):
            message = (
                "Uploading to these sites is deprecated. "
                "Try using https://upload.pypi.org/legacy/ "
                "(or https://test.pypi.org/legacy/) instead."
            )
        elif response.status_code == 405 and "pypi.org" in str(response.url):
            message = "It appears you're trying to upload to pypi.org but have an invalid URL."
        else:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as err:
                message = str(err)
                if response.text:
                    logger.debug(response.text)
        if message:
            raise PublishError(message)

    @staticmethod
    def get_repository(project: Project, options: argparse.Namespace) -> Repository:
        repository = options.repository or os.getenv("PDM_PUBLISH_REPO", "pypi")
        username = options.username or os.getenv("PDM_PUBLISH_USERNAME")
        password = options.password or os.getenv("PDM_PUBLISH_PASSWORD")
        ca_certs = options.ca_certs or os.getenv("PDM_PUBLISH_CA_CERTS")

        config = project.global_config.get_repository_config(repository, "repository")
        if config is None:
            raise PdmUsageError(f"Missing repository config of {repository}")
        assert config.url is not None
        if username is not None:
            config.username = username
        if password is not None:
            config.password = password
        if ca_certs is not None:
            config.ca_certs = ca_certs
        if options.verify_ssl is False:
            config.verify_ssl = options.verify_ssl
        return Repository(project, config)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        hooks = HookManager(project, options.skip)

        hooks.try_emit("pre_publish")

        if options.build:
            build.Command.do_build(project, dest=options.dest, hooks=hooks)

        upload_dir = project.root.joinpath(options.dest)
        package_files = [str(p) for p in upload_dir.iterdir() if not p.name.endswith(".asc")]
        signatures = {p.stem: str(p) for p in upload_dir.iterdir() if p.name.endswith(".asc")}

        repository = self.get_repository(project, options)
        uploaded: list[PackageFile] = []
        with project.core.ui.logging("publish"):
            packages = sorted(
                (self._make_package(p, signatures, options) for p in package_files),
                # Upload wheels first if they exist.
                key=lambda p: not p.base_filename.endswith(".whl"),
            )
            for package in packages:
                resp = repository.upload(package)
                logger.debug("Response from %s:\n%s %s", resp.url, resp.status_code, resp.reason_phrase)

                if options.skip_existing and self._skip_upload(resp):
                    project.core.ui.warn(f"Skipping {package.base_filename} because it appears to already exist")
                    continue
                self._check_response(resp)
                uploaded.append(package)

        release_urls = repository.get_release_urls(uploaded)
        if release_urls:
            project.core.ui.echo("\n[success]View at:")
            for url in release_urls:
                project.core.ui.echo(url)

        hooks.try_emit("post_publish")
