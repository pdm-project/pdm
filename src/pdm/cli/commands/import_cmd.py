from __future__ import annotations

import argparse

from pdm.cli.commands.base import BaseCommand
from pdm.exceptions import PdmUsageError
from pdm.formats import FORMATS
from pdm.project import Project


class Command(BaseCommand):
    """Import project metadata from other formats"""

    name = "import"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-d",
            "--dev",
            default=False,
            action="store_true",
            help="import packages into dev dependencies",
        )
        parser.add_argument("-G", "--group", help="Specify the target dependency group to import into")
        parser.add_argument(
            "-f",
            "--format",
            choices=FORMATS.keys(),
            help="Specify the file format explicitly",
        )
        parser.add_argument("filename", help="The file name")
        parser.set_defaults(search_parent=False)

    def handle(self, project: Project, options: argparse.Namespace) -> None:
        self.do_import(project, options.filename, options.format, options)

    @staticmethod
    def do_import(
        project: Project,
        filename: str,
        format: str | None = None,
        options: argparse.Namespace | None = None,
        reset_backend: bool = True,
    ) -> None:
        """Import project metadata from given file.

        :param project: the project instance
        :param filename: the file name
        :param format: the file format, or guess if not given.
        :param options: other options parsed to the CLI.
        """
        import tomlkit

        from pdm.cli.utils import merge_dictionary
        from pdm.formats import FORMATS
        from pdm.models.backends import DEFAULT_BACKEND

        if not format:
            for key in FORMATS:
                if FORMATS[key].check_fingerprint(project, filename):
                    break
            else:
                raise PdmUsageError(
                    "Can't derive the file format automatically, please specify it via '-f/--format' option."
                )
        else:
            key = format
        if options is None:
            options = argparse.Namespace(dev=False, group=None)
        project_data, settings = FORMATS[key].convert(project, filename, options)
        pyproject = project.pyproject._data

        if "tool" not in pyproject or "pdm" not in pyproject["tool"]:
            pyproject.setdefault("tool", {})["pdm"] = tomlkit.table()
        if "build" in pyproject["tool"]["pdm"] and isinstance(pyproject["tool"]["pdm"]["build"], str):
            pyproject["tool"]["pdm"]["build"] = {
                "setup-script": pyproject["tool"]["pdm"]["build"],
                "run-setuptools": True,
            }
        if "project" not in pyproject:
            pyproject.add("project", tomlkit.table())
            pyproject["project"].add(tomlkit.comment("PEP 621 project metadata"))
            pyproject["project"].add(tomlkit.comment("See https://www.python.org/dev/peps/pep-0621/"))

        merge_dictionary(pyproject["project"], project_data)
        merge_dictionary(pyproject["tool"]["pdm"], settings)
        if reset_backend:
            pyproject["build-system"] = DEFAULT_BACKEND.build_system()

        if "requires-python" not in pyproject["project"]:
            python_version = f"{project.python.major}.{project.python.minor}"
            pyproject["project"]["requires-python"] = f">={python_version}"
            project.core.ui.echo(
                "The project's [primary]requires-python[/] has been set to [primary]>="
                f"{python_version}[/]. You can change it later if necessary."
            )
        project.pyproject.write()
