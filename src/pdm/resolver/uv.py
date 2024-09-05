from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, replace
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pdm.models.candidates import Candidate
from pdm.models.markers import get_marker
from pdm.models.repositories import Package
from pdm.models.requirements import FileRequirement, NamedRequirement, Requirement, VcsRequirement
from pdm.models.specifiers import get_specifier
from pdm.project.lockfile import FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_INHERIT_METADATA, FLAG_STATIC_URLS
from pdm.resolver.base import Resolution, Resolver
from pdm.termui import Verbosity
from pdm.utils import normalize_name

if TYPE_CHECKING:
    from pdm._types import FileHash

logger = logging.getLogger(__name__)

GIT_URL = re.compile(r"(?P<repo>[^:/]+://[^\?#]+)(?:\?rev=(?P<ref>[^#]+?))?(?:#(?P<revision>[a-f0-9]+))$")


@dataclass
class UvResolver(Resolver):
    def __post_init__(self) -> None:
        self.default_source = self.project.sources[0].url
        if self.locked_repository is None:
            self.locked_repository = self.project.get_locked_repository()
        self.requested_groups = {g for r in self.requirements for g in r.groups}
        for r in self.requirements:
            if self.project.name and r.key == normalize_name(self.project.name):
                groups = r.extras or ["default"]
                for group in groups:
                    if group not in self.requested_groups:
                        self.requirements.extend(self.project.get_dependencies(group))
                        self.requested_groups.add(group)
        if self.update_strategy not in {"reuse", "all"}:
            self.project.core.ui.warn(
                f"{self.update_strategy} update strategy is not supported by uv, using 'reuse' instead"
            )
            self.update_strategy = "reuse"
        if FLAG_INHERIT_METADATA in self.strategies:
            self.project.core.ui.warn("inherit_metadata strategy is not supported by uv resolver, it will be ignored")
            self.strategies.discard(FLAG_INHERIT_METADATA)

    def _build_lock_command(self) -> list[str]:
        cmd = [*self.project.core.uv_cmd, "lock", "-p", str(self.environment.interpreter.executable)]
        if self.project.core.ui.verbosity > 0:
            cmd.append("--verbose")
        if not self.project.core.state.enable_cache:
            cmd.append("--no-cache")
        first_index = True
        for source in self.project.sources:
            assert source.url is not None
            if source.type == "find_links":
                cmd.extend(["--find-links", source.url])
            elif first_index:
                cmd.extend(["--index-url", source.url])
                first_index = False
            else:
                cmd.extend(["--extra-index-url", source.url])
        if self.project.pyproject.settings.get("resolution", {}).get("respect-source-order", False):
            cmd.append("--index-strategy=unsafe-first-match")
        else:
            cmd.append("--index-strategy=unsafe-best-match")
        if self.update_strategy != "all":
            for name in self.tracked_names:
                cmd.extend(["-P", name])
        if self.project.pyproject.allow_prereleases:
            cmd.append("--prerelease=allow")
        no_binary = self.environment._setting_list("PDM_NO_BINARY", "resolution.no-binary")
        only_binary = self.environment._setting_list("PDM_ONLY_BINARY", "resolution.only-binary")
        if ":all:" in no_binary:
            cmd.append("--no-binary")
        else:
            for pkg in no_binary:
                cmd.extend(["--no-binary-package", pkg])
        if ":all:" in only_binary:
            cmd.append("--no-build")
        else:
            for pkg in only_binary:
                cmd.extend(["--no-build-package", pkg])
        if not self.project.core.state.build_isolation:
            cmd.append("--no-build-isolation")
        if cs := self.project.core.state.config_settings:
            for k, v in cs.items():
                cmd.extend(["--config-setting", f"{k}={v}"])

        if FLAG_DIRECT_MINIMAL_VERSIONS in self.strategies:
            cmd.append("--resolution=lowest-direct")

        if dt := self.project.core.state.exclude_newer:
            cmd.extend(["--exclude-newer", dt.isoformat()])

        if self.project.core.state.overrides or self.project.pyproject.resolution.get("overrides", {}):
            self.project.core.ui.warn("PDM overrides are not supported by uv resolver, they will be ignored")

        return cmd

    def _parse_uv_lock(self, path: Path) -> Resolution:
        from unearth import Link

        from pdm.compat import tomllib

        with path.open("rb") as f:
            data = tomllib.load(f)

        packages: list[Package] = []

        def make_requirement(dep: dict[str, Any]) -> str:
            req = NamedRequirement(name=dep["name"])
            if version := dep.get("version"):
                req.specifier = get_specifier(f"=={version}")
            if marker := dep.get("marker"):
                req.marker = get_marker(marker)
            return req.as_line()

        for package in data["package"]:
            if self.project.name and package["name"] == normalize_name(self.project.name) and not self.keep_self:
                continue
            req: Requirement
            if url := package["source"].get("url"):
                req = FileRequirement.create(url=url, name=package["name"])
            elif git := package["source"].get("git"):
                matches = GIT_URL.match(git)
                if not matches:
                    raise ValueError(f"Invalid git URL: {git}")
                url = f"git+{matches.group('repo')}"
                if ref := matches.group("ref"):
                    url += f"@{ref}"
                req = VcsRequirement.create(url=url, name=package["name"])
                req.revision = matches.group("revision")
            elif editable := package["source"].get("editable"):
                req = FileRequirement.create(path=editable, name=package["name"], editable=True)
            elif filepath := package["source"].get("path"):
                req = FileRequirement.create(path=filepath, name=package["name"])
            else:
                req = NamedRequirement.create(name=package["name"], specifier=f"=={package['version']}")
            candidate = Candidate(req, name=package["name"], version=package["version"])
            if FLAG_STATIC_URLS in self.strategies:

                def hash_maker(item: dict[str, Any]) -> FileHash:
                    return {"url": item["url"], "hash": item["hash"]}
            else:

                def hash_maker(item: dict[str, Any]) -> FileHash:
                    return {"file": Link(item["url"]).filename, "hash": item["hash"]}

            if not req.is_file_or_url:
                for wheel in chain(package.get("wheels", []), [sdist] if (sdist := package.get("sdist")) else []):
                    candidate.hashes.append(hash_maker(wheel))
            entry = Package(candidate, [make_requirement(dep) for dep in package.get("dependencies", [])], "")
            packages.append(entry)
            if optional_dependencies := package.get("optional-dependencies"):
                for group, deps in optional_dependencies.items():
                    extra_entry = Package(
                        candidate.copy_with(replace(req, extras=(group,))),
                        [f"{req.key}=={candidate.version}", *(make_requirement(dep) for dep in deps)],
                        "",
                    )
                    packages.append(extra_entry)
        return Resolution(packages, self.requested_groups)

    def resolve(self) -> Resolution:
        from pdm.formats.uv import uv_file_builder

        locked_repo = self.locked_repository or self.project.get_locked_repository()
        with uv_file_builder(self.project, str(self.target.requires_python), self.requirements, locked_repo) as builder:
            builder.build_pyproject_toml()
            uv_lock_path = self.project.root / "uv.lock"
            if self.update_strategy != "all":
                builder.build_uv_lock()
            uv_lock_command = self._build_lock_command()
            self.project.core.ui.echo(f"Running uv lock command: {uv_lock_command}", verbosity=Verbosity.DETAIL)
            subprocess.run(uv_lock_command, cwd=self.project.root, check=True)
            return self._parse_uv_lock(uv_lock_path)
