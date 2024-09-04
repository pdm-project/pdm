from __future__ import annotations

import logging
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import Any, Iterator

import tomlkit

from pdm.models.candidates import Candidate
from pdm.models.repositories.lock import PackageEntry
from pdm.models.requirements import FileRequirement, NamedRequirement, Requirement, VcsRequirement
from pdm.project.lockfile import FLAG_DIRECT_MINIMAL_VERSIONS, FLAG_STATIC_URLS
from pdm.resolver.base import Resolution, Resolver
from pdm.utils import normalize_name

logger = logging.getLogger(__name__)

GIT_URL = re.compile(r"(?P<repo>[^:/]+://[^\?#]+)(?:\?rev=(?P<ref>[^#]+?))?(?:#(?P<revision>[a-f0-9]+))$")


@dataclass
class UvResolver(Resolver):
    def __post_init__(self) -> None:
        self.requested_groups = {g for r in self.requirements for g in r.groups}
        for r in self.requirements:
            if self.project.name and r.key == normalize_name(self.project.name):
                groups = r.extras or ["default"]
                for group in groups:
                    if group not in self.requested_groups:
                        self.requirements.extend(self.project.get_dependencies(group))
                        self.requested_groups.add(group)
        if self.update_strategy not in {"reuse", "all"}:
            logger.warning("%s update strategy is not supported by uv, use 'reuse' instead", self.update_strategy)
            self.update_strategy = "reuse"

    def _build_lock_command(self) -> list[str]:
        cmd = [*self.project.core.uv_cmd, "lock", "-p", str(self.environment.interpreter.executable)]
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

    def _build_pyproject_toml(self, path: Path) -> None:
        data = self.project.pyproject._data.unwrap()
        data.setdefault("project", {})["requires-python"] = str(self.target.requires_python)
        data.setdefault("project", {})["dependencies"] = []
        data.setdefault("project", {}).pop("optional-dependencies", None)
        sources = {}
        collected_deps: dict[str, list[str]] = {}
        for dep in self.requirements:
            if isinstance(dep, FileRequirement):
                entry = self._get_name(dep)
                sources[entry] = self._build_source(dep)
            else:
                entry = dep.as_line()
            for group in dep.groups:
                collected_deps.setdefault(group, []).append(entry)

        for group, deps in collected_deps.items():
            if group == "default":
                data.setdefault("project", {})["dependencies"] = deps
            else:
                data.setdefault("project", {}).setdefault("optional-dependencies", {})[group] = deps

        if sources:
            data.setdefault("tool", {}).setdefault("uv", {}).setdefault("sources", {}).update(sources)

        with path.open("r", newline="") as f:
            tomlkit.dump(data, f)

    def _build_uv_lock(self, path: Path) -> None:
        lock_repo = self.locked_repository or self.project.get_locked_repository()
        packages: list[dict[str, Any]] = []
        for package in lock_repo.packages.values():
            packages.append(self._build_lock_entry(package))

        data = {
            "version": 1,
            "requires-python": str(self.target.requires_python),
            "package": packages,
        }
        with path.open("w", newline="") as f:
            tomlkit.dump(data, f)

    def _parse_uv_lock(self, path: Path) -> Resolution:
        from unearth import Link

        from pdm._types import FileHash
        from pdm.compat import tomllib

        with path.open("rb") as f:
            data = tomllib.load(f)

        mapping: dict[str, Candidate] = {}
        all_dependencies: dict[tuple[str, str | None], list[Requirement]] = {}

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
                for wheel in chain(package.get("wheels", []), package.get("sdist", [])):
                    candidate.hashes.append(hash_maker(wheel))
            mapping[candidate.identify()] = candidate
        return Resolution(mapping, all_dependencies, self.requested_groups)

    def _build_source(self, req: FileRequirement) -> dict[str, Any]:
        result: dict[str, Any]
        if isinstance(req, VcsRequirement):
            result = {req.vcs: req.repo}
            if req.ref:
                result["rev"] = req.ref
        elif req.path:
            result = {"path": req.str_path}
        else:
            result = {"url": req.url}
        if req.editable:
            result["editable"] = True
        return result

    def _build_lock_entry(self, package: PackageEntry) -> dict[str, Any]:
        candidate = package.candidate
        default_source = self.project.sources[0].url
        req = candidate.req
        result: dict[str, Any] = {"name": candidate.name, "version": candidate.version}
        if isinstance(req, VcsRequirement):
            result["source"] = {req.vcs: f"{req.repo}?rev={req.ref}#{req.revision}"}
        elif isinstance(req, FileRequirement):
            if req.editable:
                result["source"] = {"editable": req.str_path}
            else:
                result["source"] = {"url": req.url}
        else:
            result["source"] = {"registry": default_source}
        for file_hash in candidate.hashes:
            is_wheel = file_hash.get("url", file_hash.get("file", "")).endswith(".whl")
            item = {k: v for k, v in file_hash.items() if k in {"url", "hash"}}
            if is_wheel:
                result.setdefault("wheels", []).append(item)
            else:
                result.setdefault("sdist", []).append(item)
        return result

    def _get_name(self, req: FileRequirement) -> str:
        if req.key:
            return req.key
        can = Candidate(req).prepare(self.environment)
        return normalize_name(can.metadata.name)

    @contextmanager
    def _temp_project_files(self) -> Iterator[None]:
        pyproject_backup: Path | None = None
        uv_lock_backup: Path | None = None
        if (pyproject_toml := self.project.root / "pyproject.toml").exists():
            pyproject_backup = pyproject_toml.rename(self.project.root / ".backup.pyproject.toml")
        if (uv_lock := self.project.root / "uv.lock").exists():
            uv_lock_backup = uv_lock.rename(self.project.root / ".backup.uv.lock")
        try:
            yield
        finally:
            if pyproject_backup:
                pyproject_backup.rename(self.project.root / "pyproject.toml")
            if uv_lock_backup:
                uv_lock_backup.rename(self.project.root / "uv.lock")

    def resolve(self) -> Resolution:
        with self._temp_project_files():
            self._build_pyproject_toml(self.project.root / "pyproject.toml")
            uv_lock_path = self.project.root / "uv.lock"
            if self.update_strategy != "all":
                self._build_uv_lock(uv_lock_path)
            uv_lock_command = self._build_lock_command()
            logger.debug("Running uv lock command: %s", uv_lock_command)
            subprocess.run(uv_lock_command, cwd=self.project.root, check=True)
            return self._parse_uv_lock(uv_lock_path)
