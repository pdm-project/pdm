from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

import tomlkit
from dep_logic.markers import AnyMarker, BaseMarker, MarkerUnion, parse_marker

from pdm.exceptions import ProjectError
from pdm.formats.base import make_array, make_inline_table
from pdm.models.candidates import Candidate
from pdm.models.requirements import FileRequirement, VcsRequirement
from pdm.project.lockfile import FLAG_INHERIT_METADATA
from pdm.utils import cd, normalize_name

if TYPE_CHECKING:
    from pdm.models.markers import Marker
    from pdm.models.repositories.lock import LockedRepository, Package
    from pdm.project import Project


def _group_sort_key(group: str) -> tuple[bool, str]:
    return group != "default", group


class PyLockConverter:
    lock_version = "1.0"

    def __init__(self, project: Project, locked_repository: LockedRepository) -> None:
        self.project = project
        self.locked_repository = locked_repository

    def make_package(self, package: Package) -> dict[str, Any]:
        req = package.candidate.req
        candidate = package.candidate
        result: dict[str, Any] = {
            "name": candidate.req.key,
            "version": candidate.version,
        }
        if candidate.requires_python:
            result["requires-python"] = candidate.requires_python
        if isinstance(req, VcsRequirement):
            result["vcs"] = {
                "type": req.vcs,
                "url": req.repo,
                "commit-id": candidate.get_revision(),
            }
            if req.ref:
                result["vcs"]["requested-revision"] = req.ref
            if req.subdirectory:
                result["vcs"]["subdirectory"] = req.subdirectory
        elif isinstance(req, FileRequirement):
            if req.is_local_dir:
                result["directory"] = {
                    "path": req.str_path,
                    "editable": req.editable,
                }
                if req.subdirectory:
                    result["directory"]["subdirectory"] = req.subdirectory
            else:
                archive: dict[str, Any]
                archive = result["archive"] = {"url": req.get_full_url()}
                if req.path:
                    archive["path"] = req.str_path
                for hash_item in candidate.hashes:
                    hash_type, hash_value = hash_item["hash"].split(":", 1)
                    archive.setdefault("hashes", tomlkit.inline_table())[hash_type] = hash_value
        else:
            wheels: list[dict[str, Any]] = tomlkit.array().multiline(True)
            for hash_item in candidate.hashes:
                hash_type, hash_value = hash_item["hash"].split(":", 1)
                if hash_item.get("file", "").endswith(".whl") or hash_item.get("url", "").endswith(".whl"):
                    wheel: dict[str, Any] = {}
                    if "file" in hash_item:
                        wheel["name"] = hash_item["file"]
                    if "url" in hash_item:
                        wheel["url"] = hash_item["url"]
                    wheel["hashes"] = make_inline_table({hash_type: hash_value})
                    wheels.append(wheel)
                else:
                    sdist: dict[str, Any] = {}
                    if "file" in hash_item:
                        sdist["name"] = hash_item["file"]
                    if "url" in hash_item:
                        sdist["url"] = hash_item["url"]
                    sdist["hashes"] = make_inline_table({hash_type: hash_value})
                    result["sdist"] = make_inline_table(sdist)
            if wheels:
                result["wheels"] = wheels

            if package.dependencies is not None:
                result["tool"] = {"pdm": {"dependencies": make_array(package.dependencies, multiline=True)}}

        return result

    def _populate_hashes(self, packages: Iterable[Package]) -> None:
        candidates: list[Candidate] = []
        for package in packages:
            if not package.candidate.req.is_named or package.candidate.req.extras:
                continue
            hashes = package.candidate.hashes
            if all("url" in hash_item for hash_item in hashes):
                continue
            package.candidate.hashes.clear()
            candidates.append(package.candidate)
        if candidates:
            with self.project.core.ui.open_spinner("Fetching package file URLs"):
                repo = self.project.get_repository()
                repo.fetch_hashes(candidates)

    def convert(self, all_groups: Iterable[str] | None = None) -> dict[str, Any]:
        doc = tomlkit.document()
        project = self.project
        lockfile = project.lockfile
        if FLAG_INHERIT_METADATA not in lockfile.strategy:
            raise ProjectError("inherit_metadata strategy is required for pylock format")
        repository = self.locked_repository
        if all_groups is None:
            all_groups = lockfile.groups
        if all_groups is None:
            all_groups = list(project.iter_groups())
        extras, groups = self.project.split_extras_groups(list(all_groups))
        env_markers: list[Marker] = []
        for target in repository.targets:
            env_markers.append(target.markers_with_python())

        doc.update(
            {
                "lock-version": self.lock_version,
                "requires-python": str(project.python_requires),
                "environments": make_array([str(marker) for marker in env_markers], multiline=True),
                "extras": sorted(extras),
                "dependency-groups": sorted(groups, key=_group_sort_key),
                "default-groups": ["default"],
                "created-by": "pdm",
            }
        )
        packages = doc.setdefault("packages", tomlkit.aot())

        with cd(project.root):
            self._populate_hashes(repository.packages.values())
            for package in repository.packages.values():
                if package.candidate.req.extras:
                    continue
                package_table = self.make_package(package)
                selection_markers: list[BaseMarker] = []
                for item in sorted(package.candidate.req.groups, key=_group_sort_key):
                    item = normalize_name(item)
                    if item in extras:
                        selection_markers.append(parse_marker(f"'{item}' in extras"))
                    else:
                        selection_markers.append(parse_marker(f"'{item}' in dependency_groups"))
                marker = MarkerUnion.of(*selection_markers) if selection_markers else AnyMarker()
                if package.candidate.req.marker is not None:
                    marker = package.candidate.req.marker.inner & marker
                if not marker.is_any():
                    package_table["marker"] = str(marker)
                packages.append(package_table)

        doc["tool"] = {
            "pdm": {
                "hashes": make_inline_table({"sha256": project.pyproject.content_hash()}),
                "targets": [spec.as_dict() for spec in repository.targets],
            },
        }

        return doc
