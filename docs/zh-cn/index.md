<div align="center">
<img src="assets/logo_big.png" alt="PDM logo">
</div>

# 简介

如前所述，PDM 是一个支持最新 PEP 标准的现代 Python 包和依赖项管理器。但它不仅仅是一个包管理器。它可以在各个方面提升您的开发工作流程。

<script id="asciicast-jnifN30pjfXbO9We2KqOdXEhB" src="https://asciinema.org/a/jnifN30pjfXbO9We2KqOdXEhB.js" async></script>

## 功能亮点

- 简单快速的依赖解析器，主要用于大型二进制发行版。
- 根据 [PEP 517] 规范构建后端。
- 根据 [PEP 621] 规范解析项目元数据。
- 灵活而强大的插件系统。
- 多功能用户脚本。
- 使用 [indygreg's python-build-standalone](https://github.com/indygreg/python-build-standalone)进行安装其他版本的 Python。
- 选择加入集中式安装缓存，参考 [pnpm]。

[pep 517]: https://www.python.org/dev/peps/pep-0517
[pep 621]: https://www.python.org/dev/peps/pep-0621
[pnpm]: https://pnpm.io/motivation#saving-disk-space-and-boosting-installation-speed

!!! 提示
    - PEP 517 是 Python Enhancement Proposal 的缩写，它定义了 Python 包的构建系统接口。在 PEP 517 中，构建后端负责实际执行项目构建的工作。
    - 构建后端（build backend）指的是用于构建 Python 项目的工具或库。
    - PEP 621 是 Python Enhancement Proposal 的一部分，它提出了关于 Python 项目元数据的新标准。元数据是指关于项目的信息，比如项目的名称、版本、作者、依赖项等等。

## 安装

PDM 需要安装 Python 3.8+。它适用于多个平台，包括 Windows、Linux 和 macOS。

!!! note
    你仍然可以让你的项目在较低的 Python 版本上工作，请阅读如何做到这一点 [点击这里](usage/project.md#working-with-python-37)。

### 推荐安装方式

PDM 需要 python 版本 3.8 或更高版本。

与 Pip 一样，PDM 提供了一个安装脚本，用于将 PDM 安装到隔离环境中。

=== "Linux/Mac"

    ```bash
    curl -sSL https://pdm-project.org/install-pdm.py | python3 -
    ```

=== "Windows"

    ```powershell
    [System.Text.Encoding]::UTF8.GetString((Invoke-WebRequest -Uri https://pdm-project.org/install-pdm.py).Content) | python -
    ```

出于安全原因，您应验证 `install-pdm.py` 文件的校验和。
您可以从 [install-pdm.py.sha256](https://pdm-project.org/install-pdm.py.sha256)下载该文件。

例如，在 Linux/Mac 上：

```bash
curl -sSLO https://pdm-project.org/install-pdm.py
curl -sSL https://pdm-project.org/install-pdm.py.sha256 | shasum -a 256 -c -
# 运行这个安装
python3 install-pdm.py [options]
```

安装程序会将 PDM 安装到用户家目录中，位置取决于系统：

- `$HOME/.local/bin` Unix 系统
- `$HOME/Library/Python/<version>/bin` MacOS 系统
- `%APPDATA%\Python\Scripts` Windows 系统

您可以将其他参数传递给脚本来控制 PDM 的安装方式：

```
usage: install-pdm.py [-h] [-v VERSION] [--prerelease] [--remove] [-p PATH] [-d DEP]

可选参数:
  -h, --help            显示帮助信息并退出
  -v VERSION, --version VERSION | envvar: PDM_VERSION
                        指定要安装的版本，或使用 HEAD 从主分支安装
  --prerelease | envvar: PDM_PRERELEASE    允许安装预发行版本
  --remove | envvar: PDM_REMOVE            移除 PDM 安装
  -p PATH, --path PATH | envvar: PDM_HOME  指定安装 PDM 的位置
  -d DEP, --dep DEP | envvar: PDM_DEPS     指定额外的依赖项，可以多次指定
```

您可以在运行的安装脚本命令的后面传递选项，也可以设置环境变量 env var 值。

### 其他安装方式

=== "Homebrew"

    ```bash
    brew install pdm
    ```

=== "Scoop"

    ```
    scoop bucket add frostming https://github.com/frostming/scoop-frostming.git
    scoop install pdm
    ```

=== "pipx"

    ```bash
    pipx install pdm
    ```

    安装 GitHub 存储库的最新版本。
    安装前确保您已在系统上安装了 [Git LFS](https://git-lfs.github.com/)。

    ```bash
    pipx install git+https://github.com/pdm-project/pdm.git@main#egg=pdm
    ```

    要安装具有所有功能的 PDM：

    ```bash
    pipx install pdm[all]
    ```

    要想了解 pipx 另请参阅： <https://pypa.github.io/pipx/>

=== "pip"

    ```bash
    pip install --user pdm
    ```

=== "asdf"

    假设您已经安装了 [asdf](https://asdf-vm.com/)。

    ```
    asdf plugin add pdm
    asdf local pdm latest
    asdf install pdm
    ```

=== "inside project"

    通过将 [Pyprojectx](https://pyprojectx.github.io/) 包装器脚本复制到一个项目中，您可以将 PDM 安装为该项目中的（npm 样式）开发依赖项。这允许不同的项目/分支使用不同的 PDM 版本。

    要 [ 初始化一个新的或现有的项目 ](https://pyprojectx.github.io/usage/#initialize-a-new-or-existing-project),
    cd 到项目文件夹中，然后执行对应系统的脚本:

    === "Linux/Mac"

        ```
        curl -LO https://github.com/pyprojectx/pyprojectx/releases/latest/download/wrappers.zip && unzip wrappers.zip && rm -f wrappers.zip
        ./pw --add pdm
        ```

    === "Windows"

        ```powershell
        Invoke-WebRequest https://github.com/pyprojectx/pyprojectx/releases/latest/download/wrappers.zip -OutFile wrappers.zip; Expand-Archive -Path wrappers.zip -DestinationPath .; Remove-Item -Path wrappers.zip
        .\pw --add pdm
        ```

    使用此方法安装 pdm 时, 需要通过 `pw` 包装器运行所有 `pdm` 命令:

    === "Linux/Mac/Windows"

        ```
        ./pw pdm install
        ```

### 更新 PDM 版本

```bash
pdm self update
```

## 各系统构建版本情况

[![Packaging status](https://repology.org/badge/vertical-allrepos/pdm.svg)](https://repology.org/project/pdm/versions)

## Shell 命令补全

PDM 支持为 Bash、Zsh、Fish 或 Powershell 生成补全脚本。以下是每个 shell 的一些常见的储存位置：

=== "Bash"

    ```bash
    pdm completion bash > /etc/bash_completion.d/pdm.bash-completion
    ```

=== "Zsh"

    ```bash
    # 确保在执行 compinit 参数之前将 ~/.zfunc 添加到fpath中。
    pdm completion zsh > ~/.zfunc/_pdm
    ```

    Oh-My-Zsh:

    ```bash
    mkdir $ZSH_CUSTOM/plugins/pdm
    pdm completion zsh > $ZSH_CUSTOM/plugins/pdm/_pdm
    ```

    然后确保在 ~/.zshrc 中启用了 pdm 插件

=== "Fish"

    ```bash
    pdm completion fish > ~/.config/fish/completions/pdm.fish
    ```

=== "Powershell"

    ```ps1
    # 创建一个目录来存储补全脚本。
    mkdir $PROFILE\..\Completions
    echo @'
    Get-ChildItem "$PROFILE\..\Completions\" | ForEach-Object {
        . $_.FullName
    }
    '@ | Out-File -Append -Encoding utf8 $PROFILE
    # 生成脚本
    Set-ExecutionPolicy Unrestricted -Scope CurrentUser
    pdm completion powershell | Out-File -Encoding utf8 $PROFILE\..\Completions\pdm_completion.ps1
    ```

## Virtualenv 和 PEP 582

除了 virtualenv 管理之外，PDM 还提供对 [PEP 582](https://www.python.org/dev/peps/pep-0582/) 的实验性支持作为选择加入功能。 尽管  [Python 指导委员会拒绝了 PEP 582][rejected],但您仍然可以使用 PDM 对其进行测试。

要了解有关这两种模式的更多信息， 请参阅有关使用 [Working with virtualenv](usage/venv.md) 和 [Working with PEP 582](usage/pep582.md) 使用 PEP 582 的相关章节。

[rejected]: https://discuss.python.org/t/pep-582-python-local-packages-directory/963/430

## PDM 生态系统

[Awesome PDM](https://github.com/pdm-project/awesome-pdm) 是精选的 PDM 插件和资源列表。

## 赞助商

<p align="center">
    <a href="https://cdn.jsdelivr.net/gh/pdm-project/sponsors/sponsors.svg">
        <img src="https://cdn.jsdelivr.net/gh/pdm-project/sponsors/sponsors.svg"/>
    </a>
</p>
