# Build and Publish

If you are developing a library, after adding dependencies to your project, and finishing the coding, it's time to build and publish your package. It is as simple as one command:

```bash
pdm publish
```

This will automatically build a wheel and a source distribution(sdist), and upload them to the PyPI index.

To specify another repository other than PyPI, use the `--repository` option, the parameter can be either the upload URL or the name of the repository stored in the config file.

```bash
pdm publish --repository testpypi
pdm publish --repository https://test.pypi.org/legacy/
```

## Publish with trusted publishers

You can configure trusted publishers for PyPI so that you don't need to expose the PyPI tokens in the release workflow. To do this, follow
[the guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) to add a publisher and write the GitHub Actions workflow as below:

```yaml
jobs:
  pypi-publish:
    name: upload release to PyPI
    runs-on: ubuntu-latest
    permissions:
      # IMPORTANT: this permission is mandatory for trusted publishing
      id-token: write
    steps:
      - uses: actions/checkout@v3

      - uses: pdm-project/setup-pdm@v3

      - name: Publish package distributions to PyPI
        run: pdm publish
```

## Build and publish separately

You can also build the package and upload it in two steps, to allow you to inspect the built artifacts before uploading.

```bash
pdm build
```

There are many options to control the build process, depending on the backend used. Refer to the [build configuration](../reference/build.md) section for more details.

The artifacts will be created at `dist/` and able to upload to PyPI.

```bash
pdm publish --no-build
```
