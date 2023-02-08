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

## Build and publish separately

You can also build the package and upload it in two steps, to allow you to inspect the built artifacts before uploading.

```bash
pdm build
```

There are many options to control the build process, depending on the backend used. Refer to the [build configuration](../references/build.md) section for more details.

The artifacts will be created at `dist/` and able to upload to PyPI.

```bash
pdm publish --no-build
```
