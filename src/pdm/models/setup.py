from __future__ import annotations

import ast
import os
from configparser import ConfigParser
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable, no_type_check

from pdm.compat import Distribution


@dataclass
class Setup:
    """
    Abstraction of a Python project setup file.
    """

    name: str | None = None
    version: str | None = None
    install_requires: list[str] = field(default_factory=list)
    extras_require: dict[str, list[str]] = field(default_factory=dict)
    python_requires: str | None = None
    summary: str | None = None

    def update(self, other: Setup) -> None:
        for f in fields(self):
            other_field = getattr(other, f.name)
            if other_field:
                setattr(self, f.name, other_field)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_directory(cls, dir: Path) -> Setup:
        return _SetupReader.read_from_directory(dir)

    def as_dist(self) -> Distribution:
        return SetupDistribution(self)


class _SetupReader:
    """
    Class that reads a setup.py file without executing it.
    """

    @classmethod
    def read_from_directory(cls, directory: Path) -> Setup:
        result = Setup()

        for filename, file_reader in [
            ("pyproject.toml", cls.read_pyproject_toml),
            ("setup.cfg", cls.read_setup_cfg),
            ("setup.py", cls.read_setup_py),
        ]:
            filepath = directory / filename
            if not filepath.exists():
                continue

            new_result = file_reader(filepath)
            result.update(new_result)

        return result

    @staticmethod
    def read_pyproject_toml(file: Path) -> Setup:
        from pdm import termui
        from pdm.exceptions import ProjectError
        from pdm.project.project_file import PyProject

        try:
            metadata = PyProject(file, ui=termui.UI()).metadata.unwrap()
        except ProjectError:
            return Setup()
        return Setup(
            name=metadata.get("name"),
            summary=metadata.get("description"),
            version=metadata.get("version"),
            install_requires=metadata.get("dependencies", []),
            extras_require=metadata.get("optional-dependencies", {}),
            python_requires=metadata.get("requires-python"),
        )

    @no_type_check
    @classmethod
    def read_setup_py(cls, file: Path) -> Setup:
        with file.open(encoding="utf-8") as f:
            content = f.read()

        body = ast.parse(content).body

        setup_call, body = cls._find_setup_call(body)
        if not setup_call:
            return Setup()

        return Setup(
            name=cls._find_single_string(setup_call, body, "name"),
            version=cls._find_single_string(setup_call, body, "version") or "0.0.0",
            install_requires=cls._find_install_requires(setup_call, body),
            extras_require=cls._find_extras_require(setup_call, body),
            python_requires=cls._find_single_string(setup_call, body, "python_requires"),
        )

    @staticmethod
    def read_setup_cfg(file: Path) -> Setup:
        parser = ConfigParser()

        parser.read(str(file))

        name = None
        version = "0.0.0"
        if parser.has_option("metadata", "name"):
            name = parser.get("metadata", "name")

        if parser.has_option("metadata", "version"):
            meta_version = parser.get("metadata", "version")
            if not meta_version.startswith("attr:"):
                version = meta_version

        install_requires = []
        extras_require: dict[str, list[str]] = {}
        python_requires = None
        if parser.has_section("options"):
            if parser.has_option("options", "install_requires"):
                for dep in parser.get("options", "install_requires").split("\n"):
                    dep = dep.strip()
                    if not dep:
                        continue

                    install_requires.append(dep)

            if parser.has_option("options", "python_requires"):
                python_requires = parser.get("options", "python_requires")

        if parser.has_section("options.extras_require"):
            for group in parser.options("options.extras_require"):
                extras_require[group] = []
                deps = parser.get("options.extras_require", group)
                for dep in deps.split("\n"):
                    dep = dep.strip()
                    if not dep:
                        continue

                    extras_require[group].append(dep)

        return Setup(
            name=name,
            version=version,
            install_requires=install_requires,
            extras_require=extras_require,
            python_requires=python_requires,
        )

    @classmethod
    def _find_setup_call(cls, elements: list[Any]) -> tuple[ast.Call | None, list[Any | None]]:
        funcdefs = []
        for i, element in enumerate(elements):
            if isinstance(element, ast.If) and i == len(elements) - 1:
                # Checking if the last element is an if statement
                # and if it is 'if __name__ == "__main__"' which
                # could contain the call to setup()
                test = element.test
                if not isinstance(test, ast.Compare):
                    continue

                left = test.left
                if not isinstance(left, ast.Name):
                    continue

                if left.id != "__name__":
                    continue

                setup_call, body = cls._find_sub_setup_call([element])
                if not setup_call:
                    continue

                return setup_call, body + elements
            if not isinstance(element, ast.Expr):
                if isinstance(element, ast.FunctionDef):
                    funcdefs.append(element)

                continue

            value = element.value
            if not isinstance(value, ast.Call):
                continue

            func = value.func
            if not (isinstance(func, ast.Name) and func.id == "setup") and not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "setuptools"
                and func.attr == "setup"
            ):
                continue

            return value, elements

        # Nothing, we inspect the function definitions
        return cls._find_sub_setup_call(funcdefs)

    @no_type_check
    @classmethod
    def _find_sub_setup_call(cls, elements: list[Any]) -> tuple[ast.Call | None, list[Any | None]]:
        for element in elements:
            if not isinstance(element, (ast.FunctionDef, ast.If)):
                continue

            setup_call = cls._find_setup_call(element.body)
            if setup_call != (None, None):
                setup_call, body = setup_call

                body = elements + body

                return setup_call, body

        return None, None

    @no_type_check
    @classmethod
    def _find_install_requires(cls, call: ast.Call, body: Iterable[Any]) -> list[str]:
        install_requires: list[str] = []
        value = cls._find_in_call(call, "install_requires")
        if value is None:
            # Trying to find in kwargs
            kwargs = cls._find_call_kwargs(call)

            if kwargs is None or not isinstance(kwargs, ast.Name):
                return install_requires

            variable = cls._find_variable_in_body(body, kwargs.id)
            if not isinstance(variable, (ast.Dict, ast.Call)):
                return install_requires

            if isinstance(variable, ast.Call):
                if not isinstance(variable.func, ast.Name):
                    return install_requires

                if variable.func.id != "dict":
                    return install_requires

                value = cls._find_in_call(variable, "install_requires")
            else:
                value = cls._find_in_dict(variable, "install_requires")

        if value is None:
            return install_requires

        if isinstance(value, ast.List):
            install_requires.extend([el.s for el in value.elts if isinstance(el, ast.Str)])
        elif isinstance(value, ast.Name):
            variable = cls._find_variable_in_body(body, value.id)

            if variable is not None and isinstance(variable, ast.List):
                install_requires.extend([el.s for el in variable.elts if isinstance(el, ast.Str)])

        return install_requires

    @no_type_check
    @classmethod
    def _find_extras_require(cls, call: ast.Call, body: Iterable[Any]) -> dict[str, list[str]]:
        extras_require: dict[str, list[str]] = {}
        value = cls._find_in_call(call, "extras_require")
        if value is None:
            # Trying to find in kwargs
            kwargs = cls._find_call_kwargs(call)

            if kwargs is None or not isinstance(kwargs, ast.Name):
                return extras_require

            variable = cls._find_variable_in_body(body, kwargs.id)
            if not isinstance(variable, (ast.Dict, ast.Call)):
                return extras_require

            if isinstance(variable, ast.Call):
                if not isinstance(variable.func, ast.Name):
                    return extras_require

                if variable.func.id != "dict":
                    return extras_require

                value = cls._find_in_call(variable, "extras_require")
            else:
                value = cls._find_in_dict(variable, "extras_require")

        if value is None:
            return extras_require

        if isinstance(value, ast.Dict):
            for key, val in zip(value.keys, value.values):
                if isinstance(val, ast.Name):
                    val = cls._find_variable_in_body(body, val.id)

                if isinstance(val, ast.List):
                    extras_require[key.s] = [e.s for e in val.elts if isinstance(e, ast.Str)]
        elif isinstance(value, ast.Name):
            variable = cls._find_variable_in_body(body, value.id)

            if variable is None or not isinstance(variable, ast.Dict):
                return extras_require

            for key, val in zip(variable.keys, variable.values):
                if isinstance(val, ast.Name):
                    val = cls._find_variable_in_body(body, val.id)

                if isinstance(val, ast.List):
                    extras_require[key.s] = [e.s for e in val.elts if isinstance(e, ast.Str)]

        return extras_require

    @classmethod
    def _find_single_string(cls, call: ast.Call, body: list[Any], name: str) -> str | None:
        value = cls._find_in_call(call, name)
        if value is None:
            # Trying to find in kwargs
            kwargs = cls._find_call_kwargs(call)

            if kwargs is None or not isinstance(kwargs, ast.Name):
                return None

            variable = cls._find_variable_in_body(body, kwargs.id)
            if not isinstance(variable, (ast.Dict, ast.Call)):
                return None

            if isinstance(variable, ast.Call):
                if not isinstance(variable.func, ast.Name):
                    return None

                if variable.func.id != "dict":
                    return None

                value = cls._find_in_call(variable, name)
            else:
                value = cls._find_in_dict(variable, name)

        if value is None:
            return None

        if isinstance(value, ast.Str):
            return value.s
        elif isinstance(value, ast.Name):
            variable = cls._find_variable_in_body(body, value.id)

            if variable is not None and isinstance(variable, ast.Str):
                return variable.s

        return None

    @staticmethod
    def _find_in_call(call: ast.Call, name: str) -> Any | None:
        for keyword in call.keywords:
            if keyword.arg == name:
                return keyword.value
        return None

    @staticmethod
    def _find_call_kwargs(call: ast.Call) -> Any | None:
        kwargs = None
        for keyword in call.keywords:
            if keyword.arg is None:
                kwargs = keyword.value

        return kwargs

    @staticmethod
    def _find_variable_in_body(body: Iterable[Any], name: str) -> Any | None:
        for elem in body:
            if not isinstance(elem, ast.Assign):
                continue

            for target in elem.targets:
                if not isinstance(target, ast.Name):
                    continue

                if target.id == name:
                    return elem.value
        return None

    @staticmethod
    def _find_in_dict(dict_: ast.Dict, name: str) -> Any | None:
        for key, val in zip(dict_.keys, dict_.values):
            if isinstance(key, ast.Str) and key.s == name:
                return val
        return None


class SetupDistribution(Distribution):
    def __init__(self, data: Setup) -> None:
        self._data = data

    def read_text(self, filename: str) -> str | None:
        return None

    def locate_file(self, path: str | os.PathLike[str]) -> os.PathLike[str]:
        return Path()

    @property
    def metadata(self) -> dict[str, Any]:  # type: ignore[override]
        return {
            "Name": self._data.name,
            "Version": self._data.version,
            "Summary": self._data.summary,
            "Requires-Python": self._data.python_requires,
        }

    @property
    def requires(self) -> list[str] | None:
        from pdm.models.markers import Marker
        from pdm.models.requirements import parse_requirement

        result = self._data.install_requires
        for extra, reqs in self._data.extras_require.items():
            extra_marker = f"extra == '{extra}'"
            for req in reqs:
                parsed = parse_requirement(req)
                old_marker = str(parsed.marker) if parsed.marker else None
                if old_marker:
                    if " or " in old_marker:
                        new_marker = f"({old_marker}) and {extra_marker}"
                    else:
                        new_marker = f"{old_marker} and {extra_marker}"
                else:
                    new_marker = extra_marker
                parsed.marker = Marker(new_marker)
                result.append(parsed.as_line())
        return result
