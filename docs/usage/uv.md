# Use uv (Experimental)

+++ 2.19.0

PDM has experimental support for [uv](https://github.com/astral-sh/uv) as the resolver and installer. To enable it:

```
pdm config use_uv true
```

PDM will automatically detect the `uv` binary on your system. You need to install `uv` first. See [uv's installation guide](https://docs.astral.sh/uv/getting-started/installation/) for more details.

## Limitations

Despite the significant performance improvements brought by uv, it is important to note the following limitations of uv:

- The cache files are stored in uv's own cache directory, and you have to use `uv` command to manage them.
- PEP 582 local packages layout is not supported.
- `inherit_metadata` lock strategy is not supported by uv. This will be ignored when writing to the lock file.
- Update strategies other than `all` and `reuse` are not supported.
- Editable requirement must be a local path. Requirements like `-e git+<git_url>` are not supported.
