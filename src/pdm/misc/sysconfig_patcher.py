# Copyright 2024 Ulrik Sverdrup "bluss"
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
Patch sysconfigdata and pkgconfig files in
a python installation from indygreg's python builds.

Adapted from https://github.com/bluss/sysconfigpatcher
"""

import ast
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

OLD_PREFIX = "/install"

SYSCONFIG_HEADER = """\
# system configuration generated and used by the sysconfig module
# install path patched by sysconfigpatcher
"""


@dataclass
class WordReplace:
    """Replace word with another"""

    word: str
    to: str


DEFAULT_VARIABLE_UPDATES = {
    "CC": WordReplace("clang", "cc"),
    "CXX": WordReplace("clang++", "c++"),
    "BLDSHARED": WordReplace("clang", "cc"),
    "LDSHARED": WordReplace("clang", "cc"),
    "LDCXXSHARED": WordReplace("clang++", "c++"),
    "LINKCC": WordReplace("clang", "cc"),
    "AR": "ar",
}


def read_sysconfig_data_ast(fname):
    with open(fname) as fn:
        module = ast.parse(fn.read(), filename=fname)
    return module


def update_prefix(value: str, real_prefix: str):
    if value.startswith(OLD_PREFIX):
        return value.replace(OLD_PREFIX, real_prefix, 1)
    return value


def sync_file(fn):
    if hasattr(os, "fdatasync"):
        os.fdatasync(fn)
    elif hasattr(os, "fsync"):
        os.fsync(fn)


def select_child(ast_obj, type_):
    return next((elt for elt in ast_obj.body if isinstance(elt, type_)), None)


def patch_sysconfig_ast(obj, real_prefix, variable_updates=None):
    """
    variable_updates (dict[str, str | WordReplace] | None): Extra variables that should be updated
    return True if any changes were done
    """
    did_update = False
    variable_updates = variable_updates or {}

    # find module body
    if "body" not in obj._fields:
        raise ValueError
    # find assignment
    assignment = select_child(obj, ast.Assign)
    if assignment is None:
        raise ValueError

    dict_ast = assignment.value

    if not isinstance(dict_ast, ast.Dict):
        raise ValueError(f"Expected Dict, got {dict_ast!r}")

    real_prefix_str = str(real_prefix)
    # type check
    if not all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in dict_ast.keys):
        raise ValueError("Expected all str keys dict")
    if not all(isinstance(value, ast.Constant) and isinstance(value.value, (str, int)) for value in dict_ast.values):
        raise ValueError("Expected all str and int values dict")
    # index because we are modifying
    for key_ast, value_ast in zip(dict_ast.keys, dict_ast.values):
        if not (isinstance(key_ast, ast.Constant) and isinstance(key_ast.value, str)):
            raise ValueError("Expected all str keys dict")
        if not (isinstance(value_ast, ast.Constant) and isinstance(value_ast.value, (str, int))):
            raise ValueError("Expected all str and int values dict")
        key = key_ast.value
        value = value_ast.value

        if not isinstance(value, str):
            continue

        new_value = None

        if key in variable_updates:
            updater = variable_updates[key]
            if isinstance(updater, WordReplace):
                new_value = re.sub(r"(^|\s)" + re.escape(updater.word) + r"(?=\s|$)", updater.to, value, flags=re.ASCII)
            else:
                new_value = updater
            if value == new_value:
                new_value = None
        elif value.startswith(OLD_PREFIX):
            # some keys have multiple paths like
            # DESTDIRS="/install /install/lib /install/lib/python3.12 (...)"
            new_value = " ".join(update_prefix(part, real_prefix_str) for part in value.split(" "))

        if new_value is not None:
            did_update = True
            value_ast.value = new_value
            _logger.debug("Updated %r value\n  from %r\n  to %r", key, value, new_value)

    return did_update


def patch_sysconfig(path: Path, real_prefix: Path, dry_run: bool, backup_files: bool, variable_updates=None):
    """
    return True if did patch or nothing to patch
    """
    _logger.debug("Reading %r", str(path))
    obj = read_sysconfig_data_ast(path)
    did_update = patch_sysconfig_ast(obj, real_prefix, variable_updates)

    if not did_update:
        _logger.info("Nothing to patch in sysconfig")
        return True

    new_file = path.with_suffix(".py.new")
    if dry_run:
        _logger.info("Would patch %s", path)
    else:
        if backup_files:
            backup_file = path.with_suffix(".py.backup")
            shutil.copy(path, backup_file)
            _logger.debug("Wrote %s", backup_file)

        with open(new_file, "w") as fn:
            fn.write(SYSCONFIG_HEADER)
            fn.write(ast.unparse(obj))
            sync_file(fn)

        shutil.move(new_file, path)
        _logger.info("Patched %s", path)
    return True


def find_pkgconfigs(path: Path):
    pkgconfig = path / "lib/pkgconfig"
    if not pkgconfig.exists() or not pkgconfig.is_dir():
        return

    # is_file and not is_symlink
    for child in pkgconfig.iterdir():
        if child.is_file() and not child.is_symlink() and child.suffix == ".pc":
            yield child


def write_new_pkgconfig(fname: Path, real_prefix: Path, dest_path: Path):
    """
    raises ValueError if there is a problem
    returns True if file was changed
    """

    def replace_func(matchobj):
        return matchobj.group(1) + str(real_prefix)

    did_update = False

    with open(fname) as fn:
        with open(dest_path, "w") as outfile:
            for line in fn:
                new_line = re.sub(
                    r"^(\w+=)(" + re.escape(OLD_PREFIX) + ")",
                    replace_func,
                    line,
                    count=1,
                )
                if new_line != line:
                    did_update = True
                    _logger.debug("Updated\n  from %r\n  to %r", line.rstrip(), new_line.rstrip())
                outfile.write(new_line)
            sync_file(outfile)
    return did_update


def patch_pkgconfig(pkgconfig_file, real_prefix, dry_run: bool, backup_files: bool):
    new_file = pkgconfig_file.with_suffix(".pc.new")
    if dry_run:
        _logger.info("Would patch %s", pkgconfig_file)
    else:
        did_update = write_new_pkgconfig(pkgconfig_file, real_prefix, new_file)
        if not did_update:
            os.unlink(new_file)
            _logger.info("Nothing to patch for %s", pkgconfig_file)
        else:
            if backup_files:
                backup_file = pkgconfig_file.with_suffix(".pc.backup")
                shutil.copy(pkgconfig_file, backup_file)
                _logger.debug("Wrote %s", backup_file)
            shutil.move(new_file, pkgconfig_file)
            _logger.info("Patched %s", pkgconfig_file)


def find_libdir(real_prefix: Path):
    # probe python for its libdir and path to the file
    libdir = real_prefix / "lib"
    # find python3.xy in libdir

    if libdir.is_dir():
        py_children = [child for child in libdir.iterdir() if child.is_dir() and child.name.startswith("python3")]
        if len(py_children) == 1:
            return py_children[0]
        if len(py_children) > 1:
            _logger.info("Found lib directories: %r", py_children)
    _logger.error("No lib/python3.x directory found")
    return None


def find_sysconfigdata(real_prefix: Path):
    # probe python for its libdir and path to the file
    sysconfigdata_prefix = "_sysconfigdata_"
    libdir = find_libdir(real_prefix)
    if libdir is None:
        return None
    for child in libdir.iterdir():
        if (
            child.is_file()
            and not child.is_symlink()
            and child.name.startswith(sysconfigdata_prefix)
            and child.suffix == ".py"
        ):
            return child
    return None


def patch(real_prefix: Path) -> None:
    if os.name == "nt":
        # sysconfig patching not needed on Windows
        return
    sysconfig_path = find_sysconfigdata(real_prefix)
    if sysconfig_path is None:
        _logger.error("No sysconfigdata file found")
    else:
        patch_sysconfig(
            sysconfig_path, real_prefix, dry_run=False, backup_files=False, variable_updates=DEFAULT_VARIABLE_UPDATES
        )

    pkgconfig_files = list(find_pkgconfigs(real_prefix))
    if not pkgconfig_files:
        _logger.info("No pkgconfig files found")
    for pc_file in pkgconfig_files:
        patch_pkgconfig(pc_file, real_prefix, dry_run=False, backup_files=False)
