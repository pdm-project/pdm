# PDM插件

PDM 的目标是成为社区驱动的包管理器。它附带一个功能齐全的插件系统，您可以通过该系统：

- 为 PDM 开发一个新的命令
- 为现有的 PDM 命令添加附加选项
- 通过读取额外的配置项来更改 PDM 的行为
- 控制依赖解析或安装的过程

## 插件应该做什么

PDM 项目的核心是专注于依赖管理和包发布。您希望与 PDM 集成的其他功能最好位于其自己的插件中，并作为独立的 PyPI 项目发布。如果插件被认为是核心项目的良好补充，它可能有机会被吸收到 PDM 中。

## 编写您自己的插件

在以下各节中，我将展示一个示例，添加一个新的命令 `hello`，它会读取 `hello.name` 配置。

### 编写命令

PDM 的 CLI 模块采用用户可以轻松“继承和修改”的方式设计。要编写新命令，请执行以下操作：

```python
from pdm.cli.commands.base import BaseCommand

class HelloCommand(BaseCommand):
    """向指定的人打招呼。
    如果未指定，将从"hello.name"配置中读取。
    """

    def add_arguments(self, parser):
        parser.add_argument("-n", "--name", help="要问候的人的姓名")

    def handle(self, project, options):
        if not options.name:
            name = project.config["hello.name"]
        else:
            name = options.name
        print(f"Hello, {name}")
```

首先，让我们创建一个新的 `HelloCommand` 类，它继承自 `pdm.cli.commands.base.BaseCommand`。它有两个主要函数：

- `add_arguments()` 用于操作传递给它的参数解析器，您可以向其中添加额外的命令行参数
- `handle()` 在子命令匹配时执行某些操作，您可以通过编写单个 `pass` 语句来不执行任何操作。它接受两个参数：第一个是 `pdm.project.Project` 对象，第二个是解析的 `argparse.Namespace` 对象。

文档字符串将用作命令帮助文本，在 `pdm --help` 中显示。

此外，PDM 的子命令具有两个默认选项：`-v/--verbose` 用于更改详细程度和 `-g/--global` 用于启用全局项目。如果您不想要这些默认选项，请将 `arguments` 类属性重写为 `pdm.cli.options.Option` 对象的列表，或者将其分配为空列表以没有默认选项：

```python hl_lines="3"
class HelloCommand(BaseCommand):

    arguments = []
```

!!! note
    默认选项首先加载，然后调用 `add_arguments()`。

### 将命令注册到核心对象

在插件项目的某个位置编写一个函数。对于函数的名称没有限制，但是该函数应该只接受一个参数 ——PDM 核心对象：

```python hl_lines="2"
def hello_plugin(core):
    core.register_command(HelloCommand, "hello")
```

调用 `core.register_command()` 以注册命令。作为子命令名称的第二个参数是可选的。如果未传递名称，PDM 将查找 `HelloCommand` 的 `name` 属性。

### 添加一个新的配置项

让我们回顾一下第一个代码片段，`hello.name` 如果不通过命令行传递，则会参考名称的配置键。

```python hl_lines="11"
class HelloCommand(BaseCommand):
    """向指定的人打招呼。
    如果未指定，将从"hello.name"配置中读取。
    """

    def add_arguments(self, parser):
        parser.add_argument("-n", "--name", help="要问候的人的姓名")

    def handle(self, project, options):
        if not options.name:
            name = project.config["hello.name"]
        else:
            name = options.name
        print(f"Hello, {name}")
```

到目前为止，如果通过 `pdm config get hello.name` 查询配置值，将弹出错误，说明它不是有效的配置键。您需要注册配置项：

```python hl_lines="5"
from pdm.project.config import ConfigItem

def hello_plugin(core):
    core.register_command(HelloCommand, "hello")
    core.add_config("hello.name", ConfigItem("The person's name", "John"))
```

其中 `ConfigItem` 类按照以下顺序接受4个参数：

