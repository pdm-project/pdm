# Lock file

PDM synchronizes dependencies using a locked resolution, normally stored in `pdm.lock`. Depending on the command, PDM can reuse that resolution or create a new one before installing packages. The lock file contains essential information such as:

- All packages and their versions
- The file names and hashes of the packages
- Optionally, the origin URLs to download the packages (See also: [Static URLs](#static-urls))
- The dependencies and markers of each package (See also: [Inherit the metadata from parents](#inherit-the-metadata-from-parents))

To create or overwrite the lock file, run [`pdm lock`](../reference/cli.md#lock), and it supports the same [update strategies](./dependency.md#about-update-strategy) as [`pdm add`](../reference/cli.md#add). In addition, the [`pdm install`](../reference/cli.md#install) and [`pdm add`](../reference/cli.md#add) commands will also automatically create the `pdm.lock` file.

??? note "Should I add `pdm.lock` to version control?"

    It depends. If your goal is to make CI use the same dependency versions as local development and avoid unexpected failures, you should add the `pdm.lock` file to version control. Otherwise, if your project is a library and you want CI to mimic the installation on user site to ensure that the current version on PyPI doesn't break anything, then do not submit the `pdm.lock` file.

## Command effects

There are three separate pieces of project state:

1. **`pyproject.toml` declares requirements.** It records the packages you request, acceptable version ranges, dependency groups, and other resolution inputs. It is not a list of the exact versions currently installed.
2. **The lock file records a resolution.** It pins versions and artifacts for the groups included when locking. It can contain packages for several Python versions or platforms, not all of which will be installed in the current environment.
3. **The environment contains installed packages.** It can lag behind the lock file or contain packages that are not in it. Installing a selected set of dependencies does not, by default, remove everything else.

The following table describes normal successful invocations, without flags such as `--dry-run` or `--frozen-lockfile`. Commands operate in stages: an installation error can occur after the lock file has already been updated.

| Command | Requirements and group arguments | `pyproject.toml` | Lock file | Installed packages |
| --- | --- | --- | --- | --- |
| [`pdm add`](../reference/cli.md#add) | Add or change the requested requirements in one target group (`default` unless selected otherwise). | Writes the target group's declarations. | Resolves the previously locked groups plus the target group. A new lock includes `default` and the target group. | Installs the target group's dependencies; keeps unrelated packages. |
| [`pdm lock`](../reference/cli.md#lock) | Resolve the selected groups, or reuse the recorded group selection when none is specified. | Reads, but does not change, declarations. | Creates or updates the resolution; may select new versions according to the update strategy. | Does not install or remove packages. |
| [`pdm install`](../reference/cli.md#install) | Install selected groups. A new lock uses the requested groups; refreshing an existing lock preserves its group selection. | Reads, but does not change, declarations. | Creates a missing lock or updates an outdated one, reusing compatible pins where possible. A fresh lock is reused. | Installs selected dependencies; keeps unrelated packages. |
| [`pdm sync`](../reference/cli.md#sync) | Select groups already included in an existing lock. | Reads group selections without changing declarations. | Reads the locked resolution without creating or updating it. | Installs selected pinned versions; keeps unrelated packages unless a cleanup option is used. |
| [`pdm update`](../reference/cli.md#update) | Update named packages or the selected groups, using the existing constraints and update strategy. | Keeps declarations unless `--unconstrained` is used. | Updates the resolution while preserving the locked groups. | Installs the selected dependencies; keeps unrelated packages. |

`pdm update` does not add new dependencies: use `pdm add` for that. Named update targets can be declared requirements or transitive packages already in the lock. For a requirement declared outside the default group, specify its group with `-G`. Without package names, the selected groups determine the update targets.

When the project is a distributable package and the `default` group is selected, synchronization also installs the project itself unless `--no-self` is given. A project configured with `distribution = false` is not installed itself.

### Select groups for locking and installation

Groups declared in `pyproject.toml`, groups included in the lock file, and groups selected for installation are distinct sets. The native `pdm.lock` format records the locked set in `metadata.groups`.

- For `lock`, `install`, `sync`, and `update`, omitting group-selection options reuses the recorded groups that still exist in the project. Running plain `pdm lock` does not automatically add every newly declared group.
- Without a recorded selection, the default selection includes `default` and development groups, but not optional groups. `pdm add` instead starts a new lock with `default` and its target group.
- `-G:all` explicitly selects all declared groups. `--prod` excludes development groups. See [dependency group selection](./dependency.md#select-a-subset-of-dependency-groups-to-install) for combinations with `-G`, `--without`, and `--no-default`.
- Selecting a group for installation does not by itself add that group to an existing lock file. `install`, `sync`, or `update` can report `Requested groups not in lockfile` even when the group is declared in `pyproject.toml`.

For example, if a lock was created with `pdm lock --prod`, and you later want to install a declared `docs` group, first include the desired groups in the lock:

```bash
# Resolve all declared groups, including docs and development groups.
pdm lock -G:all
# Install the requested group selection from that lock.
pdm install -G docs
```

If you intentionally maintain a smaller lock, use explicit group-selection options instead of `-G:all`. A stale-lock refresh by `pdm install` preserves the previously locked groups; it is not a replacement for selecting new groups with `pdm lock`.

Lock strategy flags, such as `static_urls`, are also persisted in `metadata.strategy` and reused by later locking operations. This is separate from the [update strategy](./dependency.md#about-update-strategy), which controls which existing versions the resolver tries to reuse. See [lock strategies](#lock-strategies) for changing the stored flags. These metadata field names describe the native `pdm` format; see [lock file formats](#change-lock-file-format) for the alternative `pylock` format.

### Keep or clean installed packages

Ordinary `install`, `sync`, `add`, and `update` invocations do not remove unrelated installed packages. For example, removing a requirement from `pyproject.toml` and running `pdm install` can update the lock without uninstalling that now-unneeded package.

Use `pdm sync` when you want cleanup:

- `--clean` removes eligible installed packages absent from the **entire lock file**. Packages locked in an unselected group are kept.
- `--clean-unselected` (also spelled `--only-keep`) additionally removes eligible packages outside the **selected groups**.

By default, `sync` selects the recorded locked groups, so the two cleanup modes differ when you select a subset, such as `pdm sync --prod --clean-unselected`. Installer-managed packages are protected from removal.

### Control resolution, writes, and installation separately

- `pdm add --no-sync` and `pdm update --no-sync` leave installed packages unchanged while updating the project/lock state described above.
- `pdm lock --check` checks freshness and exits without installing packages. `pdm install --check` refuses a missing or outdated lock, but **still installs** the selected dependencies when the lock is fresh.
- `pdm lock --refresh` refreshes lock input metadata and artifact hashes without changing the pinned versions. It does not resolve a new set of dependency versions.
- `--frozen-lockfile` prevents **writing** the lock file; it does not prohibit resolution. For example, `pdm install --frozen-lockfile` can resolve and install dependencies without creating a lock file. `pdm add --frozen-lockfile --no-sync` can change declarations without resolving or installing them.

Use `install --check`, not `--frozen-lockfile` alone, when installation must fail if the committed lock is missing or outdated. See [freshness checks](#lock-file-freshness) below for what makes a lock outdated.

## Lock file freshness

!!! tip
    Changed in 2.28.1.

Lock files that do not already contain canonical inputs use the legacy content hash by default. Canonical lock inputs can be enabled in `pyproject.toml`:

```toml
[tool.pdm.resolution]
lock_inputs = true
```

With canonical lock inputs enabled, formatting and dependency ordering changes do not invalidate the lock file. If only a version specifier changes, the lock file remains valid when all matching locked versions still satisfy the new specifier.

Local file and directory dependencies are treated as mutable inputs. PDM fingerprints local files and records static project metadata for local directories recursively. A local project with resolution-relevant dynamic metadata is conservatively treated as out of date because its dependencies cannot be validated without invoking the build backend.

Lock files with canonical inputs omit the legacy content hash. Once a lock file contains canonical inputs, PDM keeps using and writing them even if the setting is later removed. If a lock file does not contain canonical inputs, setting `lock_inputs = true` marks it as out of date until `pdm lock` records them; without the setting, PDM falls back to the content hash. Present but invalid canonical inputs are always treated as out of date.

To check if the lock file is up-to-date:

```bash
pdm lock --check
```

If you want to refresh the lock file without changing the dependencies, you can use the `--refresh` option:

```bash
pdm lock --refresh
```

This command also refreshes _all_ file hashes recorded in the lock file.

## Change lock file format

PDM supports two lock file formats: `pdm`(default file name is `pdm.lock`) and `pylock`(default file name is `pylock.toml`). The default format is `pdm`.

!!! tip
    Added in 2.25.0.

    Added experimental support for the [PEP 751](https://packaging.python.org/en/latest/specifications/pylock-toml/#pylock-toml-spec) pylock file format. It's a standard lock file format designed to minimize discrepancies among different Python package managers, enhancing interoperability with other tools. It is set to become the default in a future version of PDM. Read the specification for more details.

You can switch to the `pylock` format with `pdm config` command:

```bash
pdm config lock.format pylock
```

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

[dependency-groups]
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

!!! tip
    Added in 2.6.0.

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

!!! tip
    Added in 2.8.0.

By default, PDM only stores the filenames of the packages in the lockfile, which benefits the reusability across different package indexes.
However, if you want to store the static URLs of the packages in the lockfile, you can pass the `--strategy static_urls` option to `pdm lock`:

```bash
pdm lock --strategy static_urls
```

The settings will be saved and remembered for the same lockfile. You can also pass `--strategy no_static_urls` to disable it.

### Direct minimal versions

!!! tip
    Added in 2.10.0.

When it is enabled by passing `--strategy direct_minimal_versions`, dependencies specified in the `pyproject.toml` will be resolved to the minimal versions available, rather than the latest versions. This is useful when you want to test the compatibility of your project within a range of dependency versions.

For example, if you specified `flask>=2.0` in the `pyproject.toml`, `flask` will be resolved to version `2.0.0` if there is no other compatibility issue.

!!! note
    Version constraints in package dependencies are not future-proof. If you resolve the dependencies to the minimal versions, there will likely be backwards-compatibility issues.
    For example, `flask==2.0.0` requires `werkzeug>=2.0`, but in fact, it can not work with `Werkzeug 3.0.0`, which is released 2 years after it.

### Inherit the metadata from parents

!!! tip
    Added in 2.11.0.

Previously, the `pdm lock` command would record package metadata as it is. When installing, PDM would start from the top requirements and traverse down to the leaf node of the dependency tree. It would then evaluate any marker it encounters against the current environment. If a marker is not satisfied, the package would be discarded. In other words, we need an additional "resolution" step in installation.

When the `inherit_metadata` strategy is enabled, PDM will inherit and merge environment markers from a package's ancestors. These markers are then encoded in the lockfile during locking, resulting in faster installations. This has been enabled by default from version `2.11.0`, to disable this strategy in the config, use `pdm config strategy.inherit_metadata false`.

### Exclude packages newer than specific date

!!! tip
    Added in 2.13.0.

You can exclude packages that are newer than a specified date by passing the `--exclude-newer` option to `pdm lock`. This is useful when you want to lock the dependencies to a specific date, for example, to ensure reproducibility of the build.

The value may be specified as:

- A RFC 3339 timestamp, for example `2006-12-02T02:07:43Z`
- A UTC date, for example `2006-12-02`
- A relative duration in the format `N{d|h|w}`, for example `7d`, `12h`, or `3w`

Relative durations are calculated from the current UTC time.

```bash
pdm lock --exclude-newer 2024-01-01
pdm lock --exclude-newer 7d
```

You can also configure the default value with `strategy.exclude-newer`:

```bash
pdm config strategy.exclude-newer 7d
```

!!! tip
    Added in 2.26.9.

`exclude-newer` may also be set in the `pyproject.toml` file under the `[tool.pdm.resolution]` table:

```toml
[tool.pdm.resolution]
exclude-newer = "7d"
```

Package-specific values can override the global cutoff:

```toml
[tool.pdm.resolution]
exclude-newer = "7d"

[tool.pdm.resolution.exclude-newer-override]
mypackage = false
anotherpackage = "3d"
```

An override accepts the same date, timestamp, and duration formats as `exclude-newer`. Set it to `false` to disable the
cutoff for that package. Package names are normalized before matching, and package-specific values take precedence
over the global cutoff. Overrides may also be supplied on the command line:

```bash
pdm lock --exclude-newer 7d --exclude-newer-override mypackage=false anotherpackage=3d
```

Command-line overrides take precedence over entries for the same package in `exclude-newer-override`.

The precedence is: the `--exclude-newer` command line option, then `[tool.pdm.resolution]` in `pyproject.toml`, then `strategy.exclude-newer` in PDM config.

!!! note
    The package index must support the `upload-time` field as specified in [PEP 700]. If the field is not present for
    a given distribution, the distribution will be treated as unavailable unless its cutoff is disabled with an
    `exclude-newer-override` value of `false`.

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

You can either change to a lower version of `django` or remove the upper bound of `asgiref`. But if it is not eligible for your project, you can override the resolved version in `[tool.pdm.resolution.overrides]` or even [don't lock that specific package](./config.md#exclude-specific-packages-and-their-dependencies-from-the-lock-file) in `pyproject.toml`.

## Export locked packages to alternative formats

You can export the `pdm.lock` file to other formats, which will simplify the CI flow or image building process. At present, only the `requirements.txt` format is supported.

```bash
pdm export -o requirements.txt
```

!!! tip
    You can also run `pdm export` with a [`.pre-commit` hook](./advanced.md#hooks-for-pre-commit).

!!! tip
    Added in 2.24.0.

Additionally, PDM supports exporting to `pylock.toml` format as defined by [PEP 751](https://packaging.python.org/en/latest/specifications/pylock-toml/#pylock-toml-spec). The following command will convert your lock file to a PEP 751 compatible format:

```bash
pdm export -f pylock -o pylock.toml
```
