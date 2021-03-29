# Manage dependencies

PDM provides a bunch of handful commands to help manage your project and dependencies.
The following examples are run on Ubuntu 18.04, a few changes must be done if you are using Windows.

## Initialize a project

```console
$ mkdir pdm-test && cd pdm-test
$ pdm init
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

For details of the meaning of each field in `pyproject.toml`, please refer to [Project File](pyproject.md).

## Add dependencies

```console
$ pdm add requests
```

`pdm add` can be followed by one or several dependencies, and the dependency specification is described in
[PEP 508](https://www.python.org/dev/peps/pep-0508/).

PDM also allows extra dependency groups by providing `-s/--section <name>` option, and those dependencies will go to
`[project.optional-dependencies.<name>]` table in the project file, respectively.

After that, dependencies and sub-dependencies will be resolved properly and installed for you, you can view `pdm.lock` to see
the resolved result of all dependencies.

Local packages can be installed in [editable mode](https://pip.pypa.io/en/stable/reference/pip_install/#editable-installs)
(just like `pip install -e <local project path>` would) using `pdm add -e/--editable <local project path>`.

## Add development only dependencies

_New in 1.5.0_

PDM also supports defining groups of dependencies that are useful for development. They can be classified as different groups,
e.g. some for testing and others for linting. We usually don't want these dependencies appear in the distribution's metadata
so using `optional-dependencies` is probably not a good idea. We can define them as development dependencies:

```console
$ pdm add -ds test pytest
```

This will result in a pyproject.toml as following:

```toml
[tool.pdm.dev-dependencies]
test = ["pytest"]
```

For backward-compatibility, if `-s/--section` is not given, dependencies will go to `dev` group under `[tool.pdm.dev-dependencies]` by default.

!!! NOTE
    The group names in `[tool.pdm.dev-dependencies]` MUST NOT conflict with those in `[project.optional-dependencies]`.

### Save version specifiers

If the package is given without a version specifier like `pdm add requests`. PDM provides three different behaviors of what version
specifier is saved for the dependency, which is given by `--save-<strategy>`(Assume `2.21.0` is the latest version that can be found
for the dependency):

- `compatible`: Save the compatible version specifier: `>=2.21.0,<3.0.0`(default).
- `exact`: Save the exact version specifier: `==2.21.0`.
- `wildcard`: Don't constrain version and leave the specifier to be wildcard: `*`.

## Update existing dependencies

To update all dependencies in the lock file:

```console
$ pdm update
```

To update the specified package(s):

```console
$ pdm update requests
```

To update multiple sections of dependencies:

```console
$ pdm update -s security -s http
```

To update a given package in the specified section:

```console
$ pdm update -s security cryptography
```

If the section is not given, PDM will search for the requirement in the default dependencies set and raises an error if none is found.

To update packages in development dependencies:

```console
# Update all dev-dependencies
$ pdm update -d
# Update a package in the specified group of dev-dependencies
$ pdm update -ds test pytest
```

### About update strategy

Similarly, PDM also provides 2 different behaviors of updating dependencies and sub-dependencies，
which is given by `--update-<strategy>` option:

- `reuse`: Keep all locked dependencies except for those given in the command line.
- `eager`: Try to lock a newer version of the packages in command line and their recursive sub-dependencies
  and keep other dependencies as they are.

## Remove existing dependencies

To remove existing dependencies from project file and the library directory:

```console
# Remove requests from the default dependencies
$ pdm remove requests
# Remove h11 from the 'web' optional group
$ pdm remove -s web h11
# Remove pytest-cov from the `test` dev-dependencies group
$ pdm remove -ds test pytest-cov
```

## Install the packages pinned in lock file

There are two similar commands to do this job with a slight difference:

```console
# Install all default dependencies
$ pdm install
# Install default + web optional dependencies
$ pdm install -s web
# Install default + all dev-dependencies
$ pdm install -d
# Install web dependencies ONLY (without default dependencies)
$ pdm install --no-default -s web
```

- `pdm install` will check the lock file and relock if it mismatches with project file, then install.
- `pdm sync` installs dependencies in the lock file and will error out if it doesn't exist.
  Besides, `pdm sync` can also remove unneeded packages if `--clean` option is given.

## Show what packages are installed

Similar to `pip list`, you can list all packages installed in the packages directory:

```console
$ pdm list
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
$ pdm config set pypi.url https://testpypi.org/simple
```

By default, PDM will read the pip's configuration files to decide the PyPI URL, and fallback
to `https://pypi.org/simple` if none is found.

## Add extra sources of packages

Sometimes your packages may exist on a private repository other than PyPI(and its mirrors).
These sources should be preserved in `pyproject.toml` and shipped with the project in deployment.

```toml
[[tool.pdm.source]]
url = "http://example.com/private/index"
verify_ssl = false  # Don't verify SSL, it is required when you are using `HTTP` or the certificate is trusted.
name = "private"
```

Use the name `name = "pypi"` if you want to override the configured PyPI index. Note that PDM specific settings
are stored under `tool.pdm` namespace in the `pyproject.toml`.

## Allow prerelease versions to be installed

Include the following setting in `pyproject.toml` to enable:

```toml
[tool.pdm]
allow_prereleases = true
```

## Environment variables expansion

For convenience, PDM supports environment variables expansion in the dependency specification under some circumstances:

- Environment variables in the URL auth part will be expanded: `https://${USERNAME}:${PASSWORD}/artifacts.io/Flask-1.1.2.tar.gz`.
  It is also okay to not give the auth part in the URL directly, PDM will ask for them when `-v/--verbose` is on.
- `${PROJECT_ROOT}` will be expanded with the absolute path of the project root, in POSIX style(i.e. forward slash `/`, even on Windows).
  For consistency, URLs that refer to a local path under `${PROJECT_ROOT}` must start with `file:///`(three slashes), e.g.
  `file:///${PROJECT_ROOT}/artifacts/Flask-1.1.2.tar.gz`.

Don't worry about credential leakage, the environment variables will be expanded when needed and kept untouched in the lock file.
