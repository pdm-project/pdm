"""
griffe extension for documenting typed dicts:

Converts functional-form TypedDicts to class-form.
Functional TypedDicts may document their fields with comments in place of docstrings.

e.g.

```
MyDict = TypedDict("MyDict", {
    "a-field": str,
    # This is interpreted as a docstring
    # and it can span multiple lines
})
```
"""

from __future__ import annotations

import re
from typing import Any, cast

from griffe import (
    Attribute,
    Class,
    Docstring,
    ExprCall,
    ExprDict,
    ExprName,
    Extension,
    GriffeLoader,
    Module,
)


class TypedDictExtension(Extension):
    def __init__(self, modules: list[str] | None = None):
        """
        Args:
            modules (list[str]): fully-qualified python module names
                (e.g. "pdm.mproject.project_file").
                If present, only transform TypedDicts in these modules.
        """
        self.modules = modules

    def on_module(self, *, mod: Module, loader: GriffeLoader, **kwargs: Any) -> None:
        # need to intercept at the module level because we want to modify the types of its members
        # (otherwise we can only mutate the member's attributes, but not replace it)
        if self.modules and mod.module.canonical_path not in self.modules:
            return

        self._transform_functional_typeddicts(mod)

    def _transform_functional_typeddicts(self, mod: Module) -> Module:
        """
        Transform functional typed dicts into class-based typed dicts
        We only do the minimal work needed here to create the representation in the docs -
        just grab the field names and annotations, so other metadata will be incomplete.
        """
        tds = {
            k: v
            for k, v in mod.members.items()
            if isinstance(v, Attribute)
            and "module-attribute" in v.labels
            and isinstance(v.value, ExprCall)
            and v.value.function.name == "TypedDict"
        }

        classes = {}
        for name, td in tds.items():
            classes[name] = Class(name=name, bases=[ExprName(name="TypedDict", parent=mod, member=name)], parent=mod)
            classes[name].docstring = td.docstring

            # Convert the keys/values of the dict arg to classlike attributes
            expression = cast(ExprCall, td.value)
            fields = cast(ExprDict, expression.arguments[1])
            attrs = {}
            for key, val in zip(fields.keys, fields.values):
                key: str
                key = key.strip("'")
                attrs[key] = Attribute(name=key, value=val, annotation=val)
                attrs[key].parent = classes[name]
                attrs[key].docstring = self._extract_comment_docstring(key, td)

            classes[name].members = attrs

        mod.members.update(classes)
        return mod

    def _extract_comment_docstring(self, key: str, td: Attribute) -> Docstring | None:
        """
        find comments after this expression to use as docstrings.
        The ExprName we use to parse the key/annotation doesn't bear the line numbers,
        so regex is unfortunately the best we can do
        """
        expr_line = [idx for idx, line in enumerate(td.lines) if re.match(rf'^\s*[\'"]{key}[\'"]', line)]
        if not expr_line:
            return
        start_line = expr_line[0]

        # find trailing comments, if any
        docstring_lines = []
        for line in td.lines[start_line + 1 :]:
            if not re.match(r"^\s*#", line):
                break
            docstring_lines.append(line.strip().lstrip("#").lstrip())

        # join like a naive markdown, not handling line breaks currently
        docstring = " ".join(docstring_lines)
        if docstring:
            return Docstring(value=docstring)
