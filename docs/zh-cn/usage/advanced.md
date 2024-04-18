# 高级用法

## 自动化测试

### 使用 Tox 作为运行器

[Tox](https://tox.readthedocs.io/en/latest/) 是一个很好的工具，可以针对多个 Python 版本或依赖关系集进行测试。
您可以配置一个像下面这样的 `tox.ini` 来与 PDM 集成测试：

```ini
[tox]
env_list = py{36,37,38},lint

[testenv]
setenv =
    PDM_IGNORE_SAVED_PYTHON="1"
deps = pdm
commands =
    pdm install --dev
    pytest tests

[testenv:lint]
deps = pdm
commands =
    pdm install -G lint
    flake8 src/
```

要使用 Tox 创建的虚拟环境，您应该确保已设置 `pdm config python.use_venv true`。然后，PDM 将安装 [`pdm lock`](../reference/cli.md#lock) 中的依赖项到虚拟环境中。在专用虚拟环境中，您可以直接通过 `pytest tests/` 而不是 `pdm run pytest tests/` 运行工具。

您还应该确保在测试命令中不运行 `pdm add/pdm remove/pdm update/pdm lock`，否则 [`pdm lock`](../reference/cli.md#lock) 文件将意外修改。可以通过 `deps` 配置提供额外的依赖项。此外，`isolated_build` 和 `passenv` 配置应设置为上面的示例，以确保 PDM 正常工作。

为了摆脱这些限制，有一个 Tox 插件 [tox-pdm](https://github.com/pdm-project/tox-pdm) 可以简化使用。您可以通过以下方式安装它：

```bash
pip install tox-pdm
```

或者，

```bash
pdm add --dev tox-pdm
```

然后，您可以像下面这样使 tox.ini 更整洁：

```ini
[tox]
env_list = py{36,37,38},lint

[testenv]
groups = dev
commands =
    pytest tests

[testenv:lint]
groups = lint
commands =
    flake8 src/
```

请查看 [项目的 README](https://github.com/pdm-project/tox-pdm) 以获取详细指导。

### 使用 Nox 作为运行器

[Nox](https://nox.thea.codes/) 是另一个很棒的自动化测试工具。与 tox 不同，Nox 使用标准的 Python 文件进行配置。

在 Nox 中使用 PDM 要简单得多，这是一个 `noxfile.py` 的示例：

```python hl_lines="4"
import os
import nox

os.environ.update({"PDM_IGNORE_SAVED_PYTHON": "1"})

@nox.session
def tests(session):
    session.run_always('pdm', 'install', '-G', 'test', external=True)
    session.run('pytest')

@nox.session
def lint(session):
    session.run_always('pdm', 'install', '-G', 'lint', external=True)
    session.run('flake8', '--import-order-style', 'google')
```

请注意，必须设置 `PDM_IGNORE_SAVED_PYTHON`，以便 PDM 正确地识别虚拟环境中的 Python。还要确保 `pdm` 在 `PATH` 中可用。
在运行 nox 之前，还应确保配置项 `python.use_venv` 为 `true` 以启用虚拟环境复用。

### 关于 PEP 582 `__pypackages__` 目录

默认情况下，如果使用 [`pdm run`](../reference/cli.md#run) 运行工具，`__pypackages__` 将被程序和其创建的所有子进程看到。这意味着由这些工具创建的虚拟环境也知道 `__pypackages__` 中的软件包，这在某些情况下会导致意外行为。
对于 `nox`，您可以通过在 `noxfile.py` 中添加一行来避免这种情况：

```python
os.environ.pop("PYTHONPATH", None)
```

对于 `tox`，`PYTHONPATH` 不会传递到测试会话，因此这不会成为问题。此外，建议将 `nox` 和 `tox` 放在它们自己的 pipx 环境中，这样您就不需要为每个项目安装它们。在这种情况下，PEP 582 软件包也不会成为问题。

## 在持续集成中使用 PDM

只需记住一件事 PDM **不能安装在** Python < 3.7 上，因此，如果您的项目需要在这些 Python 版本上进行测试，
您必须确保 PDM 安装在正确的 Python 版本上，这可能与特定任务/作业要运行的目标 Python 版本不同。

幸运的是，如果您使用 GitHub Action，有一个 [pdm-project/setup-pdm](https://github.com/marketplace/actions/setup-pdm) 来简化这个过程。
这是 GitHub Actions 的一个示例工作流，您可以根据其他 CI 平台进行调整。

```yaml
Testing:
  runs-on: ${{ matrix.os }}
  strategy:
    matrix:
      python-version: [3.7, 3.8, 3.9, '3.10', '3.11']
      os: [ubuntu-latest, macOS-latest, windows-latest]

  steps:
    - uses: actions/checkout@v3
    - name: Set up PDM
      uses: pdm-project/setup-pdm@v3
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        pdm sync -d -G testing
    - name: Run Tests
      run: |
        pdm run -v pytest tests
```

!!! important "提示"
    对于 GitHub Action 用户，Ubuntu 虚拟环境存在一个  [已知的兼容性问题](https://github.com/actions/virtual-environments/issues/2803) 如果在该机器上 PDM 并行安装失败，您应该将 `parallel_install` 设置为 `false`，或设置环境变量 `LD_PRELOAD=/lib/x86_64-linux-gnu/libgcc_s.so.1`。
    这已经由 `pdm-project/setup-pdm` 操作处理。

!!! note
    如果您的 CI 脚本在没有正确用户设置的情况下运行，当 PDM 尝试创建其缓存目录时，您可能会遇到权限错误。
    为了解决这个问题，您可以自己设置 HOME 环境变量，指向一个可写的目录，例如：

    ```bash
    export HOME=/tmp/home
    ```

## 在多阶段 Dockerfile 中使用 PDM

可以在多阶段 Dockerfile 中使用 PDM，先将项目和依赖项安装到 `__pypackages__` 中，
然后将此文件夹复制到最终阶段，并将其添加到 `PYTHONPATH` 中。

```dockerfile
ARG PYTHON_BASE=3.10-slim
# 构建阶段
FROM python:$PYTHON_BASE AS builder

# 安装 PDM
RUN pip install -U pdm
# 禁用更新检查
ENV PDM_CHECK_UPDATE=false
# 复制文件
COPY pyproject.toml pdm.lock README.md /project/
COPY src/ /project/src

# 安装依赖项和项目到本地包目录
WORKDIR /project
RUN pdm install --check --prod --no-editable

# 运行阶段
FROM python:$PYTHON_BASE

# 从构建阶段获取包
COPY --from=builder /project/.venv/ /project/.venv
ENV PATH="/project/.venv/bin:$PATH"
# 设置命令/入口点，根据需要进行调整
COPY src /project/src
CMD ["python", "src/__main__.py"]
```

## 使用 PDM 管理多仓库

使用 PDM，您可以在单个项目中拥有多个子包，每个子包都有自己的 pyproject.toml 文件。您可以创建一个 pdm.lock 文件来锁定所有依赖项。子包可以相互作为它们的依赖项。要实现这一点，请按照以下步骤操作：

`project/pyproject.toml`:

```toml
[tool.pdm.dev-dependencies]
dev = [
    "-e file:///${PROJECT_ROOT}/packages/foo-core",
    "-e file:///${PROJECT_ROOT}/packages/foo-cli",
    "-e file:///${PROJECT_ROOT}/packages/foo-app",
]
```

`packages/foo-cli/pyproject.toml`:

```toml
[project]
dependencies = ["foo-core"]
```

`packages/foo-app/pyproject.toml`:

```toml
[project]
dependencies = ["foo-core"]
```

现在，在项目根目录中运行 `pdm install`，您将获得一个带有所有依赖项锁定的 `pdm.lock`。所有子包将以可编辑模式安装。

查看 [🚀 示例存储库](https://github.com/pdm-project/pdm-example-monorepo) 获取更多详细信息。

## `pre-commit` 钩子

[`pre-commit`](https://pre-commit.com/) 是一个管理 git 钩子的强大框架。PDM 已经使用 `pre-commit` [hooks](https://github.com/pdm-project/pdm/blob/main/.pre-commit-config.yaml) 进行了内部质量检查。PDM 还公开了几个钩子，可以在本地或 CI 管道中运行。

### 导出 `requirements.txt`

此钩子包装了 `pdm export` 命令以及任何有效参数。它可以作为一个钩子（例如，用于 CI）来确保您将检查代码库中的一个 `requirements.txt`，其中包含了 [`pdm lock`](../reference/cli.md#lock) 的实际内容。

```yaml
# 导出 Python 依赖
- repo: https://github.com/pdm-project/pdm
  rev: 2.x.y # 公开了该钩子的 PDM 版本
  hooks:
    - id: pdm-export
      # 命令参数，例如：
      args: ['-o', 'requirements.txt', '--without-hashes']
      files: ^pdm.lock$
```

### 检查 `pdm.lock` 是否与 pyproject.toml 保持同步

此钩子包装了 `pdm lock --check` 命令以及任何有效参数。它可以作为一个钩子（例如，用于 CI）来确保每当 `pyproject.toml` 添加/更改/删除一个依赖项时，pdm.lock 也保持同步。

```yaml
- repo: https://github.com/pdm-project/pdm
  rev: 2.x.y # 公开了该钩子的 PDM 版本
  hooks:
    - id: pdm-lock-check
```

### 将当前工作集与 `pdm.lock` 同步

此钩子包装了 `pdm sync` 命令以及任何有效参数。它可以作为一个钩子来确保您的当前工作集与 `pdm.lock` 同步，无论何时您检出或合并一个分支。如果您想使用系统凭据存储，则将 keyring 添加到 `additional_dependencies`。

```yaml
- repo: https://github.com/pdm-project/pdm
  rev: 2.x.y # 公开了该钩子的 PDM 版本
  hooks:
    - id: pdm-sync
      additional_dependencies:
        - keyring
```
