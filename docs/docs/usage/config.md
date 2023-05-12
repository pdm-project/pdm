# Configure the Project

PDM's `config` command works just like `git config`, except that `--list` isn't needed to
show configurations.

Show the current configurations:

```bash
pdm config
```

Get one single configuration:

```bash
pdm config pypi.url
```

Change a configuration value and store in home configuration:

```bash
pdm config pypi.url "https://test.pypi.org/simple"
```

By default, the configuration are changed globally, if you want to make the config seen by this project only, add a `--local` flag:

```bash
pdm config --local pypi.url "https://test.pypi.org/simple"
```

Any local configurations will be stored in `pdm.toml` under the project root directory.

## Configuration files

The configuration files are searched in the following order:

1. `<PROJECT_ROOT>/pdm.toml` - The project configuration
2. `<CONFIG_ROOT>/config.toml` - The home configuration
3. `<SITE_CONFIG_ROOT>/config.toml` - The site configuration

where `<CONFIG_ROOT>` is:

- `$XDG_CONFIG_HOME/pdm` (`~/.config/pdm` in most cases) on Linux as defined by [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- `~/Library/Preference/pdm` on MacOS as defined by [Apple File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- `%USERPROFILE%\AppData\Local\pdm` on Windows as defined in [Known folders](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders)

and `<SITE_CONFIG_ROOT>` is:

- `$XDG_CONFIG_DIRS/pdm` (`/etc/xdg/pdm` in most cases) on Linux as defined by [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- `/Library/Preference/pdm` on MacOS as defined by [Apple File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- `C:\ProgramData\pdm\pdm` on Windows as defined in [Known folders](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders)

If `-g/--global` option is used, the first item will be replaced by `<CONFIG_ROOT>/global-project/pdm.toml`.

You can find all available configuration items in [Configuration Page](../reference/configuration.md).

## Allow prereleases in resolution result

By default, `pdm`'s dependency resolver will ignore prereleases unless there are no stable versions for the given version range of a dependency. This behavior can be changed by setting `allow_prereleases` to `true` in `[tool.pdm]` table:

```toml
[tool.pdm]
allow_prereleases = true
```

## Configure the package indexes

You can tell PDM where to to find the packages by either specifying sources in the `pyproject.toml` or via `pypi.*` configurations.

Add sources in `pyproject.toml`:

```toml
[[tool.pdm.source]]
name = "private"
url = "https://private.pypi.org/simple"
verify_ssl = true
```

Change the default index via `pdm config`:

```bash
pdm config pypi.url "https://test.pypi.org/simple"
```

Add extra indexes via `pdm config`:

```bash
pdm config pypi.extra.url "https://extra.pypi.org/simple"
```

The available configuration options are:

- `url`: The URL of the index
- `verify_ssl`: (Optional)Whether to verify SSL certificates, default to true
- `username`: (Optional)The username for the index
- `password`: (Optional)The password for the index
- `type`: (Optional) index or find_links, default to index

??? note "About the source types"
    By default, all sources are [PEP 503](https://www.python.org/dev/peps/pep-0503/) style "indexes" like pip's `--index-url` and `--extra-index-url`, however, you can set the type to `find_links` which contains files or links to be looked for directly. See [this answer](https://stackoverflow.com/a/46651848) for the difference between the two types.

These configurations are read in the following order to build the final source list:

- `pypi.url`, if `pypi` doesn't appear in the `name` field of any source in `pyproject.toml`
- Sources in `pyproject.toml`
- `pypi.<name>.url` in PDM config.

You can set `pypi.ignore_stored_index` to `true` to disable all indexes from the PDM config and only use those specified in `pyproject.toml`.

!!! TIP "Disable the default PyPI index"
    If you want to omit the default PyPI index, just set the source name to `pypi` and that source will **replace** it.

    ```toml
    [[tool.pdm.source]]
    url = "https://private.pypi.org/simple"
    verify_ssl = true
    name = "pypi"
    ```

??? note "Indexes in `pyproject.toml` or config"
    When you want to share the indexes with other people who are going to use the project, you should add them in `pyproject.toml`. For example, some packages only exist in a private index and can't be installed if someone doesn't configure the index.
    Otherwise, store them in the local config which won't be seen by others.

### Respect the order of the sources

By default, all sources are considered equal, packages from them are sorted by the version and wheel tags, the most matching one with the highest version is selected.

In some cases you may want to return packages from the preferred source, and search for others if they are missing from the former source. PDM supports this by reading the configuration `respect-source-order`:

```toml
[tool.pdm.resolution]
respect-source-order = true
```

### Store credentials with the index

You can specify credentials in the URL with `${ENV_VAR}` variable expansion and these variables will be read from the environment variables:

```toml
[[tool.pdm.source]]
name = "private"
url = "https://${PRIVATE_PYPI_USERNAME}:${PRIVATE_PYPI_PASSWORD}/private.pypi.org/simple"
```

### Index configuration merging

Index configurations are merged with the `name` field of `[[tool.pdm.source]]` table or `pypi.<name>` key in the config file.
This enables you to store the url and credentials separately, to avoid secrets being exposed in the source control.
For example, if you have the following configuration:

```toml
[[tool.pdm.source]]
name = "private"
url = "https://private.pypi.org/simple"
```

You can store the credentials in the config file:

```bash
pdm config pypi.private.username "foo"
pdm config pypi.private.password "bar"
```

PDM can retrieve the configurations for `private` index from both places.

If the index requires a username and password, but they can't be found from the environment variables nor config file, PDM will prompt you to enter them. Or, if `keyring` is installed, it will be used as the credential store. PDM can use the `keyring` from either the installed package or the CLI.

## Central installation caches

If a package is required by many projects on the system, each project has to keep its own copy. This can be a waste of disk space, especially for data science and machine learning projects.

PDM supports _caching_ installations of the same wheel by installing it in a centralized package repository and linking to that installation in different projects. To enable it, run:

```bash
pdm config install.cache on
```

It can be enabled on a per-project basis by adding the `--local` option to the command.

The caches are located in `$(pdm config cache_dir)/packages`. You can view the cache usage with `pdm cache info`. Note that the cached installs are managed automatically -- they will be deleted if they are not linked to any projects. Manually deleting the caches from disk may break some projects on the system.

!!! note
    Only the installation of _named requirements_ resolved from PyPI can be cached.

## Configure the repositories for upload

When using the [`pdm publish`](../reference/cli.md#publish) command, it reads the repository secrets from the *global* config file(`<CONFIG_ROOT>/config.toml`). The content of the config is as follows:

```toml
[repository.pypi]
username = "frostming"
password = "<secret>"

[repository.company]
url = "https://pypi.company.org/legacy/"
username = "frostming"
password = "<secret>"
ca_certs = "/path/to/custom-cacerts.pem"
```

Alternatively, these credentials can be provided with env vars:

```bash
export PDM_PUBLISH_REPO=...
export PDM_PUBLISH_USERNAME=...
export PDM_PUBLISH_PASSWORD=...
export PDM_PUBLISH_CA_CERTS=...
```

A PEM-encoded Certificate Authority bundle (`ca_certs`) can be used for local / custom PyPI repositories where the server certificate is not signed by the standard [certifi](https://github.com/certifi/python-certifi/blob/master/certifi/cacert.pem) CA bundle.

!!! NOTE
    Repositories are different from indexes in the previous section. Repositories are for publishing while indexes are for locking
    and resolving. They don't share the configuration.

!!! TIP
    You don't need to configure the `url` for `pypi` and `testpypi` repositories, they are filled by default values.
    The username, password, and certificate authority bundle can be passed in from the command line for `pdm publish` via `--username`, `--password`, and `--ca-certs`, respectively.

To change the repository config from the command line, use the [`pdm config`](../reference/cli.md#config) command:

```bash
pdm config repository.pypi.username "__token__"
pdm config repository.pypi.password "my-pypi-token"

pdm config repository.company.url "https://pypi.company.org/legacy/"
pdm config repository.company.ca_certs "/path/to/custom-cacerts.pem"
```

## Password management with keyring

When keyring is available and supported, the passwords will be stored to and retrieved from the keyring instead of writing to the config file. This supports both indexes and upload repositories. The service name will be `pdm-pypi-<name>` for an index and `pdm-repository-<name>` for a repository.

You can enable keyring by either installing `keyring` into the same environment as PDM or installing globally. To add keyring to the PDM environment:

```bash
pdm self add keyring
```

Alternatively, if you have installed a copy of keyring globally, make sure the CLI is exposed in the `PATH` env var to make it discoverable by PDM:

```bash
export PATH=$PATH:path/to/keyring/bin
```

## Override the resolved package versions

_New in version 1.12.0_

Sometimes you can't get a dependency resolution due to incorrect version ranges set by upstream libraries that you can't fix.
In this case you can use PDM's overrides feature to force a specific version of a package to be installed.

Given the following configuration in `pyproject.toml`:

```toml
[tool.pdm.resolution.overrides]
asgiref = "3.2.10"  # exact version
urllib3 = ">=1.26.2"  # version range
pytz = "https://mypypi.org/packages/pytz-2020.9-py3-none-any.whl"  # absolute URL
```

Each entry of that table is a package name with the wanted version.
In this example, PDM will resolve the above packages into the given versions no matter whether there is any other resolution available.

!!! warning
    By using `[tool.pdm.resolution.overrides]` setting, you are at your own risk of any incompatibilities from that resolution. It can only be used if there is no valid resolution for your requirements and you know the specific version works.
    Most of the time, you can just add any transient constraints to the `dependencies` array.
