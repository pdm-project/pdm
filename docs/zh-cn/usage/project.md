# 新建项目

首先，使用以下命令 [`pdm init`](../reference/cli.md#init) 创建一个新项目：

```bash
mkdir my-project && cd my-project
pdm init
```

您需要回答几个问题，以帮助 PDM 为您创建 `pyproject.toml` 文件。
有关 `pdm init` 更多用法，请阅读 [从模板创建项目](./template.md)。

## 选择 Python 解释器

首先，您需要从已安装在您的计算机上的 Python 版本列表中选择一个 Python 解释器。
解释器路径将被存储在 `.pdm-python` 文件中，并在后续命令中使用。您还可以稍后使用 [`pdm use`](../reference/cli.md#use)命令更改它。

或者，您可以通过 `PDM_PYTHON`环境变量指定 Python 解释器路径。设置后，保存的 `.pdm-python` 路径将被忽略。

## 使用 PDM 安装 Python 解释器

+++ 2.13.0

PDM 支持使用命令 `pdm python install` 从 [@indygreg's python-build-standalone](https://github.com/indygreg/python-build-standalone) 安装其他 Python 解释器。
例如，要安装 CPython 3.9.8：

```bash
pdm python install 3.9.8
```

您可以使用 `pdm python install --list` 查看所有可用的 Python 版本。

这会将 Python 解释器安装到 `python.install_root` 配置指定的位置。

列出当前安装的 Python 解释器：

```bash
pdm python list
```

删除已安装的 Python 解释器：

```bash
pdm python remove 3.9.8
```

!!! TIP "与 Rye 共享安装"

    PDM 使用与 [Rye](https://rye-up.com) 相同的源来安装 Python 解释器。如果您同时使用 Rye，则可以将 `python.install_root` 指向与 Rye 相同的目录以共享 Python 解释器：

    ```bash
    pdm config python.install_root ~/.rye/py
    ```

    之后，您可以使用 `rye toolchain` 或 `pdm python`来管理安装。

## 是否使用虚拟环境

选择 Python 解释器后，PDM 将询问您是否要为项目创建虚拟环境。如果选择“是”，PDM 将在项目根目录中创建一个虚拟环境，并将其用作项目的 Python 解释器。

如果所选的 Python 解释器位于虚拟环境中，PDM 会将其用作项目环境，并在其中安装依赖项。否则，  `__pypackages__` 将在项目根目录中创建，并将依赖项安装到其中。

有关这两种方法的区别，请参阅文档中的相应部分：

- [Virtualenv](./venv.md)
- [`__pypackages__`(PEP 582)](./pep582.md)

## 库或应用程序

库和应用程序在许多方面有所不同。简而言之，库是旨在由其他项目安装和使用的包。在大多数情况下，它还需要上传到 PyPI。另一方面，应用程序是直接面向最终用户的应用程序，可能需要部署到某些生产环境中。

在PDM中，如果选择创建一个库，PDM 会向 `pyproject.toml` 文件添加 `name`、`version` 字段，以及一个 [build backend](../reference/build.md) 表格用于构建后端，这只有在您的项目需要构建和分发时才有用。因此，如果您想将项目从应用程序更改为库，您需要手动添加这些字段到 `pyproject.toml` 中。此外，当您运行 `pdm install` 或 `pdm sync` 时，库项目将被安装到环境中，除非指定了`--no-self`。

## 设定 `requires-python` 值

您需要为项目设置适当的 `requires-python` 值。这是一个重要属性，会影响依赖关系的解析方式。基本上，每个包 `requires-python` 都必须**涵盖**项目的 `requires-python`  范围。
例如，请考虑以下设置：

- 项目: `requires-python = ">=3.9"`
- 包 `foo`: `requires-python = ">=3.7,<3.11"`

解析依赖关系将导致 `Resolution Impossible` 错误:

```
Unable to find a resolution because the following dependencies don't work
on all Python versions defined by the project's `requires-python`
```

因为依赖项 `requires-python` 是 `>=3.7,<3.11`，所以它不覆盖项目的 `requires-python` 范围 `>=3.9`。换句话说，该项目承诺在 Python 3.9、3.10、3.11（等）上运行，但依赖项不支持 Python 3.11（或更高版本）。由于 PDM 创建了一个跨平台锁定文件，该文件应适用于 `requires-python` 该范围内的所有 Python 版本，因此它找不到有效的解决方案。要解决此问题，您需要将最大版本添加到 `requires-python` 中，例如 `>=3.9,<3.11`。

`requires-python` 的值是根据 [PEP 440](https://peps.python.org/pep-0440/#version-specifiers)定义的版本指定符。以下是一些示例：

| `requires-python`       | 含义                                  |
| ----------------------- | ---------------------------------------- |
| `>=3.7`                 | Python 3.7 及更高版本                     |
| `>=3.7,<3.11`           | Python 3.7, 3.8, 3.9 和 3.10            |
| `>=3.6,!=3.8.*,!=3.9.*` | Python 3.6 及更高版本，3.8 和 3.9 除外 |

## 使用较旧的 Python 版本

尽管 PDM 在 Python 3.8 及更高版本上运行，但您仍然可以为 **工作项目** 使用较低的 Python 版本。但请记住，如果你的项目是一个需要构建、发布或安装的库，你要确保正在使用的 PEP 517 构建后端支持你需要的最低 Python 版本。例如，默认后端 `pdm-backend` 仅适用于 Python 3.7+，因此如果您在使用 Python 3.6 的项目上运行 [`pdm build`](../reference/cli.md#build)，则会收到错误。大多数现代构建后端都放弃了对 Python 3.6 及更低版本的支持，因此强烈建议将 Python 版本升级到 3.7+。以下是一些常用构建后端支持的 Python 范围，我们只列出那些支持 PEP 621 的后端，否则 PDM 无法使用它们。

| Backend               | 支持的 Python | 支持 PEP 621 |
| --------------------- | ---------------- | --------------- |
| `pdm-backend`         | `>=3.7`          | Yes             |
| `setuptools>=60`      | `>=3.7`          | Experimental    |
| `hatchling`           | `>=3.7`          | Yes             |
| `flit-core>=3.4`      | `>=3.6`          | Yes             |
| `flit-core>=3.2,<3.4` | `>=3.4`          | Yes             |

请注意，如果您的项目是应用程序（即没有 `name` 元数据），则上述后端限制不适用。因此，如果您不需要构建后端，则可以使用任何 Python 版本 `>=2.7`。

## 从其他包管理器导入项目

如果您已经在使用其他包管理器工具，如 Pipenv 或 Poetry，则很容易迁移到 PDM。
PDM 提供了 `import` 命令，因此您不必手动初始化项目，它现在支持：

1. Pipenv `Pipfile`
2. Poetry 的 `pyproject.toml` 部分
3. Flit 的 `pyproject.toml` 部分
4. pip 使用的格式 `requirements.txt`
5. setuptools `setup.py`（它要求在项目环境中安装 `setuptools`。您可以通过为venv配置 `venv.with_pip` 为 `true`，并为 `__pypackages__` 添加 `pdm add setuptools` 来实现此目的）

此外，当您执行 [`pdm init`](../reference/cli.md#init)  或 [`pdm install`](../reference/cli.md#install) 时，如果您的 PDM 项目尚未初始化，PDM 可以自动检测可能要导入的文件。

!!! info
    转换一个 `setup.py` 将使用项目解释器执行文件。确保 `setuptools`与解释器一起安装，并且 是可信的 `setup.py`。

## 使用版本控制

您 **必须** 提交 `pyproject.toml` 文件。您**应该**提交 `pdm.lock` 和 `pdm.toml` 文件。**不要** commit 提交 `.pdm-python` 文件。

必须提交该 `pyproject.toml` 文件，因为它包含项目的构建元数据和 PDM 所需的依赖项。
它也通常被其他 python 工具用于配置。在 [Pip 文档](https://pip.pypa.io/en/stable/reference/build-system/pyproject-toml/) 中阅读有关该 `pyproject.toml` 文件的更多信息。

您应该提交文件 `pdm.lock` ，这样可以确保所有安装程序都使用相同版本的依赖项。若要了解如何更新依赖项，请参阅 [更新现有依赖项](./dependency.md#update-existing-dependencies)。

`pdm.toml` 包含一些项目范围的配置，提交它以供共享可能很有用。

`.pdm-python`  存储当前项目使用的 **Python 路径**，**不需要** 共享。

## 显示当前 Python 环境

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

# 查看虚拟环境信息
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
  "platform_python_implementation": "CPython",
  "python_version": "3.8",
  "sys_platform": "win32"
}
```

[pdm info](../reference/cli.md#info)这个命令可用于检查项目正在使用的模式：

- 如果 *Project Packages* 是 `None`, 则启用 [virtualenv mode](./venv.md) 模式。
- 否则，将启用 [PEP 582 mode](./pep582.md) 模式。

现在，您已经设置了一个新的 PDM 项目并获取了一个 `pyproject.toml` 文件。请参阅[元数据](../reference/pep621.md)部分，了解如何正确编写 `pyproject.toml`。
