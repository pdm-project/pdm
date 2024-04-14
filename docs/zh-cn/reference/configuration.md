# Configurations

[pdm-config]: ../reference/cli.md#config

## Color Theme

The default theme used by PDM is as follows:

| Key       | Default Style                                                |
| --------- | ------------------------------------------------------------ |
| `primary` | <span style="color:cyan">cyan</span>                         |
| `success` | <span style="color:green">green</span>                       |
| `warning` | <span style="color:yellow">yellow</span>                     |
| `error`   | <span style="color:red">red</span>                           |
| `info`    | <span style="color:blue">blue</span>                         |
| `req`     | <span style="color:green;font-weight:bold">bold green</span> |

You can change the theme colors with [`pdm config`][pdm-config] command. For example, to change the `primary` color to `magenta`:

```bash
pdm config theme.primary magenta
```

Or use a hex color code:

```bash
pdm config theme.success '#51c7bd'
```

## Available Configurations

The following configuration items can be retrieved and modified by [`pdm config`][pdm-config] command.

!!! note "Environment Variable Overrides"
    If the corresponding env var is set, the value will take precedence over what is saved in the config file.


```python exec="on"
from pdm.project.config import Config

print("| Config Item | Description | Default Value | Available in Project | Env var |")
print("| --- | --- | --- | --- | --- |")
for key, value in Config._config_map.items():
    print(f"| `{key}` | {value.description} | {('`%s`' % value.default) if value.should_show() else ''} | {'No' if value.global_only else 'Yes'} | {('`%s`' % value.env_var) if value.env_var else ''} |")
print("""\
| `pypi.<name>.url`                 | The URL of custom package source                                                     | `https://pypi.org/simple`                                             | Yes                  |                           |
| `pypi.<name>.username`            | The username to access custom source                                                 |                                                                       | Yes                  |                           |
| `pypi.<name>.password`            | The password to access custom source                                                 |                                                                       | Yes                  |                           |
| `pypi.<name>.type`                | `index` or `find_links`                                                              | `index`                                                               | Yes                  |                           |
| `pypi.<name>.verify_ssl`          | Verify SSL certificate when query custom source                                      | `True`                                                                | Yes                  |                           |
| `repository.<name>.url`           | The URL of custom package source                                                     | `https://pypi.org/simple`                                             | Yes                  |                           |
| `repository.<name>.username`      | The username to access custom repository                                             |                                                                       | Yes                  |                           |
| `repository.<name>.password`      | The password to access custom repository                                             |                                                                       | Yes                  |                           |
| `repository.<name>.ca_certs`      | Path to a PEM-encoded CA cert bundle (used for server cert verification)             | The CA certificates from [certifi](https://pypi.org/project/certifi/) | Yes                  |                           |
| `repository.<name>.verify_ssl`    | Verify SSL certificate when uploading to repository                                  | `True`                                                                | Yes                  |                           |
""")
```

