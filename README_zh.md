<div align="center">

# PDM - Python Development Manager

一个现代的 Python 包管理器，支持 [PEP 582]。[English version README](README.md)

![PDM logo](https://raw.githubusercontents.com/pdm-project/pdm/main/docs/docs/assets/logo_big.png)

[![Docs](https://img.shields.io/badge/Docs-mkdocs-blue?style=for-the-badge)](https://pdm.fming.dev)
[![Twitter Follow](https://img.shields.io/twitter/follow/pdm_project?label=get%20updates&logo=twitter&style=for-the-badge)](https://twitter.com/pdm_project)
[![Discord](https://img.shields.io/discord/824472774965329931?label=discord&logo=discord&style=for-the-badge)](https://discord.gg/Phn8smztpv)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/pdm?logo=python&logoColor=%23cccccc)](https://pypi.org/project/pdm)
[![](https://tokei.rs/b1/github/pdm-project/pdm)](https://github.com/pdm-project/pdm)
[![Downloads](https://pepy.tech/badge/pdm/week)](https://pepy.tech/project/pdm)
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

[![asciicast](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.svg)](https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB)

</div>

## 这个项目是啥?

PDM 旨在成为下一代 Python 软件包管理工具。它最初是为个人兴趣而诞生的。如果你觉得 `pipenv` 或者
`poetry` 用着非常好，并不想引入一个新的包管理器，那么继续使用它们吧；但如果你发现有些东西这些
工具不支持，那么你很可能可以在 `pdm` 中找到。

[PEP 582] 提出下面这种项目的目录结构：

```
foo
    __pypackages__
        3.8
            lib
                bottle
    myscript.py
```

项目目录中包含一个`__pypackages__`目录，用来放置所有依赖的库文件，就像`npm`的`node_modules`一样。
你可以在[这里](https://www.python.org/dev/peps/pep-0582/#specification)阅读更多提案的细节。

## 主要特性

- [PEP 582] 本地项目库目录，支持安装与运行命令，完全不需要虚拟环境。
- 一个简单且相对快速的依赖解析器，特别是对于大的二进制包发布。
- 兼容 [PEP 517] 的构建后端，用于构建发布包(源码格式与 wheel 格式)
- 灵活且强大的插件系统
- [PEP 621] 元数据格式
- 像 [pnpm] 一样的中心化安装缓存，节省磁盘空间

[pep 517]: https://www.python.org/dev/peps/pep-0517
[pep 582]: https://www.python.org/dev/peps/pep-0582
[pep 621]: https://www.python.org/dev/peps/pep-0621
[pnpm]: https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed

## 为什么不用虚拟环境?

现在大部分的 Python 包管理器也同时管理虚拟环境，这主要是为了隔离项目开发环境。但如果涉及到虚拟
环境嵌套虚拟环境的时候，问题就来了：你可能用一个虚拟环境的 Python 安装了某个虚拟环境管理工具，
然后又用这个工具去创建更多虚拟环境。当某一天你升级了新版本的 Python 你必须一个一个去检查这些
虚拟环境，没准哪个就用不了了。

然而 [PEP 582] 提供了一个能把 Python 解释器和项目开发环境解耦的方法。这是一个相对比较新的提案，
没有很多相关的工具实现它，这其中就有 [pyflow]。但 pyflow 又是用 Rust 写的，不是所有 Python 的社区
都会用 Rust，这样就没法贡献代码，而且，基于同样的原因，pyflow 并不支持 [PEP 517] 构建。

## 安装

PDM 需要 Python 3.7 或更高版本。

### 通过安装脚本

像 pip 一样，PDM 也提供了一键安装脚本，用来将 PDM 安装在一个隔离的环境中。

**Linux/Mac 安装命令**

```bash
curl -sSL https://raw.githubusercontent.com/pdm-project/pdm/main/install-pdm.py | python3 -
```

**Windows 安装命令**

```powershell
(Invoke-WebRequest -Uri https://raw.githubusercontent.com/pdm-project/pdm/main/install-pdm.py -UseBasicParsing).Content | python -
```

为安全起见，你应该检查 `install-pdm.py` 文件的正确性。
SHA256 校验和: `67dccb18923340e21f3d70f9c6a467d532c6a41b295d6f1ba884b27604074d38`

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

如果你使用的是 MacOS 并且安装了 `homebrew`：

```bash
brew install pdm
```

如果你在 Windows 上使用 [Scoop](https://scoop.sh/), 运行以下命令安装：

```
scoop bucket add frostming https://github.com/frostming/scoop-frostming.git
scoop install pdm
```

否则，强烈推荐把 `pdm` 安装在一个隔离环境中， 用 `pipx` 是坠吼的。

```bash
pipx install pdm
```

或者你可以将它安装在用户目录下:

```bash
pip install --user pdm
```

## 快速上手

**初始化一个新的 PDM 项目**

```bash
pdm init
```

按照指引回答提示的问题，一个 PDM 项目和对应的`pyproject.toml`文件就创建好了。

**把依赖安装到 `__pypackages__` 文件夹中**

```bash
pdm add requests flask
```

你可以在同一条命令中添加多个依赖。稍等片刻完成之后，你可以查看`pdm.lock`文件看看有哪些依赖以及对应版本。

**在 [PEP 582] 加持下运行你的脚本**

假设你在`__pypackages__`同级的目录下有一个`app.py`脚本，内容如下（从 Flask 的官网例子复制而来）：

```python
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World!'

if __name__ == '__main__':
    app.run()
```

如果你使用的是 Bash，可以通过执行`eval "$(pdm --pep582)"`设置环境变量，现在你可以用你最熟悉的 **Python 解释器** 运行脚本了：

```bash
$ python /home/frostming/workspace/flask_app/app.py
 * Serving Flask app "app" (lazy loading)
 ...
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

当当当当！你已经把应用运行起来了，而它的依赖全被安装在一个项目独立的文件夹下，而我们完全没有创建虚拟环境。

如果你是 Windows 用户，请参考[文档](https://pdm.fming.dev/#enable-pep-582-globally)获取设置的方法。

如果你好奇这是如何实现的，可以查看[文档](https://pdm.fming.dev/usage/project/#how-we-make-pep-582-packages-available-to-the-python-interpreter)，有一个简短的解释。

## 徽章

在 README.md 中加入以下 Markdown 代码，向大家展示项目正在使用 PDM:

```markdown
[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)
```

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm.fming.dev)

## PDM 生态

[Awesome PDM](https://github.com/pdm-project/awesome-pdm) 这个项目收集了一些非常有用的 PDM 插件及相关资源。

## 常见问题

### 1. `__pypackages__` 里都包含什么?

[PEP 582] 尚处于草案阶段，还需要补充很多细节，比如提案中并未说明可执行程序应该如何存放。PDM 会把 `bin`(可执行程序), `include`(头文件),
以及 `lib` 都放在 `__pypackages__/X.Y` 下面。

### 2. 如何运行 `__pypackages__` 下的可执行程序?

推荐的方式是在你的命令前面加上 `pdm run`, 你也可以直接运行 `bin` 下面的可执行程序。PDM 的安装器已经在可执行程序里面注入了本地包路径了。

### 3. 使用 PDM 时会载入哪些三方库路径?

本项目的 `__pypackages__` 中的包会在系统的`site-packages`之前被载入，这样能更好地隔离包的环境。

### 4. 我能把 `__pypackages__` 保存下来用来部署到别的机器上吗?

最好别这样搞，`__pypackages__` 下面安装的包是和操作系统相关的，所以除非是纯 Python 的包，都会有兼容性的问题。你应该把 `pdm.lock`
纳入版本管理，然后在目标环境中执行 `pdm sync`。

### 5. 我能用`pdm`管理一个 Python 2.7 的项目吗？

当然可以。只是`pdm`本身的安装需要 Python 版本高于 3.7，它并不限制项目使用的 Python 版本。

## 鸣谢

本项目的受到 [pyflow] 与 [poetry] 的很多启发。

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## 使用许可

本项目基于 MIT 协议开源，具体可查看 [LICENSE](LICENSE)。
