# Build Configuration

`pdm` uses the [PEP 517](https://www.python.org/dev/peps/pep-0517/) to build the package. It acts as a build frontend that calls the build backend to build the package.

A build backend is what drives the build system to build source distributions and wheels from arbitrary source trees.

If you run [`pdm init`](../reference/cli.md#init), PDM will let you choose the build backend to use. Unlike other package managers, PDM does not force you to use a specific build backend. You can choose the one you like. Here is a list of build backends and corresponding configurations initially supported by PDM:

=== "pdm-backend"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["pdm-backend"]
    build-backend = "pdm.backend"
    ```

    [:book: Read the docs](https://pdm-backend.fming.dev/)

=== "setuptools"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["setuptools", "wheel"]
    build-backend = "setuptools.build_meta"
    ```

    [:book: Read the docs](https://setuptools.pypa.io/)

=== "flit"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["flit_core >=3.2,<4"]
    build-backend = "flit_core.buildapi"
    ```

    [:book: Read the docs](https://flit.pypa.io/)

=== "hatchling"

    `pyproject.toml` configuration:

    ```toml
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"
    ```

    [:book: Read the docs](https://hatch.pypa.io/)


Apart from the above mentioned backends, you can also use any other backend that supports PEP 621, however, [poetry-core](https://python-poetry.org/) is not supported because it does not support reading PEP 621 metadata.

!!! info
    If you are using a custom build backend that is not in the above list, PDM will handle the relative paths as PDM-style(`${PROJECT_ROOT}` variable).
