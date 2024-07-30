from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

import unearth
from dep_logic.specifiers import InvalidSpecifier, parse_version_specifier
from packaging.version import Version
from unearth.evaluator import Evaluator, FormatControl, LinkMismatchError, Package

from pdm.models.markers import EnvSpec
from pdm.utils import parse_version

logger = logging.getLogger("unearth")

if TYPE_CHECKING:
    from pdm.models.session import PDMPyPIClient


class ReverseVersion(Version):
    """A subclass of version that reverse the order of comparison."""

    def __lt__(self, other: Any) -> bool:
        return super().__gt__(other)

    def __le__(self, other: Any) -> bool:
        return super().__ge__(other)

    def __gt__(self, other: Any) -> bool:
        return super().__lt__(other)

    def __ge__(self, other: Any) -> bool:
        return super().__le__(other)


class PDMEvaluator(Evaluator):
    def __init__(self, *args: Any, env_spec: EnvSpec, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.env_spec = env_spec

    def check_requires_python(self, link: unearth.Link) -> None:
        if link.requires_python:
            try:
                requires_python = parse_version_specifier(link.requires_python)
            except InvalidSpecifier as e:
                logger.debug(
                    "Invalid requires-python specifier for link(%s) %s: %s", link.redacted, link.requires_python, e
                )
                return
            if (requires_python & self.env_spec.requires_python).is_empty():
                raise LinkMismatchError(
                    f"The package requires-python {link.requires_python} is not compatible with the target {self.env_spec.requires_python}."
                )

    def check_wheel_tags(self, filename: str) -> None:
        if self.env_spec.wheel_compatibility(filename) is None:
            raise LinkMismatchError(
                f"The wheel file {filename} is not compatible with the target environment {self.env_spec}."
            )


class PDMPackageFinder(unearth.PackageFinder):
    def __init__(
        self,
        session: PDMPyPIClient | None = None,
        *,
        env_spec: EnvSpec,
        minimal_version: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(session, **kwargs)
        self.minimal_version = minimal_version
        self.env_spec = env_spec

    def build_evaluator(self, package_name: str, allow_yanked: bool = False) -> Evaluator:
        format_control = FormatControl(no_binary=self.no_binary, only_binary=self.only_binary)
        return PDMEvaluator(
            package_name=package_name,
            target_python=self.target_python,
            allow_yanked=allow_yanked,
            format_control=format_control,
            exclude_newer_than=self.exclude_newer_than,
            env_spec=self.env_spec,
        )

    def _sort_key(self, package: Package) -> tuple:
        from packaging.utils import BuildTag, canonicalize_name

        if self.minimal_version:
            version_cls: Callable[[str], Version] = ReverseVersion
        else:
            version_cls = parse_version

        link = package.link
        compatibility = (0, 0, 0, 0)  # default value for sdists
        build_tag: BuildTag = ()
        prefer_binary = False
        if link.is_wheel:
            compat = self.env_spec.wheel_compatibility(link.filename)
            if compat is None:
                compatibility = (-1, -1, -1, -1)
            else:
                compatibility = compat
            if canonicalize_name(package.name) in self.prefer_binary or ":all:" in self.prefer_binary:
                prefer_binary = True

        return (
            -int(link.is_yanked),
            int(prefer_binary),
            version_cls(package.version) if package.version is not None else version_cls("0"),
            compatibility,
            build_tag,
        )
