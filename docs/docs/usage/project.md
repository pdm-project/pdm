# Manage Project

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
python interpreter, but remember the Python interpreter must conform with the `python_requires`
constraint in the project file.

### How `requires-python` controls the project

PDM respects the value of `requires-python` in the way that it tries to pick package candidates that can work
on all python versions that `requires-python` contains. For example, if `requires-python` is `>=2.7`, PDM will try
to find the latest version of `foo`, whose `requires-python` version range is a **superset** of `>=2.7`.

So, make sure you write `requires-python` properly if you don't want any outdated packages to be locked.

## Build distribution artifacts

```console
$ pdm build
- Building sdist...
- Built pdm-test-0.0.0.tar.gz
- Building wheel...
- Built pdm_test-0.0.0-py3-none-any.whl
```

The artifacts can then be uploaded to PyPI by [twine](https://pypi.org/project/twine) or using the
[pdm-publish](https://github.com/branchvincent/pdm-publish) plugin. Available options can be found by
typing `pdm build --help`.

??? note "Looking for publish support?"
    If you are looking for `publish` subcommand as poetry, you can refer to the [pdm-publish](https://github.com/branchvincent/pdm-publish) plugin.
    Indeed, most of the time, publishing should be handled by CI/CD pipelines.

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
pdm config
```

Get one single configuration:

```console
pdm config pypi.url
```

Change a configuration value and store in home configuration:

```console
pdm config pypi.url "https://test.pypi.org/simple"
```

By default, the configuration are changed globally, if you want to make the config seen by this project only, add a `--local` flag:

```console
pdm config --local pypi.url "https://test.pypi.org/simple"
```

Any local configurations will be stored in `.pdm.toml` under the project root directory.

The configuration files are searched in the following order:

1. `<PROJECT_ROOT>/.pdm.toml` - The project configuration
2. `~/.pdm/config.toml` - The home configuration

If `-g/--global` option is used, the first item will be replaced by `~/.pdm/global-project/.pdm.toml`.

You can find all available configuration items in [Configuration Page](../configuration.md).

## Cache the installation of wheels

If a package is required by many projects on the system, each project has to keep its own copy. This may become a waste of disk space especially for data science and machine learning libraries.

PDM supports _caching_ the installations of the same wheel by installing it into a centralized package repository and linking to that installation in different projects. To enabled it, run:

```bash
pdm config install.cache on
```

It can be enabled on a project basis, by adding `--local` option to the command.

The caches are located under `$(pdm config cache_dir)/packages`. One can view the cache usage by `pdm cache info`. But be noted the cached installations are managed automatically -- They get deleted when not linked from any projects. Manually deleting the caches from the disk may break some projects on the system.

!!! note
    Only the installation of _named requirements_ resolved from PyPI can be cached.

## Manage global project

Sometimes users may want to keep track of the dependencies of global Python interpreter as well.
It is easy to do so with PDM, via `-g/--global` option which is supported by most subcommands.

If the option is passed, `~/.pdm/global-project` will be used as the project directory, which is
almost the same as normal project except that `pyproject.toml` will be created automatically for you
and it doesn't support build features. The idea is taken from Haskell's [stack](https://docs.haskellstack.org).

However, unlike `stack`, by default, PDM won't use global project automatically if a local project is not found.
Users should pass `-g/--global` explicitly to activate it, since it is not very pleasing if packages go to a wrong place.
But PDM also leave the decision to users, just set the config `global_project.fallback` to `true`.

If you want global project to track another project file other than `~/.pdm/global-project`, you can provide the
project path via `-p/--project <path>` option.

!!! attention "CAUTION"
    Be careful with `remove` and `sync --clean` commands when global project is used, because it may remove packages installed in your system Python.

## Working with a virtualenv

Although PDM enforces PEP 582 by default, it also allows users to install packages into the virtualenv. It is controlled
by the configuration item `python.use_venv`. When it is set to `True`, PDM will use the virtualenv if:

- a virtualenv is already activated.
- any of `venv`, `.venv`, `env` is a valid virtualenv folder.

Besides, when `python.use_venv` is on and the interpreter path given is a venv-like path, PDM will reuse that venv directory as well.

For enhanced virtualenv support such as virtualenv management and auto-creation, please go for [pdm-venv](https://github.com/pdm-project/pdm-venv),
which can be installed as a plugin.

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
only `requirements.txt` and `setup.py` format is supported:

```console
pdm export -o requirements.txt
pdm export -f setuppy -o setup.py
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

## Manage caches

PDM provides a convenient command group to manage the cache, there are four kinds of caches:

1. `wheels/` stores the built results of non-wheel distributions and files.
1. `http/` stores the HTTP response content.
1. `metadata/` stores package metadata retrieved by the resolver.
1. `hashes/` stores the file hashes fetched from the package index or calculated locally.
1. `packages/` The centrialized repository for installed wheels.

See the current cache usage by typing `pdm cache info`. Besides, you can use `add`, `remove` and `list` subcommands to manage the cache content.
Find the usage by the `--help` option of each command.

## How we make PEP 582 packages available to the Python interpreter

Thanks to the [site packages loading](https://docs.python.org/3/library/site.html) on Python startup. It is possible to patch the `sys.path`
by executing the `sitecustomize.py` shipped with PDM. The interpreter can search the directories
for the nearest `__pypackage__` folder and append it to the `sys.path` variable.
