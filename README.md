# PDM - Python Development Master

A modern Python package manager with PEP 582 support.

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)

## What is PDM?

PDM is meant to be a next generation Python package management tool.
It is originally built for personal interest. If you feel you are going well
with `Pipenv` or `Poetry` and don't want to introduce another package manager,
just stick to it. But if you are missing something that is not present in those tools,
you can probably find some goodness in `pdm`.

**Open for feature requests, find yourself at https://github.com/pdm-project/call-for-features.**

## Highlights of features
* PEP 582 local package installer and runner, no virtualenv involved at all.
* Simple and relatively fast dependency resolver, mainly for large binary distributions.
* A PEP 517 build backend.

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

```bash
$ pipx install pdm
```
It is recommended to install `pdm` in an isolated enviroment, with `pipx`.

Or you can install it under user site:

```bash
$ pip install --user pdm
```

## Usage

`python -m pdm --help` should be a good guidance.

## 0.1.0 Roadmap

- [x] A dependency resolver that just works.
- [x] A PEP 582 installer.
- [x] PEP 440 version specifiers.
- [x] PEP 508 environment markers.
- [x] Running scripts with PEP 582 local packages.
- [x] Console scripts are injected with local paths.
- [x] A neet CLI.
- [x] `add`, `lock`, `list`, `update`, `remove`, `build` commands.
- [x] PEP 517 build backends.
- [x] Continuous Integration.


## Credits

This project is strongly inspired by [pyflow] and [poetry].

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry


## License
This project is open sourced under MIT license, see the [LICENSE](LICENSE) file for more details.
