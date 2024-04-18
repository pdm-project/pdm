# Build Configuration

`pdm` 使用 [PEP 517](https://www.python.org/dev/peps/pep-0517/) 来构建软件包。它充当构建前端，调用构建后端来从任意源树构建源分发和轮子。

构建后端是驱动构建系统从任意源树构建源分发和轮子的组件。

如果运行 [`pdm init`](../reference/cli.md#init)，PDM 将让您选择要使用的构建后端。与其他包管理器不同，PDM 不会强迫您使用特定的构建后端。您可以选择您喜欢的构建后端。以下是 PDM 最初支持的构建后端及相应的配置列表：

=== "pdm-backend"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["pdm-backend"]
    build-backend = "pdm.backend"
    ```

    [:book: 阅读文档](https://backend.pdm-project.org/)

=== "setuptools"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["setuptools", "wheel"]
    build-backend = "setuptools.build_meta"
    ```

    [:book: 阅读文档](https://setuptools.pypa.io/)

=== "flit"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["flit_core >=3.2,<4"]
    build-backend = "flit_core.buildapi"
    ```

    [:book: 阅读文档](https://flit.pypa.io/)

=== "hatchling"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"
    ```

    [:book: 阅读文档](https://hatch.pypa.io/)

=== "maturin"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["maturin>=1.4,<2.0"]
    build-backend = "maturin"
    ```

    [:book: 阅读文档](https://www.maturin.rs/)

除了上述提到的后端之外，您还可以使用任何支持 PEP 621 的其他后端，但是 [poetry-core](https://python-poetry.org/) 不受支持，因为它不支持读取 PEP 621 元数据。

!!! info
    如果您使用的是不在上述列表中的自定义构建后端，PDM 将处理相对路径为 PDM 样式 (`${PROJECT_ROOT}` 变量)。
