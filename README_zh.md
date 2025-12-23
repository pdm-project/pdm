<div align="center">

# PDM

一个现代的 Python 包管理器，支持 PEP 最新标准。[English version README](README.md)

![PDM logo](https://raw.githubusercontent.com/pdm-project/pdm/main/docs/assets/logo_big.png)

[![Docs](https://img.shields.io/badge/Docs-mkdocs-blue?style=for-the-badge)](https://pdm-project.org)
[![Twitter Follow](https://img.shields.io/twitter/follow/pdm_project?label=get%20updates&logo=twitter&style=for-the-badge)](https://twitter.com/pdm_project)
[![Discord](https://img.shields.io/discord/824472774965329931?label=discord&logo=discord&style=for-the-badge)](https://discord.gg/Phn8smztpv)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)](https://pypi.org/project/pdm)
[![Packaging status](https://repology.org/badge/tiny-repos/pdm.svg)](https://repology.org/project/pdm/versions)
[![Downloads](https://pepy.tech/badge/pdm/week)](https://pepy.tech/project/pdm)
[![pdm-managed](https://img.shields.io/endpoint?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fpdm-project%2F.github%2Fbadge.json)](https://pdm-project.org)

[![asciicast](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.svg)](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB)

</div>

## 这个项目是啥？

PDM 旨在成为下一代 Python 软件包管理工具。它最初是为个人兴趣而诞生的。如果你觉得 `pipenv` 或者
`poetry` 用着非常好，并不想引入一个新的包管理器，那么继续使用它们吧；但如果你发现有些东西这些
工具不支持，那么你很可能可以在 `pdm` 中找到。

## 主要特性

- 一个简单且相对快速的依赖解析器，特别是对于大的二进制包发布。
- 兼容 [PEP 517] 的构建后端，用于构建发布包 (源码格式与 wheel 格式)
- 灵活且强大的插件系统
- [PEP 621] 元数据格式
- 功能强大的用户脚本
- 支持从 [astral-sh's python-build-standalone](https://github.com/astral-sh/python-build-standalone) 安装 Python。
- 像 [pnpm] 一样的中心化安装缓存，节省磁盘空间

[pep 517]: https://www.python.org/dev/peps/pep-0517
[pep 621]: https://www.python.org/dev/peps/pep-0621
[pnpm]: https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed

## 与其他包管理器的比较

### [Pipenv](https://pipenv.pypa.io)

Pipenv 是一个依赖管理器，它结合了 `pip` 和 `venv`，正如其名称所暗示的。它可以从一种自定义格式文件 `Pipfile.lock` 或 `Pipfile` 中安装软件包。
然而，Pipenv 并不处理任何与构建、打包和发布相关的工作。所以它只适用于开发不可安装的应用程序（例如 Django 网站）。
如果你是一个库的开发者，无论如何你都需要 `setuptools`。

### [Poetry](https://python-poetry.org)

Poetry 以类似于 Pipenv 的方式管理环境和依赖，它也可以从你的代码构建 `.whl` 文件，并且可以将轮子和源码发行版上传到 PyPI。
它有一个漂亮的用户界面，用户可以通过贡献插件来定制它。Poetry 使用 `pyproject.toml` 标准。

### [Hatch](https://hatch.pypa.io)

Hatch 也可以管理环境（它允许每个项目有多个环境，但不允许把它们放在项目目录中），并且可以管理包（但不支持 lockfile）。Hatch 也可以用来打包一个项目（用符合 PEP 621 标准的 `pyproject.toml` 文件）并上传到 PyPI。

### 本项目

PDM 也可以像 Pipenv 那样在项目或集中的位置管理 venvs。它从一个标准化的 `pyproject.toml` 文件中读取项目元数据，并支持 lockfile。用户可以在插件中添加更多的功能，并将其作为一个发行版上传，以供分享。

此外，与 Poetry 和 Hatch 不同，PDM 并没有和任何特定的构建后端绑定，你可以选择任何你喜欢的构建后端。

## 安装

<a href="https://repology.org/project/pdm/versions">
    <img src="https://repology.org/badge/vertical-allrepos/pdm.svg" alt="Packaging status" align="right">
</a>

PDM 需要 Python 3.9 或更高版本。你也可以从 [release assets](https://github.com/pdm-project/pdm/releases) 下载独立的可执行文件来使用。

### 推荐：通过脚本安装二进制

优先使用预构建的独立二进制，直接运行安装脚本即可：

**Linux/Mac 安装命令**

```bash
curl -sSL https://pdm-project.org/install.sh | bash
```

**Windows 安装命令**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://pdm-project.org/install.ps1 | iex"
```

其他安装方式（Python 安装脚本、包管理器等）请查看[安装文档](https://pdm-project.org/zh-cn/latest/#_3)。

## 快速上手

**初始化一个新的 PDM 项目**

```bash
pdm new my_project
```

按照指引回答提示的问题，一个 PDM 项目和对应的`pyproject.toml`文件就创建好了。

**添加依赖**

```bash
pdm add requests flask
```

你可以在同一条命令中添加多个依赖。稍等片刻完成之后，你可以查看`pdm.lock`文件看看有哪些依赖以及对应版本。

## 徽章

在 README.md 中加入以下 Markdown 代码，向大家展示项目正在使用 PDM:

```markdown
[![pdm-managed](https://img.shields.io/endpoint?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fpdm-project%2F.github%2Fbadge.json)](https://pdm-project.org)
```

[![pdm-managed](https://img.shields.io/endpoint?url=https%3A%2F%2Fcdn.jsdelivr.net%2Fgh%2Fpdm-project%2F.github%2Fbadge.json)](https://pdm-project.org)

## PDM 生态

[Awesome PDM](https://github.com/pdm-project/awesome-pdm) 这个项目收集了一些非常有用的 PDM 插件及相关资源。

## 赞助

<p align="center">
    <a href="https://cdn.jsdelivr.net/gh/pdm-project/sponsors/sponsors.svg">
        <img src="https://cdn.jsdelivr.net/gh/pdm-project/sponsors/sponsors.svg"/>
    </a>
</p>

## 鸣谢

本项目的受到 [pyflow] 与 [poetry] 的很多启发。

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## 使用许可

本项目基于 MIT 协议开源，具体可查看 [LICENSE](./LICENSE)。
