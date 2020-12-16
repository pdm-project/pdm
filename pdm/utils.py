"""
Utility functions
"""
import atexit
import functools
import importlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse as parse
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from distlib.wheel import Wheel
from packaging.version import parse as parse_version

from pdm._types import Source
from pdm.models.pip_shims import (
    InstallCommand,
    InstallRequirement,
    PackageFinder,
    get_package_finder,
    url_to_path,
)

try:
    from functools import cached_property
except ImportError:

    class cached_property:
        def __init__(self, func):
            self.func = func
            self.attr_name = func.__name__
            self.__doc__ = func.__doc__

        def __get__(self, inst, cls=None):
            if inst is None:
                return self
            if self.attr_name not in inst.__dict__:
                inst.__dict__[self.attr_name] = self.func(inst)
            return inst.__dict__[self.attr_name]


def prepare_pip_source_args(
    sources: List[Source], pip_args: Optional[List[str]] = None
) -> List[str]:
    if pip_args is None:
        pip_args = []
    if sources:
        # Add the source to pip9.
        pip_args.extend(["-i", sources[0]["url"]])  # type: ignore
        # Trust the host if it's not verified.
        if not sources[0].get("verify_ssl", True):
            pip_args.extend(
                ["--trusted-host", parse.urlparse(sources[0]["url"]).hostname]
            )  # type: ignore
        # Add additional sources as extra indexes.
        if len(sources) > 1:
            for source in sources[1:]:
                pip_args.extend(["--extra-index-url", source["url"]])  # type: ignore
                # Trust the host if it's not verified.
                if not source.get("verify_ssl", True):
                    pip_args.extend(
                        ["--trusted-host", parse.urlparse(source["url"]).hostname]
                    )  # type: ignore
    return pip_args


def get_pypi_source():
    """Get what is defined in pip.conf as the index-url."""
    install_cmd = InstallCommand()
    options, _ = install_cmd.parser.parse_args([])
    index_url = options.index_url
    parsed = parse.urlparse(index_url)
    verify_ssl = parsed.scheme == "https"
    if any(parsed.hostname.startswith(host) for host in options.trusted_hosts):
        verify_ssl = False
    return index_url, verify_ssl


def get_finder(
    sources: List[Source],
    cache_dir: Optional[str] = None,
    python_version: Optional[Tuple[int, int]] = None,
    ignore_requires_python: bool = False,
) -> PackageFinder:
    install_cmd = InstallCommand()
    pip_args = prepare_pip_source_args(sources)
    options, _ = install_cmd.parser.parse_args(pip_args)
    if cache_dir:
        options.cache_dir = cache_dir
    finder = get_package_finder(
        install_cmd=install_cmd,
        options=options,
        python_version=python_version,
        ignore_requires_python=ignore_requires_python,
    )
    if not hasattr(finder, "session"):
        finder.session = finder._link_collector.session
    return finder


def create_tracked_tempdir(
    suffix: Optional[str] = None, prefix: Optional[str] = "", dir: Optional[str] = None
) -> str:
    name = tempfile.mkdtemp(suffix, prefix, dir)
    os.makedirs(name, mode=0o777, exist_ok=True)

    def clean_up():
        shutil.rmtree(name, ignore_errors=True)

    atexit.register(clean_up)
    return name


def parse_name_version_from_wheel(filename: str) -> Tuple[str, str]:
    w = Wheel(filename)
    return w.name, w.version


def url_without_fragments(url: str) -> str:
    return parse.urlunparse(parse.urlparse(url)._replace(fragment=""))


def is_readonly_property(cls, name):
    """Tell whether a attribute can't be setattr'ed."""
    attr = getattr(cls, name, None)
    return attr and isinstance(attr, property) and not attr.fset


def join_list_with(items: List[Any], sep: Any) -> List[Any]:
    new_items = []
    for item in items:
        new_items.extend([item, sep])
    return new_items[:-1]


def _wheel_supported(self, tags=None):
    # Ignore current platform. Support everything.
    return True


def _wheel_support_index_min(self, tags=None):
    # All wheels are equal priority for sorting.
    return 0


@contextmanager
def allow_all_wheels(enable: bool = True):
    """Monkey patch pip.Wheel to allow all wheels

    The usual checks against platforms and Python versions are ignored to allow
    fetching all available entries in PyPI. This also saves the candidate cache
    and set a new one, or else the results from the previous non-patched calls
    will interfere.
    """
    from pdm.models.pip_shims import PipWheel

    if not enable:
        yield
        return

    original_wheel_supported = PipWheel.supported
    original_support_index_min = PipWheel.support_index_min

    PipWheel.supported = _wheel_supported
    PipWheel.support_index_min = _wheel_support_index_min
    yield
    PipWheel.supported = original_wheel_supported
    PipWheel.support_index_min = original_support_index_min


def find_project_root(cwd: str = ".", max_depth: int = 5) -> Optional[str]:
    """Recursively find a `pyproject.toml` at given path or current working directory.
    If none if found, go to the parent directory, at most `max_depth` levels will be
    looked for.
    """
    original_path = Path(cwd).absolute()
    path = original_path
    for _ in range(max_depth):
        if path.joinpath("pyproject.toml").exists():
            return path.as_posix()
        if path.parent == path:
            # Root path is reached
            break
        path = path.parent
    return None


