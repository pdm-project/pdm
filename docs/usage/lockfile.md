# Lock file

PDM installs packages exclusively from the existing lock file named `pdm.lock`. This file serves as the sole source of truth for installing dependencies. The lock file contains essential information such as:

- All packages and their versions
- The file names and hashes of the packages
- Optionally, the origin URLs to download the packages (See also: [Static URLs](#static-urls))
- The dependencies and markers of each package (See also: [Inherit the metadata from parents](#inherit-the-metadata-from-parents))

To create or overwrite the lock file, run [`pdm lock`](../reference/cli.md#lock), and it supports the same [update strategies](./dependency.md#about-update-strategy) as [`pdm add`](../reference/cli.md#add). In addition, the [`pdm install`](../reference/cli.md#install) and [`pdm add`](../reference/cli.md#add) commands will also automatically create the `pdm.lock` file.

??? NOTE "Should I add `pdm.lock` to version control?"

    It depends. If your goal is to make CI use the same dependency versions as local development and avoid unexpected failures, you should add the `pdm.lock` file to version control. Otherwise, if your project is a library and you want CI to mimic the installation on user site to ensure that the current version on PyPI doesn't break anything, then do not submit the `pdm.lock` file.

## Install the packages pinned in lock file

There are a few similar commands to do this job with slight differences:

- [`pdm sync`](../reference/cli.md#sync) installs packages from the lock file.
- [`pdm update`](../reference/cli.md#update) will update the lock file, then `pdm sync`.
- [`pdm install`](../reference/cli.md#install) will check the project file for changes, update the lock file if needed, then `pdm sync`.

`pdm sync` also has a few options to manage installed packages:

- `--clean`: will remove packages no longer in the lockfile
- `--clean-unselected` (or `--only-keep`): more thorough version of `--clean` that will also remove packages not in the groups specified by the `-G`, `-d`, and `--prod` options.
Note: by default, `pdm sync` selects all groups from the lockfile, so `--clean-unselected` is identical to `--clean` unless `-G`, `-d`, and `--prod` are used.


## Hashes in the lock file

By default, `pdm install` will check if the lock file matches the content of `pyproject.toml`, this is done by storing a content hash of `pyproject.toml` in the lock file.

To check if the hash in the lock file is up-to-date:

```bash
pdm lock --check
```

If you want to refresh the lock file without changing the dependencies, you can use the `--refresh` option:

```bash
pdm lock --refresh
```

This command also refreshes *all* file hashes recorded in the lock file.

## Specify another lock file to use

By default, PDM uses `pdm.lock` in the current directory. You can specify another lock file with the `-L/--lockfile` option or the `PDM_LOCKFILE` environment variable:

```bash
pdm install --lockfile my-lockfile.lock
```

This command installs packages from `my-lockfile.lock` instead of `pdm.lock`.

Alternate lock files are helpful when there exist conflicting dependencies for different environments. In this case, if you lock them as a whole, PDM will raise an error. So you have to [select a subset of dependency groups](./dependency.md#select-a-subset-of-dependency-groups-to-install) and lock them separately.

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

## Option to not write lock file

Sometimes you want to add or update dependencies without updating the lock file, or you don't want to generate `pdm.lock`, you can use the `--frozen-lockfile` option:

```bash
pdm add --frozen-lockfile flask
```

In this case, the lock file, if existing, will become read-only, no write operation will be performed on it.
However, dependency resolution step will still be performed if needed.

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

+++ 2.6.0

!!! warning "Deprecated in 2.17.0"
    See [Lock for specific platforms or Python versions](./lock-targets.md) for the new behavior.

By default, the generated lockfile is **cross-platform**, which means the current platform isn't taken into account when resolving the dependencies. The result lockfile will contain wheels and dependencies for all possible platforms and Python versions.
However, sometimes this will result in a wrong lockfile when a release doesn't contain all wheels.
To avoid this, you can tell PDM to create a lockfile that works for **this platform** only, trimming the wheels not relevant to the current platform.
This can be done by passing the `--strategy no_cross_platform` option to `pdm lock`:

```bash
pdm lock --strategy no_cross_platform
```

### Static URLs

+++ 2.8.0

By default, PDM only stores the filenames of the packages in the lockfile, which benefits the reusability across different package indexes.
However, if you want to store the static URLs of the packages in the lockfile, you can pass the `--strategy static_urls` option to `pdm lock`:

```bash
pdm lock --strategy static_urls
```

The settings will be saved and remembered for the same lockfile. You can also pass `--strategy no_static_urls` to disable it.

### Direct minimal versions

+++ 2.10.0

When it is enabled by passing `--strategy direct_minimal_versions`, dependencies specified in the `pyproject.toml` will be resolved to the minimal versions available, rather than the latest versions. This is useful when you want to test the compatibility of your project within a range of dependency versions.

For example, if you specified `flask>=2.0` in the `pyproject.toml`, `flask` will be resolved to version `2.0.0` if there is no other compatibility issue.

!!! NOTE
    Version constraints in package dependencies are not future-proof. If you resolve the dependencies to the minimal versions, there will likely be backwards-compatibility issues.
    For example, `flask==2.0.0` requires `werkzeug>=2.0`, but in fact, it can not work with `Werkzeug 3.0.0`, which is released 2 years after it.

### Inherit the metadata from parents

+++ 2.11.0

Previously, the `pdm lock` command would record package metadata as it is. When installing, PDM would start from the top requirements and traverse down to the leaf node of the dependency tree. It would then evaluate any marker it encounters against the current environment. If a marker is not satisfied, the package would be discarded. In other words, we need an additional "resolution" step in installation.

When the `inherit_metadata` strategy is enabled, PDM will inherit and merge environment markers from a package's ancestors. These markers are then encoded in the lockfile during locking, resulting in faster installations. This has been enabled by default from version `2.11.0`, to disable this strategy in the config, use `pdm config strategy.inherit_metadata false`.

### Exclude packages newer than specific date

+++ 2.13.0

You can exclude packages that are newer than a specified date by passing the `--exclude-newer` option to `pdm lock`. This is useful when you want to lock the dependencies to a specific date, for example, to ensure reproducibility of the build.

The date may be specified as a RFC 3339 timestamp (e.g., `2006-12-02T02:07:43Z`) or UTC date in the same format (e.g., `2006-12-02`).

```bash
pdm lock --exclude-newer 2024-01-01
```

!!! note
    The package index must support the `upload-time` field as specified in [PEP 700]. If the field is not present for a given distribution, the distribution will be treated as unavailable.

[PEP 700]: https://peps.python.org/pep-0700/

## Set acceptable format for locking or installing

If you want to control the format(binary/sdist) of the packages, you can set the env vars `PDM_NO_BINARY`, `PDM_ONLY_BINARY` and `PDM_PREFER_BINARY`.

Each env var is a comma-separated list of package name. You can set it to `:all:` to apply to all packages. For example:

```toml
# No binary for werkzeug will be locked nor used for installation
PDM_NO_BINARY=werkzeug pdm add flask
# Only binaries will be locked in the lock file
PDM_ONLY_BINARY=:all: pdm lock
# No binaries will be used for installation
PDM_NO_BINARY=:all: pdm install
# Prefer binary distributions and even if sdist with higher version is available
PDM_PREFER_BINARY=flask pdm install
```

You can also defined those values in your project `pyproject.toml` with the `no-binary`, `only-binary` and `prefer-binary` keys of the `tool.pdm.resolution` section.
They accept the same format as the environment variables and also support lists.

```toml
[tool.pdm.resolution]
# No binary for werkzeug and flask will be locked nor used for installation
no-binary = "werkzeug,flask"
# equivalent to
no-binary = ["werkzeug", "flask"]
# Only binaries will be locked in the lock file
only-binary = ":all:"
# Prefer binary distributions and even if sdist with higher version is available
prefer-binary = "flask"
```

!!! note
    Each environment variable takes precedence over its `pyproject.toml` alternative.

## Allow prerelease versions to be installed

Include the following setting in `pyproject.toml` to enable:

```toml
[tool.pdm.resolution]
allow-prereleases = true
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

## Export locked packages to alternative formats

You can export the `pdm.lock` file to other formats, which will simplify the CI flow or image building process. At present, only the `requirements.txt` format is supported.

```bash
pdm export -o requirements.txt
```

!!! TIP
    You can also run `pdm export` with a [`.pre-commit` hook](./advanced.md#hooks-for-pre-commit).
