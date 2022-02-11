# Manage Dependencies

PDM provides a bunch of handful commands to help manage your project and dependencies.
The following examples are run on Ubuntu 18.04, a few changes must be done if you are using Windows.

## Initialize a project

```console
mkdir pdm-test && cd pdm-test
pdm init
```

Answer several questions asked by PDM and a `pyproject.toml` will be created for you in the project root:

```toml
[project]
name = "pdm-test"
version = "0.0.0"
description = ""
authors = [
    {name = "Frost Ming", email = "mianghong@gmail.com"}
]
license = {text = "MIT"}
requires-python = ">=3.7"

dependencies = []
```

If `pyproject.toml` is already present, it will be updated with the metadata. The metadata format follows the
[PEP 621 specification](https://www.python.org/dev/peps/pep-0621/)

For details of the meaning of each field in `pyproject.toml`, please refer to [Project File](/pyproject/pep621/).

## Add dependencies

```console
pdm add requests
```

`pdm add` can be followed by one or several dependencies, and the dependency specification is described in
[PEP 508](https://www.python.org/dev/peps/pep-0508/).

PDM also allows extra dependency groups by providing `-G/--group <name>` option, and those dependencies will go to
`[project.optional-dependencies.<name>]` table in the project file, respectively.

After that, dependencies and sub-dependencies will be resolved properly and installed for you, you can view `pdm.lock` to see the resolved result of all dependencies.

### Add local dependencies

Local packages can be added with their paths:

```console
pdm add ./sub-package
```

Local packages can be installed in [editable mode](https://pip.pypa.io/en/stable/cli/pip_install/#editable-installs)
(just like `pip install -e <local project path>` would) using `pdm add -e/--editable <local project path>`.

### Add development only dependencies

_New in 1.5.0_

PDM also supports defining groups of dependencies that are useful for development,
e.g. some for testing and others for linting. We usually don't want these dependencies appear in the distribution's metadata
so using `optional-dependencies` is probably not a good idea. We can define them as development dependencies:

```console
pdm add -dG test pytest
```

This will result in a pyproject.toml as following:

```toml
[tool.pdm.dev-dependencies]
test = ["pytest"]
```

For backward-compatibility, if only `-d` or `--dev` is specified, dependencies will go to `dev` group under `[tool.pdm.dev-dependencies]` by default.

!!! NOTE
    The same group name MUST NOT appear in both `[tool.pdm.dev-dependencies]` and `[project.optional-dependencies]` .

### Save version specifiers

If the package is given without a version specifier like `pdm add requests`. PDM provides three different behaviors of what version
specifier is saved for the dependency, which is given by `--save-<strategy>`(Assume `2.21.0` is the latest version that can be found
for the dependency):

- `minimum`: Save the minimum version specifier: `>=2.21.0` (default).
- `compatible`: Save the compatible version specifier: `>=2.21.0,<3.0.0`.
- `exact`: Save the exact version specifier: `==2.21.0`.
- `wildcard`: Don't constrain version and leave the specifier to be wildcard: `*`.

### Add prereleases

One can give `--pre/--prerelease` option to `pdm add` so that prereleases are allowed to be pinned for the given packages.

## Update existing dependencies

To update all dependencies in the lock file:

```console
pdm update
```

To update the specified package(s):

```console
pdm update requests
```

To update multiple groups of dependencies:

```console
pdm update -G security -G http
```

To update a given package in the specified group:

```console
pdm update -G security cryptography
```

If the group is not given, PDM will search for the requirement in the default dependencies set and raises an error if none is found.

To update packages in development dependencies:

```console
# Update all default + dev-dependencies
pdm update -d
# Update a package in the specified group of dev-dependencies
pdm update -dG test pytest
```

### About update strategy

Similarly, PDM also provides 2 different behaviors of updating dependencies and sub-dependencies，
which is given by `--update-<strategy>` option:

- `reuse`: Keep all locked dependencies except for those given in the command line (default).
- `eager`: Try to lock a newer version of the packages in command line and their recursive sub-dependencies
  and keep other dependencies as they are.

### Update packages to the versions that break the version specifiers

One can give `-u/--unconstrained` to tell PDM to ignore the version specifiers in the `pyproject.toml`.
This works similarly to the `yarn upgrade -L/--latest` command. Besides, `pdm update` also supports the
`--pre/--prerelease` option.

## Remove existing dependencies

To remove existing dependencies from project file and the library directory:

```console
# Remove requests from the default dependencies
pdm remove requests
# Remove h11 from the 'web' group of optional-dependencies
pdm remove -G web h11
# Remove pytest-cov from the `test` group of dev-dependencies
pdm remove -dG test pytest-cov
```

## Install the packages pinned in lock file

There are two similar commands to do this job with a slight difference:

- `pdm install` will check the lock file and relock if it mismatches with project file, then install.
- `pdm sync` installs dependencies in the lock file and will error out if it doesn't exist.
  Besides, `pdm sync` can also remove unneeded packages if `--clean` option is given.

### Select a subset of dependencies with CLI options

Say we have a project with following dependencies:

```toml
[project]  # This is production dependencies
dependencies = ["requests"]

[project.optional-dependencies]  # This is optional dependencies
extra1 = ["flask"]
extra2 = ["django"]

[tool.pdm.dev-dependencies]  # This is dev dependencies
dev1 = ["pytest"]
dev2 = ["mkdocs"]
```

| Command                         | What it does                                                         | Comments                  |
| ------------------------------- | -------------------------------------------------------------------- | ------------------------- |
| `pdm install`                   | install prod and dev deps (no optional)                              |                           |
| `pdm install -G extra1`         | install prod deps, dev deps, and "extra1" optional group             |                           |
| `pdm install -G dev1`           | install prod deps and only "dev1" dev group                          |                           |
| `pdm install -G:all`            | install prod deps, dev deps and "extra1", "extra2" optional groups   |                           |
| `pdm install -G extra1 -G dev1` | install prod deps, "extra1" optional group and only "dev1" dev group |                           |
| `pdm install --prod`            | install prod only                                                    |                           |
| `pdm install --prod -G extra1`  | install prod deps and "extra1" optional                              |                           |
| `pdm install --prod -G dev1`    | Fail, `--prod` can't be given with dev dependencies                  | Leave the `--prod` option |

**All** development dependencies are included as long as `--prod` is not passed and `-G` doesn't specify any dev groups.

Besides, if you don't want the root project to be installed, add `--no-self` option, and `--no-editable` can be used when you want all packages to be installed in non-editable versions. With `--no-editable` turn on, you can safely archive the whole `__pypackages__` and copy it to the target environment for deployment.

## Show what packages are installed

Similar to `pip list`, you can list all packages installed in the packages directory:

```console
pdm list
```

Or show a dependency graph by:

```
$ pdm list --graph
tempenv 0.0.0
└── click 7.0 [ required: <7.0.0,>=6.7 ]
black 19.10b0
├── appdirs 1.4.3 [ required: Any ]
├── attrs 19.3.0 [ required: >=18.1.0 ]
├── click 7.0 [ required: >=6.5 ]
├── pathspec 0.7.0 [ required: <1,>=0.6 ]
├── regex 2020.2.20 [ required: Any ]
├── toml 0.10.0 [ required: >=0.9.4 ]
└── typed-ast 1.4.1 [ required: >=1.4.0 ]
bump2version 1.0.0
```

## Set PyPI index URL

You can specify a PyPI mirror URL by following commands:

```console
pdm config pypi.url https://test.pypi.org/simple
```

By default, PDM will read the pip's configuration files to decide the PyPI URL, and fallback
to `https://pypi.org/simple` if none is found.

## Allow prerelease versions to be installed

Include the following setting in `pyproject.toml` to enable:

```toml
[tool.pdm]
allow_prereleases = true
```

## Solve the locking failure

If PDM is not able to find a resolution to satisfy the requirements, it will raise an error. For example,

```bash
pdm django==3.1.4 "asgiref<3"
...
🔒 Lock failed
Unable to find a resolution for asgiref because of the following conflicts:
  asgiref<3 (from project)
  asgiref<4,>=3.2.10 (from <Candidate django 3.1.4 from https://pypi.org/simple/django/>)
To fix this, you could loosen the dependency version constraints in pyproject.toml. If that is not possible, you could also override the resolved version in [tool.pdm.overrides] table.
```

You can either change to a lower version of `django` or remove the upper bound of `asgiref`. But if it is not eligible for your project,
you can tell PDM to forcedly resolve `asgiref` to a specific version by adding the following lines to `pyproject.toml`:

_New in version 1.12.0_

```toml
[tool.pdm.overrides]
asgiref = "3.2.10"
pytz = "file:///${PROJECT_ROOT}/pytz-2020.9-py3-none-any.whl"
```
Each entry of that table is a package name with the wanted version. The value can also be a URL to a file or a VCS repository like `git+https://...`.
On reading this, PDM will pin `asgiref@3.2.10` in the lock file no matter whether there is any other resolution available.

!!! NOTE
    By using `[tool.pdm.overrides]` setting, you are at your own risk of any incompatibilities from that resolution. It can only be
    used if there is no valid resolution for your requirements and you know the specific version works.
    Most of the time, you can just add any transient constraints to the `dependencies` array.

## Environment variables expansion

For convenience, PDM supports environment variables expansion in the dependency specification under some circumstances:

- Environment variables in the URL auth part will be expanded: `https://${USERNAME}:${PASSWORD}/artifacts.io/Flask-1.1.2.tar.gz`.
  It is also okay to not give the auth part in the URL directly, PDM will ask for them when `-v/--verbose` is on.
- `${PROJECT_ROOT}` will be expanded with the absolute path of the project root, in POSIX style(i.e. forward slash `/`, even on Windows).
  For consistency, URLs that refer to a local path under `${PROJECT_ROOT}` must start with `file:///`(three slashes), e.g.
  `file:///${PROJECT_ROOT}/artifacts/Flask-1.1.2.tar.gz`.

Don't worry about credential leakage, the environment variables will be expanded when needed and kept untouched in the lock file.
