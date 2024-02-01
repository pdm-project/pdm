from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pdm.exceptions import PdmException
from pdm.utils import normalize_name

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from typing import Callable, TypeVar

    ST = TypeVar("ST", Traversable, Path)

TEMPLATE_PACKAGE = "pdm.cli.templates"
BUILTIN_TEMPLATES = ["default", "minimal"]


class ProjectTemplate:
    _path: Path

    def __init__(self, path_or_url: str | None) -> None:
        self.template = path_or_url or "default"

    def __enter__(self) -> ProjectTemplate:
        self._path = Path(tempfile.mkdtemp(suffix="-template", prefix="pdm-"))
        self.prepare_template()
        return self

    def __exit__(self, *args: Any) -> None:
        shutil.rmtree(self._path, ignore_errors=True)

    def generate(self, target_path: Path, metadata: dict[str, Any], overwrite: bool = False) -> None:
        from pdm.compat import tomllib

        def replace_all(path: str, old: str, new: str) -> None:
            with open(path, encoding=encoding) as fp:
                content = fp.read()
            content = re.sub(rf"\b{old}\b", new, content)
            with open(path, "w", encoding=encoding) as fp:
                fp.write(content)

        if metadata.get("project", {}).get("name"):
            try:
                with open(self._path / "pyproject.toml", "rb") as fp:
                    pyproject = tomllib.load(fp)
            except FileNotFoundError:
                raise PdmException("Template pyproject.toml not found") from None
            new_name = metadata["project"]["name"]
            new_import_name = normalize_name(new_name).replace("-", "_")
            try:
                original_name = pyproject["project"]["name"]
            except KeyError:
                raise PdmException("Template pyproject.toml is not PEP-621 compliant") from None
            import_name = normalize_name(original_name).replace("-", "_")
            encoding = "utf-8"
            for root, dirs, filenames in os.walk(self._path):
                for i, d in enumerate(dirs):
                    if d == import_name:
                        os.rename(os.path.join(root, d), os.path.join(root, new_import_name))
                        dirs[i] = new_import_name
                for f in filenames:
                    if f.endswith(".py"):
                        replace_all(os.path.join(root, f), import_name, new_import_name)
                        if f == import_name + ".py":
                            os.rename(os.path.join(root, f), os.path.join(root, new_import_name + ".py"))
                    elif f.endswith((".md", ".rst")):
                        replace_all(os.path.join(root, f), original_name, new_name)
                    elif Path(root) == self._path and f == "pyproject.toml":
                        replace_all(os.path.join(root, f), import_name, new_import_name)

        target_path.mkdir(exist_ok=True, parents=True)
        self.mirror(self._path, target_path, [self._path / "pyproject.toml"], overwrite=overwrite)
        self._generate_pyproject(target_path / "pyproject.toml", metadata)

    def prepare_template(self) -> None:
        if self.template in BUILTIN_TEMPLATES:
            self._prepare_package_template(f"{TEMPLATE_PACKAGE}.{self.template}")
        elif "://" in self.template or self.template.startswith("git@"):
            self._prepare_git_template(self.template)
        elif os.path.exists(self.template):
            self._prepare_local_template(self.template)
        else:  # template name
            template = f"https://github.com/pdm-project/template-{self.template}"
            self._prepare_git_template(template)

    @staticmethod
    def mirror(
        src: ST,
        dst: Path,
        skip: list[ST] | None = None,
        copyfunc: Callable[[ST, Path], Any] = shutil.copyfile,  # type: ignore[assignment]
        *,
        overwrite: bool = False,
    ) -> None:
        if skip and src in skip:
            return
        if src.is_dir():
            dst.mkdir(exist_ok=True)
            for child in src.iterdir():
                ProjectTemplate.mirror(child, dst / child.name, skip, copyfunc)
        elif src.name.endswith(".pyc"):
            return
        elif overwrite or not dst.exists():
            copyfunc(src, dst)

    @staticmethod
    def _copy_package_file(src: Traversable, dst: Path) -> Path:
        from pdm.compat import importlib_resources

        with importlib_resources.as_file(src) as f:
            return shutil.copyfile(f, dst)

    def _generate_pyproject(self, path: Path, metadata: dict[str, Any]) -> None:
        import tomlkit

        from pdm.cli.utils import merge_dictionary

        try:
            with open(path, encoding="utf-8") as fp:
                content = tomlkit.load(fp)
        except FileNotFoundError:
            content = tomlkit.document()
        try:
            with open(self._path / "pyproject.toml", encoding="utf-8") as fp:
                template_content = tomlkit.load(fp)
        except FileNotFoundError:
            template_content = tomlkit.document()

        merge_dictionary(content, template_content)
        if "version" in content.get("project", {}).get("dynamic", []):
            metadata["project"].pop("version", None)
        merge_dictionary(content, metadata)
        if "build-system" in metadata:
            content["build-system"] = metadata["build-system"]
        else:
            content.pop("build-system", None)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(tomlkit.dumps(content))

    def _prepare_package_template(self, import_name: str) -> None:
        from pdm.compat import importlib_resources

        files = importlib_resources.files(import_name)

        self.mirror(files, self._path, skip=[files / "__init__.py"], copyfunc=self._copy_package_file)

    def _prepare_git_template(self, url: str) -> None:
        left, amp, right = url.rpartition("@")
        if left != "git" and amp:
            extra_args = [f"--branch={right}"]
            url = left
        else:
            extra_args = []
        git_command = ["git", "clone", "--recursive", "--depth=1", *extra_args, url, self._path.as_posix()]
        result = subprocess.run(git_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise PdmException(f"Failed to clone template from git repository {url}: {result.stderr}")
        shutil.rmtree(self._path / ".git", ignore_errors=True)

    def _prepare_local_template(self, path: str) -> None:
        src = Path(path)

        self.mirror(src, self._path, skip=[src / ".git", src / ".svn", src / ".hg"])
