# Manage project

PDM can act as a PEP 517 build backend, to enable that, write the following lines in your
`pyproject.toml`. If you used `pdm init` to create it for you, it should be done already.

```toml
[build-system]
requires = ["pdm-pep517"]
build-backend = "pdm.pep517.api"
```

`pip` will read the backend settings to install or build a package.

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

```console
$ pdm build
- Building sdist...
- Built pdm-test-0.0.0.tar.gz
- Building wheel...
- Built pdm_test-0.0.0-py3-none-any.whl
```

The artifacts can then be uploaded to PyPI by [twine](https://pypi.org/project/twine).

## Show the current Python environment

```console
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

## Configure the project

PDM's `config` command works just like `git config`, except that `--list` isn't needed to
show configurations.

Show the current configurations:

```console
$ pdm config
```

Get one single configuration:

```console
$ pdm config pypi.url
```

Change a configuration value and store in home configuration:

```console
$ pdm config pypi.url "https://testpypi.org/simple"
```

Change a configuration value and store in `.pdm.toml`:

```console
$ pdm config --local pypi.url "https://testpypi.org/simple"
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

!!! attention "CAUTION"
    Be careful with `remove` and `sync --clean` commands when global project is used, because it may remove packages installed in your system Python.

## Working with a virtualenv

Although PDM enforces PEP 582 by default, it also allows users to install packages into the virtualenv. It is controlled
by the configuration item `use_venv`. When it is set to `True` PDM will use the virtualenv if:

- a virtualenv is already activated.
- any of `venv`, `.venv`, `env` is a valid virtualenv folder.

Besides, when `use-venv` is on and the interpreter path given is a venv-like path, PDM will reuse that venv directory as well.

## Import project metadata from existing project files

If you are already other package manager tools like Pipenv or Poetry, it is easy to migrate to PDM.
PDM provides `import` command so that you don't have to initialize the project manually, it now supports:

1. Pipenv's `Pipfile`
2. Poetry's section in `pyproject.toml`
3. Flit's section in `pyproject.toml`
4. `requirements.txt` format used by Pip

Also, when you are executing `pdm init` or `pdm install`, PDM can auto-detect possible files to import
if your PDM project has not been initialized yet.

## Export locked packages to alternative formats

You can also export `pdm.lock` to other formats, to ease the CI flow or image building process. Currently,
only `requirements.txt` format is supported:

```console
$ pdm export -o requirements.txt
```

## Hide the credentials from pyproject.toml

There are many times when we need to use sensitive information, such as login credentials for the PyPI server
and username passwords for VCS repositories. We do not want to expose this information in `pyproject.toml` and upload it to git.

PDM provides several methods to achieve this:

1. User can give the auth information with environment variables which are encoded in the URL directly:

   ```toml
   [[tool.pdm.source]]
   url = "http://${INDEX_USER}:${INDEX_PASSWD}@test.pypi.org/simple"
   name = "test"
   verify_ssl = false

   [project]
   dependencies = [
     "mypackage @ git+http://${VCS_USER}:${VCS_PASSWD}@test.git.com/test/mypackage.git@master"
   ]
   ```

   Environment variables must be encoded in the form `${ENV_NAME}`, other forms are not supported. Besides, only auth part will be expanded.

2. If the credentials are not provided in the URL and a 401 response is received from the server, PDM will prompt for username and password when `-v/--verbose`
   is passed as command line argument, otherwise PDM will fail with an error telling users what happens. Users can then choose to store the credentials in the
   keyring after a confirmation question.

3. A VCS repository applies the first method only, and an index server applies both methods.

## Available Configurations

| Config Item                   | Description                                                               | Default Value                                                             | Available in Project | Env var                  |
| ----------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------- | ------------------------ |
| `cache_dir`                   | The root directory of cached files                                        | The default cache location on OS                                          | No                   |                          |
| `auto_global`                 | Use global package implicitly if no local project is found                | `False`                                                                   | No                   | `PDM_AUTO_GLOBAL`        |
| `use_venv`                    | Install packages into the activated venv site packages instead of PEP 582 | `False`                                                                   | Yes                  | `PDM_USE_VENV`           |
| `parallel_install`            | Whether to perform installation and uninstallation in parallel            | `True`                                                                    | Yes                  | `PDM_PARALLEL_INSTALL`   |
| `python.path`                 | The Python interpreter path                                               |                                                                           | Yes                  | `PDM_PYTHON_PATH`        |
| `python.use_pyenv`            | Use the pyenv interpreter                                                 | `True`                                                                    | Yes                  |                          |
| `pypi.url`                    | The URL of PyPI mirror                                                    | Read `index-url` in `pip.conf`, or `https://pypi.org/simple` if not found | Yes                  | `PDM_PYPI_URL`           |
| `pypi.verify_ssl`             | Verify SSL certificate when query PyPI                                    | Read `trusted-hosts` in `pip.conf`, defaults to `True`                    | Yes                  |                          |
| `pypi.json_api`               | Consult PyPI's JSON API for package metadata                              | `False`                                                                   | Yes                  | `PDM_PYPI_JSON_API`      |
| `strategy.save`               | Specify how to save versions when a package is added                      | `compatible`(can be: `exact`, `wildcard`)                                 | Yes                  |                          |
| `strategy.update`             | The default strategy for updating packages                                | `reuse`(can be : `eager`)                                                 | Yes                  |                          |
| `strategy.resolve_max_rounds` | Specify the max rounds of resolution process                              | 1000                                                                      | Yes                  | `PDM_RESOLVE_MAX_ROUNDS` |

_If the env var is set, the value will take precedence over what is saved in the config file._

## Run Scripts in Isolated Environment

With PDM, you can run arbitrary scripts or commands with local packages loaded:

```bash
$ pdm run flask run -p 54321
```

PDM also supports custom script shortcuts in the optional `[tool.pdm.scripts]` section of `pyproject.toml`.

You can then run `pdm run <shortcut_name>` to invoke the script in the context of your PDM project. For example:

```toml
[tool.pdm.scripts]
start_server = "flask run -p 54321"
```

And then in your terminal:

```bash
$ pdm run start_server
Flask server started at http://127.0.0.1:54321
```

Any extra arguments will be appended to the command:

```bash
$ pdm run start_server -h 0.0.0.0
Flask server started at http://0.0.0.0:54321
```

PDM supports 3 types of scripts:

### Normal command

Plain text scripts are regarded as normal command, or you can explicitly specify it:

```toml
[tool.pdm.scripts]
start_server = {cmd = "flask run -p 54321"}
```

### Shell script

Shell scripts can be used to run more shell-specific tasks, such as pipeline and output redirecting.
This is basically run via `subprocess.Popen()` with `shell=True`:

```toml
[tool.pdm.scripts]
filter_error = {shell = "cat error.log|grep CRITICAL > critical.log"}
```

### Call a Python function

The script can be also defined as calling a python function in the form `<module_name>:<func_name>`:

```toml
[tool.pdm.scripts]
foobar = {call = "foo_package.bar_module:main"}
```

The function can be supplied with literal arguments:

```toml
[tool.pdm.scripts]
foobar = {call = "foo_package.bar_module:main('dev')"}
```

### Environment variables support

All environment variables set in the current shell can be seen by `pdm run` and will be expanded when executed.
Besides, you can also define some fixed environment variables in your `pyproject.toml`:

```toml
[tool.pdm.scripts]
start_server.cmd = "flask run -p 54321"
start_server.env = {FOO = "bar", FLASK_ENV = "development"}
```

Note how we use [TOML's syntax](https://github.com/toml-lang/toml) to define a compound dictionary.

A dotenv file is also supported via `env_file = "<file_path>"` setting.

For environment variables and/or dotenv file shared by all scripts, you can define `env` and `env_file`
settings under a special key named `_` of `tool.pdm.scripts` table:

```toml
[tool.pdm.scripts]
_.env_file = ".env"
start_server = "flask run -p 54321"
migrate_db = "flask db upgrade"
```

### Show the list of scripts shortcuts

Use `pdm run --list/-l` to show the list of available script shortcuts:

```bash
$ pdm run --list
Name        Type  Script           Description
----------- ----- ---------------- ----------------------
test_cmd    cmd   flask db upgrade
test_script call  test_script:main call a python function
test_shell  shell echo $FOO        shell command
```

You can add an `help` option with the description of the script, and it will be displayed in the `Description` column in the above output.

## How we make PEP 582 packages available to the Python interpreter

Thanks to the [site packages loading](https://docs.python.org/3/library/site.html) on Python startup. It is possible to patch the `sys.path`
by executing the `sitecustomize.py` shipped with PDM. The interpreter can search the directories
for the nearest `__pypackage__` folder and append it to the `sys.path` variable.
