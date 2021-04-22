<div align="center">

# PDM - Python Development Master

A modern Python package manager with PEP 582 support. [中文版本说明](README_zh.md)

![PDM logo](https://github.com/pdm-project/pdm/blob/master/docs/docs/assets/logo_big.png)

[![Docs](https://img.shields.io/badge/Docs-mkdocs-blue?style=for-the-badge)](https://pdm.fming.dev)
[![Twitter Follow](https://img.shields.io/twitter/follow/pdm_project?label=get%20updates&logo=twitter&style=for-the-badge)](https://twitter.com/pdm_project)
[![Discord](https://img.shields.io/discord/824472774965329931?label=discord&logo=discord&style=for-the-badge)](https://discord.gg/CEUwAmYm)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)
[![codecov](https://codecov.io/gh/pdm-project/pdm/branch/master/graph/badge.svg?token=erZTquL5n0)](https://codecov.io/gh/pdm-project/pdm)
[![Docker Cloud Build Status](https://img.shields.io/docker/cloud/build/frostming/pdm)](https://hub.docker.com/r/frostming/pdm)
[![Downloads](https://pepy.tech/badge/pdm)](https://pepy.tech/project/pdm)
[![Downloads](https://pepy.tech/badge/pdm/week)](https://pepy.tech/project/pdm)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

[![asciicast](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.svg)](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB)

</div>

## What is PDM?

PDM is meant to be a next generation Python package management tool.
It was originally built for personal use. If you feel you are going well
with `Pipenv` or `Poetry` and don't want to introduce another package manager,
just stick to it. But if you are missing something that is not present in those tools,
you can probably find some goodness in `pdm`.

PEP 582 proposes a project structure as below:

```
foo
    __pypackages__
        3.8
            lib
                bottle
    myscript.py
```

There is a `__pypackages__` directory in the project root to hold all dependent libraries, just like what `npm` does.
Read more about the specification [here](https://www.python.org/dev/peps/pep-0582/#specification).

## Highlights of features

- PEP 582 local package installer and runner, no virtualenv involved at all.
- Simple and relatively fast dependency resolver, mainly for large binary distributions.
- A PEP 517 build backend.
- A full-featured plug-in system.
- PEP 621 project metadata format.

## Why not virtualenv?

The majority of Python packaging tools also act as virtualenv managers to gain the ability
to isolate project environments. But things get tricky when it comes to nested venvs: One
installs the virtualenv manager using a venv encapsulated Python, and create more venvs using the tool
which is based on an encapsulated Python. One day a minor release of Python is released and one has to check
all those venvs and upgrade them if required.

PEP 582, on the other hand, introduces a way to decouple the Python interpreter from project
environments. It is a relative new proposal and there are not many tools supporting it (one that does
is [pyflow]), but it is written with Rust and thus can't get much help from the big Python community.
For the same reason it can't act as a PEP 517 backend.

## Installation:

PDM requires python version 3.7 or higher.

If you are on MacOS and using `homebrew`, install it by:

```bash
$ brew install pdm
```

Otherwise, it is recommended to install `pdm` in an isolated environment with `pipx`:

```bash
$ pipx install pdm
```

Or you can install it under a user site:

```bash
$ pip install --user pdm
```

## Quickstart

**Initialize a new PDM project**

```bash
$ pdm init
```

Answer the questions following the guide, and a PDM project with a `pyproject.toml` file will be ready to use.

**Install dependencies into the `__pypackages__` directory**

```bash
$ pdm add requests flask
```

You can add multiple dependencies in the same command. After a while, check the `pdm.lock` file to see what is locked for each package.

**Run your script with PEP 582 support**

Suppose you have a script `app.py` placed next to the `__pypackages__` directory with the following content(taken from Flask's website):

```python
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World!'

if __name__ == '__main__':
    app.run()
```

If you are a Bash user, set the environment variable by `eval $(pdm --pep582)`. Now you can run the app directly with your familiar **Python interpreter**:

```bash
$ python /home/frostming/workspace/flask_app/app.py
 * Serving Flask app "app" (lazy loading)
 ...
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

Ta-da! You are running an app with its dependencies installed in an isolated place, while no virtualenv is involved.

For Windows users, please refer to [the doc](https://pdm.fming.dev/#enable-pep-582-globally) about how to make it work.

If you are curious about how this works, check [this doc section](https://pdm.fming.dev/usage/project/#how-we-make-pep-582-packages-available-to-the-python-interpreter) for some explanation.

## Docker image

```console
$ docker pull frostming/pdm
```

## FAQ

### 1. What is put in `__pypackages__`?

PEP 582 is a draft proposal which still needs a lot of polishing. For instance, it doesn't mention how to manage
CLI executables. PDM makes the decision to put `bin` and `include` together with `lib` under `__pypackages__/X.Y`.

### 2. How do I run CLI scripts in the local package directory?

The recommended way is to prefix your command with `pdm run`. It is also possible to run CLI scripts directly from
the outside. PDM's installer has already injected the package path to the `sys.path` in the entry script file.

### 3. What site-packages will be loaded when using PDM?

Packages in the local `__pypackages__` directory will be loaded before the system-level `site-packages` for isolation.

### 4. Can I relocate or move the `__pypackages__` folder for deployment?

You'd better not. The packages installed inside `__pypackages__` are OS dependent. Instead, you should keep `pdm.lock`
in VCS and do `pdm sync` on the target environment to deploy.

### 5. Can I use `pdm` to manage a Python 2.7 project?

Sure. The `pdm` itself can be installed under Python 3.7+ only, but it doesn't restrict the Python used by the project.

## Badges

Tell people you are using PDM in your project by including the markdown code in README.md:

```markdown
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
```

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

## Credits

This project is strongly inspired by [pyflow] and [poetry].

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## License

This project is open sourced under MIT license, see the [LICENSE](LICENSE) file for more details.
