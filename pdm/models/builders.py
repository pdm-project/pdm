import os
import subprocess
import sys

from build import ProjectBuilder
from build.env import IsolatedEnvironment

from pdm.exceptions import BuildError
from pdm.iostream import stream
from pdm.pep517.base import Builder

_SETUPTOOLS_SHIM = (
    "import sys, setuptools, tokenize; sys.argv[0] = {0!r}; __file__={0!r};"
    "f=getattr(tokenize, 'open', open)(__file__);"
    "code=f.read().replace('\\r\\n', '\\n');"
    "f.close();"
    "exec(compile(code, __file__, 'exec'))"
)


def build_wheel(src_dir: str, out_dir: str) -> str:
    """Build wheel and return the full path of the artifact."""
    builder = ProjectBuilder(srcdir=src_dir)
    stream.echo("Building wheel...")
    with IsolatedEnvironment.for_current() as env:
        env.install(builder.build_dependencies)
        filename = builder.hook.build_wheel(out_dir)
    stream.echo(f"Built {filename}")
    return os.path.join(out_dir, filename)


def build_sdist(src_dir: str, out_dir: str) -> str:
    """Build sdist and return the full path of the artifact."""
    builder = ProjectBuilder(srcdir=src_dir)
    stream.echo("Building sdist...")
    with IsolatedEnvironment.for_current() as env:
        env.install(builder.build_dependencies)
        filename = builder.hook.build_sdist(out_dir)
    stream.echo(f"Built {filename}")
    return os.path.join(out_dir, filename)


def _find_egg_info(directory: str) -> str:
    filename = next(
        (f for f in os.listdir(directory) if f.endswith(".egg-info")),
        None,
    )
    if not filename:
        raise BuildError("No egg info is generated.")
    return filename


def build_egg_info(src_dir: str, out_dir: str) -> str:
    # Ignore destination since editable builds should be build locally
    builder = Builder(src_dir)
    setup_py_path = builder.ensure_setup_py().as_posix()
    args = [sys.executable, "-c", _SETUPTOOLS_SHIM.format(setup_py_path)]
    args.extend(["egg_info", "--egg-base", out_dir])
    stream.echo("Building egg info...")
    proc = subprocess.run(args, capture_output=stream.verbosity <= stream.DETAIL)
    if proc.returncode:
        raise BuildError(f"Error occurs when running {args}:\n{proc.stderr}")
    filename = _find_egg_info(out_dir)
    stream.echo(f"Built {filename}")
    return os.path.join(out_dir, filename)
