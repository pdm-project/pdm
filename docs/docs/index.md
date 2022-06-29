<div align="center">
<img src="assets/logo_big.png" alt="PDM logo">
</div>

# Introduction

PDM, as described, is a modern Python package and dependency manager supporting the latest PEP standards. But it is more than a package manager. It boosts your development workflow in various aspects. The most significant benefit is it installs and manages packages
in a similar way to `npm` that doesn't need to create a virtualenv at all!

<script id="asciicast-jnifN30pjfXbO9We2KqOdXEhB" src="https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.js" async></script>

## Feature highlights

- [PEP 582] local package installer and runner, no virtualenv involved at all.
- Simple and fast dependency resolver, mainly for large binary distributions.
- A [PEP 517] build backend.
- [PEP 621] project metadata.
- Flexible and powerful plug-in system.
- Versatile user scripts.
- Opt-in centralized installation cache like [pnpm](https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed).

[pep 517]: https://www.python.org/dev/peps/pep-0517
[pep 582]: https://www.python.org/dev/peps/pep-0582
[pep 621]: https://www.python.org/dev/peps/pep-0621
[pnpm]: https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed

## Installation

PDM requires Python 3.7+ to be installed. It works on multiple platforms including Windows, Linux and MacOS.

!!! note
    You can still have your project working on lower Python versions, read how to do it [here](usage/project.md#working-with-python-37).

### Recommended installation method

PDM requires python version 3.7 or higher.

Like Pip, PDM provides an installation script that will install PDM into an isolated environment.

=== "Linux/Mac"

    ```bash
    curl -sSL https://raw.githubusercontent.com/pdm-project/pdm/main/install-pdm.py | python3 -
    ```

=== "Windows"

    ```powershell
    (Invoke-WebRequest -Uri https://raw.githubusercontent.com/pdm-project/pdm/main/install-pdm.py -UseBasicParsing).Content | python -
    ```

For security reasons, you should verify the checksum of `install-pdm.py`.
The sha256 checksum is: `5efebd44f477521d0d8ef0e118b7e5765ff20f80d3d4dd9394f1b8ff1094fb4d`

The installer will install PDM into the user site and the location depends on the system:

- `$HOME/.local/bin` for Unix
- `%APPDATA%\Python\Scripts` on Windows

You can pass additional options to the script to control how PDM is installed:

```
usage: install-pdm.py [-h] [-v VERSION] [--prerelease] [--remove] [-p PATH] [-d DEP]

optional arguments:
  -h, --help            show this help message and exit
  -v VERSION, --version VERSION | envvar: PDM_VERSION
                        Specify the version to be installed, or HEAD to install from the main branch
  --prerelease | envvar: PDM_PRERELEASE    Allow prereleases to be installed
  --remove | envvar: PDM_REMOVE            Remove the PDM installation
  -p PATH, --path PATH | envvar: PDM_HOME  Specify the location to install PDM
  -d DEP, --dep DEP | envvar: PDM_DEPS     Specify additional dependencies, can be given multiple times
```

You can either pass the options after the script or set the env var value.

### Other installation methods

=== "Homebrew"

    ```bash
    brew install pdm
    ```

=== "Scoop"

    ```
    scoop bucket add frostming https://github.com/frostming/scoop-frostming.git
    scoop install pdm
    ```

=== "pipx"

    ```bash
    pipx install pdm
    ```

    Install the head version of GitHub repository.
    Make sure you have installed [Git LFS](https://git-lfs.github.com/) on your system.

    ```bash
    pipx install git+https://github.com/pdm-project/pdm.git@main#egg=pdm
    ```

    See also: <https://pypa.github.io/pipx/>

=== "pip"

    ```bash
    pip install --user pdm
    ```

=== "inside project"

    By copying the [Pyprojectx](https://pyprojectx.github.io/) wrapper scripts to a project, you can install PDM as
    (npm-style) dev dependency inside that project. This allows different projects/branches to use different PDM versions.

    To [initialize a new or existing project](https://pyprojectx.github.io/usage/#initialize-a-new-or-existing-project),
    cd into the project folder and:

    === "Linux/Mac"

        ```
        curl -LO https://github.com/pyprojectx/pyprojectx/releases/latest/download/wrappers.zip && unzip wrappers.zip && rm -f wrappers.zip
        ./pw --init pdm
        ```

    === "Windows"

        ```powershell
        Invoke-WebRequest https://github.com/pyprojectx/pyprojectx/releases/latest/download/wrappers.zip -OutFile wrappers.zip; Expand-Archive -Path wrappers.zip -DestinationPath .; Remove-Item -Path wrappers.zip
        .\pw --init pdm
        ```

### Enable PEP 582 globally

To make the Python interpreters aware of PEP 582 packages, one need to add the `pdm/pep582/sitecustomize.py`
to the Python library search path.

#### For Windows users

One just needs to execute `pdm --pep582`, then environment variable will be changed automatically. Don't forget
to restart the terminal session to take effect.

#### For Mac and Linux users

The command to change the environment variables can be printed by `pdm --pep582 [<SHELL>]`. If `<SHELL>`
isn't given, PDM will pick one based on some guesses. You can run `eval "$(pdm --pep582)"` to execute the command.

You may want to write a line in your `.bash_profile`(or similar profiles) to make it effective when logging in.
For example, in bash you can do this:

```bash
pdm --pep582 >> ~/.bash_profile
```

Once again, Don't forget to restart the terminal session to take effect.

## Shell Completion

PDM supports generating completion scripts for Bash, Zsh, Fish or Powershell. Here are some common locations for each shell:

=== "Bash"

    ```bash
    pdm completion bash > /etc/bash_completion.d/pdm.bash-completion
    ```

=== "Zsh"

    ```bash
    # Make sure ~/.zfunc is added to fpath, before compinit.
    pdm completion zsh > ~/.zfunc/_pdm
    ```

    Oh-My-Zsh:

    ```bash
    mkdir $ZSH_CUSTOM/plugins/pdm
    pdm completion zsh > $ZSH_CUSTOM/plugins/pdm/_pdm
    ```

    Then make sure pdm plugin is enabled in ~/.zshrc

=== "Fish"

    ```bash
    pdm completion fish > ~/.config/fish/completions/pdm.fish
    ```

=== "Powershell"

    ```ps1
    # Create a directory to store completion scripts
    mkdir $PROFILE\..\Completions
    echo @'
    Get-ChildItem "$PROFILE\..\Completions\" | ForEach-Object {
        . $_.FullName
    }
    '@ | Out-File -Append -Encoding utf8 $PROFILE
    # Generate script
    Set-ExecutionPolicy Unrestricted -Scope CurrentUser
    pdm completion powershell | Out-File -Encoding utf8 $PROFILE\..\Completions\pdm_completion.ps1
    ```

## Use with IDE

Now there are not built-in support or plugins for PEP 582 in most IDEs, you have to configure your tools manually.

PDM will write and store project-wide configurations in `.pdm.toml` and you are recommended to add following lines
in the `.gitignore`:

```
.pdm.toml
__pypackages__/
```

### PyCharm

Mark `__pypackages__/<major.minor>/lib` as [Sources Root](https://www.jetbrains.com/help/pycharm/configuring-project-structure.html#mark-dir-project-view).
Then, select as [Python interpreter](https://www.jetbrains.com/help/pycharm/configuring-python-interpreter.html#interpreter) a Python installation with the same `<major.minor>` version.

Additionally, if you want to use tools from the environment (e.g. `pytest`), you have to add the
`__pypackages__/<major.minor>/bin` directory to the `PATH` variable in the corresponding
run/debug configuration.

### VSCode

Add the following two entries to the top-level dict in `.vscode/settings.json`:

```json
{
  "python.autoComplete.extraPaths": ["__pypackages__/<major.minor>/lib"],
  "python.analysis.extraPaths": ["__pypackages__/<major.minor>/lib"]
}
```

[Enable PEP582 globally](#enable-pep-582-globally),
and make sure VSCode runs using the same user and shell you enabled PEP582 for.

??? note "Cannot enable PEP582 globally?"
    If for some reason you cannot enable PEP582 globally, you can still configure each "launch" in each project:
    set the `PYTHONPATH` environment variable in your launch configuration, in `.vscode/launch.json`.
    For example, to debug your `pytest` run:

    ```json
    {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "pytest",
                "type": "python",
                "request": "launch",
                "module": "pytest",
                "args": ["tests"],
                "justMyCode": false,
                "env": {"PYTHONPATH": "__pypackages__/<major.minor>/lib"}
            }
        ]
    }
    ```

    If your package resides in a `src` directory, add it to `PYTHONPATH` as well:

    ```json
    "env": {"PYTHONPATH": "src:__pypackages__/<major.minor>/lib"}
    ```

??? note "Using Pylance/Pyright?"
    If you have configured `"python.analysis.diagnosticMode": "workspace"`,
    and you see a ton of errors/warnings as a result.
    you may need to create `pyrightconfig.json` in the workspace directory, and fill in the following fields:

    ```json
    {
        "exclude": ["__pypackages__"]
    }
    ```

    Then restart the language server or VS Code and you're good to go.
    In the future ([microsoft/pylance-release#1150](https://github.com/microsoft/pylance-release/issues/1150)), maybe the problem will be solved.

??? note "Using Jupyter Notebook?"
    If you wish to use pdm to install jupyter notebook and use it in vscode in conjunction with the python extension:

    1. Use `pdm add notebook` or so to install notebook
    2. Add a `.env` file inside of your project director with contents like the following:

    ```
    PYTHONPATH=/your-workspace-path/__pypackages__/<major>.<minor>/lib
    ```

    If the above still doesn't work, it's most likely because the environment variable is not properly loaded when the Notebook starts. There are two workarounds.

    1. Run `code .` in Terminal. It will open a new VSCode window in the current directory with the path set correctly. Use the Jupyter Notebook in the new window
    2. If you prefer not to open a new window, run the following at the beginning of your Jupyter Notebook to explicitly set the path:

    ```
    import sys
    sys.path.append('/your-workspace-path/__pypackages__/<major>.<minor>/lib')
    ```

    > [Reference Issue](https://github.com/pdm-project/pdm/issues/848)

#### Task Provider

In addition, there is a [VSCode Task Provider extension][pdm task provider] available for download.

This makes it possible for VSCode to automatically detect [pdm scripts][pdm scripts] so they
can be run natively as [VSCode Tasks][vscode tasks].

[vscode tasks]: https://code.visualstudio.com/docs/editor/tasks
[pdm task provider]: https://marketplace.visualstudio.com/items?itemName=knowsuchagency.pdm-task-provider
[pdm scripts]: usage/scripts.md

### Neovim

If using [neovim-lsp](https://github.com/neovim/nvim-lspconfig) with
[pyright](https://github.com/Microsoft/pyright) and want your
`__pypackages__` directory to be added to the path, you can add this to your
project's `pyproject.toml`.

```toml
[tool.pyright]
extraPaths = ["__pypackages__/<major.minor>/lib/"]
```

### [Seek for other IDEs or editors](usage/advanced.md#integrate-with-other-ide-or-editors)

## PDM Eco-system

[Awesome PDM](https://github.com/pdm-project/awesome-pdm) is a curated list of awesome PDM plugins and resources.
