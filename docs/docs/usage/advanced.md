# Advanced Usage

## Automatic Testing

### Use Tox as the runner

[Tox](https://tox.readthedocs.io/en/latest/) is a great tool for testing against multiple Python versions or dependency sets.
You can configure a `tox.ini` like the following to integrate your testing with PDM:

```ini
[tox]
env_list = py{36,37,38},lint
isolated_build = true

[testenv]
setenv =
    PDM_IGNORE_SAVED_PYTHON="1"
deps = pdm
commands =
    pdm install --dev
    pytest tests

[testenv:lint]
deps = pdm
commands =
    pdm install -G lint
    flake8 src/
```

To use the virtualenv created by Tox, you should make sure you have set `pdm config python.use_venv true`. PDM then will install
dependencies from [`pdm lock`](../reference/cli.md#lock) into the virtualenv. In the dedicated venv you can directly run tools by `pytest tests/` instead
of `pdm run pytest tests/`.

You should also make sure you don't run `pdm add/pdm remove/pdm update/pdm lock` in the test commands, otherwise the [`pdm lock`](../reference/cli.md#lock)
file will be modified unexpectedly. Additional dependencies can be supplied with the `deps` config. Besides, `isolated_buid` and `passenv`
config should be set as the above example to make PDM work properly.

To get rid of these constraints, there is a Tox plugin [tox-pdm](https://github.com/pdm-project/tox-pdm) which can ease the usage. You can install it by

```bash
pip install tox-pdm
```

Or,

```bash
pdm add --dev tox-pdm
```

And you can make the `tox.ini` much tidier as following, :

```ini
[tox]
env_list = py{36,37,38},lint

[testenv]
groups = dev
commands =
    pytest tests

[testenv:lint]
groups = lint
commands =
    flake8 src/
```

See the [project's README](https://github.com/pdm-project/tox-pdm) for a detailed guidance.

### Use Nox as the runner

[Nox](https://nox.thea.codes/) is another great tool for automated testing. Unlike tox, Nox uses a standard Python file for configuration.

It is much easier to use PDM in Nox, here is an example of `noxfile.py`:

```python hl_lines="4"
import os
import nox

os.environ.update({"PDM_IGNORE_SAVED_PYTHON": "1"})

@nox.session
def tests(session):
    session.run_always('pdm', 'install', '-G', 'test', external=True)
    session.run('pytest')

@nox.session
def lint(session):
    session.run_always('pdm', 'install', '-G', 'lint', external=True)
    session.run('flake8', '--import-order-style', 'google')
```

Note that `PDM_IGNORE_SAVED_PYTHON` should be set so that PDM can pick up the Python in the virtualenv correctly. Also make sure `pdm` is available in the `PATH`.
Before running nox, you should also ensure configuration item `python.use_venv` is true to enable venv reusing.

### About PEP 582 `__pypackages__` directory

By default, if you run tools by [`pdm run`](../reference/cli.md#run), `__pypackages__` will be seen by the program and all subprocesses created by it. This means virtual environments created by those tools are also aware of the packages inside `__pypackages__`, which result in unexpected behavior in some cases.
For `nox`, you can avoid this by adding a line in `noxfile.py`:

```python
os.environ.pop("PYTHONPATH", None)
```

For `tox`, `PYTHONPATH` will not be passed to the test sessions so this isn't going to be a problem. Moreover, it is recommended to make `nox` and `tox` live in their own pipx environments so you don't need to install for every project. In this case, PEP 582 packages will not be a problem either.

## Use PDM in Continuous Integration

Only one thing to keep in mind -- PDM can't be installed on Python < 3.7, so if your project is to be tested on those Python versions,
you have to make sure PDM is installed on the correct Python version, which can be different from the target Python version the particular job/task is run on.

Fortunately, if you are using GitHub Action, there is [pdm-project/setup-pdm](https://github.com/marketplace/actions/setup-pdm) to make this process easier.
Here is an example workflow of GitHub Actions, while you can adapt it for other CI platforms.

```yaml
Testing:
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      python-version: [3.7, 3.8, 3.9, '3.10']
      os: [ubuntu-latest, macOS-latest, windows-latest]

  steps:
    - uses: actions/checkout@v3
    - name: Set up PDM
      uses: pdm-project/setup-pdm@v2
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        pdm sync -d -G testing
    - name: Run Tests
      run: |
        pdm run -v pytest tests
```

!!! important "TIPS"
    For GitHub Action users, there is a [known compatibility issue](https://github.com/actions/virtual-environments/issues/2803) on Ubuntu virtual environment.
    If PDM parallel install is failed on that machine you should either set `parallel_install` to `false` or set env `LD_PRELOAD=/lib/x86_64-linux-gnu/libgcc_s.so.1`.
    It is already handled by the `pdm-project/setup-pdm` action.

!!! note
    If your CI scripts run without a proper user set, you might get permission errors when PDM tries to create its cache directory.
    To work around this, you can set the HOME environment variable yourself, to a writable directory, for example:

    ```bash
    export HOME=/tmp/home
    ```

## Use PDM in a multi-stage Dockerfile

It is possible to use PDM in a multi-stage Dockerfile to first install the project and dependencies into `__pypackages__`
and then copy this folder into the final stage, adding it to `PYTHONPATH`.

```dockerfile
# build stage
FROM python:3.8 AS builder

# install PDM
RUN pip install -U pip setuptools wheel
RUN pip install pdm

# copy files
COPY pyproject.toml pdm.lock README.md /project/
COPY src/ /project/src

# install dependencies and project into the local packages directory
WORKDIR /project
RUN mkdir __pypackages__ && pdm sync --prod --no-editable


# run stage
FROM python:3.8

# retrieve packages from build stage
ENV PYTHONPATH=/project/pkgs
COPY --from=builder /project/__pypackages__/3.8/lib /project/pkgs

# retrieve executables
COPY --from=builder /project/__pypackages__/3.8/bin/* /bin/

# set command/entrypoint, adapt to fit your needs
CMD ["python", "-m", "project"]
```

## Use PDM to manage a monorepo

With PDM, you can have multiple sub-packages within a single project, each with its own `pyproject.toml` file. And you can create only one `pdm.lock` file to lock all dependencies. The sub-packages can have each other as their dependencies. To achieve this, follow these steps:

`project/pyproject.toml`:

```toml
[tool.pdm.dev-dependencies]
dev = [
    "-e file:///${PROJECT_ROOT}/packages/foo-core",
    "-e file:///${PROJECT_ROOT}/packages/foo-cli",
    "-e file:///${PROJECT_ROOT}/packages/foo-app",
]
```

`packages/foo-cli/pyproject.toml`:

```toml
[projects]
dependencies = ["foo-core"]
```

`packages/foo-app/pyproject.toml`:

```toml
[projects]
dependencies = ["foo-core"]
```

Now, run `pdm install` in the project root, and you will get a `pdm.lock` with all dependencies locked. All sub-packages will be installed in editable mode.

Look at the [🚀 Example repository](https://github.com/pdm-project/pdm-example-monorepo) for more details.

## Hooks for `pre-commit`

[`pre-commit`](https://pre-commit.com/) is a powerful framework for managing git hooks in a centralized fashion. PDM already uses `pre-commit` [hooks](https://github.com/pdm-project/pdm/blob/main/.pre-commit-config.yaml) for its internal QA checks. PDM exposes also several hooks that can be run locally or in CI pipelines.

### Export `requirements.txt` or `setup.py`

This hook wraps the command `pdm export` along with any valid argument. It can be used as a hook (e.g., for CI) to ensure that you are going to check in the codebase a `requirements.txt` or a `setup.py` file, which reflects the actual content of [`pdm lock`](../reference/cli.md#lock).

```yaml
# export python requirements
- repo: https://github.com/pdm-project/pdm
  rev: 2.x.y # a PDM release exposing the hook
  hooks:
    - id: pdm-export
      # command arguments, e.g.:
      args: ['-o', 'requirements.txt', '--without-hashes']
      files: ^pdm.lock$
```

### Check `pdm.lock` is up to date with pyproject.toml

This hook wraps the command `pdm lock --check` along with any valid argument. It can be used as a hook (e.g., for CI) to ensure that whenever `pyproject.toml` has a dependency added/changed/removed, that `pdm.lock` is also up to date.

```yaml
- repo: https://github.com/pdm-project/pdm
  rev: 2.x.y # a PDM release exposing the hook
  hooks:
    - id: pdm-lock-check
```
