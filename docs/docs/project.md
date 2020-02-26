# Manage project

PDM can act as a PEP 517 build backend, to enable that, write the following lines in your
`pyproject.toml`. If you used `pdm init` to create it for you, it should be done already.

```toml
[build-system]
requires = ["pdm"]
build-backend = "pdm.builders.api"
```

`pip` will read the backend settings to install or build a package.

!!! note "About editable installation"
    As described, [PEP 517](https://www.python.org/dev/peps/pep-0517/) doesn't provide a
    way to specify how to install a package in editable mode. So you can't install a PEP 517
    package by `pip install -e <path_or_url>`. But PDM can install a "PDM package" in editable
    mode.

## Choose a Python interpreter

If you have used `pdm init`, you must have already seen how PDM detects and selects the Python
interpreter. After initialized, you can also change the settings by `pdm use <python_version_or_path>`.
The argument can be either a version specifier of any length, or a relative or absolute path to the
python interpreter, but remember the Python interpreter must be compatible with `python_requires`
constraint in the project file.

### How `python_requires` controls the project

PDM respects the value of `python_requires` in the way that it tries to pick package candidates that can work
on all python versions that `python_requires` contains. For example if `python_requires` is `>=2.7`, PDM will try
to find the latest version of `foo`, whose `python_requires` version range is a **superset** of `>=2.7`.

So, make sure you write `python_requires` properly if you don't want any outdated packages to be locked.


## Build distribution artifacts

```bash
$ pdm build
- Building sdist...
- Built pdm-test-0.0.0.tar.gz
- Building wheel...
- Built pdm_test-0.0.0-py3-none-any.whl
```
The artifacts can then be uploaded to PyPI by [twine](https://pypi.org/project/twine).
