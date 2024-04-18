# 使用虚拟环境

当你运行 [`pdm init`](../reference/cli.md#init) 命令时，PDM [询问要使用的Python解释器](./project.md#choose-a-python-interpreter) ，这是安装依赖项和运行任务的基本解释器。

与 [PEP 582](https://www.python.org/dev/peps/pep-0582/) 相比，虚拟环境被认为更加成熟，并且在 Python 生态系统以及 IDE 中有更好的支持。因此，默认情况下，如果未另行配置，PDM 将使用虚拟环境模式。

**如果项目解释器（存储在 `.pdm-python` 中的解释器，可以通过 `pdm info` 检查）来自虚拟环境，则将使用虚拟环境。**

## 虚拟环境自动创建

默认情况下，PDM 倾向于使用其他包管理器所使用的虚拟环境布局。当你在一个新的由 PDM 管理的项目上第一次运行 `pdm install`，且该项目的 Python 解释器尚未确定时，PDM 将在 `<project_root>/.venv` 中创建一个虚拟环境，并在其中安装依赖项。在 `pdm init` 的交互会话中，PDM 也会询问是否为你创建一个虚拟环境。

你可以选择由 PDM 使用的虚拟环境创建后端。目前支持三种后端：

- [`virtualenv`](https://virtualenv.pypa.io/)（默认）
- `venv`
- `conda`

你可以通过 `pdm config venv.backend [virtualenv|venv|conda]` 进行更改。

+++ 2.13.0

    此外，当 `python.use_venv` 配置设置为 `true` 时，PDM 在使用 `pdm use` 切换Python解释器时将始终尝试创建虚拟环境。

## 自己创建虚拟环境

你可以创建任意Python版本的多个虚拟环境。

```bash
# 基于 3.8 解释器创建虚拟环境
$ pdm venv create 3.8
# 分配一个与版本字符串不同的名称
$ pdm venv create --name for-test 3.8
# 使用 venv 作为后端创建，支持 3 个后端：virtualenv（默认）、venv、conda
$ pdm venv create --with venv 3.9
```

## 虚拟环境的位置

如果没有给出 `--name`，PDM 将在 `<project_root>/.venv` 中创建虚拟环境。否则，虚拟环境将保存在由 `venv.location` 配置指定的位置。
它们的命名方式是 `<project_name>-<path_hash>-<name_or_python_version>`，以避免名称冲突。
你可以通过 `pdm config venv.in_project false` 来禁用项目内部的虚拟环境创建。所有虚拟环境都将创建在 `venv.location` 下。

## 重用你在其他地方创建的虚拟环境

你可以告诉PDM使用你在之前步骤中创建的虚拟环境，使用 [`pdm use`](../reference/cli.md#use):

```bash
pdm use -f /path/to/venv
```

## 虚拟环境自动检测

当项目配置中未存储解释器，或者设置了 `PDM_IGNORE_SAVED_PYTHON` 环境变量时，PDM 将尝试检测可能使用的虚拟环境：

- 项目根目录中的 `venv`、`env`、`.venv` 目录
- 当前激活的虚拟环境，除非设置了 `PDM_IGNORE_ACTIVE_VENV`

## 列出所有与此项目创建的虚拟环境

```bash
$ pdm venv list
Virtualenvs created with this project:

-  3.8.6: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-3.8.6
-  for-test: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test
-  3.9.1: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-3.9.1
```

## 显示虚拟环境的路径或Python解释器

```bash
$ pdm venv --path for-test
$ pdm venv --python for-test
```

## 删除虚拟环境

```bash
$ pdm venv remove for-test
Virtualenvs created with this project:
Will remove: C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test, continue? [y/N]:y
Removed C:\Users\Frost Ming\AppData\Local\pdm\pdm\venvs\test-project-8Sgn_62n-for-test
```

## 激活虚拟环境

与 `pipenv` 和 `poetry` 不同，`pdm venv` 不会为你创建子shell，而是将激活命令打印到控制台。这样你就不会离开当前shell。然后你可以将输出提供给 `eval` 以激活虚拟环境：

=== "bash/csh/zsh"

    ```bash
    $ eval $(pdm venv activate for-test)
    (test-project-for-test) $  # 进入虚拟环境
    ```

=== "Fish"

    ```bash
    $ eval (pdm venv activate for-test)
    ```

=== "Powershell"

    ```ps1
    PS1> Invoke-Expression (pdm venv activate for-test)
    ```

    另外，如果项目解释器是一个 venv Python，你可以省略跟在 activate 后的名称参数。

!!! NOTE
    `venv activate` **不会** 切换项目使用的Python解释器。它仅通过将虚拟环境路径注入到环境变量中来更改shell。对于前述目的，请使用 `pdm use` 命令。

更多CLI使用方法，请参阅 [`pdm venv`](../reference/cli.md#venv) documentation.

!!! TIP "寻找 `pdm shell`?"
    PDM 不提供 `shell` 命令，因为许多复杂的 shell 函数在子 shell 中可能无法完美工作，这会给支持所有边缘情况带来维护负担。但是，你仍然可以通过以下方式获得此功能：

    - 使用 `pdm run $SHELL`，这将以正确设置环境变量的方式生成一个子shell。**子shell 可以使用 `exit` 或 `Ctrl+D` 退出。**
    - 添加一个激活虚拟环境的shell函数，以下是一个在BASH中也适用于ZSH的示例：

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

    复制并粘贴此函数到你的 `~/.bashrc` 文件中，并重新启动shell。

    对于 `fish` shell，你可以将以下内容放入你的 `~/fish/config.fish` 或 `~/.config/fish/config.fish`：


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

    现在你可以运行 `pdm shell` 来激活虚拟环境。
    **虚拟环境可以像往常一样使用 `deactivate` 命令来停用。**

## 提示定制

默认情况下，当你激活一个虚拟环境时，提示将显示为：`{project_name}-{python_version}`。

例如，如果你的项目名为 `test-project`：

```bash
$ eval $(pdm venv activate for-test)
(test-project-3.10) $  # {project_name} == test-project and {python_version} == 3.10
```

格式可以在虚拟环境创建之前通过 [`venv.prompt`](../reference/configuration.md) 配置或 `PDM_VENV_PROMPT` 环境变量进行自定义（在 `pdm init` 或 `pdm venv create` 之前）。
可用的变量有：

- `project_name`: 你的项目名称
- `python_version`: Python版本（用于虚拟环境）

```bash
$ PDM_VENV_PROMPT='{project_name}-py{python_version}' pdm venv create --name test-prompt
$ eval $(pdm venv activate test-prompt)
(test-project-py3.10) $
```

## 在不激活虚拟环境的情况下运行虚拟环境中的命令

```bash
# 运行脚本
$ pdm run --venv test test
# 安装包
$ pdm sync --venv test
# 列出已安装的包
$ pdm list --venv test
```

还有其他支持 `--venv` 标志或 `PDM_IN_VENV` 环境变量的命令，请参阅 [CLI reference](../reference/cli.md)。在使用此功能之前，你应该使用 `pdm venv create --name <name>` 创建虚拟环境。

## 将虚拟环境切换为项目环境

默认情况下，如果你使用 pdm use 并选择了非 venv 的Python，则项目将切换到 [PEP 582 模式](./pep582.md)。我们还允许你通过 `--venv` 标志切换到一个命名的虚拟环境：

```bash
# 切换到名为 test 的虚拟环境
$ pdm use --venv test
# 切换到项目根目录下的 .venv 位置的虚拟环境
$ pdm use --venv in-project
```

## 禁用虚拟环境模式

你可以通过 `pdm config python.use_venv false` 来禁用虚拟环境的自动创建和自动检测。
**如果禁用了 venv，即使选择的解释器来自虚拟环境，PDM 也将始终使用 PEP 582 模式。**

## 在虚拟环境中包含pip

默认情况下，PDM 不会在虚拟环境中包含 pip。
这增加了隔离性，确保虚拟环境中仅安装了 _你当前项目的依赖项_。

要安装 `pip` 一次（例如，如果你想在CI中安装任意依赖项），你可以运行：

```bash
# 在虚拟环境中安装pip
$ pdm run python -m ensurepip
# 安装任意依赖项
# 这些依赖项不会与锁定文件中的依赖项进行冲突检查！
$ pdm run python -m pip install coverage
```

或者你可以使用 `--with-pip` 在创建虚拟环境时包含 `pip`：

```bash
$ pdm venv create --with-pip 3.9
```

有关 ensurepip 的更多详细信息，请参阅 [ensurepip 文档](https://docs.python.org/3/library/ensurepip.html)。

如果你想永久配置PDM以在虚拟环境中包含 pip，你可以使用 [`venv.with_pip`](../reference/configuration.md) 配置。
