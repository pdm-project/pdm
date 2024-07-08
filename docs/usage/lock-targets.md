# Lock for specific platforms or Python versions

+++ 2.17.0

By default, PDM will try to make a lock file that works on all platforms within the Python versions specified by [`requires-python` in `pyproject.toml`](./project.md#specify-requires-python). This is very convenient during development. You can generate a lock file in your development environment and then use this lock file to replicate the same dependency versions in CI/CD or production environments.

However, there are times when this approach may not work. For example, your project or dependency has some platform-specific dependencies, or conditional dependencies depending on the Python version, like the following:

```toml
[project]
name = "myproject"
requires-python = ">=3.8"
dependencies = [
    "numpy<1.25; python_version < '3.9'",
    "numpy>=1.25; python_version >= '3.9'",
    "pywin32; sys_platform == 'win32'",
]
```

In this case, it's almost impossible to get a single resolution for each package on all platforms and Python versions(`>=3.8`). You should, instead, make lock files for specific platforms or Python versions.

## Specify lock target when generating lock file

PDM supports specifying one or more environment criteria when generating a lock file. These criteria include:

- `--python=<PYTHON_RANGE>`: A [PEP 440](https://www.python.org/dev/peps/pep-0440/) compatible Python version specifier. For example, `--python=">=3.8,<3.10"` will generate a lock file for Python versions `>=3.8` and `<3.10`.
- `--platform=<PLATFORM>`: A platform specifier. For example, `pdm lock --platform=linux` will generate a lock file for Linux x86_64 platform. Available options are:
    * `linux`
    * `windows`
    * `macos`
    * `alpine`
    * `windows_amd64`
    * `windows_x86`
    * `windows_arm64`
    * `macos_arm64`
    * `macos_x86_64`
    * `macos_X_Y_arm64`
    * `macos_X_Y_x86_64`
    * `manylinux_X_Y_x86_64`
    * `manylinux_X_Y_aarch64`
    * `musllinux_X_Y_x86_64`
    * `musllinux_X_Y_aarch64`
- `--implementation=cpython|pypy|pyston`: A Python implementation specifier. Currently only `cpython`, `pypy`, and `pyston` are supported.

You can ignore some of the criteria, for example, by specifying only `--platform=linux`, the generated lock file will be applicable to Linux platform and all implementations.

!!! note "`python` criterion and `requires-python`"

    `--python` option, or `requires-python` criterion in the lock target is still limited by the `requires-python` in `pyproject.toml`. For example, if `requires-python` is `>=3.8` and you specified `--python="<3.11"`, the lock target will be `>=3.8,<3.11`.

## Separate lock files or merge into one

If you need more than one lock targets, you can either create separate lock files for each target or combine them into a single lock file. PDM supports both ways.

To create separate lock file with a specific target:

```bash
# Generate a lock file for Linux platform and Python 3.8, write the result to py38-linux.lock
pdm lock --platform=linux --python="==3.8.*" --lockfile=py38-linux.lock
```

When you install dependencies on Linux and Python 3.8, you can use this lock file:

```bash
pdm install --lockfile=py38-linux.lock
```

Additionally, you can also select a subset of dependency groups for the lock file, see [here](./lockfile.md#specify-another-lock-file-to-use) for more details.

If you would like to use the same lock file for multiple targets, add `--append` to the `pdm lock` command:

```bash
# Generate a lock file for Linux platform and Python 3.8, append the result to pdm.lock
pdm lock --platform=linux --python="==3.8.*" --append
```

The advantages of using a single lock file are you don't need to manage multiple lock files when updating dependencies. However, you can't specify different lock strategies for different targets in a single lock file. And the time cost of updating the locks is expected to be higher.

What's more, each lock file can have one or more lock targets, making it rather flexible to use. You can choose to merge some targets in a lock file and lock specific groups and targets in separate lock files. We'll illustrate this with an example in the next section.

## Example

Here is the `pyproject.toml` content:

```toml
[project]
name = "myproject"
requires-python = ">=3.8"
dependencies = [
    "numpy<1.25; python_version < '3.9'",
    "numpy>=1.25; python_version >= '3.9'",
    "pandas"
]

[project.optional-dependencies]
windows = ["pywin32"]
macos = ["pyobjc"]
```

In the above example, we have conditional dependency versions for `numpy` and platform-specific optional dependencies for Windows and MacOS. We want to generate lock files for Linux, Windows, and MacOS platforms, and Python 3.8 and 3.9.

```bash
pdm lock --python=">=3.9"
pdm lock --python="<3.9" --append

pdm lock --platform=windows --python=">=3.9" --lockfile=py39-windows.lock --with windows
pdm lock --platform=macos --python=">=3.9" --lockfile=py39-macos.lock --with macos
```
Run the above commands in order, and you will get 3 lockfiles:

- `pdm.lock`: the default main lock file, which works on all platforms and Python versions in `>=3.8`. No platform specific dependencies are included. In this lock file, there are two versions of `numpy`, suitable for Python 3.9 and above and below respectively. The PDM installer will choose the correct version according to the Python version.
- `py39-windows.lock`: lock file for Windows platform and Python 3.9 above, including the optional dependencies for Windows.
- `py39-macos.lock`: lock file for MacOS platform and Python 3.9 above, including the optional dependencies for MacOS.
