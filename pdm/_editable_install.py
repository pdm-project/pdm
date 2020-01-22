from setuptools.command import easy_install
import sys
import os
import tokenize


def install(setup_py, prefix):
    __file__ = setup_py
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    install_dir = os.path.join(prefix, "lib")
    scripts_dir = os.path.join(prefix, bin_dir)

    with getattr(tokenize, "open", open)(setup_py) as f:
        code = f.read().replace("\\r\\n", "\n")
    sys.argv[1:] = [
        "develop",
        f"--install-dir={install_dir}",
        "--no-deps",
        f"--prefix={prefix}",
        f"--script-dir={scripts_dir}",
        f"--site-dirs={install_dir}",
    ]
    # Patches the script writer to inject library path
    easy_install.ScriptWriter.template = easy_install.ScriptWriter.template.replace(
        "import sys",
        "import sys\nsys.path.insert(0, {!r})".format(install_dir.replace("\\", "/")),
    )
    exec(compile(code, __file__, "exec"))


if __name__ == "__main__":
    setup_py, prefix = sys.argv[1:3]
    install(setup_py, prefix)
