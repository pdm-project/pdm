"""A compatible script to install editable distributions."""
import os
import sys
import tokenize

# Initialize working_set early so it WON'T see the dependencies in lib_dir
# See issue/601
__import__("pkg_resources")  # noqa

setup_py, prefix, lib_dir, bin_dir = sys.argv[1:5]
__file__ = setup_py

with getattr(tokenize, "open", open)(__file__) as f:
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
exec(compile(code, __file__, "exec"))
