# Build Configuration

`pdm` uses the [PEP 517](https://www.python.org/dev/peps/pep-0517/) to build the package. It acts as a build frontend that calls the build backend to build the package.
A build backend is what drives the build system to build source distributions and wheels from arbitrary source trees.

`pdm` also ships with its own build backend, [`pdm-backend`](https://pypi.org/project/pdm-backend/). To use it, you need to add the following to your `pyproject.toml`:

```toml
[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"
```

Read the [backend docs](https://pdm-backend.fming.dev/) about how to configure the build backend.

## Use other build backends

Apart from `pdm-backend`, `pdm` plays well with any PEP 517 build backend that reads PEP 621 metadata. At the time of writing, [`flit`](https://pypi.org/project/flit)(backend: `flit-core`) and [`hatch`](https://pypi.org/project/hatch)(backend: `hatchling`) are working well with PEP 621 and [`setuptools`](https://pypi.org/project/setuptools) also added the support recently. To use one of them, you can specify the backend in the `pyproject.toml`:

```toml
[build-system]
requires = ["flit_core >=3.2,<4"]
build-backend = "flit_core.buildapi"
```

PDM will show the list of available backends when running [`pdm init`](../usage/cli_reference.md#exec-0--init). Based on the selected backend, PDM will complete the `build-system` table for you.
