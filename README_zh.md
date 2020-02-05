# PDM - Python Development Master

一个现代的 Python 包管理器，支持 PEP 582。[English version README](README.md)

![Github Actions](https://github.com/pdm-project/pdm/workflows/Tests/badge.svg)

## 这个项目是啥?

PDM 旨在成为下一代 Python 软件包管理工具。它最初是为个人兴趣而诞生的。如果你觉得 `pipenv` 或者
`poetry` 用着非常好，并不想引入一个新的包管理器，那么继续使用它们吧；但如果你发现有些东西这些
工具不支持，那么你很可能可以在 `pdm` 中找到。

**需求收集正在进行中，请戳 https://github.com/pdm-project/call-for-features.**

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

```bash
$ pipx install pdm
```

强烈推荐把 `pdm` 安装在一个隔离环境中， 用 `pipx` 是坠吼的。

或者你可以将它安装在用户目录下:

```bash
$ pip install --user pdm
```

## 使用方法

作者很懒，还没来得及写，先用 `python -m pdm --help` 查看帮助吧。

## Credits

本项目的受到 [pyflow] 与 [poetry] 的很多启发。

[pyflow]: https://github.com/David-OConnor/pyflow
[poetry]: https://github.com/python-poetry/poetry

## License

本项目基于 MIT 协议开源，具体可查看 [LICENSE](LICENSE)。
