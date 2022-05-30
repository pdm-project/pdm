import argparse

from pdm.cli.commands.base import BaseCommand


class Command(BaseCommand):
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-r",
            "--repository",
            help="The repository name or url to publish the package to"
            " [env var: PDM_PUBLISH_REPO]",
        )
        parser.add_argument(
            "-u",
            "--username",
            help="The username to access the repository"
            " [env var: PDM_PUBLISH_USERNAME]",
        )
        parser.add_argument(
            "-P",
            "--password",
            help="The password to access the repository"
            " [env var: PDM_PUBLISH_PASSWORD]",
        )
        parser.add_argument(
            "-S",
            "--sign",
            action="store_true",
            help="Upload the package with PGP signature",
        )
        parser.add_argument(
            "--no-build",
            action="store_false",
            dest="build",
            help="Don't build the package before publishing",
        )
