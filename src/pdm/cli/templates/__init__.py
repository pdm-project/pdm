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

BUILTIN_TEMPLATE = "pdm.cli.templates.default"


class ProjectTemplate:
    _path: Path

    def __init__(self, path_or_url: str | None) -> None:
        self.template = path_or_url

    def __enter__(self) -> "ProjectTemplate":
        self._path = Path(tempfile.mkdtemp(suffix="-template", prefix="pdm-"))
        self.prepare_template()
        return self

    def __exit__(self, *args: Any) -> None:
        shutil.rmtree(self._path, ignore_errors=True)

    def generate(self, target_path: Path, metadata: dict[str, Any]) -> None:
        from pdm.compat import tomllib

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
                for d in dirs:
                    if d == import_name:
                        os.rename(os.path.join(root, d), os.path.join(root, new_import_name))
                for f in filenames:
                    if f.endswith(".py"):
                        with open(os.path.join(root, f), encoding=encoding) as fp:
                            content = fp.read()
                        content = re.sub(rf"\b{import_name}\b", new_import_name, content)
                        with open(os.path.join(root, f), "w", encoding=encoding) as fp:
                            fp.write(content)
                        if f == import_name + ".py":
                            os.rename(os.path.join(root, f), os.path.join(root, new_import_name + ".py"))
                    elif f.endswith((".md", ".rst")):
                        with open(os.path.join(root, f), encoding=encoding) as fp:
                            content = fp.read()
                        content = re.sub(rf"\b{original_name}\b", new_name, content)
                        with open(os.path.join(root, f), "w", encoding=encoding) as fp:
                            fp.write(content)

        target_path.mkdir(exist_ok=True, parents=True)
        self.mirror(self._path, target_path, [self._path / "pyproject.toml"])
        self._generate_pyproject(target_path / "pyproject.toml", metadata)

    def prepare_template(self) -> None:
        if self.template is None:
            self._prepare_package_template(BUILTIN_TEMPLATE)
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
        skip: list[Path] | None = None,
        copyfunc: Callable[[ST, Path], Path] = shutil.copy2,  # type: ignore[assignment]
    ) -> None:
        if skip and src in skip:
            return
        if src.is_dir():
            dst.mkdir(exist_ok=True)
            for child in src.iterdir():
                ProjectTemplate.mirror(child, dst / child.name, skip, copyfunc)
        else:
            copyfunc(src, dst)

    @staticmethod
    def _copy_package_file(src: Traversable, dst: Path) -> Path:
        from pdm.compat import importlib_resources

        with importlib_resources.as_file(src) as f:
            return shutil.copy2(f, dst)

    def _generate_pyproject(self, path: Path, metadata: dict[str, Any]) -> None:
        import tomlkit

        from pdm.cli.utils import merge_dictionary

        try:
            with open(path, encoding="utf-8") as fp:
                content = tomlkit.load(fp)
        except FileNotFoundError:
            content = tomlkit.document()

        with open(self._path / "pyproject.toml", encoding="utf-8") as fp:
            template_content = tomlkit.load(fp)

        merge_dictionary(content, template_content, False)
        merge_dictionary(content, metadata, False)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(tomlkit.dumps(content))

    def _prepare_package_template(self, import_name: str) -> None:
        from pdm.compat import importlib_resources

        self.mirror(importlib_resources.files(import_name), self._path, copyfunc=self._copy_package_file)

    def _prepare_git_template(self, url: str) -> None:
        git_command = ["git", "clone", "--depth", "1", "--recursive", url, self._path.as_posix()]
        result = subprocess.run(git_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise PdmException(f"Failed to clone template from git repository {url}: {result.stderr}")
        shutil.rmtree(self._path / ".git", ignore_errors=True)

    def _prepare_local_template(self, path: str) -> None:
        self.mirror(Path(path), self._path)

        for scm_dir in ".git", ".svn", ".hg":
            if (self._path / scm_dir).exists():
                shutil.rmtree(self._path / scm_dir, ignore_errors=True)
