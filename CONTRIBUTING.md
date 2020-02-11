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
$ python setup_dev.py
```

Now, all dependencies are installed into local `__pypackages__` directory, which will be used for development
after this point. The `pdm` executable located at `__pypackages__/<VERSION>/bin` can be run directly from outside,
which is installed in editable mode, or you can use `python -m pdm` from inside the venv.

### Run tests

```bash
$ pdm run pytest tests
```

The test suite is still simple and requires to be supplied, please help write more test cases.

### Code style

PDM uses `pre-commit` for linting, you need to install `pre-commit` first, then:

```bash
$ pre-commit install
$ pre-commit run --all-files
```

PDM uses `black` coding style and `isort` for sorting import statements, if you are not following them,
the CI will fail and your Pull Request will not be merged.
