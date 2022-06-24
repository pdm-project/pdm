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

To use the virtualenv created by Tox, you should make sure you have set `pdm config use_venv true`. PDM then will install
dependencies from [`pdm lock`](cli_reference.md#exec-0--lock) into the virtualenv. In the dedicated venv you can directly run tools by `pytest tests/` instead
of `pdm run pytest tests/`.

You should also make sure you don't run `pdm add/pdm remove/pdm update/pdm lock` in the test commands, otherwise the [`pdm lock`](cli_reference.md#exec-0--lock)
file will be modified unexpectedly. Additional dependencies can be supplied with the `deps` config. Besides, `isolated_buid` and `passenv`
config should be set as the above example to make PDM work properly.

To get rid of these constraints, there is a Tox plugin [tox-pdm](https://github.com/pdm-project/tox-pdm) which can ease the usage. You can install it by

```console
pip install tox-pdm
```

Or,

```console
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
    session.run('pdm', 'install', '-G', 'test', external=True)
    session.run('pytest')

@nox.session
def lint(session):
    session.run('pdm', 'install', '-G', 'lint', external=True)
    session.run('flake8', '--import-order-style', 'google')
```

Note that `PDM_IGNORE_SAVED_PYTHON` should be set so that PDM can pick up the Python in the virtualenv correctly. Also make sure `pdm` is available in the `PATH`.
Before running nox, you should also `pdm config use_venv true` to enable venv reusing.

### About PEP 582 `__pypackages__` directory

By default, if you run tools by [`pdm run`](cli_reference.md#exec-0--run), `__pypackages__` will be seen by the program and all subprocesses created by it. This means virtual environments created by those tools are also aware of the packages inside `__pypackages__`, which result in unexpected behavior in some cases.
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
      python-version: [3.7, 3.8, 3.9, "3.10"]
      os: [ubuntu-latest, macOS-latest, windows-latest]

  steps:
    - uses: actions/checkout@v1
    - name: Set up PDM
      uses: pdm-project/setup-pdm@main
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

# install dependencies and project
WORKDIR /project
RUN pdm install --prod --no-lock --no-editable


# run stage
FROM python:3.8

# retrieve packages from build stage
ENV PYTHONPATH=/project/pkgs
COPY --from=builder /project/__pypackages__/3.8/lib /project/pkgs

# set command/entrypoint, adapt to fit your needs
CMD ["python", "-m", "project"]
```

## Integrate with other IDE or editors

### Work with lsp-python-ms in Emacs

Below is a sample code snippet showing how to make PDM work with [lsp-python-ms](https://github.com/emacs-lsp/lsp-python-ms) in Emacs. Contributed by [@linw1995](https://github.com/pdm-project/pdm/discussions/372#discussion-3303501).

```emacs-lisp
  ;; TODO: Cache result
  (defun linw1995/pdm-get-python-executable (&optional dir)
    (let ((pdm-get-python-cmd "pdm info --python"))
      (string-trim
       (shell-command-to-string
        (if dir
            (concat "cd "
                    dir
                    " && "
                    pdm-get-python-cmd)
          pdm-get-python-cmd)))))

  (defun linw1995/pdm-get-packages-path (&optional dir)
    (let ((pdm-get-packages-cmd "pdm info --packages"))
      (concat (string-trim
               (shell-command-to-string
                (if dir
                    (concat "cd "
                            dir
                            " && "
                            pdm-get-packages-cmd)
                  pdm-get-packages-cmd)))
              "/lib")))

  (use-package lsp-python-ms
    :ensure t
    :init (setq lsp-python-ms-auto-install-server t)
    :hook (python-mode
           . (lambda ()
               (setq lsp-python-ms-python-executable (linw1995/pdm-get-python-executable))
               (setq lsp-python-ms-extra-paths (vector (linw1995/pdm-get-packages-path)))
               (require 'lsp-python-ms)
               (lsp))))  ; or lsp-deferred
```
