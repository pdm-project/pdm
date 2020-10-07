"""A compatible script to install editable distributions."""
import os
import site
import sys
import tokenize

from setuptools.command import easy_install

EXE_INITIALIZE = """
import sys
with open({0!r}) as fp:
    exec(compile(fp.read(), __file__, "exec"))
""".strip()


def install(setup_py, prefix, lib_dir, bin_dir):
    __file__ = setup_py

    with getattr(tokenize, "open", open)(setup_py) as f:
        code = f.read().replace("\\r\\n", "\n")
    if os.path.exists(os.path.join(lib_dir, "site.py")):
        # Remove the custom site.py for editable install.
        # It will be added back after installation is done.
        os.remove(os.path.join(lib_dir, "site.py"))
    sys.argv[1:] = [
        "develop",
        "--install-dir={0}".format(lib_dir),
        "--no-deps",
        "--prefix={0}".format(prefix),
        "--script-dir={0}".format(bin_dir),
        "--site-dirs={0}".format(lib_dir),
    ]
    sys.path.append(lib_dir)
    if os.path.normpath(lib_dir) not in site.getsitepackages():
        # Patches the script writer to inject library path
        easy_install.ScriptWriter.template = easy_install.ScriptWriter.template.replace(
            "import sys",
            EXE_INITIALIZE.format(
                os.path.abspath(
                    os.path.join(lib_dir, os.path.pardir, "site/sitecustomize.py")
                )
            ),
        )
    exec(compile(code, __file__, "exec"))


if __name__ == "__main__":
    setup_py, prefix, lib_dir, bin_dir = sys.argv[1:5]
    install(setup_py, prefix, lib_dir, bin_dir)
