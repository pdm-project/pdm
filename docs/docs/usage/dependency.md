# Manage Dependencies

PDM provides a bunch of handful commands to help manage your project and dependencies.
The following examples are run on Ubuntu 18.04, a few changes must be done if you are using Windows.

## Add dependencies

[`pdm add`](../reference/cli.md#add) can be followed by one or several dependencies, and the dependency specification is described in [PEP 508](https://www.python.org/dev/peps/pep-0508/).

Examples:

```bash
pdm add requests   # add requests
pdm add requests==2.25.1   # add requests with version constraint
pdm add requests[socks]   # add requests with extra dependency
pdm add "flask>=1.0" flask-sqlalchemy   # add multiple dependencies with different specifiers
```

PDM also allows extra dependency groups by providing `-G/--group <name>` option, and those dependencies will go to
`[project.optional-dependencies.<name>]` table in the project file, respectively.

You can reference other optional groups in `optional-dependencies`, even before the package is uploaded:

```toml
[project]
name = "foo"
version = "0.1.0"

[project.optional-dependencies]
socks = ["pysocks"]
jwt = ["pyjwt"]
all = ["foo[socks,jwt]"]
```

After that, dependencies and sub-dependencies will be resolved properly and installed for you, you can view `pdm.lock` to see the resolved result of all dependencies.

### Local dependencies

Local packages can be added with their paths. The path can be a file or a directory:

```bash
pdm add ./sub-package
pdm add ./first-1.0.0-py2.py3-none-any.whl
```

The paths MUST start with a `.`, otherwise it will be recognized as a normal named requirement. The local dependencies will be written to the `pyproject.toml` file with the URL format:

```toml
[project]
dependencies = [
    "sub-package @ file:///${PROJECT_ROOT}/sub-package",
    "first @ file:///${PROJECT_ROOT}/first-1.0.0-py2.py3-none-any.whl",
]
```

??? note "Using other build backends"
    If you are using `hatchling` instead of the pdm backend, the URLs would be as follows:

    ```
    sub-package @ {root:uri}/sub-package
    first @ {root:uri}/first-1.0.0-py2.py3-none-any.whl
    ```
    Other backends doesn't support encoding relative paths in the URL and will write the absolute path instead.

### URL dependencies

PDM also supports downloading and installing packages directly from a web address.

Examples:

```bash
# Install gzipped package from a plain URL
pdm add "https://github.com/numpy/numpy/releases/download/v1.20.0/numpy-1.20.0.tar.gz"
# Install wheel from a plain URL
pdm add "https://github.com/explosion/spacy-models/releases/download/en_core_web_trf-3.5.0/en_core_web_trf-3.5.0-py3-none-any.whl"
```

### VCS dependencies

You can also install from a git repository url or other version control systems. The following are supported:

- Git: `git`
- Mercurial: `hg`
- Subversion: `svn`
- Bazaar: `bzr`

The URL should be like: `{vcs}+{url}@{rev}`

Examples:

```bash
# Install pip repo on tag `22.0`
pdm add "git+https://github.com/pypa/pip.git@22.0"
# Provide credentials in the URL
pdm add "git+https://username:password@github.com/username/private-repo.git@master"
# Give a name to the dependency
pdm add "pip @ git+https://github.com/pypa/pip.git@22.0"
# Or use the #egg fragment
pdm add "git+https://github.com/pypa/pip.git@22.0#egg=pip"
# Install from a subdirectory
pdm add "git+https://github.com/owner/repo.git@master#egg=pkg&subdirectory=subpackage"
```

### Hide credentials in the URL

You can hide the credentials in the URL by using the `${ENV_VAR}` variable syntax:

```toml
[project]
dependencies = [
  "mypackage @ git+http://${VCS_USER}:${VCS_PASSWD}@test.git.com/test/mypackage.git@master"
]
```

These variables will be read from the environment variables when installing the project.

### Add development only dependencies

_New in 1.5.0_

PDM also supports defining groups of dependencies that are useful for development,
e.g. some for testing and others for linting. We usually don't want these dependencies appear in the distribution's metadata
so using `optional-dependencies` is probably not a good idea. We can define them as development dependencies:

```bash
pdm add -dG test pytest
```

This will result in a pyproject.toml as following:

```toml
[tool.pdm.dev-dependencies]
test = ["pytest"]
```

You can have several groups of development only dependencies. Unlike `optional-dependencies`, they won't appear in the package distribution metadata such as `PKG-INFO` or `METADATA`.
The package index won't be aware of these dependencies. The schema is similar to that of `optional-dependencies`, except that it is in `tool.pdm` table.

```toml
[tool.pdm.dev-dependencies]
lint = [
    "flake8",
    "black"
]
test = ["pytest", "pytest-cov"]
doc = ["mkdocs"]
```
For backward-compatibility, if only `-d` or `--dev` is specified, dependencies will go to `dev` group under `[tool.pdm.dev-dependencies]` by default.

!!! NOTE
    The same group name MUST NOT appear in both `[tool.pdm.dev-dependencies]` and `[project.optional-dependencies]`.

### Editable dependencies

**Local directories** and **VCS dependencies** can be installed in [editable mode](https://pip.pypa.io/en/stable/cli/pip_install/#editable-installs). If you are familiar with `pip`, it is just like `pip install -e <package>`. **Editable packages are allowed only in development dependencies**:

!!! NOTE
    Editable installs are only allowed in the `dev` dependency group. Other groups, including the default, will fail with a `[PdmUsageError]`.

```bash
# A relative path to the directory
pdm add -e ./sub-package --dev
# A file URL to a local directory
pdm add -e file:///path/to/sub-package --dev
# A VCS URL
pdm add -e git+https://github.com/pallets/click.git@main#egg=click --dev
```

### Save version specifiers

If the package is given without a version specifier like `pdm add requests`. PDM provides three different behaviors of what version
specifier is saved for the dependency, which is given by `--save-<strategy>`(Assume `2.21.0` is the latest version that can be found
for the dependency):

- `minimum`: Save the minimum version specifier: `>=2.21.0` (default).
- `compatible`: Save the compatible version specifier: `>=2.21.0,<3.0.0`.
- `exact`: Save the exact version specifier: `==2.21.0`.
- `wildcard`: Don't constrain version and leave the specifier to be wildcard: `*`.

### Add prereleases

One can give `--pre/--prerelease` option to [`pdm add`](../reference/cli.md#add) so that prereleases are allowed to be pinned for the given packages.

## Update existing dependencies

To update all dependencies in the lock file:

```bash
pdm update
```

To update the specified package(s):

```bash
pdm update requests
```

To update multiple groups of dependencies:

```bash
pdm update -G security -G http
```

Or using comma-separated list:

```bash
pdm update -G "security,http"
```

To update a given package in the specified group:

```bash
pdm update -G security cryptography
```

If the group is not given, PDM will search for the requirement in the default dependencies set and raises an error if none is found.

To update packages in development dependencies:

```bash
# Update all default + dev-dependencies
pdm update -d
# Update a package in the specified group of dev-dependencies
pdm update -dG test pytest
```

### About update strategy

Similarly, PDM also provides 3 different behaviors of updating dependencies and sub-dependencies，
which is given by `--update-<strategy>` option:

- `reuse`: Keep all locked dependencies except for those given in the command line (default).
- `reuse-installed`: Try to reuse the versions installed in the working set. **This will also affect the packages requested in the command line**.
- `eager`: Try to lock a newer version of the packages in command line and their recursive sub-dependencies and keep other dependencies as they are.
- `all`: Update all dependencies and sub-dependencies.

### Update packages to the versions that break the version specifiers

One can give `-u/--unconstrained` to tell PDM to ignore the version specifiers in the `pyproject.toml`.
This works similarly to the `yarn upgrade -L/--latest` command. Besides, [`pdm update`](../reference/cli.md#update) also supports the
`--pre/--prerelease` option.

## Remove existing dependencies

To remove existing dependencies from project file and the library directory:

```bash
# Remove requests from the default dependencies
pdm remove requests
# Remove h11 from the 'web' group of optional-dependencies
pdm remove -G web h11
# Remove pytest-cov from the `test` group of dev-dependencies
pdm remove -dG test pytest-cov
```

## Install the packages pinned in lock file

There are a few similar commands to do this job with slight differences:

- [`pdm sync`](../reference/cli.md#sync) installs packages from the lock file.
- [`pdm update`](../reference/cli.md#update) will update the lock file, then `sync`.
- [`pdm install`](../reference/cli.md#install) will check the project file for changes, update the lock file if needed, then `sync`.

`sync` also has a few options to manage installed packages:

- `--clean`: will remove packages no longer in the lockfile
- `--only-keep`: only selected packages (using options like `-G` or `--prod`) will be kept.

## Specify the lockfile to use

You can specify another lockfile than the default [`pdm lock`](../reference/cli.md#lock) by using the `-L/--lockfile <filepath>` option or the `PDM_LOCKFILE` environment variable.

## Select a subset of dependency groups to be installed or locked

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
| `pdm install`                   | install all groups locked in the lockfile                            |                           |
| `pdm install -G extra1`         | install prod deps, dev deps, and "extra1" optional group             |                           |
| `pdm install -G dev1`           | install prod deps and only "dev1" dev group                          |                           |
| `pdm install -G:all`            | install prod deps, dev deps and "extra1", "extra2" optional groups   |                           |
| `pdm install -G extra1 -G dev1` | install prod deps, "extra1" optional group and only "dev1" dev group |                           |
| `pdm install --prod`            | install prod only                                                    |                           |
| `pdm install --prod -G extra1`  | install prod deps and "extra1" optional                              |                           |
| `pdm install --prod -G dev1`    | Fail, `--prod` can't be given with dev dependencies                  | Leave the `--prod` option |

**All** development dependencies are included as long as `--prod` is not passed and `-G` doesn't specify any dev groups.

Besides, if you don't want the root project to be installed, add `--no-self` option, and `--no-editable` can be used when you want all packages to be installed in non-editable versions.

You may also use the pdm lock command with these options to lock only the specified groups, which will be recorded in the `[metadata]` table of the lock file. If no `--group/--prod/--dev/--no-default` option is specified, `pdm sync` and `pdm update` will operate using the groups in the lockfile. However, if any groups that are not included in the lockfile are given as arguments to the commands, PDM will raise an error.

This feature is especially valuable when managing multiple lockfiles, where each may have different versions of the same package pinned. To switch between lockfiles, you can use the `--lockfile/-L` option.

For a realistic example, your project depends on a release version of `werkzeug` and you may want to work with a local in-development copy of it when developing. You can add the following to your `pyproject.toml`:

```toml
[project]
requires-python = ">=3.7"
dependencies = ["werkzeug"]

[tool.pdm.dev-dependencies]
dev = ["werkzeug @ file:///${PROJECT_ROOT}/dev/werkzeug"]
```

Then, run `pdm lock` with different options to generate lockfiles for different purposes:

```bash
# Lock default + dev, write to pdm.lock
# with the local copy of werkzeug pinned.
pdm lock
# Lock default, write to pdm.prod.lock
# with the release version of werkzeug pinned.
pdm lock --prod -L pdm.prod.lock
```

Check the `metadata.groups` field in the lockfile to see which groups are included.

## Lock strategies

Currently, we support three flags to control the locking behavior: `cross_platform`, `static_urls` and `direct_minimal_versions`, with the meanings as follows.
You can pass one or more flags to `pdm lock` by `--strategy/-S` option, either by giving a comma-separated list or by passing the option multiple times.
Both of these commands function in the same way:

```bash
pdm lock -S cross_platform,static_urls
pdm lock -S cross_platform -S static_urls
```

The flags will be encoded in the lockfile and get read when you run `pdm lock` next time. But you can disable flags by prefixing the flag name with `no_`:

```bash
pdm lock -S no_cross_platform
```

This command makes the lockfile not cross-platform.

### Cross platform

_New in version 2.6.0_

By default, the generated lockfile is **cross-platform**, which means the current platform isn't taken into account when resolving the dependencies. The result lockfile will contain wheels and dependencies for all possible platforms and Python versions.
However, sometimes this will result in a wrong lockfile when a release doesn't contain all wheels. To avoid this, you can tell PDM
to create a lockfile that works for **this platform** only, trimming the wheels not relevant to the current platform. This can be done by passing the `--strategy no_cross_platform` option to `pdm lock`:

```bash
pdm lock --strategy no_cross_platform
```

### Static URLs

_New in version 2.8.0_

By default, PDM only stores the filenames of the packages in the lockfile, which benefits the reusability across different package indexes.
However, if you want to store the static URLs of the packages in the lockfile, you can pass the `--strategy static_urls` option to `pdm lock`:

```bash
pdm lock --strategy static_urls
```

The settings will be saved and remembered for the same lockfile. You can also pass `--strategy no_static_urls` to disable it.

### Direct minimal versions

_New in version 2.10.0_

When it is enabled by passing `--strategy direct_minimal_versions`, dependencies specified in the `pyproject.toml` will be resolved to the minimal versions available, rather than the latest versions. This is useful when you want to test the compatibility of your project within a range of dependency versions.

For example, if you specified `flask>=2.0` in the `pyproject.toml`, `flask` will be resolved to version `2.0.0` if there is no other compatibility issue.

!!! NOTE
    Version constraints in package dependencies are not future-proof. If you resolve the dependencies to the minimal versions, there will likely be backwards-compatibility issues.
    For example, `flask==2.0.0` requires `werkzeug>=2.0`, but in fact, it can not work with `Werkzeug 3.0.0`, which is released 2 years after it.

### Inherit the metadata from parents

_New in version 2.11.0_

Previously, the `pdm lock` command would record package metadata as it is. When installing, PDM would start from the top requirements and traverse down to the leaf node of the dependency tree. It would then evaluate any marker it encounters against the current environment. If a marker is not satisfied, the package would be discarded. In other words, we need an additional "resolution" step in installation.

When the `inherit_metadata` strategy is enabled, PDM will inherit and merge environment markers from a package's ancestors. These markers are then encoded in the lockfile during locking, resulting in faster installations. This has been enabled by default from version `2.11.0`, to disable this strategy in the config, use `pdm config strategy.inherit_metadata false`.

## Show what packages are installed

Similar to `pip list`, you can list all packages installed in the packages directory:

```bash
pdm list
```

### Include and exclude groups

By default, all packages installed in the working set will be listed. You can specify which groups to be listed
by `--include/--exclude` options, and `include` has a higher priority than `exclude`.

```bash
pdm list --include dev
pdm list --exclude test
```

There is a special group `:sub`, when included, all transitive dependencies will also be shown. It is included by default.

You can also pass `--resolve` to `pdm list`, which will show the packages resolved in `pdm.lock`, rather than installed in the working set.

### Change the output fields and format

By default, name, version and location will be shown in the list output, you can view more fields or specify the order of fields by `--fields` option:

```bash
pdm list --fields name,licenses,version
```

For all supported fields, please refer to the [CLI reference](../reference/cli.md#list_1).

Also, you can specify the output format other than the default table output. The supported formats and options are `--csv`, `--json`, `--markdown` and `--freeze`.

### Show the dependency tree

Or show a dependency tree by:

```
$ pdm list --tree
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

Note that `--fields` option doesn't work with `--tree`.

### Filter packages by patterns

You can also limit the packages to show by passing the patterns to `pdm list`:

```bash
pdm list flask-* requests-*
```

??? warning "Be careful with the shell expansion"
    In most shells, the wildcard `*` will be expanded if there are matching files under the current directory.
    To avoid getting unexpected results, you can wrap the patterns with single quotes: `pdm list 'flask-*' 'requests-*'`.

In `--tree` mode, only the subtree of the matched packages will be displayed. This can be used to achieve the same purpose as `pnpm why`, which is to show why a specific package is required.

```bash
$ pdm list --tree --reverse certifi
certifi 2023.7.22
└── requests 2.31.0 [ requires: >=2017.4.17 ]
    └── cachecontrol[filecache] 0.13.1 [ requires: >=2.16.0 ]
```
## Allow prerelease versions to be installed

Include the following setting in `pyproject.toml` to enable:

```toml
[tool.pdm.resolution]
allow-prereleases = true
```

## Set acceptable format for locking or installing

If you want to control the format(binary/sdist) of the packages, you can set the env vars `PDM_NO_BINARY` and `PDM_ONLY_BINARY`.

Each env var is a comma-separated list of package name. You can set it to `:all:` to apply to all packages. For example:

```
# No binary for werkzeug will be locked nor used for installation
PDM_NO_BINARY=werkzeug pdm add flask
# Only binaries will be locked in the lock file
PDM_ONLY_BINARY=:all: pdm lock
# No binaries will be used for installation
PDM_NO_BINARY=:all: pdm install
# Prefer binary distributions and even if sdist with higher version is available
PDM_PREFER_BINARY=flask pdm install
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
To fix this, you could loosen the dependency version constraints in pyproject.toml. If that is not possible, you could also override the resolved version in `[tool.pdm.resolution.overrides]` table.
```

You can either change to a lower version of `django` or remove the upper bound of `asgiref`. But if it is not eligible for your project, you can try [overriding the resolved package versions](./config.md#override-the-resolved-package-versions) or even [don't lock that specific package](./config.md#exclude-specific-packages-and-their-dependencies-from-the-lock-file) in `pyproject.toml`.

## Manage global project

Sometimes users may want to keep track of the dependencies of global Python interpreter as well.
It is easy to do so with PDM, via `-g/--global` option which is supported by most subcommands.

If the option is passed, `<CONFIG_ROOT>/global-project` will be used as the project directory, which is
almost the same as normal project except that `pyproject.toml` will be created automatically for you
and it doesn't support build features. The idea is taken from Haskell's [stack](https://docs.haskellstack.org).

However, unlike `stack`, by default, PDM won't use global project automatically if a local project is not found.
Users should pass `-g/--global` explicitly to activate it, since it is not very pleasing if packages go to a wrong place.
But PDM also leave the decision to users, just set the config `global_project.fallback` to `true`.

By default, when `pdm` uses global project implicitly the following message is printed: `Project is not found, fallback to the global project`. To disable this message set the config `global_project.fallback_verbose` to `false`.

If you want global project to track another project file other than `<CONFIG_ROOT>/global-project`, you can provide the
project path via `-p/--project <path>` option. Especially if you pass `--global --project .`, PDM will install the dependencies
of the current project into the global Python.

!!! warning
    Be careful with `remove` and `sync --clean/--pure` commands when global project is used, because it may remove packages installed in your system Python.

## Export locked packages to alternative formats

You can also export [`pdm lock`](../reference/cli.md#lock) to other formats, to ease the CI flow or image building process. Currently,
only `requirements.txt` format is supported:

```bash
pdm export -o requirements.txt
```

!!! NOTE
    You can also run `pdm export` with a [`.pre-commit` hook](./advanced.md#hooks-for-pre-commit).
