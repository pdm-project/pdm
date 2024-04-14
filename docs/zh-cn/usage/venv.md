# Working with Virtual Environments

When you run [`pdm init`](../reference/cli.md#init) command, PDM will [ask for the Python interpreter to use](./project.md#choose-a-python-interpreter) in the project, which is the base interpreter to install dependencies and run tasks.

Compared to [PEP 582](https://www.python.org/dev/peps/pep-0582/), virtual environments are considered more mature and have better support in the Python ecosystem as well as IDEs. Therefore, virtualenv is the default mode if not configured otherwise.

**Virtual environments will be used if the project interpreter (the interpreter stored in `.pdm-python`, which can be checked by `pdm info`) is from a virtualenv.**

## Virtualenv auto-creation

By default, PDM prefers to use the virtualenv layout as other package managers do. When you run `pdm install` the first time on a new PDM-managed project, whose Python interpreter is not decided yet, PDM will create a virtualenv in `<project_root>/.venv`, and install dependencies into it. In the interactive session of `pdm init`, PDM will also ask to create a virtualenv for you.

You can choose the backend used by PDM to create a virtualenv. Currently it supports three backends:

- [`virtualenv`](https://virtualenv.pypa.io/)(default)
- `venv`
- `conda`

You can change it by `pdm config venv.backend [virtualenv|venv|conda]`.

+++ 2.13.0

    Moreover, when `python.use_venv` config is set to `true`, PDM will always try to create a virtualenv when using `pdm use` to switch the Python interpreter.

## Create a virtualenv yourself

You can create more than one virtualenvs with whatever Python version you want.

```bash
# Create a virtualenv based on 3.8 interpreter
$ pdm venv create 3.8
# Assign a different name other than the version string
$ pdm venv create --name for-test 3.8
# Use venv as the backend to create, support 3 backends: virtualenv(default), venv, conda
$ pdm venv create --with venv 3.9
```

## The location of virtualenvs

If no `--name` is given, PDM will create the venv in `<project_root>/.venv`. Otherwise, virtualenvs go to the location specified by the `venv.location` configuration.
They are named as `<project_name>-<path_hash>-<name_or_python_version>` to avoid name collision.
You can disable the in-project virtualenv creation by `pdm config venv.in_project false`. And all virtualenvs will be created under `venv.location`.

## Reuse the virtualenv you created elsewhere

You can tell PDM to use a virtualenv you created in preceding steps, with [`pdm use`](../reference/cli.md#use):

```bash
pdm use -f /path/to/venv
```

## Virtualenv auto-detection

When no interpreter is stored in the project config or `PDM_IGNORE_SAVED_PYTHON` env var is set, PDM will try to detect possible virtualenvs to use:

- `venv`, `env`, `.venv` directories in the project root
- The currently activated virtualenv, unless `PDM_IGNORE_ACTIVE_VENV` is set

## List all virtualenvs created with this project

```bash
$ pdm venv list
Virtualenvs created with this project:

-  3.8.6: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-3.8.6
-  for-test: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test
-  3.9.1: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-3.9.1
```

## Show the path or python interpreter of a virtualenv

```bash
$ pdm venv --path for-test
$ pdm venv --python for-test
```

## Remove a virtualenv

```bash
$ pdm venv remove for-test
Virtualenvs created with this project:
Will remove: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test, continue? [y/N]:y
Removed C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test
```

## Activate a virtualenv

Instead of spawning a subshell like what `pipenv` and `poetry` do, `pdm venv` doesn't create the shell for you but print the activate command to the console. In this way you won't leave the current shell. You can then feed the output to `eval` to activate the virtualenv:

=== "bash/csh/zsh"

    ```bash
    $ eval $(pdm venv activate for-test)
    (test-project-for-test) $  # Virtualenv entered
    ```

=== "Fish"

    ```bash
    $ eval (pdm venv activate for-test)
    ```

=== "Powershell"

    ```ps1
    PS1> Invoke-Expression (pdm venv activate for-test)
    ```

    Additionally, if the project interpreter is a venv Python, you can omit the name argument following activate.

!!! NOTE
    `venv activate` **does not** switch the Python interpreter used by the project. It only changes the shell by injecting the virtualenv paths to environment variables. For the forementioned purpose, use the `pdm use` command.

For more CLI usage, see the [`pdm venv`](../reference/cli.md#venv) documentation.

!!! TIP "Looking for `pdm shell`?"
    PDM doesn't provide a `shell` command because many fancy shell functions may not work perfectly in a subshell, which brings a maintenance burden to support all the corner cases. However, you can still gain the ability via the following ways:

    - Use `pdm run $SHELL`, this will spawn a subshell with the environment variables set properly. **The subshell can be quit with `exit` or `Ctrl+D`.**
    - Add a shell function to activate the virtualenv, here is an example of BASH function that also works on ZSH:

      ```bash
      pdm() {
        local command=$1

        if [[ "$command" == "shell" ]]; then
            eval $(pdm venv activate)
        else
            command pdm $@
        fi
      }
      ```

      Copy and paste this function to your `~/.bashrc` file and restart your shell.

      For `fish` shell you can put the following into your `~/fish/config.fish` or in `~/.config/fish/config.fish`

      ```fish
        function pdm
            set cmd $argv[1]

            if test "$cmd" = "shell"
                eval (pdm venv activate)
            else
                command pdm $argv
            end
        end
      ```

      Now you can run `pdm shell` to activate the virtualenv.
      **The virtualenv can be deactivated with `deactivate` command as usual.**

## Prompt customization

By default when you activate a virtualenv, the prompt will show: `{project_name}-{python_version}`.

For example if your project is named `test-project`:


```bash
$ eval $(pdm venv activate for-test)
(test-project-3.10) $  # {project_name} == test-project and {python_version} == 3.10
```

The format can be customized before virtualenv creation with the [`venv.prompt`](../reference/configuration.md) configuration or `PDM_VENV_PROMPT` environment variable (before a `pdm init` or `pdm venv create`).
Available variables are:

 - `project_name`: name of your project
 - `python_version`: version of Python (used by the virtualenv)

```bash
$ PDM_VENV_PROMPT='{project_name}-py{python_version}' pdm venv create --name test-prompt
$ eval $(pdm venv activate test-prompt)
(test-project-py3.10) $
```

## Run a command in a virtual environment without activating it

```bash
# Run a script
$ pdm run --venv test test
# Install packages
$ pdm sync --venv test
# List the packages installed
$ pdm list --venv test
```

There are other commands supporting `--venv` flag or `PDM_IN_VENV` environment variable, see the [CLI reference](../reference/cli.md). You should create the virtualenv with `pdm venv create --name <name>` before using this feature.

## Switch to a virtualenv as the project environment

By default, if you use `pdm use` and select a non-venv Python, the project will be switched to [PEP 582 mode](./pep582.md). We also allow you to switch to a named virtual environment via the `--venv` flag:

```bash
# Switch to a virtualenv named test
$ pdm use --venv test
# Switch to the in-project venv located at $PROJECT_ROOT/.venv
$ pdm use --venv in-project
```

## Disable virtualenv mode

You can disable the auto-creation and auto-detection for virtualenv by `pdm config python.use_venv false`.
**If venv is disabled, PEP 582 mode will always be used even if the selected interpreter is from a virtualenv.**

## Including pip in your virtual environment

By default PDM will not include `pip` in virtual environments.
This increases isolation by ensuring that _only your dependencies_ are installed in the virtual environment.

To install `pip` once (if for example you want to install arbitrary dependencies in CI) you can run:

```bash
# Install pip in the virtual environment
$ pdm run python -m ensurepip
# Install arbitrary dependencies
# These dependencies are not checked for conflicts against lockfile dependencies!
$ pdm run python -m pip install coverage
```

Or you can create the virtual environment with `--with-pip`:

```bash
$ pdm venv create --with-pip 3.9
```

See the [ensurepip docs](https://docs.python.org/3/library/ensurepip.html) for more details on `ensurepip`.

If you want to permanently configure PDM to include `pip` in virtual environments you can use the [`venv.with_pip`](../reference/configuration.md) configuration.