- `description`: 配置项的描述
- `default`: 配置项的默认值
- `global_only`: 配置是否只允许在主目录配置中设置
- `env_var`: 将作为配置值读取的环境变量的名称

### 其他插件点

除了命令和配置之外，该 core 对象还公开了一些其他方法和属性以重写。PDM 还提供一些您可以收听的信号。有关详细信息，请阅读 [API 参考](../reference/api.md)。

### 开发 PDM 插件的技巧

在开发插件时，希望激活并在代码更改时得到更新。

您可以通过在可编辑模式下安装插件来实现这一点。为此，请在 `tool.pdm.plugins` 数组中指定依赖项：

```toml
[tool.pdm]
plugins = [
    "-e file:///${PROJECT_ROOT}"
]
```

然后用以下命令安装：

```bash
pdm install --plugins
```

之后，所有依赖项都可在项目插件库中使用，包括插件本身，以可编辑模式安装。这意味着对代码库的任何更改都会立即生效，无需重新安装。`pdm` 可执行文件也在幕后使用Python解释器，因此如果您从插件项目内运行 `pdm`，插件开发模式将自动激活，并且您可以进行一些测试以查看其工作原理。

### 测试您的插件

PDM 在 [pdm.pytest](fixtures.md) 模块中以插件形式公开了一些pytest fixtures。
要从中受益，必须将 pdm[pytest] 添加为测试依赖项。

要在测试中启用它们，请将 `pdm.pytest` 添加为插件。您可以在根 `conftest.py` 中这样做：

```python title="conftest.py"
# 单个插件
pytest_plugins = "pytest.plugin"

# 多个插件
pytest_plugins = [
    ...
    "pdm.pytest",
    ...
]
```

您可以在 PDM 自己的 [tests](https://github.com/pdm-project/pdm/tree/main/tests)中看到一些用法示例，特别是关于 [conftest.py 文件](https://github.com/pdm-project/pdm/blob/main/tests/conftest.py) 的配置。

有关更多详细信息，请参阅 [pytest fixtures 文档](fixtures.md)。

## 发布您的插件

现在您已经定义了自己的插件，让我们将其分发到PyPI。PDM的插件通过入口点类型进行发现。
创建一个 `pdm` 入口点并指向您的插件可调用对象（是的，它不需要是函数，任何可调用对象都可以工作）：

**PEP 621**:

```toml
# pyproject.toml

[project.entry-points.pdm]
hello = "my_plugin:hello_plugin"
```

**setuptools**:

```python
# setup.py

setup(
    ...
    entry_points={"pdm": ["hello = my_plugin:hello_plugin"]}
    ...
)
```

## 激活插件

由于插件是通过入口点加载的，因此激活插件不需要更多步骤，只需安装插件即可。
为方便起见，PDM 提供了一个 `plugin` 命令组来管理插件。

假设您的插件发布为 `pdm-hello`：

```bash
pdm self add pdm-hello
```

现在在终端中键入 `pdm --help`，您将看到新添加的 `hello` 命令，并使用它：

```bash
$ pdm hello Jack
Hello, Jack
```

通过在终端中键入 `pdm self --help`，可以看到更多插件管理子命令。

## 在项目中指定插件

要为项目指定所需的插件，您可以使用 `pyproject.toml` 文件中的 `tool.pdm.plugins` 配置。
通过运行 `pdm install --plugins`，可以将这些依赖项安装到项目插件库中。
项目插件库将在后续的PDM命令中加载。

当您希望与项目的贡献者共享相同的插件集时，这非常有用。

```toml
# pyproject.toml
[tool.pdm]
plugins = [
    "pdm-packer"
]
```

运行 `pdm install --plugins` 来安装并激活插件。

或者，您可以使用可编辑的本地依赖项具有项目本地插件，这些插件未发布到PyPI：

```toml
# pyproject.toml
[tool.pdm]
plugins = [
    "-e file:///${PROJECT_ROOT}/plugins/my_plugin"
]
```
