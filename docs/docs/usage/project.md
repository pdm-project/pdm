# Manage Project

## Choose a Python interpreter

If you have used [`pdm init`](cli_reference.md#exec-0--init), you must have already seen how PDM detects and selects the Python
interpreter. After initialized, you can also change the settings by `pdm use <python_version_or_path>`.
The argument can be either a version specifier of any length, or a relative or absolute path to the
python interpreter, but remember the Python interpreter must conform with the `requires-python`
constraint in the project file.

!!! note "Application or Library"
    You may have noticed that PDM will ask you whether the project is a library to be uploaded to PyPI. [Here is an good explanation](https://pipenv.pypa.io/en/latest/advanced/#pipfile-vs-setup-py) of the difference between them. PDM knows that by inspecting the `project.name` field in `pyproject.toml`. If it is not empty, it will be considered as a library. A library can be built by `pdm build` or other PEP 517 builders, and itself will be installed in *editable* mode every time you execute `pdm sync` or `pdm install`, unless opted out with `--no-self` option. On the contrary, an application isn't installable because it's missing the project `name`.

### How `requires-python` controls the project

PDM respects the value of `requires-python` in the way that it tries to pick package candidates that can work
on all python versions that `requires-python` contains. For example, if `requires-python` is `>=2.7`, PDM will try
to find the latest version of `foo`, whose `requires-python` version range is a **superset** of `>=2.7`.

So, make sure you write `requires-python` properly if you don't want any outdated packages to be locked.

### Working with Python < 3.7

Although PDM run on Python 3.7 and above, you can still have lower Python versions for your **working project**. But remember, if your project is a library, which needs to be built, published or installed, you make sure the PEP 517 build backend being used supports the lowest Python version you need. For instance, the default backend `pdm-pep517` only works on Python 3.7+, so if you run `pdm build` on a project with Python 3.6, you will get an error. Most modern build backends have dropped the support for Python 3.6 and lower, so it is highly recommended to upgrade the Python version to 3.7+. Here are the supported Python range for some commonly used build backends, we only list those that support PEP 621 since otherwise PDM can't work with them.

| Backend               | Supported Python | Support PEP 621 |
| --------------------- | ---------------- | --------------- |
| `pdm-pep517`          | `>=3.7`          | Yes             |
| `setuptools>=60`      | `>=3.7`          | Experimental    |
| `hatchling`           | `>=3.7`          | Yes             |
| `flit-core>=3.4`      | `>=3.6`          | Yes             |
| `flit-core>=3.2,<3.4` | `>=3.4`          | Yes             |

Note that if your project is an application(without `name` metadata), the above limitation of backends don't apply, since you don't need a build backend after all, and you can use a Python version up to `2.7`.

## Build distribution artifacts

```bash
$ pdm build
- Building sdist...
- Built pdm-test-0.0.0.tar.gz
- Building wheel...
- Built pdm_test-0.0.0-py3-none-any.whl
```

The artifacts will be available at `dist/` and able to upload to PyPI.

## Configure the project

PDM's `config` command works just like `git config`, except that `--list` isn't needed to
show configurations.

Show the current configurations:

```bash
pdm config
```

Get one single configuration:

```bash
pdm config pypi.url
```

Change a configuration value and store in home configuration:

```bash
pdm config pypi.url "https://test.pypi.org/simple"
```

By default, the configuration are changed globally, if you want to make the config seen by this project only, add a `--local` flag:

```bash
pdm config --local pypi.url "https://test.pypi.org/simple"
```

Any local configurations will be stored in `.pdm.toml` under the project root directory.

The configuration files are searched in the following order:

1. `<PROJECT_ROOT>/.pdm.toml` - The project configuration
2. `<CONFIG_ROOT>/config.toml` - The home configuration
3. `<SITE_CONFIG_ROOT>/config.toml` - The site configuration

where `<CONFIG_ROOT>` is:

- `$XDG_CONFIG_HOME/pdm` (`~/.config/pdm` in most cases) on Linux as defined by [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- `~/Library/Preferences/pdm` on MacOS as defined by [Apple File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- `%USERPROFILE%\AppData\Local\pdm` on Windows as defined in [Known folders](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders)

and `<SITE_CONFIG_ROOT>` is:

- `$XDG_CONFIG_DIRS/pdm` (`/etc/xdg/pdm` in most cases) on Linux as defined by [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- `/Library/Preferences/pdm` on MacOS as defined by [Apple File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- `C:\ProgramData\pdm\pdm` on Windows as defined in [Known folders](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders)

If `-g/--global` option is used, the first item will be replaced by `<CONFIG_ROOT>/global-project/.pdm.toml`.

You can find all available configuration items in [Configuration Page](configuration.md).

## Publish the project to PyPI

With PDM, you can build and then upload your project to PyPI in one step.

```bash
pdm publish
```

You can specify which repository you would like to publish:

```bash
pdm publish -r pypi
```

PDM will look for the repository named `pypi` from the configuration and use the URL for upload.
You can also give the URL directly with `-r/--repository` option:

```bash
pdm publish -r https://test.pypi.org/simple
```

See all supported options by typing `pdm publish --help`.

### Configure the repository secrets for upload

When using the [`pdm publish`](cli_reference.md#exec-0--publish) command, it reads the repository secrets from the *global* config file(`<CONFIG_ROOT>/config.toml`). The content of the config is as follows:

```toml
[repository.pypi]
username = "frostming"
password = "<secret>"

[repository.company]
url = "https://pypi.company.org/legacy/"
username = "frostming"
password = "<secret>"
ca_certs = "/path/to/custom-cacerts.pem"
```

A PEM-encoded Certificate Authority bundle (`ca_certs`) can be used for local / custom PyPI repositories where the server certificate is not signed by the standard [certifi](https://github.com/certifi/python-certifi/blob/master/certifi/cacert.pem) CA bundle.

!!! NOTE
    You don't need to configure the `url` for `pypi` and `testpypi` repositories, they are filled by default values.

!!! TIP
    The username, password, and certificate authority bundle can be passed in from the command line for `pdm publish` via `--username`, `--password`, and `--ca-certs`, respectively.

To change the repository config from the command line, use the [`pdm config`](cli_reference.md#exec-0--config) command:

```bash
pdm config repository.pypi.username "__token__"
pdm config repository.pypi.password "my-pypi-token"

pdm config repository.company.url "https://pypi.company.org/legacy/"
pdm config repository.company.ca_certs "/path/to/custom-cacerts.pem"
```

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

## Show the current Python environment

```bash
$ pdm info
PDM version:
  2.0.0
Python Interpreter:
  /opt/homebrew/opt/python@3.9/bin/python3.9 (3.9)
Project Root:
  /Users/fming/wkspace/github/test-pdm
Project Packages:
  /Users/fming/wkspace/github/test-pdm/__pypackages__/3.9

# Show environment info
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

[This command](cli_reference.md#exec-0--info) is useful for checking which mode is being used by the project:

- If *Project Packages* is `None`, [virtualenv mode](venv.md) is enabled.
- Otherwise, [PEP 582 mode](pep582.md) is enabled.

## Manage global project

Sometimes users may want to keep track of the dependencies of global Python interpreter as well.
It is easy to do so with PDM, via `-g/--global` option which is supported by most subcommands.

If the option is passed, `<CONFIG_ROOT>/global-project` will be used as the project directory, which is
almost the same as normal project except that `pyproject.toml` will be created automatically for you
and it doesn't support build features. The idea is taken from Haskell's [stack](https://docs.haskellstack.org).

However, unlike `stack`, by default, PDM won't use global project automatically if a local project is not found.
Users should pass `-g/--global` explicitly to activate it, since it is not very pleasing if packages go to a wrong place.
But PDM also leave the decision to users, just set the config `global_project.fallback` to `true`.

By default, when `pdm` uses global project implicitly the following message is printed: `Project is not found, fallback to the global project`. To disable this message set the config `global_project.fallback_verbose` to `false`.

If you want global project to track another project file other than `<CONFIG_ROOT>/global-project`, you can provide the
project path via `-p/--project <path>` option.

!!! attention "CAUTION"
    Be careful with `remove` and `sync --clean/--pure` commands when global project is used, because it may remove packages installed in your system Python.

## Import project metadata from existing project files

If you are already using other package manager tools like Pipenv or Poetry, it is easy to migrate to PDM.
PDM provides `import` command so that you don't have to initialize the project manually, it now supports:

1. Pipenv's `Pipfile`
2. Poetry's section in `pyproject.toml`
3. Flit's section in `pyproject.toml`
4. `requirements.txt` format used by pip
5. setuptools `setup.py`

Also, when you are executing [`pdm init`](cli_reference.md#exec-0--init) or [`pdm install`](cli_reference.md#exec-0--install), PDM can auto-detect possible files to import if your PDM project has not been initialized yet.

!!! attention "CAUTION"
    Converting a `setup.py` will execute the file with the project interpreter. Make sure `setuptools` is installed with the interpreter and the `setup.py` is trusted.

## Export locked packages to alternative formats

You can also export [`pdm lock`](cli_reference.md#exec-0--lock) to other formats, to ease the CI flow or image building process. Currently,
only `requirements.txt` and `setup.py` format is supported:

```bash
pdm export -o requirements.txt
pdm export -f setuppy -o setup.py
```

!!! NOTE
    You can also run `pdm export` with a [`.pre-commit` hook](advanced.md#hooks-for-pre-commit).

## Working with version control

You **must** commit the `pyproject.toml` file. You **should** commit the `pdm.lock` file. **Do not** commit the `.pdm.toml` file.

The `pyproject.toml` file must be committed as it contains the project's build metadata and dependencies needed for PDM.
It is also commonly used by other python tools for configuration. Read more about the `pyproject.toml` file at
[pip.pypa.io/en/stable/reference/build-system/pyproject-toml/](https://pip.pypa.io/en/stable/reference/build-system/pyproject-toml/).

You should be committing the `pdm.lock` file, by doing so you ensure that all installers are using the same versions of dependencies.
To learn how to update dependencies see [update existing dependencies](dependency.md#update-existing-dependencies).

It is not necessary to commit your `.pdm.toml` file as it contains configuration specific to your system.
If you are using git you can safely add `.pdm.toml` to your `.gitignore` file.

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

PDM provides a convenient command group to manage the cache, there are five different caches:

1. `wheels/` stores the built results of non-wheel distributions and files.
1. `http/` stores the HTTP response content.
1. `metadata/` stores package metadata retrieved by the resolver.
1. `hashes/` stores the file hashes fetched from the package index or calculated locally.
1. `packages/` The centralized repository for installed wheels.

See the current cache usage by typing `pdm cache info`. Besides, you can use `add`, `remove` and `list` subcommands to manage the cache content.
Find the usage by the `--help` option of each command.