@functools.lru_cache()
def get_python_version(executable, as_string=False):
    """Get the version of the Python interperter."""
    args = [
        executable,
        "-c",
        "import sys,json;print(json.dumps(tuple(sys.version_info[:3])))",
    ]
    result = tuple(json.loads(subprocess.check_output(args)))
    if not as_string:
        return result
    return ".".join(map(str, result))


def get_sys_config_paths(executable: str, vars=None) -> Dict[str, str]:
    """Return the sys_config.get_paths() result for the python interpreter"""
    if not vars:
        args = [
            executable,
            "-c",
            "import sysconfig,json;print(json.dumps(sysconfig.get_paths()))",
        ]
        return json.loads(subprocess.check_output(args))
    else:
        env = os.environ.copy()
        env.update(SYSCONFIG_VARS=json.dumps(vars))
        args = [
            executable,
            "-c",
            "import os,sysconfig,json;print(json.dumps(sysconfig."
            "get_paths(vars=json.loads(os.getenv('SYSCONFIG_VARS')))))",
        ]
        return json.loads(subprocess.check_output(args, env=env))


def get_pep508_environment(executable: str) -> Dict[str, Any]:
    script = importlib.import_module("pdm.pep508").__file__.rstrip("co")
    args = [executable, script]
    return json.loads(subprocess.check_output(args))


def convert_hashes(hashes: Dict[str, str]) -> Dict[str, List[str]]:
    """Convert Pipfile.lock hash lines into InstallRequirement option format.

    The option format uses a str-list mapping. Keys are hash algorithms, and
    the list contains all values of that algorithm.
    """
    result = {}
    for hash_value in hashes.values():
        try:
            name, hash_value = hash_value.split(":")
        except ValueError:
            name = "sha256"
        result.setdefault(name, []).append(hash_value)
    return result


def get_user_email_from_git() -> Tuple[str, str]:
    """Get username and email from git config.
    Return empty if not configured or git is not found.
    """
    git = shutil.which("git")
    if not git:
        return "", ""
    try:
        username = subprocess.check_output(
            [git, "config", "user.name"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        username = ""
    try:
        email = subprocess.check_output(
            [git, "config", "user.email"], text=True
        ).strip()
    except subprocess.CalledProcessError:
        email = ""
    return username, email


def add_ssh_scheme_to_git_uri(uri: str) -> str:
    """Cleans VCS uris from pip format"""
    # Add scheme for parsing purposes, this is also what pip does
    if "://" not in uri:
        uri = "ssh://" + uri
        parsed = parse.urlparse(uri)
        if ":" in parsed.netloc:
            netloc, _, path_start = parsed.netloc.rpartition(":")
            path = "/{0}{1}".format(path_start, parsed.path)
            uri = parse.urlunparse(parsed._replace(netloc=netloc, path=path))
    return uri


def get_venv_python(root: Path) -> Optional[str]:
    """Get the python interpreter path of venv"""
    if os.name == "nt":
        suffix = ".exe"
        scripts = "Scripts"
    else:
        suffix = ""
        scripts = "bin"
    venv = None
    if "VIRTUAL_ENV" in os.environ:
        venv = os.environ["VIRTUAL_ENV"]
    else:
        for possible_dir in ("venv", ".venv", "env"):
            if (root / possible_dir / scripts / f"python{suffix}").exists():
                venv = str(root / possible_dir)
                break
    if venv:
        return os.path.join(venv, scripts, f"python{suffix}")
    return None


@contextmanager
def atomic_open_for_write(filename: Union[Path, str], *, encoding: str = "utf-8"):
    fd, name = tempfile.mkstemp("-atomic-write", "pdm-")
    filename = str(filename)
    try:
        f = open(fd, "w", encoding=encoding)
        yield f
    except Exception:
        f.close()
        os.unlink(name)
        raise
    else:
        f.close()
        try:
            os.unlink(filename)
        except OSError:
            pass
        shutil.move(name, filename)


@contextmanager
def cd(path: str):
    _old_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(_old_cwd)


@contextmanager
def temp_environ():
    environ = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ)


@contextmanager
def open_file(url, session=None):
    if url.startswith("file://"):
        local_path = url_to_path(url)
        if os.path.isdir(local_path):
            raise ValueError("Cannot open directory for read: {}".format(url))
        else:
            with open(local_path, "rb") as local_file:
                yield local_file
    else:
        headers = {"Accept-Encoding": "identity"}
        with session.get(url, headers=headers, stream=True) as resp:
            try:
                raw = getattr(resp, "raw", None)
                result = raw if raw else resp
                yield result
            finally:
                if raw:
                    conn = getattr(raw, "_connection")
                    if conn is not None:
                        conn.close()
                result.close()


def highest_version(versions: List[str]) -> str:
    """Return the highest version of a given list."""
    return max(versions, key=parse_version)


def populate_link(
    finder: PackageFinder,
    ireq: InstallRequirement,
    upgrade: bool = False,
):
    """Populate ireq's link attribute"""
    if not ireq.link:
        link = finder.find_requirement(ireq, upgrade)
        if not link:
            return
        link = getattr(link, "link", link)
        ireq.link = link
