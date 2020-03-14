from pdm.cli.commands.base import BaseCommand


class HelloCommand(BaseCommand):
    """Say hello to somebody"""

    def add_arguments(self, parser):
        parser.add_argument("-n", "--name", help="the person's name")

    def handle(self, project, options):
        print(f"Hello, {options.name or 'world'}")


def main(core):
    core.register_command(HelloCommand, "hello")
