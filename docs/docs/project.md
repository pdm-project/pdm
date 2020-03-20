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

## Show the current Python environment

```bash
$ pdm info
Python Interpreter: D:/Programs/Python/Python38/python.exe (3.8.0)
Project Root:       D:/Workspace/pdm
                                                                                                                                   [10:42]
$ pdm info --env
{
  "implementation_name": "cpython",
  "implementation_version": "3.8.0",
  "os_name": "nt",
  "platform_machine": "AMD64",
  "platform_release": "10",
  "platform_system": "Windows",
  "platform_version": "10.0.18362",
  "python_full_version": "3.8.0",
  "platform_python_implementaiton": "CPython",
  "python_version": "3.8",
  "sys_platform": "win32"
}
```

## Configrate the project

Show the configurations:
```bash
$ pdm config
```
Get one single configuration:
```bash
$ pdm config get pypi.url
```
Change a configuration value and store in home configuration:
```bash
$ pdm config set pypi.url "https://testpypi.org/simple"
```
Change a configuration value and store in `.pdm.toml`:
```bash
$ pdm config set --local pypi.url "https://testpypi.org/simple"
```

The configuration files are searched in the following order:

1. `<PROJECT_ROOT>/.pdm.toml` - The project configuration
2. `~/.pdm/config.toml` - The home configuration

If `-g/--global` option is used, `~/.pdm/global-project/.pdm.toml` will replace the first item.

## Manage global project

Sometimes users may want to keep track of the dependencies of global Python interpreter.
It is easy to do it with PDM, via `-g/--global` option which is supported by most subcommands.

If the option is passed, `~/.pdm/global-project` will be used as the project directory, which is
almost the same as normal project except that `pyproject.toml` will be created automatically for you
and it doesn't support build features. The idea is taken from Haskell's [stack](https://docs.haskellstack.org).

However, unlike `stack`, by default, PDM won't use global project automatically if a local project is not found.
Users should pass `-g/--global` explicitly to activate it, since it is not very pleasing if packages go to a wrong place.
To change this behavior, simply change the config `auto_global` to `true`.

If you want global project to track another project file other than `~/.pdm/global-project`, you can provide the
project path following `-g/--global`.

!!! danger "NOTE"
    Be careful with `remove` and `sync --clean` commands when global project is used. Because it may
    remove packages installed in your system Python.


## Working inside a virtualenv

Although PDM enforces PEP 582 by default, it also allows users to install packages into the virtualenv. It is controlled
by the configuration item `use_venv`, when it is set to `True`, PDM will use the virtualenv **when it is activated**.

## Configurations

| Config Item | Description | Default Value | Available in Project | Env var |
| ----------- | ----------- | ------------- | -------------------- | ------- |
| `cache_dir` | The root directory of cached files | The default cache location on OS | No | |
| `auto_global` | Use global package implicity if no local project is found | `False` | No | `PDM_AUTO_GLOBAL` |
| `use_venv` | Install packages into the activated venv site packages instead of PEP 582 | `False` | Yes | `PDM_USE_VENV` |
| `parallel_install` | Whether to perform installation and uninstallation in parallel | `True` | Yes | `PDM_PARALLEL_INSTALL` |
| `python.path` | The Python interpreter path | | Yes | `PDM_PYTHON_PATH` |
| `python.use_pyenv` | Use the pyenv interpreter | `True` | Yes | |
| `pypi.url` | The URL of PyPI mirror | Read `index-url` in `pip.conf`, or `https://pypi.org/simple` if not found | Yes | `PDM_PYPI_URL` |
| `pypi.verify_ssl` | Verify SSL certificate when query PyPI | Read `trusted-hosts` in `pip.conf`, defaults to `True` | Yes | |
| `pypi.json_api` | Consult PyPI's JSON API for package metadata | `True` | Yes | `PDM_PYPI_JSON_API` |

*If the env var is set, the value will take precendence over what is saved in the config file.*
