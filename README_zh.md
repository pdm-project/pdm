<div align="center">

# PDM

一个现代的 Python 包管理器，支持 PEP 最新标准。[English version README](README.md)

![PDM logo](https://raw.githubusercontents.com/pdm-project/pdm/main/docs/docs/assets/logo_big.png)

[![Docs](https://img.shields.io/badge/Docs-mkdocs-blue?style=for-the-badge)](https://pdm.fming.dev)
[![Twitter Follow](https://img.shields.io/twitter/follow/pdm_project?label=get%20updates&logo=twitter&style=for-the-badge)](https://twitter.com/pdm_project)
[![Discord](https://img.shields.io/discord/824472774965329931?label=discord&logo=discord&style=for-the-badge)](https://discord.gg/Phn8smztpv)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)](https://pypi.org/project/pdm)
[![Packaging status](https://repology.org/badge/tiny-repos/pdm.svg)](https://repology.org/project/pdm/versions)
[![Downloads](https://pepy.tech/badge/pdm/week)](https://pepy.tech/project/pdm)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

[![asciicast](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.svg)](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB)

</div>

## 这个项目是啥?

PDM 旨在成为下一代 Python 软件包管理工具。它最初是为个人兴趣而诞生的。如果你觉得 `pipenv` 或者
`poetry` 用着非常好，并不想引入一个新的包管理器，那么继续使用它们吧；但如果你发现有些东西这些
工具不支持，那么你很可能可以在 `pdm` 中找到。

## 主要特性

- 一个简单且相对快速的依赖解析器，特别是对于大的二进制包发布。
- 兼容 [PEP 517] 的构建后端，用于构建发布包(源码格式与 wheel 格式)
- 灵活且强大的插件系统
- [PEP 621] 元数据格式
- 功能强大的用户脚本
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
它有一个漂亮的用户界面，用户可以通过贡献插件来定制它。Poetry 使用 `pyproject.toml` 标准。但它并不遵循指定元数据应如何在 `pyproject.toml` 文件中表示的标准（[PEP 621]）。而是使用一个自定义的 `[tool.poetry]` 表。这部分是因为 Poetry 诞生在 PEP 621 出现之前。

### [Hatch](https://hatch.pypa.io)

Hatch 也可以管理环境（它允许每个项目有多个环境，但不允许把它们放在项目目录中），并且可以管理包（但不支持 lockfile）。Hatch 也可以用来打包一个项目（用符合 PEP 621 标准的 `pyproject.toml` 文件）并上传到 PyPI。

### 本项目

PDM 也可以像 Pipenv 那样在项目或集中的位置管理 venvs。它从一个标准化的 `pyproject.toml` 文件中读取项目元数据，并支持 lockfile。用户可以在插件中添加更多的功能，并将其作为一个发行版上传，以供分享。

此外，与 Poetry 和 Hatch 不同，PDM 并没有被和一个特定的构建后端绑定，你可以选择任何你喜欢的构建后端。

## 安装

PDM 需要 Python 3.7 或更高版本。

### 通过安装脚本

像 pip 一样，PDM 也提供了一键安装脚本，用来将 PDM 安装在一个隔离的环境中。

**Linux/Mac 安装命令**

```bash
curl -sSL https://pdm.fming.dev/install-pdm.py | python3 -
```

**Windows 安装命令**

```powershell
(Invoke-WebRequest -Uri https://pdm.fming.dev/install-pdm.py -UseBasicParsing).Content | python -
```

为安全起见，你应该检查 `install-pdm.py` 文件的正确性。
校验和文件下载地址：[install-pdm.py.sha256](https://pdm.fming.dev/install-pdm.py.sha256)

默认情况下，此脚本会将 PDM 安装在 Python 的用户目录下，具体位置取决于当前系统：

- Unix 上是 `$HOME/.local/bin`
- Windows 上是 `%APPDATA%\Python\Scripts`

你还可以通过命令行的选项来改变安装脚本的行为：

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

你既可以通过直接增加选项，也可以通过设置对应的环境变量来达到这一效果。

### 其他安装方法

如果你使用的是 macOS 并且安装了 `homebrew`：

```bash
brew install pdm
```

如果你在 Windows 上使用 [Scoop](https://scoop.sh/), 运行以下命令安装：

```
scoop bucket add frostming https://github.com/frostming/scoop-frostming.git
scoop install pdm
```

否则，强烈推荐把 `pdm` 安装在一个隔离环境中， 用 `pipx` 是最好的。

```bash
pipx install pdm
```

或者你可以将它安装在用户目录下:

```bash
pip install --user pdm
```

[asdf-vm](https://asdf-vm.com/)

```bash
asdf plugin add pdm
asdf install pdm latest
```

## 快速上手

**初始化一个新的 PDM 项目**

```bash
pdm init
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
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
```

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

## 打包状态

[![打包状态](https://repology.org/badge/vertical-allrepos/pdm.svg)](https://repology.org/project/pdm/versions)

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

本项目基于 MIT 协议开源，具体可查看 [LICENSE](LICENSE)。
