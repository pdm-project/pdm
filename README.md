<div align="center">

# PDM

A modern Python package and dependency manager supporting the latest PEP standards.
[中文版本说明](README_zh.md)

![PDM logo](https://raw.githubusercontent.com/pdm-project/pdm/main/docs/assets/logo_big.png)

[![Docs](https://img.shields.io/badge/Docs-mkdocs-blue?style=for-the-badge)](https://pdm-project.org)
[![Twitter Follow](https://img.shields.io/twitter/follow/pdm_project?label=get%20updates&logo=twitter&style=for-the-badge)](https://twitter.com/pdm_project)
[![Discord](https://img.shields.io/discord/824472774965329931?label=discord&logo=discord&style=for-the-badge)](https://discord.gg/Phn8smztpv)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)](https://pypi.org/project/pdm)
[![codecov](https://codecov.io/gh/pdm-project/pdm/branch/main/graph/badge.svg?token=erZTquL5n0)](https://codecov.io/gh/pdm-project/pdm)
[![Packaging status](https://repology.org/badge/tiny-repos/pdm.svg)](https://repology.org/project/pdm/versions)
[![Downloads](https://pepy.tech/badge/pdm/week)](https://pepy.tech/project/pdm)
[![pdm-managed](https://img.shields.io/endpoint?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fpdm-project%2F.github%2Fbadge.json)](https://pdm-project.org)
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

- Simple and fast dependency resolver, mainly for large binary distributions.
- A [PEP 517] build backend.
- [PEP 621] project metadata.
- Flexible and powerful plug-in system.
- Versatile user scripts.
- Install Pythons using [astral-sh's python-build-standalone](https://github.com/astral-sh/python-build-standalone).
- Opt-in centralized installation cache like [pnpm](https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed).

[pep 517]: https://www.python.org/dev/peps/pep-0517
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
It has a pretty user interface and users can customize it via a plugin. Poetry uses the `pyproject.toml` standard.

### [Hatch](https://hatch.pypa.io)

Hatch can also manage environments, allowing multiple environments per project. By default it has a central location for all environments but it can be configured to put a project's environment(s) in the project root directory. It can manage packages but without lockfile support. It can also be used to package a project (with PEP 621 compliant pyproject.toml files) and upload it to PyPI.

### This project

PDM can manage virtual environments (venvs) in both project and centralized locations, similar to Pipenv. It reads project metadata from a standardized `pyproject.toml` file and supports lockfiles. Users can add additional functionality through plugins, which can be shared by uploading them as distributions.

Unlike Poetry and Hatch, PDM is not limited to a specific build backend; users have the freedom to choose any build backend they prefer.

## Installation

<a href="https://repology.org/project/pdm/versions">
    <img src="https://repology.org/badge/vertical-allrepos/pdm.svg" alt="Packaging status" align="right">
</a>

PDM requires python version 3.9 or higher. Alternatively, you can download the standalone binary file from the [release assets](https://github.com/pdm-project/pdm/releases).

### Install Binary via Script (recommended)

Install the standalone binary directly with the installer scripts:

**For Linux/Mac**

```bash
curl -sSL https://pdm-project.org/install.sh | bash
```

**For Windows**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://pdm-project.org/install.ps1 | iex"
```

For alternative installation methods (Python script, package managers, etc.), see the [installation section in documentation](https://pdm-project.org/en/latest/#installation).

## Quickstart

**Create a new PDM project**

```bash
pdm new my-project
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
[![pdm-managed](https://img.shields.io/endpoint?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fpdm-project%2F.github%2Fbadge.json)](https://pdm-project.org)
```

[![pdm-managed](https://img.shields.io/endpoint?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fpdm-project%2F.github%2Fbadge.json)](https://pdm-project.org)

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
