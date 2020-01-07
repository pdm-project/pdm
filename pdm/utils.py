"""
Compatibility code
"""
import os
import atexit
import shutil
import tempfile
from typing import List, Optional, Tuple
import urllib.parse as parse
from distlib.wheel import Wheel
import pkg_resources
from contextlib import contextmanager

from pip_shims.shims import InstallCommand, PackageFinder, get_package_finder

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


@contextmanager
def allow_all_markers():
    """This is a monkey patch function that temporarily disables marker evaluation."""
    from pip._vendor import pkg_resources as vendor_pkg

    def evaluate_marker(text, extra=None):
        return True

    old_evaluate = pkg_resources.evaluate_marker
    pkg_resources.evaluate_marker = evaluate_marker
    vendor_pkg.evaluate_marker = evaluate_marker
    yield
    pkg_resources.evaluate_marker = old_evaluate
    vendor_pkg = old_evaluate
