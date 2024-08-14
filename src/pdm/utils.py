"""
Utility functions
"""

from __future__ import annotations

import atexit
import contextlib
import functools
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.parse as parse
import warnings
from datetime import datetime, timezone
from os import name as os_name
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from packaging.version import Version, _cmpkey
from pbs_installer import PythonVersion

from pdm.compat import importlib_metadata
from pdm.exceptions import PDMDeprecationWarning, PdmException

if TYPE_CHECKING:
    from re import Match
    from typing import IO, Any, Iterator

    from pdm._types import FileHash, RepositoryConfig
    from pdm.compat import Distribution

_egg_fragment_re = re.compile(r"(.*)[#&]egg=[^&]*")

try:
    _packaging_version = importlib_metadata.version("packaging")
except Exception:
    from packaging import __version__ as _packaging_version


@functools.lru_cache(maxsize=1024)
def parse_version(version: str) -> Version:
    return Version(version)


PACKAGING_22 = parse_version(_packaging_version) >= parse_version("22")


def create_tracked_tempdir(suffix: str | None = None, prefix: str | None = None, dir: str | None = None) -> str:
    name = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
    os.makedirs(name, mode=0o777, exist_ok=True)

    def clean_up() -> None:
        shutil.rmtree(name, ignore_errors=True)

    atexit.register(clean_up)
    return name


def get_trusted_hosts(sources: list[RepositoryConfig]) -> list[str]:
    """Parse the project sources and return the trusted hosts"""
    trusted_hosts = []
    for source in sources:
        assert source.url
        url = source.url
        netloc = parse.urlparse(url).netloc
        host = netloc.rsplit("@", 1)[-1]
        if host not in trusted_hosts and source.verify_ssl is False:
            trusted_hosts.append(host)
    return trusted_hosts


def url_without_fragments(url: str) -> str:
    return parse.urlunparse(parse.urlparse(url)._replace(fragment=""))


def join_list_with(items: list[Any], sep: Any) -> list[Any]:
    new_items = []
    for item in items:
        new_items.extend([item, sep])
    return new_items[:-1]


def find_project_root(cwd: str = ".") -> str | None:
    """Recursively find a `pyproject.toml` at given path or current working directory."""
    path = Path(cwd).absolute()
    if list(path.glob("pyproject.toml")):
        return path.as_posix()

    if path == path.parent:
        return None

    return find_project_root(str(path.parent))


def convert_hashes(files: list[FileHash]) -> dict[str, list[str]]:
    """Convert Pipfile.lock hash lines into InstallRequirement option format.

    The option format uses a str-list mapping. Keys are hash algorithms, and
    the list contains all values of that algorithm.
    """
    result: dict[str, list[str]] = {}
    for f in files:
        hash_value = f.get("hash", "")
        name, has_name, hash_value = hash_value.partition(":")
        if not has_name:
            name, hash_value = "sha256", name
        result.setdefault(name, []).append(hash_value)
    return result


def get_user_email_from_git() -> tuple[str, str]:
    """Get username and email from git config.
    Return empty if not configured or git is not found.
    """
    git = shutil.which("git")
    if not git:
        return "", ""
    try:
        username = subprocess.check_output([git, "config", "user.name"], text=True, encoding="utf-8").strip()
    except subprocess.CalledProcessError:
        username = ""
    try:
        email = subprocess.check_output([git, "config", "user.email"], text=True, encoding="utf-8").strip()
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
            path = f"/{path_start}{parsed.path}"
            uri = parse.urlunparse(parsed._replace(netloc=netloc, path=path))
    return uri


@contextlib.contextmanager
def atomic_open_for_write(filename: str | Path, *, mode: str = "w", encoding: str = "utf-8") -> Iterator[IO]:
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    fd, name = tempfile.mkstemp(prefix="atomic-write-", dir=dirname)
    fp = open(fd, mode, encoding=encoding if "b" not in mode else None)
    try:
        yield fp
    except Exception:
        fp.close()
        raise
    else:
        fp.close()
        with contextlib.suppress(OSError):
            os.unlink(filename)
        # The tempfile is created with mode 600, we need to restore the default mode
        # with copyfile() instead of move().
        # See: https://github.com/pdm-project/pdm/issues/542
        shutil.copyfile(name, str(filename))
    finally:
        os.unlink(name)


@contextlib.contextmanager
def cd(path: str | Path) -> Iterator:
    _old_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(_old_cwd)


