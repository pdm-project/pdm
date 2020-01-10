"""
Compatibility code
"""
import os
import atexit
from contextlib import contextmanager
import shutil
import tempfile
from typing import List, Optional, Tuple, Any
import urllib.parse as parse

from distlib.wheel import Wheel
from pip_shims.shims import InstallCommand, PackageFinder, get_package_finder
from pip._internal.download import url_to_path

from pdm.types import Source

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


def get_finder(sources: List[Source], cache_dir: Optional[str] = None) -> PackageFinder:
    install_cmd = InstallCommand()
    pip_args = prepare_pip_source_args(sources)
    options, _ = install_cmd.parser.parse_args(pip_args)
    if cache_dir:
        options.cache_dir = cache_dir
    return get_package_finder(install_cmd=install_cmd, options=options)


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


@contextmanager
def unified_open_file(url, session):
    try:
        path = url_to_path(url)
    except AssertionError:
        # Remote URL
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
    else:
        if os.path.isdir(path):
            raise ValueError("Can't read content of a local directory.")
        with open(path, 'rb') as fp:
            yield fp
