# 配置项目

PDM的 `config` 命令的工作方式与 `git config` 类似，只是不需要 `--list` 来显示配置。

显示当前配置：

```bash
pdm config
```

获单一配置的内容：

```bash
pdm config pypi.url
```

更改配置值并存储在配置中：

```bash
pdm config pypi.url "https://test.pypi.org/simple"
```

默认情况下，配置是全局更改的，如果只想让这个项目看到配置，请添加一个 `--local` 标志：

```bash
pdm config --local pypi.url "https://test.pypi.org/simple"
```

任何本地配置都将存储在 `pdm.toml` 项目根目录下。

## 配置文件

按以下顺序搜索配置文件：

1. `<PROJECT_ROOT>/pdm.toml` - 项目配置
2. `<CONFIG_ROOT>/config.toml` - 用户配置
3. `<SITE_CONFIG_ROOT>/config.toml` - 站点配置 <!-- TODO 站点？还是全局 -->

其中 `<CONFIG_ROOT>` 的存储位置为：

- `$XDG_CONFIG_HOME/pdm` （在大多数情况下是在 `~/.config/pdm` 这个位置） 在 Linux 上的默认位置由 [XDG 基本目录规范定义](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- `~/Library/Application Support/pdm` 在 macOS 上的默认位置由 [Apple 文件系统基础知识所定义](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- `%USERPROFILE%\AppData\Local\pdm`  在 Windows 上的默认位置由 [已知文件夹](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders) 中定义

并且 `<SITE_CONFIG_ROOT>` 的存储位置为：

- `$XDG_CONFIG_DIRS/pdm` （在大多数情况下是在 `/etc/xdg/pdm` 这个位置） 在 Linux 上的默认位置由 [XDG 基本目录规范定义](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)
- `/Library/Application Support/pdm` 在 macOS 上的默认位置由 [Apple 文件系统基础知识所定义](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- `C:\ProgramData\pdm\pdm` 在 Windows 上的默认位置由 [已知文件夹](https://docs.microsoft.com/en-us/windows/win32/shell/known-folders) 中定义

如果使用 `-g/--global` 选项，则第一项将替换为 `<CONFIG_ROOT>/global-project/pdm.toml`。 <!-- TODO 第一项是什么？ -->

您可以在配置页面中找到所有可用的 [配置项目](../reference/configuration.md).

## 配置 Python 查找器

默认情况下，PDM会尝试在以下来源中查找Python解释器：

- `venv`: PDM 虚拟环境位置
- `path`: `PATH` 环境变量路径
- `pyenv`: [pyenv](https://github.com/pyenv/pyenv) 的安装根目录
- `rye`: [rye](https://rye-up.com/) 工具链安装根目录
- `asdf`: [asdf](https://asdf-vm.com/) python 安装根目录
- `winreg`: Windows 注册表

您可以通过设置 `python.providers` 取消选择其中一些或更改顺序：

```bash
# 默认内容为
# ['venv', 'path', 'asdf', 'pyenv', 'rye', 'winreg', 'macos']
pdm config python.providers rye   # 只使用 Rye 来管理 Python 的虚拟环境
pdm config python.providers pyenv,asdf  # 使用 pyenv 和 asdf 来管理 Python 的虚拟环境
```

## 在依赖项解析程序允许预发布版本

默认情况下，依赖项解析程序将忽略预发行版，除非依赖项的给定版本范围没有稳定版本。可以通过在表中 `[tool.pdm.resolution]` 设置为 `allow-prereleases` 的值为 `true` 来更改此行为：

```toml
[tool.pdm.resolution]
allow-prereleases = true
```

## 配置包索引

您可以通过在配置中 `pyproject.toml` 指定源或通过 `pypi.*` 配置来告诉 PDM 在哪里可以找到包。

在 `pyproject.toml` 以下位置添加源：

```toml
[[tool.pdm.source]]
name = "private"
url = "https://mirrors.aliyun.com/pypi/simple/"
verify_ssl = true
```

`pdm config` 通过以下方式更改默认索引：

```bash
pdm config pypi.url "https://mirrors.aliyun.com/pypi/simple/"
```

`pdm config` 通过以下方式添加额外的索引：

```bash
pdm config pypi.extra.url "https://pypi.python.org/simple/"
```

可用的配置选项包括：

- `url`: 索引的 URL
- `verify_ssl`: （可选）是否验证SSL证书，默认为true
- `username`: （可选）索引的用户名
- `password`: （可选）索引的密码
- `type`: （可选）索引或find_links，默认为 index

??? note "关于源类型"
    默认情况下，所有源都是 `index` 这是依据 [PEP 503](https://www.python.org/dev/peps/pep-0503/) ，如 `pip --index-url` 和 `--extra-index-url` ，但是，您可以将类型设置为 `find_links`，其中包含要直接查找的文件或链接。有关两种类型之间的区别，请参[阅此答案](https://stackoverflow.com/a/46651848)。

这些配置按以下顺序读取，以生成最终的源列表：

- 如果在 `pyproject.toml` 的任何源的 `name` 字段中没有出现 `pypi`，则使用 `pypi.url` <!-- TODO 翻译和原文都很别扭 -->
- 在 `pyproject.toml` 文件中的源
- PDM 配置中的 `pypi.<name>.url`

您可以将 `pypi.ignore_stored_index` 设置为 `true`，以禁用 PDM 配置中的所有索引，并仅使用在 `pyproject.toml` 中指定的索引。

!!! TIP "禁用默认 PyPI 索引"
    如果要省略默认的 PyPI 索引，只需将源名称设置为 `pypi` ，该源将**替换**它。

    ```toml
    [[tool.pdm.source]]
    url = "https://private.pypi.org/simple"
    verify_ssl = true
    name = "pypi"
    ```

??? note "`pyproject.toml` 中的索引和配置"
    当您想与将要使用该项目的其他人共享索引时，您应该将它们添加到 `pyproject.toml` 中。例如，某些包仅存在于专用索引中，如果有人未配置索引，则无法安装。否则，请将它们存储在其他人看不到的本地配置中。

### 尊重来源的顺序

默认情况下，所有来源都被认为是相等的，其中的包按版本和轮标签排序，选择与最高版本最匹配的包。

在某些情况下，您可能希望从首选源返回包，如果前一个源中缺少其他包，则搜索其他包。PDM 通过读取配置 `respect-source-order` 来支持此功能：

```toml
[tool.pdm.resolution]
respect-source-order = true
```

### 指定单个包的索引

您可以使用 `tool.pdm.source` 表下的 `include_packages` 和 `exclude_packages` 配置将软件包绑定到特定的源。

```toml
[[tool.pdm.source]]
name = "private"
url = "https://private.pypi.org/simple"
include_packages = ["foo", "foo-*"]
exclude_packages = ["bar-*"]
```

根据上述配置，任何与 `foo` 或 `foo-*` 匹配的软件包将仅从 `private` 索引中搜索，而任何与 `bar-*` 匹配的软件包将从除 `private` 索引外的所有索引中搜索。

`include_packages` 和 `exclude_packages` 都是可选的，它们接受一个 **通配符** 模式的列表，并且 `include_packages` 仅在模式匹配时生效。

### 存储索引凭据

您可以在 URL 中指定具有 `${ENV_VAR}` 变量扩展的凭据，这些变量将从环境变量中读取：

```toml
[[tool.pdm.source]]
name = "private"
url = "https://${PRIVATE_PYPI_USERNAME}:${PRIVATE_PYPI_PASSWORD}@private.pypi.org/simple"
```

### 配置 HTTPS 证书

您可以将自定义 CA 捆绑包或客户端证书用于 HTTPS 请求。它可以为索引（用于包下载）和存储库（用于上传）进行配置：

```bash
pdm config pypi.ca_certs /path/to/ca_bundle.pem
pdm config repository.pypi.ca_certs /path/to/ca_bundle.pem
```

此外，还可以使用系统信任存储而不是捆绑的 certifi 证书来验证 HTTPS 证书。此方法通常支持公司代理证书，而无需其他配置。
<!-- TODO truststore 没有个超链接解释下是啥 -->
要使用 `truststore` ，您需要 Python 3.10 或更高版本，并安装 `truststore` 到与 PDM 相同的环境中： 

```bash
pdm self add truststore
```

### 索引配置合并

索引配置与配置文件中的 `[[tool.pdm.source]]` 表或 `pypi.<name>` 键 `name` 字段合并。这使你能够单独存储 url 和凭据，以避免机密在源代码管理中公开。例如，如果您有以下配置：

```toml
[[tool.pdm.source]]
name = "private"
url = "https://private.pypi.org/simple"
```

您可以将凭据存储在配置文件中：

```bash
pdm config pypi.private.username "foo"
pdm config pypi.private.password "bar"
```

PDM 可以从两个位置检索索引的 `private` 配置。
<!-- TODO keyring 是啥 -->
如果索引需要用户名和密码，但无法从环境变量和配置文件中找到它们，PDM 将提示您输入它们。或者，如果 `keyring` 已安装，它将用作凭据存储。PDM 可以使用 `keyring` 已安装软件包或 CLI 中的 。


## 集中式软件包存储库

如果系统中的许多项目都需要一个包，则每个项目都必须保留自己的副本。这可能会浪费磁盘空间，特别是对于数据科学和机器学习项目来说。

PDM 支持缓存同一轮子的安装，方法是将其安装在集中式软件包存储库中，并在不同的项目中链接到该安装。若要启用它，请运行：

```bash
pdm config install.cache on
```

可以通过向命令添加 `--local` 选项来按项目启用它。

缓存位于 `$(pdm config cache_dir)/packages` 中。您可以使用 `pdm cache info` 查看缓存使用情况。请注意，缓存的安装是自动管理的，如果它们未链接到任何项目，它们将被删除。从磁盘手动删除缓存可能会破坏系统上的某些项目。

此外，还支持链接到缓存条目的几种不同方式：

- `symlink`（默认），创建指向包文件的符号链接。
- `hardlink`, 创建指向缓存条目的包文件的硬链接。

您可以通过运行 `pdm config [-l] install.cache_method <method>` 在它们之间切换。

!!! note
    只能缓存从 PyPI 解析的命名需求的安装。

## 配置要上传的存储库

使用该 [`pdm publish`](../reference/cli.md#publish) 命令时，它会从全局配置文件 (`<CONFIG_ROOT>/config.toml`) 中读取存储库密钥。配置内容如下：

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

或者，可以用环境变量提供这些凭据：

```bash
export PDM_PUBLISH_REPO=...
export PDM_PUBLISH_USERNAME=...
export PDM_PUBLISH_PASSWORD=...
export PDM_PUBLISH_CA_CERTS=...
```

PEM 编码的证书颁发机构捆绑包 （ `ca_certs` ） 可用于本地/自定义 PyPI 存储库，其中服务器证书未由标准 [certifi](https://github.com/certifi/python-certifi/blob/master/certifi/cacert.pem) CA 捆绑包签名。

!!! NOTE
    存储库与上一节中的索引不同。存储库用于发布，而索引用于锁定和解析。它们不共享配置。

!!! TIP
    您无需配置 `pypi` 和 `testpypi` 仓库的 URL，它们已填充默认值。用户名、密码和证书颁发机构捆绑包可以通过命令行传递给 `pdm publish`，分别使用 `--username`、`--password` 和 `--ca-certs`。

要从命令行更改存储库配置，请使用以下 [`pdm config`](../reference/cli.md#config) 命令：

```bash
pdm config repository.pypi.username "__token__"
pdm config repository.pypi.password "my-pypi-token"

pdm config repository.company.url "https://pypi.company.org/legacy/"
pdm config repository.company.ca_certs "/path/to/custom-cacerts.pem"
```

## 使用密钥环进行密码管理

当密钥环可用且受支持时，密码将存储到密钥环中并从密钥环中检索，而不是写入配置文件。这同时支持索引和上传存储库。服务名称将用于 `pdm-pypi-<name>` 索引和 `pdm-repository-<name>` 存储库。

您可以通过 `keyring` 安装到与 PDM 相同的环境中或全局安装来启用密钥环。要向 PDM 环境添加密钥环：

```bash
pdm self add keyring
```

或者，如果您已全局安装了密钥环的副本，请确保 CLI 在环境变量中公开，以便 PDM 可以发现它：

```bash
export PATH=$PATH:path/to/keyring/bin
```

## 使用覆盖功能解决包的依赖问题

+++ 1.12.0

有时，由于上游库设置的版本范围不正确，无法修复依赖项解析。在这种情况下，您可以使用 PDM 的覆盖功能来强制安装特定版本的软件包。

给定以下 `pyproject.toml` 配置：

```toml
[tool.pdm.resolution.overrides]
asgiref = "3.2.10"  # 准确的版本
urllib3 = ">=1.26.2"  # 版本范围
pytz = "https://mypypi.org/packages/pytz-2020.9-py3-none-any.whl"  # absolute URL
```

该表中的每个条目都是一个包名及其所需的版本。在这个例子中，PDM将解析上述包，无论是否存在其他可用的解决方案，都会将其解析为给定的版本。

!!! warning
    通过使用 `[tool.pdm.resolution.overrides]` 设置，您自行承担由该解决方案引起的任何不兼容性的风险。只有当您的要求没有有效的解决方案并且您知道特定版本有效时，才可以使用它。大多数情况下，您可以将任何短暂的约束添加到依赖关系数组中。

## 从锁定文件中排除特定包及其依赖项

+++ 2.12.0

有时您甚至不想在锁定的文件中包含某些包，因为您确信它们不会被任何代码使用。在这种情况下，您可以在依赖关系解析期间完全跳过它们及其依赖项：

```toml
[tool.pdm.resolution]
excludes = ["requests"]
```

使用此配置，`requests` 将不会在锁定文件中锁定，并且其依赖项，如 `urllib3` 和 `idna` ，如果没有其他软件包依赖它们，也不会出现在解析结果中。安装程序也无法选择它们。

## 将常量参数传递给每个 pdm 调用

+++ 2.7.0

您可以通过 `tool.pdm.options` 配置来添加传递给各个pdm命令的额外选项：

```toml
[tool.pdm.options]
add = ["--no-isolation", "--no-self"]
install = ["--no-self"]
lock = ["--no-cross-platform"]
```

这些选项将在命令名之后添加。例如，根据上述配置，`pdm add requests` 等同于 `pdm add --no-isolation --no-self requests`。

## 忽略包警告

+++ 2.10.0

解析依赖项时，您可能会看到一些警告，如下所示：

```txt
PackageWarning: Skipping scipy@1.10.0 because it requires Python
<3.12,>=3.8 but the project claims to work with Python>=3.9.
Narrow down the `requires-python` range to include this version. For example, ">=3.9,<3.12" should work.
  warnings.warn(record.message, PackageWarning, stacklevel=1)
Use `-q/--quiet` to suppress these warnings, or ignore them per-package with `ignore_package_warnings` config in [tool.pdm] table.
```

这是因为包的 Python 版本支持的范围不包括 `requires-python` `pyproject.toml` 。您可以通过添加以下配置来忽略每个包的这些警告：

```toml
[tool.pdm]
ignore_package_warnings = ["scipy", "tensorflow-*"]
```

其中，每个项目都是不区分大小写的 **通配符** 模式，以匹配包名称。
