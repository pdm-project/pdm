## Available Configurations

| Config Item                   | Description                                                               | Default Value                                                             | Available in Project | Env var                  |
| ----------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------- | ------------------------ |
| `cache_dir`                   | The root directory of cached files                                        | The default cache location on OS                                          | No                   |                          |
| `auto_global`                 | Use global package implicitly if no local project is found                | `False`                                                                   | No                   | `PDM_AUTO_GLOBAL`        |
| `use_venv`                    | Install packages into the activated venv site packages instead of PEP 582 | `False`                                                                   | Yes                  | `PDM_USE_VENV`           |
| `parallel_install`            | Whether to perform installation and uninstallation in parallel            | `True`                                                                    | Yes                  | `PDM_PARALLEL_INSTALL`   |
| `python.path`                 | The Python interpreter path                                               |                                                                           | Yes                  | `PDM_PYTHON_PATH`        |
| `python.use_pyenv`            | Use the pyenv interpreter                                                 | `True`                                                                    | Yes                  |                          |
| `pypi.url`                    | The URL of PyPI mirror                                                    | Read `index-url` in `pip.conf`, or `https://pypi.org/simple` if not found | Yes                  | `PDM_PYPI_URL`           |
| `pypi.verify_ssl`             | Verify SSL certificate when query PyPI                                    | Read `trusted-hosts` in `pip.conf`, defaults to `True`                    | Yes                  |                          |
| `pypi.json_api`               | Consult PyPI's JSON API for package metadata                              | `False`                                                                   | Yes                  | `PDM_PYPI_JSON_API`      |
| `strategy.save`               | Specify how to save versions when a package is added                      | `compatible`(can be: `exact`, `wildcard`)                                 | Yes                  |                          |
| `strategy.update`             | The default strategy for updating packages                                | `reuse`(can be : `eager`)                                                 | Yes                  |                          |
| `strategy.resolve_max_rounds` | Specify the max rounds of resolution process                              | 1000                                                                      | Yes                  | `PDM_RESOLVE_MAX_ROUNDS` |

_If the corresponding env var is set, the value will take precedence over what is saved in the config file._