def url_to_path(url: str) -> str:
    """
    Convert a file: URL to a path.
    """
    from urllib.request import url2pathname

    WINDOWS = sys.platform == "win32"

    assert url.startswith("file:"), f"You can only turn file: urls into filenames (not {url!r})"

    _, netloc, path, _, _ = parse.urlsplit(url)

    if not netloc or netloc == "localhost":
        # According to RFC 8089, same as empty authority.
        netloc = ""
    elif WINDOWS:
        # If we have a UNC path, prepend UNC share notation.
        netloc = "\\\\" + netloc
    else:
        raise ValueError(f"non-local file URIs are not supported on this platform: {url!r}")

    path = url2pathname(netloc + path)

    # On Windows, urlsplit parses the path as something like "/C:/Users/foo".
    # This creates issues for path-related functions like io.open(), so we try
    # to detect and strip the leading slash.
    if (
        WINDOWS
        and not netloc  # Not UNC.
        and len(path) >= 3
        and path[0] == "/"  # Leading slash to strip.
        and path[1].isalpha()  # Drive letter.
        and path[2:4] in (":", ":/")  # Colon + end of string, or colon + absolute path.
    ):
        path = path[1:]

    return path


def path_to_url(path: str) -> str:
    """
    Convert a path to a file: URL.  The path will be made absolute and have
    quoted path parts.
    """
    from urllib.request import pathname2url

    path = os.path.normpath(os.path.abspath(path))
    url = parse.urljoin("file:", pathname2url(path))
    return url


def expand_env_vars(credential: str, quote: bool = False, env: Mapping[str, str] | None = None) -> str:
    """A safe implementation of env var substitution.
    It only supports the following forms:

        ${ENV_VAR}

    Neither $ENV_VAR and %ENV_VAR is supported.
    """
    if env is None:
        env = os.environ

    def replace_func(match: Match) -> str:
        rv = env.get(match.group(1), match.group(0))
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


@functools.lru_cache
def path_replace(pattern: str, replace_with: str, dest: str) -> str:
    """Safely replace the pattern in a path with given string.

    :param pattern: the pattern to match
    :param replace_with: the string to replace with
    :param dest: the path to replace
    :return the replaced path
    """
    sub_flags = re.IGNORECASE if os_name == "nt" else 0
    return re.sub(
        pattern.replace("\\", "/"),
        replace_with,
        dest.replace("\\", "/"),
        flags=sub_flags,
    )


def is_path_relative_to(path: str | Path, other: str | Path) -> bool:
    try:
        Path(path).relative_to(other)
    except ValueError:
        return False
    return True


def get_venv_like_prefix(interpreter: str | Path) -> tuple[Path | None, bool]:
    """Check if the given interpreter path is from a virtualenv,
    and return two values: the root path and whether it's a conda env.
    """
    interpreter = Path(interpreter)
    prefix = interpreter.parent
    if prefix.joinpath("conda-meta").exists():
        return prefix, True

    prefix = prefix.parent
    if prefix.joinpath("pyvenv.cfg").exists():
        return prefix, False
    if prefix.joinpath("conda-meta").exists():
        return prefix, True

    virtual_env = os.getenv("VIRTUAL_ENV")
    if virtual_env and is_path_relative_to(interpreter, virtual_env):
        return Path(virtual_env), False
    virtual_env = os.getenv("CONDA_PREFIX")
    if virtual_env and is_path_relative_to(interpreter, virtual_env):
        return Path(virtual_env), True
    return None, False


def find_python_in_path(path: str | Path) -> Path | None:
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


@functools.lru_cache
def normalize_name(name: str, lowercase: bool = True) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "-", name)
    return name.lower() if lowercase else name


def comparable_version(version: str) -> Version:
    """Normalize a version to make it valid in a specifier."""
    parsed = parse_version(version)
    if parsed.local is not None:
        # strip the local part
        parsed._version = parsed._version._replace(local=None)

        # To make comparable_version("1.2.3+local1") == Version("1.2.3")
        parsed._key = _cmpkey(
            parsed._version.epoch,
            parsed._version.release,
            parsed._version.pre,
            parsed._version.post,
            parsed._version.dev,
            parsed._version.local,
        )

    return parsed


def is_egg_link(dist: Distribution) -> bool:
    """Check if the distribution is an egg-link install"""
    return getattr(dist, "link_file", None) is not None


def is_editable(dist: Distribution) -> bool:
    """Check if the distribution is installed in editable mode"""
    if is_egg_link(dist):
        return True
    direct_url = dist.read_text("direct_url.json")
    if not direct_url:
        return False
    direct_url_data = json.loads(direct_url)
    return direct_url_data.get("dir_info", {}).get("editable", False)


def pdm_scheme(base: str) -> dict[str, str]:
    """Return a PEP 582 style install scheme"""
    if "pep582" not in sysconfig.get_scheme_names():
        bin_prefix = "Scripts" if os.name == "nt" else "bin"
        sysconfig._INSTALL_SCHEMES["pep582"] = {  # type: ignore[attr-defined]
            "stdlib": "{pep582_base}/lib",
            "platstdlib": "{pep582_base}/lib",
            "purelib": "{pep582_base}/lib",
            "platlib": "{pep582_base}/lib",
            "include": "{pep582_base}/include",
            "scripts": f"{{pep582_base}}/{bin_prefix}",
            "data": "{pep582_base}",
            "prefix": "{pep582_base}",
            "headers": "{pep582_base}/include",
        }
    return sysconfig.get_paths("pep582", vars={"pep582_base": base}, expand=True)


