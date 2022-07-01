# Manage Environments

When you run [`pdm init`](cli_reference.md#exec-0--init) command, PDM will [ask for the Python interpreter to use](project.md#choose-a-python-interpreter) in the project, which is the base interpreter to install dependencies and run tasks.
**The type of the Python interpreter being used(and stored in `.pdm.toml` in the project root) determines how the project stores
your dependencies.**

## Virtual environments mode

**This type is used if the project interpreter(the interpreter stored in `.pdm.toml`, which can be checked by `pdm info`) is from a virtualenv.**

By default, PDM prefers to use the virtualenv layout as other package managers do. When you run `pdm install` the first time on a new PDM-managed project, whose Python interpreter is not decided yet, PDM will create a virtualenv in `<project_root>/.venv`, and install dependencies into it. In the interactive session of `pdm init`, PDM will also ask to create a virtualenv for you.

You can choose the backend used by PDM to create a virtualenv. Currently we support three backends:

- [`virtualenv`](https://virtualenv.pypa.io/)(default)
- `venv`
- `conda`

You can change it by `pdm config venv.backend [virtualenv|venv|conda]`.

### Create a virtualenv yourself

You can create more than one virtualenvs with whatever Python version you want.

```bash
# Create a virtualenv based on 3.8 interpreter
$ pdm venv create 3.8
# Assign a different name other than the version string
$ pdm venv create --name for-test 3.8
# Use venv as the backend to create, support 3 backends: virtualenv(default), venv, conda
$ pdm venv create --with venv 3.9
```

### The location of virtualenvs

For the first time, PDM will try to create a virtualenv **in project**, unless `.venv` already exists.
Other virtualenvs go to the location specified by the `venv.location` configuration. They are named as `<project_name>-<path_hash>-<name_or_python_version>` to avoid name collision. A virtualenv created with `--name` option will always go to this location. You can disable the in-project virtualenv creation by `pdm config venv.in_project false`.

### Virtualenv auto-detection

When no interpreter is stored in the project config or `PDM_IGNORE_SAVED_PYTHON` env var is set, PDM will try to detect possible virtualenvs to use:

- `venv`, `env`, `.venv` directories in the project root
- The currently activated virtualenv

### List all virtualenvs created with this project

```bash
$ pdm venv list
Virtualenvs created with this project:

-  3.8.6: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-3.8.6
-  for-test: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test
-  3.9.1: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-3.9.1
```

### Remove a virtualenv

```bash
$ pdm venv remove for-test
Virtualenvs created with this project:
Will remove: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test, continue? [y/N]:y
Removed C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test
```

### Activate a virtualenv

Instead of spawning a subshell like what `pipenv` and `poetry` do, `pdm-venv` doesn't create the shell for you but print the activate command to the console. In this way you won't leave the current shell. You can then feed the output to `eval` to activate the virtualenv:

=== "bash/csh/zsh"

    ```bash
    $ eval $(pdm venv activate for-test)
    (test-project-8Sgn_62n-for-test) $  # Virtualenv entered
    Fish

    $ eval (pdm venv activate for-test)
    ```

=== "Powershell"

    ```ps1
    PS1> Invoke-Expression (pdm venv activate for-test)
    ```

    You can make your own shell shortcut function to avoid the input of long command. Here is an example of Bash:

    ```ps1
    pdm_venv_activate() {
        eval $('pdm' 'venv' 'activate' "$1")
    }
    ```

    Then you can activate it by `pdm_venv_activate $venv_name` and deactivate by deactivate directly.

    Additionally, if the project interpreter is a venv Python, you can omit the name argument following activate.

!!! NOTE
    `venv activate` **does not** switch the Python interpreter used by the project. It only changes the shell by injecting the virtualenv paths to environment variables. For the forementioned purpose, use the `pdm use` command.

For more CLI usage, see the [`pdm venv`](cli_reference.md#exec-0--venv) documentation.

## PEP 582 mode

**When the project interpreter is a normal Python, this mode is enabled.**

Dependencies will be installed into `__pypackages__` directory under the project root. With [PEP 582 enabled globally](../index.md#enable-pep-582-globally), you can also use the project interpreter to run scripts directly.

## Disable virtualenv mode

You can disable the auto-creation and auto-detection for virtualenv by `pdm config python.use_venv` false.
**If venv is disabled, PEP 582 mode will always be used even if the selected interpreter is from a virtualenv.**
