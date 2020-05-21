# PDM - Python Development Master

A modern Python package manager with PEP 582 support. [中文版本说明](README_zh.md)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)
[![Docker Cloud Build Status](https://img.shields.io/docker/cloud/build/frostming/pdm)](https://hub.docker.com/repository/docker/frostming/pdm)

[![asciicast](https://asciinema.org/a/OKzNEKz1Lj0wmCVtcIqefskim.svg)](https://asciinema.org/a/OKzNEKz1Lj0wmCVtcIqefskim)

[📖 Documentation](https://pdm.fming.dev)

## What is PDM?

PDM is meant to be a next generation Python package management tool.
It is originally built for personal interest. If you feel you are going well
with `Pipenv` or `Poetry` and don't want to introduce another package manager,
just stick to it. But if you are missing something that is not present in those tools,
you can probably find some goodness in `pdm`.

## Highlights of features

- PEP 582 local package installer and runner, no virtualenv involved at all.
- Simple and relatively fast dependency resolver, mainly for large binary distributions.
- A PEP 517 build backend.
- A full-featured plug-in system.

## Why not virtualenv?

Now the majority of Python packaging tools also act as virtualenv managers. It is for the benifit
of isolating project environments. But things will get tricky when it comes to nested venvs: One
installs the virtualenv manager using a venv capsulated Python, and create more venvs using the tool
which is based on a capsulated Python. One day a minor release of Python out and one has to check
all those venvs and upgrade them if required.

While PEP 582, in the other hand, introduce a way to decouple Python interpreter with project
environments. It is a relative new proposal and there are not many tools supporting it, among which
there is [pyflow], but it is written with Rust and can't get much help from the big Python community.
Moreover, due to the same reason, it can't act as a PEP 517 backend.

## Installation:

PDM requires python version 3.7 or higher.

It is recommended to install `pdm` in an isolated enviroment, with `pipx`.

```bash
$ pipx install pdm
```

Or you can install it under user site:

```bash
$ pip install --user pdm
```

## Usage

`python -m pdm --help` should be a good guidance.

## Docker image

```console
$ docker pull frostming/pdm
```

## FAQ

### 1. What is put in `__pypackages__`?

PEP 582 is a draft proposal which still needs a lot of polishment, for instance, it doesn't mention how to manage
CLI executables. PDM take the decision to put `bin`, `include` together with `lib` under `__pypackages__/X.Y`.

### 2. How do I run CLI scripts in the local package directory?

The recommended way is to prefix your command with `pdm run`. It is also possible to run CLI scripts directly from
the outside, the PDM's installer has already injected the package path to the `sys.path` in the entry script file.

### 3. What site-packages will be loaded when using PDM?

Only packages in local `__pypackages__` directory will be loaded. `site-packages` of Python interpreter isn't loaded.
It is fully isolated.

### 4. Can I relocate or move the `__pypackages__` folder for deployment?

You'd better not. The packages installed inside `__pypackages__` are OS dependent. Instead, you should keep `pdm.lock`
in VCS and do `pdm sync` on the target environment to deploy.

### 5. Can I use `pdm` to manage a Python 2.7 project?

Sure. The `pdm` itself can be installed under Python 3.7+ only, but it doesn't restrict the Python used by the project.

## Credits

This project is strongly inspired by [pyflow] and [poetry].

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## License

This project is open sourced under MIT license, see the [LICENSE](LICENSE) file for more details.
