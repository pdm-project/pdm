import ast
from configparser import ConfigParser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, no_type_check


@dataclass
class Setup:
    """
    Abstraction of a Python project setup file.
    """

    name: Optional[str] = None
    version: Optional[str] = None
    install_requires: List[str] = field(default_factory=list)
    extras_require: Dict[str, List[str]] = field(default_factory=dict)
    python_requires: Optional[str] = None

    def update(self, other: "Setup"):
        if other.name:
            self.name = other.name
        if other.version:
            self.version = other.version
        if other.install_requires:
            self.install_requires = other.install_requires
        if other.extras_require:
            self.extras_require = other.extras_require
        if other.python_requires:
            self.python_requires = other.python_requires

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_directory(cls, dir: Path) -> "Setup":
        return _SetupReader.read_from_directory(dir)


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
        from pdm.project.metadata import MutableMetadata

        try:
            metadata = MutableMetadata(file)
        except ValueError:
            return Setup()
        return Setup(
            name=metadata.name,
            version=metadata.version,
            install_requires=metadata.dependencies,
            extras_require=metadata.optional_dependencies,
            python_requires=metadata.requires_python,
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
            version=cls._find_single_string(setup_call, body, "version"),
            install_requires=cls._find_install_requires(setup_call, body),
            extras_require=cls._find_extras_require(setup_call, body),
            python_requires=cls._find_single_string(
                setup_call, body, "python_requires"
            ),
        )

    @staticmethod
    def read_setup_cfg(file: Path) -> Setup:
        parser = ConfigParser()

        parser.read(str(file))

        name = None
        version = None
        if parser.has_option("metadata", "name"):
            name = parser.get("metadata", "name")

        if parser.has_option("metadata", "version"):
            version = parser.get("metadata", "version")

        install_requires = []
        extras_require: Dict[str, List[str]] = {}
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
    def _find_setup_call(
        cls, elements: List[Any]
    ) -> Tuple[Optional[ast.Call], Optional[List[Any]]]:
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
    def _find_sub_setup_call(
        cls, elements: List[Any]
    ) -> Tuple[Optional[ast.Call], Optional[List[Any]]]:
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
    def _find_install_requires(cls, call: ast.Call, body: Iterable[Any]) -> List[str]:
        install_requires: List[str] = []
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
            for el in value.elts:
                install_requires.append(el.s)
        elif isinstance(value, ast.Name):
            variable = cls._find_variable_in_body(body, value.id)

            if variable is not None and isinstance(variable, ast.List):
                for el in variable.elts:
                    install_requires.append(el.s)

        return install_requires

    @no_type_check
    @classmethod
    def _find_extras_require(
        cls, call: ast.Call, body: Iterable[Any]
    ) -> Dict[str, List[str]]:
        extras_require: Dict[str, List[str]] = {}
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
                    extras_require[key.s] = [e.s for e in val.elts]
        elif isinstance(value, ast.Name):
            variable = cls._find_variable_in_body(body, value.id)

            if variable is None or not isinstance(variable, ast.Dict):
                return extras_require

            for key, val in zip(variable.keys, variable.values):
                if isinstance(val, ast.Name):
                    val = cls._find_variable_in_body(body, val.id)

                if isinstance(val, ast.List):
                    extras_require[key.s] = [e.s for e in val.elts]

        return extras_require

    @classmethod
    def _find_single_string(
        cls, call: ast.Call, body: List[Any], name: str
    ) -> Optional[str]:
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
    def _find_in_call(call: ast.Call, name: str) -> Optional[Any]:
        for keyword in call.keywords:
            if keyword.arg == name:
                return keyword.value
        return None

    @staticmethod
    def _find_call_kwargs(call: ast.Call) -> Optional[Any]:
        kwargs = None
        for keyword in call.keywords:
            if keyword.arg is None:
                kwargs = keyword.value

        return kwargs

    @staticmethod
    def _find_variable_in_body(body: Iterable[Any], name: str) -> Optional[Any]:
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
    def _find_in_dict(dict_: ast.Dict, name: str) -> Optional[Any]:
        for key, val in zip(dict_.keys, dict_.values):
            if isinstance(key, ast.Str) and key.s == name:
                return val
        return None
