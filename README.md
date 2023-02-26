<div align="center">

# PDM

A modern Python package and dependency manager supporting the latest PEP standards.
[中文版本说明](README_zh.md)

![PDM logo](https://raw.githubusercontent.com/pdm-project/pdm/main/docs/docs/assets/logo_big.png)

[![Docs](https://img.shields.io/badge/Docs-mkdocs-blue?style=for-the-badge)](https://pdm.fming.dev)
[![Twitter Follow](https://img.shields.io/twitter/follow/pdm_project?label=get%20updates&logo=twitter&style=for-the-badge)](https://twitter.com/pdm_project)
[![Discord](https://img.shields.io/discord/824472774965329931?label=discord&logo=discord&style=for-the-badge)](https://discord.gg/Phn8smztpv)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)](https://pypi.org/project/pdm)
[![codecov](https://codecov.io/gh/pdm-project/pdm/branch/main/graph/badge.svg?token=erZTquL5n0)](https://codecov.io/gh/pdm-project/pdm)
[![Packaging status](https://repology.org/badge/tiny-repos/pdm.svg)](https://repology.org/project/pdm/versions)
[![Downloads](https://pepy.tech/badge/pdm/week)](https://pepy.tech/project/pdm)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
<a href="https://trackgit.com">
<img src="https://us-central1-trackgit-analytics.cloudfunctions.net/token/ping/l4eztudjnh9bfay668fl" alt="trackgit-views" />
</a>

[![asciicast](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.svg)](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB)

</div>

## What is PDM?

PDM is meant to be a next generation Python package management tool.
It was originally built for personal use. If you feel you are going well
with `Pipenv` or `Poetry` and don't want to introduce another package manager,
just stick to it. But if you are missing something that is not present in those tools,
you can probably find some goodness in `pdm`.

## Highlights of features

- Opt-in [PEP 582] support, no virtualenv involved at all.
- Simple and fast dependency resolver, mainly for large binary distributions.
- A [PEP 517] build backend.
- [PEP 621] project metadata.
- Flexible and powerful plug-in system.
- Versatile user scripts.
- Opt-in centralized installation cache like [pnpm](https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed).

[pep 517]: https://www.python.org/dev/peps/pep-0517
[pep 582]: https://www.python.org/dev/peps/pep-0582
[pep 621]: https://www.python.org/dev/peps/pep-0621
[pnpm]: https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed

## Comparisons to other alternatives

### [Pipenv](https://pipenv.pypa.io)

Pipenv is a dependency manager that combines `pip` and `venv`, as the name implies.
It can install packages from a non-standard `Pipfile.lock` or `Pipfile`.
However, Pipenv does not handle any packages related to packaging your code,
so it’s useful only for developing non-installable applications (Django sites, for example).
If you’re a library developer, you need `setuptools` anyway.

### [Poetry](https://python-poetry.org)

Poetry manages environments and dependencies in a similar way to Pipenv,
but it can also build .whl files with your code, and it can upload wheels and source distributions to PyPI.
It has a pretty user interface and users can customize it via a plugin. Poetry uses the `pyproject.toml` standard,
but it does not follow the standard specifying how metadata should be represented in a pyproject.toml file ([PEP 621]),
instead using a custom `[tool.poetry]` table. This is partly because Poetry came out before PEP 621.

### [Hatch](https://hatch.pypa.io)

Hatch can also manage environments (it allows multiple environments per project, but it does not allow to put them in the project directory), and it can manage packages (but without lockfile support). Hatch can also be used to package a project (with PEP 621-compliant pyproject.toml files) and upload it to PyPI.

### This project

PDM also can manage venvs, both in project and centralized location as Pipenv does. It reads the project metadata from a standardized `pyproject.toml` file, and has lockfile support. Users can add more functionalities in a plugin and upload it as a distribution for sharing.
Besides, PDM has an experimental [PEP 582] support([docs](https://pdm.fming.dev/latest/usage/pep582/)), which means you can install packages without creating a virtual environment. Moreover, unlike Poetry and Hatch, PDM isn't locked to a specific build backend, you can choose any build backend you like.

## Installation

PDM requires python version 3.7 or higher.

### Via Install Script

Like Pip, PDM provides an installation script that will install PDM into an isolated environment.

**For Linux/Mac**

```bash
curl -sSL https://raw.githubusercontent.com/pdm-project/pdm/main/install-pdm.py | python3 -
```

**For Windows**

```powershell
(Invoke-WebRequest -Uri https://raw.githubusercontent.com/pdm-project/pdm/main/install-pdm.py -UseBasicParsing).Content | python -
```

For security reasons, you should verify the checksum of `install-pdm.py`.
The sha256 checksum is: `ce0a116987b2667231391d13dd005006433114033cac74aa18f0b2dec5538d03`

The installer will install PDM into the user site and the location depends on the system:

- `$HOME/.local/bin` for Unix
- `%APPDATA%\Python\Scripts` on Windows

You can pass additional options to the script to control how PDM is installed:

```
usage: install-pdm.py [-h] [-v VERSION] [--prerelease] [--remove] [-p PATH] [-d DEP]

optional arguments:
  -h, --help            show this help message and exit
  -v VERSION, --version VERSION | envvar: PDM_VERSION
                        Specify the version to be installed, or HEAD to install from the main branch
  --prerelease | envvar: PDM_PRERELEASE    Allow prereleases to be installed
  --remove | envvar: PDM_REMOVE            Remove the PDM installation
  -p PATH, --path PATH | envvar: PDM_HOME  Specify the location to install PDM
  -d DEP, --dep DEP | envvar: PDM_DEPS     Specify additional dependencies, can be given multiple times
```

You can either pass the options after the script or set the env var value.

### Alternative Installation Methods

If you are on MacOS and using `homebrew`, install it by:

```bash
brew install pdm
```

If you are on Windows and using [Scoop](https://scoop.sh/), install it by:

```
scoop bucket add frostming https://github.com/frostming/scoop-frostming.git
scoop install pdm
```

Otherwise, it is recommended to install `pdm` in an isolated environment with `pipx`:

```bash
pipx install pdm
```

Or you can install it under a user site:

```bash
pip install --user pdm
```

With [asdf-vm](https://asdf-vm.com/)

```bash
asdf plugin add pdm
asdf install pdm latest
```

## Quickstart

**Initialize a new PDM project**

```bash
pdm init
```

Answer the questions following the guide, and a PDM project with a `pyproject.toml` file will be ready to use.

**Install dependencies**

```bash
pdm add requests flask
```

You can add multiple dependencies in the same command. After a while, check the `pdm.lock` file to see what is locked for each package.

## Badges

Tell people you are using PDM in your project by including the markdown code in README.md:

```markdown
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
```

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)


## Packaging Status

[![Packaging status](https://repology.org/badge/vertical-allrepos/pdm.svg)](https://repology.org/project/pdm/versions)

## PDM Eco-system

[Awesome PDM](https://github.com/pdm-project/awesome-pdm) is a curated list of awesome PDM plugins and resources.

## Sponsors

<p align="center">
    <a href="https://cdn.jsdelivr.net/gh/pdm-project/sponsors/sponsors.svg">
        <img src="https://cdn.jsdelivr.net/gh/pdm-project/sponsors/sponsors.svg"/>
    </a>
</p>

## Credits

This project is strongly inspired by [pyflow] and [poetry].

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## License

This project is open sourced under MIT license, see the [LICENSE](LICENSE) file for more details.
