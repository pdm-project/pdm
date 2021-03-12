# Advanced Usage

## Automatic Testing with Tox

[Tox](https://tox.readthedocs.io/en/latest/) is a great tool for testing against multiple Python versions or dependency sets.
You can configure a `tox.ini` like the following to integrate your testing with PDM:

```ini
[tox]
env_list = py{36,37,38},lint
isolated_build = true
passenv = PDM_IGNORE_SAVED_PYTHON=1

[testenv]
deps = pdm
commands =
    pdm install --dev
    pytest tests

[testenv:lint]
deps = pdm
commands =
    pdm install -s lint
    flake8 src/
```

To use the virtualenv created by Tox, you should make sure you have set `pdm config use_venv true`. PDM then will install
dependencies from `pdm.lock` into the virtualenv. In the dedicated venv you can directly run tools by `pytest tests/` instead
of `pdm run pytest tests/`.

You should also make sure you don't run `pdm add/pdm remove/pdm update/pdm lock` in the test commands, otherwise the `pdm.lock`
file will be modified unexpectedly. Additional dependencies can be supplied with the `deps` config. Besides, `isolated_buid` and `passenv`
config should be set as the above example to make PDM work properly.

To get rid of these constraints, there is a Tox plugin [tox-pdm](https://github.com/pdm-project/tox-pdm) which can ease the usage. You can install it by

```console
$ pip install tox-pdm
```

Or,

```console
$ pdm add --dev tox-pdm
```

And the `tox.ini` can be updated to the following:

```ini
[tox]
env_list = py{36,37,38},lint
isolated_build = true

[testenv]
sections = dev
commands =
    pytest tests

[testenv:lint]
sections = lint
commands =
    flake8 src/
```

See the [project's README](https://github.com/pdm-project/tox-pdm) for a detailed guidance.

## Automatic Testing with Nox

[Nox](https://nox.thea.codes/) is another great tool for automated testing. Unlike tox, Nox uses a standard Python file for configuration.

It is much easier to use PDM in Nox, here is an example of `noxfile.py`:

```python hl_lines="3"
import os

os.environ.update({"PDM_IGNORE_SAVED_PYTHON": "1"})

@nox.session
def tests(session):
    session.run('pdm', 'install', '-s', 'test', external=True)
    session.run('pytest')

@nox.session
def lint(session):
    session.run('pdm', 'install', '-s', 'lint', external=True)
    session.run('flake8', '--import-order-style', 'google')
```

Note that `PDM_IGNORE_SAVED_PYTHON` should be set so that PDM can pick up the Python in the virtualenv correctly. Also make sure `pdm` is available in the `PATH`.

## Use PDM in Continuous Integration

Only one thing to keep in mind -- PDM can't be installed on Python < 3.7, so if your project is to be tested on those Python versions,
you have to make sure PDM is installed on the correct Python version, which can be different from the target Python version the particular job/task is run on.

Here is an example worflow of GitHub Actions, while you can adapt it for other CI platforms.

```yaml
Testing:
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
    python-version: [3.6, 3.7, 3.8, 3.9]
    os: [ubuntu-latest, macOS-latest, windows-latest]

  steps:
    - uses: actions/checkout@v1
    - name: Set up Python 3.8
      uses: actions/setup-python@v1
      with:
        python-version: 3.8 # <-- We explicitly request Python 3.8 for installing PDM.
    - name: Install PDM
      run: python -m pip install --upgrade --pre pdm
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }} # <-- Then change to whatever is required by this task.
    - name: Install dependencies
      run: |
        pdm use -f ${{ matrix.python-version }}
        pdm sync -d -s testing
    - name: Run Tests
      run: |
        pdm run -v pytest tests
```

!!! danger "NOTE"
    For GitHub Action users, there is a [known compatibility issue](https://github.com/actions/virtual-environments/issues/2803) on Ubuntu virtual environment. If PDM parallel install is failed on that machine you should either set `parallel_install` to `false` or set env `LD_PRELOAD=/lib/x86_64-linux-gnu/libgcc_s.so.1`.
