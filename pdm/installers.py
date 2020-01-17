from pdm.models.environment import Environment


class Installer:

    def __init__(self, environment: Environment) -> None:
        self.environment = environment
