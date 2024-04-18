# 构建和发布

如果您正在开发库，则在向项目添加依赖项并完成编码后，就可以构建和发布包了。它就像一个命令一样简单：

```bash
pdm publish
```

这将自动构建一个轮子和一个源分发（sdist），并将它们上传到 PyPI 索引。

要指定 PyPI 以外的其他存储库，请使用选项 `--repository` ，参数可以是上传 URL，也可以是存储在配置文件中的存储库的名称。

```bash
pdm publish --repository testpypi
pdm publish --repository https://test.pypi.org/legacy/
```

## 使用受信任的发布者发布

可以为 PyPI 配置受信任的发布者，这样就不需要在发布工作流中公开 PyPI 令牌。为此，请按照[指南](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)添加发布者并编写 GitHub Actions 工作流，如下所示：

```yaml
jobs:
  pypi-publish:
    name: upload release to PyPI
    runs-on: ubuntu-latest
    permissions:
      # 这个权限是为了私有仓库。
      contents: read
      # 重要提示：这个权限对于可信发布是必需的。
      id-token: write
    steps:
      - uses: actions/checkout@v3

      - uses: pdm-project/setup-pdm@v3

      - name: Publish package distributions to PyPI
        run: pdm publish
```

## 单独生成和发布

您还可以通过两个步骤构建包并上传它，以便您在上传之前检查构建的项目。

```bash
pdm build
```

有许多选项可以控制生成过程，具体取决于使用的后端。有关更多详细信息，请参阅[构建配置](../reference/build.md)部分。

工件将在 PyPI 处创建 `dist/` 并能够上传到 PyPI。

```bash
pdm publish --no-build
```
