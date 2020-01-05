"""
Compatibility code
"""
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from pip_shims.shims import InstallCommand, PackageFinder, get_package_finder

from pdm.types import Source


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
                ["--trusted-host", urlparse(sources[0]["url"]).hostname]
            )  # type: ignore
        # Add additional sources as extra indexes.
        if len(sources) > 1:
            for source in sources[1:]:
                pip_args.extend(["--extra-index-url", source["url"]])  # type: ignore
                # Trust the host if it's not verified.
                if not source.get("verify_ssl", True):
                    pip_args.extend(
                        ["--trusted-host", urlparse(source["url"]).hostname]
                    )  # type: ignore
    return pip_args


def get_finder(
    sources: List[Source], python_versions: Optional[Tuple[str, ...]] = None
) -> PackageFinder:
    install_cmd = InstallCommand()
    pip_args = prepare_pip_source_args(sources)
    options, _ = install_cmd.parser.parse_args(pip_args)
    return get_package_finder(
        install_cmd=install_cmd, options=options, python_versions=python_versions
    )
