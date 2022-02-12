# PDM Tool Settings

There are also some useful settings to control the packaging behavior of PDM. They should be shipped with `pyproject.toml`, defined in `[tool.pdm]` table.

## Development dependencies

You can have several groups of development only dependencies. Unlike `optional-dependencies`, they won't appear in the package distribution metadata such as `PKG-INFO` or `METADATA`.
And the package index won't be aware of these dependencies. The schema is similar to that of `optional-dependencies`, except that it is in `tool.pdm` table.

```toml
[tool.pdm.dev-dependencies]
lint = [
    "flake8",
    "black"
]
test = ["pytest", "pytest-cov"]
doc = ["mkdocs"]
```

To install all of them:

```bash
pdm install
```

For more CLI usage, please refer to [Manage Dependencies](/usage/dependency/)

## Specify other sources for finding packages

Like Pipenv, you can specify extra sources for finding packages with the same format. They are stored in an array of table named `[[tool.pdm.source]]` in `pyproject.toml`:

```toml
[[tool.pdm.source]]
url = "https://private-site.org/pypi/simple"
verify_ssl = true
name = "internal"
```

This works as if `--extra-index-url https://private-site.org/pypi/simple` is passed.

Or you can override the `pypi.url` value by using a source named `pypi`:

```toml
[[tool.pdm.source]]
url = "https://private.pypi.org/simple"
verify_ssl = true
name = "pypi"
```

By default, or sources are [PEP 503](https://www.python.org/dev/peps/pep-0503/) style "index urls" like pip's `--index-url` and `--extra-url`, however, you can also specify "find links" with
`type = "find_links"`. See [this answer](https://stackoverflow.com/a/46651848) for the difference between the two types.

!!! note "Difference from changing config value"
    When you want all packages to be fetched from the given index instead of the default one, despite what platform your are on or who is to deploy the app,
    write it in the `[[tool.pdm.source]]`. Otherwise if you would like to change the index temporarily on the current platform (for network reasons), you should use
    `pdm config pypi.url https://private.pypi.org/simple`.

## Include and exclude package files

The way of specifying include and exclude files are simple, they are given as a list of glob patterns:

```toml
includes = [
    "**/*.json",
    "mypackage/",
]
excludes = [
    "mypackage/_temp/*"
]
```

In case you want some files to be included in sdist only, you use the `source-includes` field:

```toml
includes = [...]
excludes = [...]
source-includes = ["tests/"]
```

Note that the files defined in `source-includes` will be **excluded** automatically from non-sdist builds.

### Default values for includes and excludes

If you don't specify any of these fields, PDM also provides smart default values to fit the most common workflows.

- Top-level packages will be included.
- `tests` package will be excluded from **non-sdist** builds.
- `src` directory will be detected as the `package-dir` if it exists.

If your project follows the above conventions you don't need to config any of these fields and it just works.
Be aware PDM won't add [PEP 420 implicit namespace packages](https://www.python.org/dev/peps/pep-0420/) automatically and they should always be specified in `includes` explicitly.

## Select another package directory to look for packages

Similar to `setuptools`' `package_dir` setting, one can specify another package directory, such as `src`, in `pyproject.toml` easily:

```toml
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

## Build Platform-specific Wheels

You may want to build platform-specific wheels if it contains binaries. Currently, building C extensions still relies on `setuptools`. 
You should write a python script with a function named `build` which accepts the ``kwargs`` of `setup()` as the argument.
Then, update the dictionary with your `ext_modules` settings in the function.

Here is an example taken from `MarkupSafe`:

```python
# build.py
from setuptools import Extension

ext_modules = [Extension("markupsafe._speedups", ["src/markupsafe/_speedups.c"])]

def build(setup_kwargs):
    setup_kwargs.update(ext_modules=ext_modules)
```

Now, specify the build script path via `build` in the `pyproject.toml`:

```toml
# pyproject.toml
[tool.pdm]
build = "build.py"
```

If you run `pdm build`(or any other build frontends such as [build](https://pypi.org/project/build)), PDM will build a platform-specific wheel file as well as a sdist.

By default, every build is performed in a clean and isolated environment, only build requirements can be seen. If your build has optional requirements that depend on the project environment, you can turn off the environment isolation by `pdm build --no-isolation` or setting config `build_isolation` to falsey value.

### Override the "Is-Purelib" value

Sometimes you may want to build platform-specific wheels but don't have a build script(the binaries may be built or fetched by other tools). In this case
you can set the `is-purelib` value in the `pyproject.toml` to `false`:

```toml
[tool.pdm]
is-purelib = false
```

## Editable build backend

PDM leverages [PEP 660](https://www.python.org/dev/peps/pep-0660/) to build wheels for editable installation.
One can choose how to generate the wheel out of the two methods:

- `path`: (Default)The legacy method used by setuptools that create .pth files under the packages path.
- `editables`: Create proxy modules under the packages path. Since the proxy module is looked for at runtime, it may not work with some static analysis tools.

Read the PEP for the difference of the two methods and how they work.

Specify the method in pyproject.toml like below:

```toml
[tool.pdm]
editable-backend = "path"
```

`editables` backend is more recommended but there is a known limitation that it can't work with PEP 420 namespace packages.
So you would need to change to `path` in that case.

!!! note "About Python 2 compatibility"
    Due to the fact that the build backend for PDM managed projects requires Python>=3.6, you would not be able to
    install the current project if Python 2 is being used as the host interpreter. You can still install other dependencies not PDM-backed.
