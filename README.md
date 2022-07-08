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
[![](https://tokei.rs/b1/github/pdm-project/pdm)](https://github.com/pdm-project/pdm)
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

## What is PEP 582?

The majority of Python packaging tools also act as virtualenv managers to gain the ability
to isolate project environments. But things get tricky when it comes to nested venvs: One
installs the virtualenv manager using a venv encapsulated Python, and create more venvs using the tool
which is based on an encapsulated Python. One day a minor release of Python is released and one has to check
all those venvs and upgrade them if required.

[PEP 582], on the other hand, introduces a way to decouple the Python interpreter from project
environments. It is a relatively new proposal and there are not many tools supporting it (one that does
is [pyflow], but it is written with Rust and thus can't get much help from the big Python community and for the same reason it can't act as a [PEP 517] backend).

[PEP 582] proposes a project structure as below:

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
The sha256 checksum is: `f09accb8a530315be312cf9ce7af987ccb608aa90d3972968d73e7ef7d8c547b`

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
asdf plugin add github.com/1oglop1/asdf-pdm.git
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

**Run your script with [PEP 582] support**

By default, PDM will create `.venv` in the project root, when doing `pdm install` on an existing project, as other package managers do.
But you can make PEP 582 the default by `pdm config python.use_venv false`. To enable the full power of PEP 582, do the following steps to make the Python interpreter use it.

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

If you are a Bash user, set the environment variable by `eval "$(pdm --pep582)"`. Now you can run the app directly with your familiar **Python interpreter**:

```bash
$ python /home/frostming/workspace/flask_app/app.py
 * Serving Flask app "app" (lazy loading)
 ...
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

Ta-da! You are running an app with its dependencies installed in an isolated place, while no virtualenv is involved.

For Windows users, please refer to [the doc](https://pdm.fming.dev/latest/usage/pep582/#enable-pep-582-globally) about how to make it work, it also includes a simple explanation of how
it works.

## Badges

Tell people you are using PDM in your project by including the markdown code in README.md:

```markdown
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
```

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

## PDM Eco-system

[Awesome PDM](https://github.com/pdm-project/awesome-pdm) is a curated list of awesome PDM plugins and resources.

## FAQ

### 1. What is put in `__pypackages__`?

[PEP 582] is a draft proposal which still needs a lot of polishing. For instance, it doesn't mention how to manage
CLI executables. PDM makes the decision to put `bin` and `include` together with `lib` under `__pypackages__/X.Y`.

### 2. How do I run CLI scripts in the local package directory?

The recommended way is to prefix your command with `pdm run`. It is also possible to run CLI scripts directly from
the outside. PDM's installer has already injected the package path to the `sys.path` in the entry script file.

### 3. What site-packages will be loaded when using PDM?

Packages in the local `__pypackages__` directory will be loaded before the system-level `site-packages` for isolation.

### 4. Can I relocate or move the `__pypackages__` folder for deployment?

You'd better not. The packages installed inside `__pypackages__` are OS dependent. Instead, you should keep `pdm.lock`
in VCS and do `pdm sync` on the target environment to deploy.

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
