# PDM - Python Development Master

一个现代的 Python 包管理器，支持 PEP 582。[English version README](README.md)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)

## 这个项目是啥?

PDM 旨在成为下一代 Python 软件包管理工具。它最初是为个人兴趣而诞生的。如果你觉得 `pipenv` 或者
`poetry` 用着非常好，并不想引入一个新的包管理器，那么继续使用它们吧；但如果你发现有些东西这些
工具不支持，那么你很可能可以在 `pdm` 中找到。

## 主要特性

- PEP 582 本地项目库目录，支持安装与运行命令，完全不需要虚拟环境。
- 一个简单且相对快速的依赖解析器，特别是对于大的二进制包发布。
- 兼容 PEP 517 的构建后端，用于构建发布包(源码格式与 wheel 格式)

## 为什么不用虚拟环境?

现在大部分的 Python 包管理器也同时管理虚拟环境，这主要是为了隔离项目开发环境。但如果涉及到虚拟
环境嵌套虚拟环境的时候，问题就来了：你可能用一个虚拟环境的 Python 安装了某个虚拟环境管理工具，
然后又用这个工具去创建更多虚拟环境。当某一天你升级了新版本的 Python 你必须一个一个去检查这些
虚拟环境，没准哪个就用不了了。

然而 PEP 582 提供了一个能把 Python 解释器和项目开发环境解耦的方法。这是一个相对比较新的提案，
没有很多相关的工具实现它，这其中就有 [pyflow]。但 pyflow 又是用 Rust 写的，不是所有 Python 的社区
都会用 Rust，这样就没法贡献代码，而且，基于同样的原因，pyflow 并不支持 PEP 517 构建。

## 安装:

PDM 需要 Python 3.7 或更高版本。

强烈推荐把 `pdm` 安装在一个隔离环境中， 用 `pipx` 是坠吼的。

```bash
$ pipx install pdm
```

或者你可以将它安装在用户目录下:

```bash
$ pip install --user pdm
```

## 使用方法

作者很懒，还没来得及写，先用 `python -m pdm --help` 查看帮助吧。

## 常见问题

### 1. `__pypackages__` 里都包含什么?

PEP 582 尚处于草案阶段，还需要补充很多细节，比如提案中并未说明可执行程序应该如何存放。PDM 会把 `bin`(可执行程序), `include`(头文件),
以及 `lib` 都放在 `__pypackage__/X.Y` 下面。

### 2. 如何运行 `__pypackages__` 下的可执行程序?

推荐的方式是在你的命令前面加上 `pdm run`, 你也可以直接运行 `bin` 下面的可执行程序。PDM 的安装器已经在可执行程序里面注入了本地包路径了。

### 3. 使用 PDM 时会载入哪些三方库路径?

PDM 会首先在 `__pypackage__` 中寻找，然后会在选择的 Python 解释器对应的 `site-packages` 中寻找包。

### 4. 我能把 `__pypackage__` 保存下来用来部署到别的机器上吗?

最好别这样搞，`__pypackage__` 下面安装的包是和操作系统相关的，所以除非是纯 Python 的包，都会有兼容性的问题。你应该把 `pdm.lock`
纳入版本管理，然后在目标环境中执行 `pdm sync`。

### 5. 我能用`pdm`管理一个 Python 2.7 的项目吗？
当然可以。只是`pdm`本身的安装需要 Python 版本高于 3.7，它并不限制项目使用的 Python 版本。

## 鸣谢

本项目的受到 [pyflow] 与 [poetry] 的很多启发。

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## 使用许可

本项目基于 MIT 协议开源，具体可查看 [LICENSE](LICENSE)。
