# Introduction

PDM is a modern Python package manager with [PEP 582] support. It installs and manages packages
 in a similar way to `npm` that doesn't need to create a virtualenv at all!

[PEP 582]: https://www.python.org/dev/peps/pep-0582/

## Feature highlights

- PEP 582 local package installer and runner, no virtualenv involved at all.
- Simple and relatively fast dependency resolver, mainly for large binary distributions.
- A PEP 517 build backend.

## Installation

PDM requires Python 3.7+ to be installed. It works on multiple platforms including Windows, Linux and MacOS.

!!! note
    There is no restriction about what Python version that your project is using but installing
    PDM itself needs Python 3.7+.

### Recommended installation method
To avoid messing up with the system Python environemnt, the most recommended way to install PDM
is via [pipx](https://pypi.org/project/pipx):

```bash
$ pipx install pdm
```

### Other installation methods

Install PDM into user site with `pip`:

```bash
$ pip install --user pdm
```

## Use with IDE

Now there are not built-in support or plugins for PEP 582 in most IDEs, you have to configure your tools manually.

### PyCharm

Mark `__pypackages__/<major.minor>/lib` as Sources Root.

### VSCode

Add following in the `settings.json`:

```json
{
  ...
  "python.autoComplete.extraPaths": ["__pypackages__/<major.minor>/lib"]
}
```
