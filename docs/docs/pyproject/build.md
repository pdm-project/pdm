# Build Configuration

`pdm` uses the [PEP 517](https://www.python.org/dev/peps/pep-0517/) to build the package.
A build backend is what drives the build system to build source distributions and wheels from arbitrary source trees.

`pdm` also ships with its own build backend, [`pdm-pep517`](https://pypi.org/project/pdm-pep517/). Besides the [PEP 621 project meta](pep621.md), it reads additional configurations stored in `[tool.pdm.build]` table to control the build behavior. To use it, include the following in your `pyproject.toml`(It will be done automatically if you use the [`pdm init`](../usage/cli_reference.md#exec-0--init) or [`pdm import`](../usage/cli_reference.md#exec-0--import) to create the file):

```toml
[build-system]
requires = ["pdm-pep517"]
build-backend = "pdm.pep517.api"
```

!!! NOTE
    The following part of this documentation assumes you are using the `pdm-pep517` backend as mentioned above. Different backends will have different configurations.

## Dynamic versioning

`pdm-pep517` supports dynamic versions from two sources. To enable dynamic versioning, remember to include `version` in the `dynamic` field of PEP 621 metadata:

```toml
[project]
...
dynamic = ["version"]
```

### Dynamic version from file

```toml
[tool.pdm]
version = { source = "file", path = "mypackage/__version__.py" }
```

The backend will search for the pattern `__version__ = "{version}"` in the given file and use the value as the version.

!!! TIP

    Thanks to the TOML syntax, the above example is equivalent to the following:

    ```toml
    [tool.pdm.version]
    source = "file"
    path = "mypackage/__version__.py"
    ```
    Or:
    ```toml
    [tool.pdm]
    version.source = "file"
    version.path = "mypackage/__version__.py"
    ```

### Dynamic version from SCM

If you've used [`setuptools-scm`](https://pypi.org/project/setuptools-scm/) you will be familiar with this approach. `pdm-pep517` can also read the version from the tag of your SCM repository:

```toml
[tool.pdm]
version = { source = "scm" }
```

#### Specify the version manually

When building the package, `pdm-pep517` will require the SCM to be available to populate the version. If that is not the case, you can still specify the version with an environment variable `PDM_PEP517_SCM_VERSION`:

```bash
export PDM_PEP517_SCM_VERSION="1.2.3"
pdm build
```

#### Write the version to file

For dynamic version read from SCM, it would be helpful to write the evaluated value to a file when building a wheel, so that you do not need `importlib.metadata` to get the version in code.

```toml
[tool.pdm.version]
source = "scm"
write_to = "mypackage/__version__.py"
write_template = "__version__ = '{}'"  # optional, default to "{}"
```

For source distributions, the version will be *frozen* and converted to a static version in the `pyproject.toml` file, which will be included in the distribution.

## Include and exclude files

To include extra files and/or exclude files from the distribution, give the paths in `includes` and `excludes` configuration, as glob patterns:

```toml
[tool.pdm.build]
includes = [
    "**/*.json",
    "mypackage/",
]
excludes = [
    "mypackage/_temp/*"
]
```

In case you may want some files to be included in source distributions only, use the `source-includes` field:

```toml
[tool.pdm.build]
includes = [...]
excludes = [...]
source-includes = ["tests/"]
```

Note that the files defined in `source-includes` will be **excluded** automatically from binary distributions.

### Default values for includes and excludes

If you don't specify any of these fields, PDM can determine the values for you to fit the most common workflows, in the following manners:

- Top-level packages will be included.
- `tests` package will be excluded from **non-sdist** builds.
- `src` directory will be detected as the `package-dir` if it exists.

If your project follows the above conventions you don't need to config any of these fields and it just works.
Be aware PDM won't add [PEP 420 implicit namespace packages](https://www.python.org/dev/peps/pep-0420/) automatically and they should always be specified in `includes` explicitly.

## Select another package directory to look for packages

Similar to `setuptools`' `package_dir` setting, one can specify another package directory, such as `src`, in `pyproject.toml` easily:

```toml
[tool.pdm.build]
package-dir = "src"
```

If no package directory is given, PDM can also recognize `src` as the `package-dir` implicitly if:

1. `src/__init__.py` doesn't exist, meaning it is not a valid Python package, and
2. There exist some packages under `src/*`.

## Implicit namespace packages

As specified in [PEP 420](https://www.python.org/dev/peps/pep-0420), a directory will be recognized as a namespace package if:

1. `<package>/__init__.py` doesn't exist, and
2. There exist normal packages and/or other namespace packages under `<package>/*`, and
3. `<package>` is explicitly listed in `includes`

## Custom file generation

During the build, you may want to generate other files or download resources from the internet. You can achieve this by the `setup-script` build configuration:

```toml
[tool.pdm.build]
setup-script = "build.py"
```

In the `build.py` script, `pdm-pep517` looks for a `build` function and calls it with two arguments:

- `src`: (str) the path to the source directory
- `dst`: (str) the path to the distribution directory

Example:

```python
# build.py
def build(src, dst):
    target_file = os.path.join(dst, "mypackage/myfile.txt")
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    download_file_to(dst)
```

The generated file will be copied to the resulted wheel with the same hierarchy, you need to create the parent directories if necessary.

## Build Platform-specific Wheels

`setup-script` can also be used to build platform-specific wheels, such as C extensions. Currently, building C extensions still relies on `setuptools`.

Set `run-setuptools = true` under `setup-script`, and `pdm-pep517` will generate a `setup.py` with the custom `build` function in the script then run `python setup.py build` to build the wheel and any extensions:

```toml
# pyproject.toml
[tool.pdm.build]
setup-script = "build_setuptools.py"
run-setuptools = true
```

In the `setup-script`, the expected `build` function receives the argument dictionary to be passed to the `setuptools.setup()` call. In the function, you can update the [keyword dictionary](https://setuptools.pypa.io/en/latest/references/keywords.html) with any additional or changed values as you want.

Here is an example adapted to build `MarkupSafe`:

```python
# build_setuptools.py
from setuptools import Extension

ext_modules = [
    Extension("markupsafe._speedups", ["src/markupsafe/_speedups.c"])
]

def build(setup_kwargs):
    setup_kwargs.update(ext_modules=ext_modules)
```

If you run [`pdm build`](../usage/cli_reference.md#exec-0--build)(or any other build frontends such as [build](https://pypi.org/project/build)), PDM will build a platform-specific wheel file as well as a sdist.

By default, every build is performed in a clean and isolated environment, only build requirements can be seen. If your build has optional requirements that depend on the project environment, you can turn off the environment isolation by `pdm build --no-isolation` or setting config `build_isolation` to falsey value.

## Override the "Is-Purelib" value

If this value is not specified, `pdm-pep517` will build platform-specific wheels if `run-setuptools` is `true`.

Sometimes you may want to build platform-specific wheels but don't have a build script (the binaries may be built or fetched by other tools). In this case
you can set the `is-purelib` value in the `pyproject.toml` to `false`:

```toml
[tool.pdm.build]
is-purelib = false
```

## Editable build backend

PDM implements [PEP 660](https://www.python.org/dev/peps/pep-0660/) to build wheels for editable installation.
One can choose how to generate the wheel out of the two methods:

- `path`: (Default)The legacy method used by setuptools that create .pth files under the packages path.
- `editables`: Create proxy modules under the packages path. Since the proxy module is looked for at runtime, it may not work with some static analysis tools.

Read the PEP for the difference of the two methods and how they work.

Specify the method in pyproject.toml like below:

```toml
[tool.pdm.build]
editable-backend = "path"
```

`editables` backend is more recommended but there is a known limitation that it can't work with PEP 420 namespace packages.
So you would need to change to `path` in that case.

!!! note "About Python 2 compatibility"
    Due to the fact that the build backend for PDM managed projects requires Python>=3.6, you would not be able to
    install the current project if Python 2 is being used as the host interpreter. You can still install other dependencies not PDM-backed.

## Use other PEP 517 backends

Apart from `pdm-pep517`, `pdm` plays well with any PEP 517 build backends that read PEP 621 metadata. At the time of writing, [`flit`](https://pypi.org/project/flit)(backend: `flit-core`) and [`hatch`](https://pypi.org/project/hatch)(backend: `hatchling`) are working well with PEP 621 and [`setuptools`](https://pypi.org/project/setuptools) has experimental support. To use one of them, you can specify the backend in the `pyproject.toml`:

```toml
[build-system]
requires = ["flit_core >=3.2,<4"]
build-backend = "flit_core.buildapi"
```

PDM will call the correct backend when doing [`pdm build`](../usage/cli_reference.md#exec-0--build).


