import os
import subprocess

from pip_shims import shims

import distlib.scripts
from distlib.wheel import Wheel
from pdm.models.candidates import Candidate
from pdm.models.environment import Environment

SETUPTOOLS_SHIM = (
    "import setuptools, tokenize;__file__=%r;"
    "f=getattr(tokenize, 'open', open)(__file__);"
    "code=f.read().replace('\\r\\n', '\\n');"
    "f.close();"
    "exec(compile(code, __file__, 'exec'))"
)


class Installer:
    # TODO: Support PEP 517 builds

    def __init__(self, environment: Environment) -> None:
        self.environment = environment

    def install_candidate(self, candidate: Candidate) -> None:
        print(f"Installing {candidate.name} {candidate.version}...")
        candidate.get_metadata()
        if candidate.wheel:
            self.install_wheel(candidate.wheel)
        else:
            self.install_editable(candidate.ireq)

    def install_wheel(self, wheel: Wheel) -> None:
        paths = self.environment.get_paths()
        scripts = distlib.scripts.ScriptMaker(None, None)
        scripts.script_template = scripts.script_template.replace(
            "import sys",
            "import sys; sys.path.insert(0, {!r})".format(paths["platlib"])
        )
        wheel.install(paths, scripts)

    def install_editable(self, ireq: shims.InstallRequirement) -> None:
        setup_path = ireq.setup_py_path
        paths = self.environment.get_paths()
        old_pwd = os.getcwd()
        install_args = [
            self.environment.python_executable, "-u", "-c",
            SETUPTOOLS_SHIM % setup_path,
            "develop", "--install-dir={}".format(paths["platlib"]), "--no-deps",
            "--prefix={}".format(paths["prefix"]),
            "--script-dir={}".format(paths["scripts"]),
            "--site-dirs={}".format(paths["platlib"])
        ]
        os.chdir(ireq.source_dir)
        try:
            with self.environment.activate():
                subprocess.check_call(install_args)
        finally:
            os.chdir(old_pwd)
