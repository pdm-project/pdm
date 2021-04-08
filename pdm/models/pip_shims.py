# flake8: noqa
"""
This module provides a middle layer between pdm and pip.
All pip members are imported here for compatiblity purpose.
"""
from __future__ import annotations

import atexit
import inspect
import sys
from typing import TYPE_CHECKING, Optional, Tuple

from pip._internal.cache import WheelCache
from pip._internal.commands.install import InstallCommand as _InstallCommand
from pip._internal.index.package_finder import PackageFinder
from pip._internal.models.candidate import InstallationCandidate
from pip._internal.models.format_control import FormatControl
from pip._internal.models.link import Link
from pip._internal.models.target_python import TargetPython
from pip._internal.models.wheel import Wheel as PipWheel
from pip._internal.network.auth import MultiDomainBasicAuth
from pip._internal.network.cache import SafeFileCache
from pip._internal.network.download import Downloader
from pip._internal.operations.prepare import unpack_url
from pip._internal.req import InstallRequirement, req_uninstall
from pip._internal.req.constructors import (
    install_req_from_editable,
    install_req_from_line,
    install_req_from_parsed_requirement,
)
from pip._internal.req.req_file import parse_requirements
from pip._internal.utils import logging as pip_logging
from pip._internal.utils import misc
from pip._internal.utils.compatibility_tags import get_supported
from pip._internal.utils.filesystem import directory_size, file_size, find_files
from pip._internal.utils.hashes import FAVORITE_HASH, STRONG_HASHES
from pip._internal.utils.temp_dir import global_tempdir_manager
from pip._internal.utils.urls import path_to_url, url_to_path
from pip._internal.vcs.versioncontrol import VcsSupport

if TYPE_CHECKING:
    from optparse import Values


class InstallCommand(_InstallCommand):
    def __init__(self) -> None:
        super().__init__(name="InstallCommand", summary="Install packages.")


def get_package_finder(
    install_cmd: InstallCommand,
    options: Optional[Values] = None,
    python_version: Optional[Tuple[int, ...]] = None,
    python_abi_tag: Optional[str] = None,
    ignore_requires_python: Optional[bool] = None,
) -> PackageFinder:
    """Shim for compatibility to generate package finders.

    Build and return a :class:`~pip._internal.index.package_finder.PackageFinder`
    instance using the :class:`~pip._internal.commands.install.InstallCommand` helper
    method to construct the finder, shimmed with backports as needed for compatibility.
    """
    if options is None:
        options, _ = install_cmd.parser.parse_args([])
    session = install_cmd._build_session(options)
    atexit.register(session.close)
    build_kwargs = {"options": options, "session": session}
    if python_version:
        assert python_abi_tag is not None
        target_python_builder = TargetPython
        builder_args = inspect.signature(target_python_builder).parameters
        target_python_params = {"py_version_info": python_version}
        if "abi" in builder_args:
            target_python_params["abi"] = python_abi_tag
        elif "abis" in builder_args:
            target_python_params["abis"] = [python_abi_tag]

        target_python = target_python_builder(**target_python_params)
        build_kwargs["target_python"] = target_python

    build_kwargs["ignore_requires_python"] = ignore_requires_python
    return install_cmd._build_package_finder(**build_kwargs)  # type: ignore
