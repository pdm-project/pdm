# 锁定文件

PDM 仅从名为 `pdm.lock` 的现有锁定文件安装软件包。此文件是安装依赖项的唯一事实来源。锁定文件包含基本信息，例如：

- 所有软件包及其版本
- 包的文件名和哈希值
- （可选）用于下载包的源 URL（另请参阅：[静态 URL](#static-urls)）i
- 每个包的依赖项和标记（另请参阅：[从父级继承元数据](#inherit-the-metadata-from-parents)）

若要创建或覆盖锁定文件，请运行 [`pdm lock`](../reference/cli.md#lock),它支持与 [`pdm add`](../reference/cli.md#add) 相同的 [更新策略](./dependency.md#about-update-strategy)。此外 [`pdm install`](../reference/cli.md#install) 和 [`pdm add`](../reference/cli.md#add) 命令还将自动创建 `pdm.lock` 文件。

??? NOTE "我应该添加到 `pdm.lock` 版本控制吗？"

    这要视情况而定。如果目标是使 CI 使用与本地开发相同的依赖项版本并避免意外失败，则应将该 `pdm.lock` 文件添加到版本控制中。否则，如果你的项目是一个库，并且你希望 CI 模拟用户站点上的安装，以确保 PyPI 上的当前版本不会破坏任何内容，则不要提交该 `pdm.lock` 文件。

## 安装固定在锁定文件中的包

有一些类似的命令可以完成这项工作，但略有不同：

- [`pdm sync`](../reference/cli.md#sync) 从锁定文件安装软件包。
- [`pdm update`](../reference/cli.md#update) 将更新锁定文件，然后 `pdm sync` 更新 .
- [`pdm install`](../reference/cli.md#install) 将检查项目文件是否有更改，如果需要更新锁定文件，然后 `pdm sync`。

`pdm sync` 还有几个选项可以管理已安装的软件包：

- `--clean`: 将删除不再在锁定文件中的软件包
- `--only-keep`: 仅保留选定的包（使用 或 --prod 等 -G 选项）。

## 锁定文件中的哈希值

默认情况下， `pdm install` 将检查锁定文件是否与 的内容匹配 `pyproject.toml` ，这是通过在锁定文件中存储内容 `pyproject.toml` 哈希来完成的。

要检查锁定文件中的哈希值是否为最新，请执行以下操作：

```bash
pdm lock --check
```

如果要在不更改依赖项的情况下刷新锁定文件，可以使用以下 `--refresh` 选项：

```bash
pdm lock --refresh
```

此命令还会刷新锁定文件中记录的所有文件哈希。

## 指定要使用的其他锁定文件

默认情况下，PDM 在当前目录中使用 `pdm.lock`。您可以使用选项 `-L/--lockfile` 或 `PDM_LOCKFILE` 环境变量指定另一个锁定文件：

```bash
pdm install --lockfile my-lockfile.lock
```

此命令从 `my-lockfile.lock` 而不是 `pdm.lock` 安装软件包。

当不同环境存在冲突的依赖关系时，备用锁文件很有帮助。在这种情况下，如果将它们作为一个整体锁定，PDM 将引发错误。因此，您必须[选择依赖项组的子集](./dependency.md#select-a-subset-of-dependency-groups-to-install)并单独锁定它们。

举个实际的例子，你的项目依赖于一个 `werkzeug` 发布版本，你可能希望在开发时使用它的本地开发中副本。您可以将以下内容添加到您的 `pyproject.toml`：

```toml
[project]
requires-python = ">=3.7"
dependencies = ["werkzeug"]

[tool.pdm.dev-dependencies]
dev = ["werkzeug @ file:///${PROJECT_ROOT}/dev/werkzeug"]
```

然后，使用不同的选项运行 `pdm lock` 以生成用于不同目的的锁定文件：

```bash
# 锁定默认依赖项和开发依赖项，并将结果写入pdm.lock文件中，
# 同时将werkzeug的本地副本固定。
pdm lock
# 锁定默认依赖项，并将结果写入pdm.prod.lock文件中
# 同时将werkzeug的发布版本固定。
pdm lock --prod -L pdm.prod.lock
```

检查锁定文件中的 `metadata.groups` 字段以查看包含哪些组。

## 不写入锁定文件的选项

有时您想在不更新锁定文件的情况下添加或更新依赖项，或者您不想生成 `pdm.lock` ，您可以使用以下 `--frozen-lockfile` 选项：

```bash
pdm add --frozen-lockfile flask
```

在这种情况下，锁定文件（如果存在）将变为只读，不会对其执行写入操作。但是，如果需要，仍将执行依赖项解析步骤。

## 锁定策略

目前，我们支持三个标志来控制锁定行为： `cross_platform` 、 `static_urls` 和 `direct_minimal_versions` ，含义如下文。
您可以通过提供逗号分隔的列表或多次传递该选项， `pdm lock` 将一个或多个标志传递给 `by --strategy/-S` 选项。
这两个命令的工作方式相同：

```bash
pdm lock -S cross_platform,static_urls
pdm lock -S cross_platform -S static_urls
```

这些标志将在锁定文件中编码，并在您下次运行 `pdm lock` 时被读取。但是您可以通过在标志名称前面加上以下 `no_` 内容来禁用标志：

```bash
pdm lock -S no_cross_platform
```

此命令使锁定文件不跨平台。

### Cross platform

**全平台**

+++ 2.6.0

默认情况下，生成的锁定文件是**跨平台**的，这意味着在解析依赖项时不考虑当前平台。结果锁定文件将包含所有可能的平台和 Python 版本的轮子和依赖项。但是，有时当版本不包含所有轮子时，这会导致错误的锁定文件。为避免这种情况，您可以告诉 PDM 创建一个仅适用于**此平台**的锁定文件，修剪与当前平台无关的车轮。这可以通过将 `--strategy no_cross_platform` 选项传递给以下 `pdm lock` 选项来完成：

```bash
pdm lock --strategy no_cross_platform
```

### Static URLs

**静态 URL**

+++ 2.8.0

默认情况下，PDM 仅将包的文件名存储在锁文件中，这有利于跨不同包索引的可重用性。但是，如果要将包的静态 URL 存储在锁定文件中，则可以将 `--strategy static_urls` 选项传递给 `pdm lock`：

```bash
pdm lock --strategy static_urls
```

将保存并记住同一锁定文件的设置。您也可以通过 `--strategy no_static_urls` 禁用它。

### Direct minimal versions

**直接最小版本**

+++ 2.10.0

当它通过传递 `--strategy direct_minimal_versions` 启用时，将 `pyproject.toml` 解析为可用的最小版本，而不是最新版本。当您想要在依赖项版本范围内测试项目的兼容性时，这很有用。

例如，如果在 `pyproject.toml` 中指定 `flask>=2.0`, `flask` 则在没有其他兼容性问题的情况下，将解析为版本 `2.0.0`。

!!! NOTE
    包依赖项中的版本约束不是面向未来的。如果将依赖项解析为最低版本，则可能会出现向后兼容性问题。
    例如， `flask==2.0.0` 需要 `werkzeug>=2.0`，但实际上它不能与 `Werkzeug 3.0.0`一起使用 ，后者在它发布 2 年后发布。

### Inherit the metadata from parents

**从父级继承元数据**

+++ 2.11.0

以前，该 `pdm lock` 命令将按原样记录包元数据。安装时，PDM 将从最高需求开始，向下遍历到依赖树的叶节点。然后，它将针对当前环境评估它遇到的任何标记。如果标记不满意，则包将被丢弃。换句话说，我们需要在安装中增加一个“解决”步骤。

启用该 `inherit_metadata` 策略后，PDM 将从包的祖先继承并合并环境标记。然后，在锁定期间将这些标记编码到锁定文件中，从而加快安装速度。这已从版本 2.11.0 默认启用，要在配置中禁用此策略，请使用 `pdm config strategy.inherit_metadata false`。

### Exclude packages newer than specific date

**排除比特定日期更加新的软件包**

+++ 2.13.0

您可以通过将 `--exclude-newer` 选项传递给 `pdm lock` 来排除比指定日期更加新的包。当您想要将依赖项锁定到特定日期时，例如，以确保生成的可重现性，这非常有用。

日期可以指定为 RFC 3339 时间戳（例如，`2006-12-02T02:07:43Z`）或相同格式（例如 `2006-12-02`）的 UTC 日期。

```bash
pdm lock --exclude-newer 2024-01-01
```

!!! note
    包索引必须支持 [PEP 700] 中指定的 `upload-time` 字段。如果给定分布的字段不存在，则该分布将被视为不可用。

[PEP 700]: https://peps.python.org/pep-0700/

## 设置可接受的锁定或安装格式

如果要控制软件包的格式（二进制格式 `binary`/源码分发格式 `sdist`），可以设置环境变量 `PDM_NO_BINARY` 和 `PDM_ONLY_BINARY`。

每个 env var 都是一个以逗号分隔的包名列表。您可以将其 `:all:` 设置为应用于所有包。例如：

```
# 不会锁定werkzeug的二进制文件，也不会用于安装
PDM_NO_BINARY=werkzeug pdm add flask
# 只有二进制文件将被锁定在锁定文件中
PDM_ONLY_BINARY=:all: pdm lock
# 不会使用任何二进制文件进行安装
PDM_NO_BINARY=:all: pdm install
# 首选二进制分发，即使有更高版本的 sdist 可用
PDM_PREFER_BINARY=flask pdm install
```

## 允许安装预发行版本

包括以下设置以 `pyproject.toml` 启用：

```toml
[tool.pdm.resolution]
allow-prereleases = true
```

## 解决锁定故障

如果 PDM 无法找到满足要求的解决方案，则会引发错误。例如

```bash
pdm django==3.1.4 "asgiref<3"
...
🔒 Lock failed
Unable to find a resolution for asgiref because of the following conflicts:
  asgiref<3 (from project)
  asgiref<4,>=3.2.10 (from <Candidate django 3.1.4 from https://pypi.org/simple/django/>)
To fix this, you could loosen the dependency version constraints in pyproject.toml. If that is not possible, you could also override the resolved version in `[tool.pdm.resolution.overrides]` table.
```

您可以更改为 的 `django` 下限或删除 的 `asgiref` 上限。但是，如果它不符合您的项目条件，您可以尝试[覆盖已解析的包版本](./config.md#override-the-resolved-package-versions)，甚至[不要将该特定包锁定](./config.md#exclude-specific-packages-and-their-dependencies-from-the-lock-file)在 pyproject.toml。

## 将锁定的包导出为其他格式

您可以将 `pdm.lock` 文件导出为其他格式，这将简化 CI 流程或图像构建过程。目前仅支持该 `requirements.txt` 格式。

```bash
pdm export -o requirements.txt
```

!!! TIP
    你也可以用 [`.pre-commit` hook](./advanced.md#hooks-for-pre-commit) 钩子跑 `pdm export`。
