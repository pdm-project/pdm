# 配置

[pdm-config]: ../reference/cli.md#config

## 颜色主题

PDM 使用的默认主题如下：

| Key       | 默认样式                                                |
| --------- | ------------------------------------------------------------ |
| `primary` | <span style="color:cyan">cyan</span>                         |
| `success` | <span style="color:green">green</span>                       |
| `warning` | <span style="color:yellow">yellow</span>                     |
| `error`   | <span style="color:red">red</span>                           |
| `info`    | <span style="color:blue">blue</span>                         |
| `req`     | <span style="color:green;font-weight:bold">bold green</span> |

您可以使用 [pdm config][pdm-config] 命令更改主题颜色。例如，要将 `primary` 颜色更改为 `magenta`：

```bash
pdm config theme.primary magenta
```

或者使用十六进制颜色代码：

```bash
pdm config theme.success '#51c7bd'
```

## 可用配置

可以通过 [`pdm config`][pdm-config] 命令检索和修改以下配置项。

!!! note "Environment Variable Overrides"
    如果设置了相应的 env var，则该值将优先于配置文件中保存的值。


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

