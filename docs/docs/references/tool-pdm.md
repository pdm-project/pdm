# PDM Tool Settings

There are also some useful settings to control the behaviors of PDM in various aspects. They should be stored in `pyproject.toml`, defined in `[tool.pdm]` table.

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

Editable dependencies are also allowed in `dev-dependencies`. to define an editable dependency, prefix it with `-e `:

```toml
[tool.pdm.dev-dependencies]
editable = [
    "-e git+https://github.com/pallets/click.git@main#egg=click",  # VCS link
    "-e ./mypackage/",  # local package
]
```

## Allow prereleases in resolution result

By default, `pdm`'s dependency resolver will ignore prereleases unless there are no stable versions for the given version range of a dependency. This behavior can be changed by setting `allow_prereleases` to `true` in `[tool.pdm]` table:

```toml
[tool.pdm]
allow_prereleases = true
```

## Specify other sources for finding packages

Like Pipenv, you can specify extra sources for finding packages with the same format. They are stored in an array of table named `[[tool.pdm.source]]` in `pyproject.toml`:

```toml
[[tool.pdm.source]]
url = "https://private-site.org/pypi/simple"
verify_ssl = true
name = "internal"
```

With this, the PyPI index and the above internal source will be searched for packages. It basically does the same as passing `--extra-index-url https://private-site.org/pypi/simple` to `pip install` command.

### Disable the PyPI repository

If you want to omit the default PyPI index, just set the source name to `pypi` and that source will **replace** it.

```toml
[[tool.pdm.source]]
url = "https://private.pypi.org/simple"
verify_ssl = true
name = "pypi"
```

### Find links source

By default, all sources are [PEP 503](https://www.python.org/dev/peps/pep-0503/) style "indexes" like pip's `--index-url` and `--extra-index-url`, however, you can also specify "find links" with
`type = "find_links"`. See [this answer](https://stackoverflow.com/a/46651848) for the difference between the two types.

For example, to install from a local directory containing package files:

```toml
[[tool.pdm.source]]
url = "file:///path/to/packages"
name = "local"
type = "find_links"
```

!!! note "Difference from changing config value"
    When you want all packages to be fetched from the given index instead of the default one, despite what platform your are on or who is to deploy the app,
    write it in the `[[tool.pdm.source]]`. Otherwise if you would like to change the index temporarily on the current platform (for network reasons), you should use
    `pdm config pypi.url https://private.pypi.org/simple`.


### Respect the order of the sources

By default, all sources are considered equal, packages from them are sorted by the version and wheel tags, the most matching one with the highest version is selected.

In some cases you may want to return packages from the preferred source, and search for others if they are missing from the former source. PDM supports this by reading the configuration `respect-source-order`:

```toml
[tool.pdm.resolution]
respect-source-order = true
```
