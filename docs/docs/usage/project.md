# New Project

To start with, create a new project with [`pdm init`](../reference/cli.md#exec-0--init):

```bash
mkdir my-project && cd my-project
pdm init
```

You will need to answer a few questions, to help PDM to create a `pyproject.toml` file for you.

## Choose a Python interpreter

At first, you need to choose a Python interpreter from a list of Python versions installed on your machine. The interpreter path
will be stored in `.pdm-python` and used by subsequent commands. You can also change it later with [`pdm use`](../reference/cli.md#exec-0--use).

## Virtualenv or not

After you select the Python interpreter, PDM will ask you whether you want to create a virtual environment for the project.
If you choose yes, PDM will create a virtual environment in the project root directory, and use it as the Python interpreter
for the project.

If the selected Python interpreter is in a virtual environment, PDM will use it as the project environment and install dependencies
into it. Otherwise, `__pypackages__` will be created in the project root and dependencies will be installed into it.

For the difference between these two approaches, please refer to the corresponding sections in the docs:

- [Virtualenv](./venv.md)
- [`__pypackages__`(PEP 582)](./pep582.md)

## Library or Application

A library and an application differ in many ways, [here is a good explanation](https://pipenv.pypa.io/en/latest/advanced/#pipfile-vs-setup-py) for them. In short, a library is a package that is intended to be installed and used by other projects.
Usually it also needs to be uploaded to PyPI. An application, on the other hand, is one that is directly facing end users and may need to be deployed into production.

In PDM, if you choose to create a library, PDM will add a `name`, `version` field to the `pyproject.toml` file, as well as a `[build-system]` table for the [build backend](../reference/build.md), which is only useful if your project needs to be built and distributed. So you need to manually add these fields to `pyproject.toml` if you want to change the project from an application to a library. Also, a library project will be installed into the environment when you run `pdm install` or `pdm sync`, unless `--no-self` is specified.

## Set `requires-python` value

You need to set an appropriate `requires-python` value for your project. This is an important property that affects how dependencies are resolved. Basically, each package's `requires-python` must *cover* the project's `requires-python` range. For example, consider the following setup:

- Project: `requires-python = ">=3.9"`
- Package `foo`: `requires-python = ">=3.7,<3.11"`

Resolving the dependencies will cause a `ResolutionImpossible`:

```
Unable to find a resolution because the following dependencies don't work
on all Python versions defined by the project's `requires-python`
```

Because the dependency's `requires-python` is `>=3.7,<3.11`, it *doesn't* cover the project's `requires-python` range of `>=3.9`. In other words, the project promises to work on Python 3.11 and above, but the dependency doesn't support it. Since PDM creates a cross-platform lockfile that should work on all Python versions within the `requires-python` range, it can't find a valid resolution.
To fix this, you need add a maximum version to `requires-python`, like `>=3.9,<3.11`.

The value of `requires-python` is a [version specifier as defined in PEP 440](https://peps.python.org/pep-0440/#version-specifiers). Here are some examples:

| `requires-python`       | Meaning                                  |
| ----------------------- | ---------------------------------------- |
| `>=3.7`                 | Python 3.7 and above                     |
| `>=3.7,<3.11`           | Python 3.7, 3.8 and 3.10                 |
| `>=3.6,!=3.8.*,!=3.9.*` | Python 3.6 and above, except 3.8 and 3.9 |

## Working with Python < 3.7

Although PDM run on Python 3.7 and above, you can still have lower Python versions for your **working project**. But remember, if your project is a library, which needs to be built, published or installed, you make sure the PEP 517 build backend being used supports the lowest Python version you need. For instance, the default backend `pdm-pep517` only works on Python 3.7+, so if you run [`pdm build`](../reference/cli.md#exec-0--build) on a project with Python 3.6, you will get an error. Most modern build backends have dropped the support for Python 3.6 and lower, so it is highly recommended to upgrade the Python version to 3.7+. Here are the supported Python range for some commonly used build backends, we only list those that support PEP 621 since otherwise PDM can't work with them.

| Backend               | Supported Python | Support PEP 621 |
| --------------------- | ---------------- | --------------- |
| `pdm-pep517`          | `>=3.7`          | Yes             |
| `setuptools>=60`      | `>=3.7`          | Experimental    |
| `hatchling`           | `>=3.7`          | Yes             |
| `flit-core>=3.4`      | `>=3.6`          | Yes             |
| `flit-core>=3.2,<3.4` | `>=3.4`          | Yes             |

Note that if your project is an application(without `name` metadata), the above limitation of backends don't apply, since you don't need a build backend after all, and you can use a Python version up to `2.7`.

## Import the project from other package managers

If you are already using other package manager tools like Pipenv or Poetry, it is easy to migrate to PDM.
PDM provides `import` command so that you don't have to initialize the project manually, it now supports:

1. Pipenv's `Pipfile`
2. Poetry's section in `pyproject.toml`
3. Flit's section in `pyproject.toml`
4. `requirements.txt` format used by pip
5. setuptools `setup.py`(It requires `setuptools` to be installed in the project environment. You can do this by configuring `venv.with_pip` to `true` for venv and `pdm add setuptools` for `__pypackages__`)

Also, when you are executing [`pdm init`](../reference/cli.md#exec-0--init) or [`pdm install`](../reference/cli.md#exec-0--install), PDM can auto-detect possible files to import if your PDM project has not been initialized yet.

!!! info
    Converting a `setup.py` will execute the file with the project interpreter. Make sure `setuptools` is installed with the interpreter and the `setup.py` is trusted.

## Working with version control

You **must** commit the `pyproject.toml` file. You **should** commit the `pdm.lock` and `pdm.toml` file. **Do not** commit the `.pdm-python` file.

The `pyproject.toml` file must be committed as it contains the project's build metadata and dependencies needed for PDM.
It is also commonly used by other python tools for configuration. Read more about the `pyproject.toml` file at
[Pip documentation](https://pip.pypa.io/en/stable/reference/build-system/pyproject-toml/).

You should be committing the `pdm.lock` file, by doing so you ensure that all installers are using the same versions of dependencies.
To learn how to update dependencies see [update existing dependencies](./dependency.md#update-existing-dependencies).

`pdm.toml` contains some project-wide configuration and it may be useful to commit it for sharing.

`.pdm-python` stores the **Python path** used by the **current** project and doesn't need to be shared.

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

[This command](../reference/cli.md#exec-0--info) is useful for checking which mode is being used by the project:

- If *Project Packages* is `None`, [virtualenv mode](./venv.md) is enabled.
- Otherwise, [PEP 582 mode](./pep582.md) is enabled.

Now, you have setup a new PDM project and get a `pyproject.toml` file. Refer to [metadata section](../reference/pep621.md)
about how to write `pyproject.toml` properly.
