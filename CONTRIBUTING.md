# Contributing to PDM

First off, thanks for taking the time to contribute! Contributions include but are not restricted to:

- Reporting bugs
- Contributing to code
- Writing tests
- Writing documents

The following is a set of guidelines for contributing.

## Local development

```bash
$ git clone https://github.com/pdm-project/pdm.git
$ cd pdm
```

First, you need to install base dependencies in a venv. Although PDM uses local package directory to install
dependencies, venv is still needed to start up PDM at the first time:

```bash
$ python -m venv env
$ . env/bin/activate
(env) $ pip install pdm
(env) $ python -m pdm install -d
```

Now, all dependencies are installed into local `__pypackages__` directory, which will be used for development
after this point. The `pdm` executable located at `__pypackages__/<VERSION>/bin` can be run directly from outside,
which is installed in editable mode, or you can use `python -m pdm` from inside the venv.

TIP: create alias for the editable `pdm` executable to reduce the command length. If you run `pdm` in the local package
directory, the venv you created before won't be needed anymore, feel free to remove it.

### Run tests

```bash
(env) $ python -m pdm run pytest tests
```

The test suites are still simple and require a lot more, please help write more test cases.

### Code style

PDM uses `pre-commit` for linting, you need to install `pre-commit` first, then:

```bash
$ pre-commit install
$ pre-commit run --all-files
```

PDM uses `black` coding style and `isort` for sorting import statements, if you are not following them,
the CI will fail and your Pull Request will not be merged.
