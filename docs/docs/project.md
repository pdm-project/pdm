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

However, unlike `stack`, PDM won't use global project automatically if a local project is not found.
Users should pass `-g/--global` explicity to activate it, since it is not very pleasing if packages go to a wrong place.

!!! danger "NOTE"
    Be careful with `remove` and `sync --clean` commands when global project is used. Because it may
    remove packages installed in your system Python.

## Choose another directory as project root

The default project root is `cwd` or the nearest parent(at a max depth of 3) with a valid `pyproject.toml`,
or `~/.pdm/global-project` if `-g/--global` flag is on. If you would like a different directory, pass it
with `-p/--project` option. The project-level configuration will be changed, too.

!!! note "TIPS"
    With the help of `-g/--global` and `-p/--project` options, you can gain a familiar experience of the
    old "venv" manners: inside an activated venv: `pdm install -gp .` will install all dependencies into the
    venv's library path. To make this happen, check the content of `.pdm.toml` and make sure `python.path`
    is correct.
