# 从模板创建项目


从模板创建项目
类似于 `yarn create` 和 `npm create`，PDM 也支持从模板初始化或创建项目。模板作为 `pdm init` 的位置参数给出，可以采用以下形式之一：

- `pdm init django` - 从模板 `https://github.com/pdm-project/template-django` 初始化项目
- `pdm init https://github.com/frostming/pdm-template-django` - 从 Git URL 初始化项目。可以接受 HTTPS 和 SSH URL。
- `pdm init django@v2` - 检出特定的分支或标签。完整的 Git URL 也支持这样做。
- `pdm init /path/to/template` - 从本地文件系统上的模板目录初始化项目。
- `pdm init minimal` - 使用内置的 "最小" 模板初始化，只生成一个 `pyproject.toml`.

`pdm init` 将使用内置的默认模板。

项目将在当前目录初始化，同名的现有文件将被覆盖。您还可以使用 `-p <path>` 选项在新路径下创建项目。

## 贡献模板

根据模板参数的第一个形式，`pdm init <name>` 将引用位于 `https://github.com/pdm-project/template-<name>` 的模板存储库。要贡献模板，您可以创建一个模板存储库，并提出请求将所有权转移给 `pdm-project` 组织（可以在存储库设置页面的底部找到）。组织的管理员将审核请求并完成后续步骤。如果转移被接受，您将被添加为存储库的维护者。

## 模板的要求

模板存储库必须是一个基于 `pyproject` 的项目，其中包含一个具有符合 PEP-621 规范的元数据的 `pyproject.toml` 文件。
不需要其他特殊的配置文件。

## 项目名称替换

在初始化时，模板中的项目名称将被新项目的名称替换。这通过递归全文搜索和替换来完成。导入名称是由项目名称派生的，通过将所有非字母数字字符替换为下划线并转为小写来完成，它也将以相同的方式进行替换。

例如，如果模板中的项目名称为 `foo-project`，而您想要初始化一个名为 `bar-project` 的新项目，则将进行以下替换：

- 在所有 `.md` 文件和 `.rst` 文件中，将 `foo-project` 替换为 `bar-project`
- 在所有 `.py` 文件中，将 `foo_project` 替换为 `bar_project`
- 在目录名中，将 `foo_project` 替换为 `bar_project`
- 在文件名中，将 `foo_project.py` 替换为 `bar_project.py`

因此，如果导入名称不是从项目名称派生的，我们不支持名称替换。

## 使用其他项目生成器

如果您正在寻找更强大的项目生成器，您可以通过 `--cookiecutter` 选项使用 [cookiecutter](https://github.com/cookiecutter/cookiecutter) 以及通过 `--copier` 选项使用 [copier](https://github.com/copier-org/copier)。

您需要分别安装 `cookiecutter` 和 `copier` 来使用它们。您可以通过运行 `pdm self add <package>` 来完成。要使用它们：

```bash
pdm init --cookiecutter gh:cjolowicz/cookiecutter-hypermodern-python
# 或者
pdm init --copier gh:pawamoy/copier-pdm --UNSAFE
```
