# Project file syntax

## Project metadata

There are several differences from the metadata of `setuptools`:

- `readme` is the file name of README file and PDM can derive the content type automatically.
- `author` and `maintainer` is a combination of name and email address in the form of `Name <email>`.

## Package version

You can specify a file source for `version` field like: `version = {from = "pdm/__init__.py"}`, in this form,
the version will be read from the `__version__` variable in that file.

## Include and exclude pacakge files

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
If neither `includes` or `excludes` is given, PDM is also smart enough to include top level packages and all data files in them.
Packages can also lie in `src` directory that PDM can find it.

## Console scripts

The following content:
```toml
[tool.pdm.cli]
mycli = "mycli.__main__:main"
```
will be translated to setuptools style:
```python
entry_points = {
    'console_scripts': [
        'mycli=mycli.__main__:main'
    ]
}
```

## Entry points

Other types of entry points are given by `[tool.pdm.entry_points.<type>]` section, with the same
format of `[tool.pdm.cli]` format:

```toml
[tool.pdm.entry_points.pytest11]
myplugin = "mypackage.plugin:pytest_plugin"
```
