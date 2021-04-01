"""
Utility functions
"""
import atexit
import functools
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse as parse
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from re import Match
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    TextIO,
    Tuple,
    TypeVar,
    overload,
)

from distlib.wheel import Wheel
from pip._vendor.packaging.tags import Tag
from pip._vendor.requests import Session

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

    _T = TypeVar("_T")
    _C = TypeVar("_C")

    class cached_property(Generic[_T]):
        def __init__(self, func: Callable[[Any], _T]):
            self.func = func
            self.attr_name = func.__name__
            self.__doc__ = func.__doc__

        @overload
        def __get__(self: _C, inst: None, cls: Any = ...) -> _C:
            ...

        @overload
        def __get__(self, inst: object, cls: Any = ...) -> _T:
            ...

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


def get_pypi_source() -> Tuple[str, bool]:
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

    def clean_up() -> None:
        shutil.rmtree(name, ignore_errors=True)

    atexit.register(clean_up)
    return name


def parse_name_version_from_wheel(filename: str) -> Tuple[str, str]:
    w = Wheel(filename)
    return w.name, w.version


def url_without_fragments(url: str) -> str:
    return parse.urlunparse(parse.urlparse(url)._replace(fragment=""))


def is_readonly_property(cls: Any, name: str) -> Optional[Any]:
    """Tell whether a attribute can't be setattr'ed."""
    attr = getattr(cls, name, None)
    return attr and isinstance(attr, property) and not attr.fset


def join_list_with(items: List[Any], sep: Any) -> List[Any]:
    new_items = []
    for item in items:
        new_items.extend([item, sep])
    return new_items[:-1]


def _wheel_supported(self: Any, tags: List[Tag] = None) -> bool:
    # Ignore current platform. Support everything.
    return True


def _wheel_support_index_min(self: Any, tags: Optional[str] = None) -> int:
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


def convert_hashes(hashes: Dict[str, str]) -> Dict[str, List[str]]:
    """Convert Pipfile.lock hash lines into InstallRequirement option format.

    The option format uses a str-list mapping. Keys are hash algorithms, and
    the list contains all values of that algorithm.
    """
    result: Dict[str, List[str]] = {}
    for hash_value in hashes.values():
        try:
            name, hash_value = hash_value.split(":")
        except ValueError:
            name = "sha256"
        setdefault(result, name, []).append(hash_value)
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


def get_in_project_venv_python(root: Path) -> Optional[Path]:
    """Get the python interpreter path of venv-in-project"""
    if os.name == "nt":
        suffix = ".exe"
        scripts = "Scripts"
    else:
        suffix = ""
        scripts = "bin"
    for possible_dir in ("venv", ".venv", "env"):
        if (root / possible_dir / scripts / f"python{suffix}").exists():
            venv = root / possible_dir
            return venv / scripts / f"python{suffix}"
    return None


@contextmanager
def atomic_open_for_write(filename: PathLike, *, encoding: str = "utf-8"):
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
def temp_environ() -> Iterator:
    environ = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ)


@contextmanager
def open_file(url: str, session: Optional[Session] = None) -> TextIO:
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


def setdefault(document: Dict, key: str, value: Any) -> Dict:
    """A compatiable dict.setdefault() for tomlkit data structures."""
    if key not in document:
        document[key] = value
    return document[key]


def get_python_version_string(version: str, is_64bit: bool) -> str:
    if os.name == "nt" and not is_64bit:
        return f"{version}-32"
    return version


def expand_env_vars(credential: str, quote: bool = False) -> str:
    """A safe implementation of env var substitution.
    It only supports the following forms:

        ${ENV_VAR}

    Neither $ENV_VAR and %ENV_VAR is not supported.
    """

    def replace_func(match: Match) -> str:
        rv = os.getenv(match.group(1), match.group(0))
        return parse.quote(rv) if quote else rv

    return re.sub(r"\$\{(.+?)\}", replace_func, credential)


def expand_env_vars_in_auth(url: str) -> str:
    """In-place expand the auth in url"""
    scheme, netloc, path, params, query, fragment = parse.urlparse(url)
    if "@" in netloc:
        auth, rest = netloc.split("@", 1)
        auth = expand_env_vars(auth, True)
        netloc = "@".join([auth, rest])
    return parse.urlunparse((scheme, netloc, path, params, query, fragment))


@functools.lru_cache()
def path_replace(pattern: str, replace_with: str, dest: str) -> str:
    """Safely replace the pattern in a path with given string.

    :param pattern: the pattern to match
    :param replace_with: the string to replace with
    :param dest: the path to replace
    :return the replaced path
    """
    sub_flags = re.IGNORECASE if os.name == "nt" else 0
    return re.sub(
        pattern.replace("\\", "/"),
        replace_with,
        dest.replace("\\", "/"),
        flags=sub_flags,
    )


def is_venv_python(interpreter: os.PathLike) -> bool:
    """Check if the given interpreter path is from a virtualenv"""
    interpreter = Path(interpreter)
    if interpreter.parent.parent.joinpath("pyvenv.cfg").exists():
        return True
    if os.getenv("VIRTUAL_ENV"):
        try:
            interpreter.relative_to(os.getenv("VIRTUAL_ENV"))
        except ValueError:
            pass
        else:
            return True
    return False


def find_python_in_path(path: os.PathLike) -> Optional[Path]:
    """Find a python interpreter from the given path, the input argument could be:

    - A valid path to the interpreter
    - A Python root directory that contains the interpreter
    """
    pathlib_path = Path(path).absolute()
    if pathlib_path.is_file():
        return pathlib_path

    if os.name == "nt":
        for root_dir in (pathlib_path, pathlib_path / "Scripts"):
            if root_dir.joinpath("python.exe").exists():
                return root_dir.joinpath("python.exe")
    else:
        executable_pattern = re.compile(r"python(?:\d(?:\.\d+m?)?)?$")

        for python in pathlib_path.joinpath("bin").glob("python*"):
            if executable_pattern.match(python.name):
                return python

    return None


def get_rev_from_url(url: str) -> str:
    """Get the rev part from the VCS URL."""
    path = parse.urlparse(url).path
    if "@" in path:
        _, rev = path.rsplit("@", 1)
        return rev
    return ""