def is_url(url: str) -> bool:
    """Check if the given string is a URL"""
    return bool(parse.urlparse(url).scheme)


@functools.lru_cache
def fs_supports_link_method(method: str) -> bool:
    if not hasattr(os, method):
        return False
    if sys.platform == "win32":
        with tempfile.TemporaryDirectory(prefix="TmP") as temp_dir:
            with open(src := os.path.join(temp_dir, "a"), "w") as tmp_file:
                tmp_file.write("foo")
            dest = f"{src}-link"
            try:
                getattr(os, method)(src, dest)
                return True
            except (OSError, NotImplementedError):
                return False
    else:
        return True


def deprecation_warning(message: str, stacklevel: int = 1, raise_since: str | None = None) -> None:  # pragma: no cover
    """Show a deprecation warning with the given message and raise an error
    after a specified version.
    """
    from pdm.__version__ import __version__

    if raise_since is not None:
        if parse_version(__version__) >= parse_version(raise_since):
            raise PDMDeprecationWarning(message)
    warnings.warn(message, PDMDeprecationWarning, stacklevel=stacklevel + 1)


def is_pip_compatible_with_python(python_version: Version | str) -> bool:
    """Check the given python version is compatible with the pip installed"""
    from pdm.compat import importlib_metadata
    from pdm.models.specifiers import get_specifier

    pip = importlib_metadata.distribution("pip")
    requires_python = get_specifier(pip.metadata.get("Requires-Python"))
    return requires_python.contains(python_version, True)


def path_without_fragments(path: str) -> Path:
    """Remove egg fragment from path"""
    match = _egg_fragment_re.search(path)
    if not match:
        return Path(path)
    return Path(match.group(1))


def is_in_zipapp() -> bool:
    """Check if the current process is running in a zipapp"""
    return not os.path.exists(__file__)


@functools.lru_cache(None)
def package_installed(package_name: str) -> bool:
    try:
        importlib_metadata.distribution(package_name)
    except importlib_metadata.PackageNotFoundError:
        return False
    else:
        return True


def validate_project_name(name: str) -> bool:
    """Check if the project name is valid or not"""

    pattern = r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$"
    return re.fullmatch(pattern, name, flags=re.IGNORECASE) is not None


def sanitize_project_name(name: str) -> str:
    """Sanitize the project name and remove all illegal characters"""
    pattern = r"[^a-zA-Z0-9\-_\.]+"
    result = re.sub(pattern, "-", name)
    result = re.sub(r"^[\._-]|[\._-]$", "", result)
    if not result:
        raise PdmException(f"Invalid project name: {name}")
    return result


def is_conda_base() -> bool:
    return os.getenv("CONDA_DEFAULT_ENV", "") == "base"


def is_conda_base_python(python: Path) -> bool:
    if not is_conda_base():
        return False
    prefix = os.environ["CONDA_PREFIX"]
    try:
        python.relative_to(prefix)
    except ValueError:
        return False
    return True


def filtered_sources(sources: list[RepositoryConfig], package: str | None) -> list[RepositoryConfig]:
    """Get matching sources based on the index attribute."""
    source_preferences = [(s, _source_preference(package, s)) for s in sources]
    included_by = [s for s, p in source_preferences if p is True]
    if included_by:
        return included_by
    return [s for s, p in source_preferences if p is None]


def _source_preference(package: str | None, source: RepositoryConfig) -> bool | None:
    import fnmatch

    if package is None:
        return None
    key = normalize_name(package)
    if any(fnmatch.fnmatch(key, pat) for pat in source.include_packages):
        return True
    if any(fnmatch.fnmatch(key, pat) for pat in source.exclude_packages):
        return False
    return None


def get_file_hash(filename: str | Path, algorithm: str = "sha256") -> str:
    """Calculate the hash of a file with the given algorithm"""
    import hashlib

    h = hashlib.new(algorithm)
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_to_datetime(value: str) -> datetime:
    if "T" in value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def get_all_installable_python_versions(build_dir: bool = False) -> list[PythonVersion]:
    """Returns all installable standalone Python interpreter versions from @indygreg

    Installable means:
        Fitting current platform and arch

    Parameters:
        build_dir: Whether to include the `build/` directory from indygreg builds (aka 'Full Archive')
    """
    from pbs_installer._install import THIS_ARCH, THIS_PLATFORM
    from pbs_installer._versions import PYTHON_VERSIONS

    arch = "x86" if THIS_ARCH == "32" else THIS_ARCH
    matches = [v for v, u in PYTHON_VERSIONS.items() if u.get((THIS_PLATFORM, arch, not build_dir))]
    return matches


def get_class_init_params(klass: type) -> set[str]:
    arguments: set[str] = set()
    for cls in klass.__mro__:
        if "__init__" not in cls.__dict__:
            continue
        params = inspect.signature(cls).parameters
        arguments.update({k for k, v in params.items() if v.kind not in (v.VAR_POSITIONAL, v.VAR_KEYWORD)})
        if not any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params.values()):
            break
    return arguments
