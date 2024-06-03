import _imp
import json
import sys
import sysconfig

# Copied from packaging/tags.py

EXTENSION_SUFFIXES = _imp.extension_suffixes()
INTERPRETER_SHORT_NAMES = {
    "python": "py",  # Generic.
    "cpython": "cp",
    "pypy": "pp",
    "ironpython": "ip",
    "jython": "jy",
}


def _version_nodot(version):
    return "".join(map(str, version))


def _normalize_string(string):
    return string.replace(".", "_").replace("-", "_").replace(" ", "_")


def _cpython_abis(py_version):
    py_version = tuple(py_version)  # To allow for version comparison.
    abis = []
    version = _version_nodot(py_version[:2])
    debug = pymalloc = ucs4 = ""
    with_debug = sysconfig.get_config_var("Py_DEBUG")
    has_refcount = hasattr(sys, "gettotalrefcount")
    # Windows doesn't set Py_DEBUG, so checking for support of debug-compiled
    # extension modules is the best option.
    # https://github.com/pypa/pip/issues/3383#issuecomment-173267692
    has_ext = "_d.pyd" in EXTENSION_SUFFIXES
    if with_debug or (with_debug is None and (has_refcount or has_ext)):
        debug = "d"
    if py_version < (3, 8):
        with_pymalloc = sysconfig.get_config_var("WITH_PYMALLOC")
        if with_pymalloc or with_pymalloc is None:
            pymalloc = "m"
        if py_version < (3, 3):
            unicode_size = sysconfig.get_config_var("Py_UNICODE_SIZE")
            if unicode_size == 4 or (unicode_size is None and sys.maxunicode == 0x10FFFF):
                ucs4 = "u"
    elif debug:
        # Debug builds can also load "normal" extension modules.
        # We can also assume no UCS-4 or pymalloc requirement.
        abis.append(f"cp{version}")
    abis.insert(
        0,
        "cp{version}{debug}{pymalloc}{ucs4}".format(version=version, debug=debug, pymalloc=pymalloc, ucs4=ucs4),
    )
    return abis


def _generic_abi():
    """
    Return the ABI tag based on EXT_SUFFIX.
    """
    # The following are examples of `EXT_SUFFIX`.
    # We want to keep the parts which are related to the ABI and remove the
    # parts which are related to the platform:
    # - linux:   '.cpython-310-x86_64-linux-gnu.so' => cp310
    # - mac:     '.cpython-310-darwin.so'           => cp310
    # - win:     '.cp310-win_amd64.pyd'             => cp310
    # - win:     '.pyd'                             => cp37 (uses _cpython_abis())
    # - pypy:    '.pypy38-pp73-x86_64-linux-gnu.so' => pypy38_pp73
    # - graalpy: '.graalpy-38-native-x86_64-darwin.dylib'
    #                                               => graalpy_38_native

    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not isinstance(ext_suffix, str) or ext_suffix[0] != ".":
        raise SystemError("invalid sysconfig.get_config_var('EXT_SUFFIX')")
    parts = ext_suffix.split(".")
    if len(parts) < 3:
        # CPython3.7 and earlier uses ".pyd" on Windows.
        return _cpython_abis(sys.version_info[:2])
    soabi = parts[1]
    if soabi.startswith("cpython"):
        # non-windows
        abi = "cp" + soabi.split("-")[1]
    elif soabi.startswith("cp"):
        # windows
        abi = soabi.split("-")[0]
    elif soabi.startswith("pypy"):
        abi = "-".join(soabi.split("-")[:2])
    elif soabi.startswith("graalpy"):
        abi = "-".join(soabi.split("-")[:3])
    elif soabi:
        # pyston, ironpython, others?
        abi = soabi
    else:
        return []
    return [_normalize_string(abi)]


def interpreter_name() -> str:
    """
    Returns the name of the running interpreter.

    Some implementations have a reserved, two-letter abbreviation which will
    be returned when appropriate.
    """
    name = sys.implementation.name
    return INTERPRETER_SHORT_NAMES.get(name) or name


if __name__ == "__main__":
    if interpreter_name() == "cp":
        abis = _cpython_abis(sys.version_info[:2])
    else:
        abis = _generic_abi()
    print(json.dumps(abis))
