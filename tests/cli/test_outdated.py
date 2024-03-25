import json
from unittest import mock

import pytest
from rich.box import ASCII


@mock.patch("pdm.termui.ROUNDED", ASCII)
@pytest.mark.usefixtures("working_set")
def test_outdated(project, pdm, index):
    pdm(["add", "requests"], obj=project, strict=True, cleanup=False)
    project.project_config["pypi.url"] = "https://my.pypi.org/simple"
    del project.pyproject.settings["source"]
    project.pyproject.write()
    index["/simple/requests/"] = b"""\
<!DOCTYPE html>
<html>
  <body>
    <h1>requests</h1>
    <a
      href="http://fixtures.test/artifacts/requests-2.20.0-py3-none-any.whl"
      data-requires-python=">=3.7"
    >
      requests-2.20.0-py3-none-any.whl
    </a>
  </body>
</html>

"""

    result = pdm(["outdated"], obj=project, strict=True, cleanup=False)
    assert "| requests | 2.19.1    | 2.19.1 | 2.20.0 |" in result.stdout

    result = pdm(["outdated", "re*"], obj=project, strict=True, cleanup=False)
    assert "| requests | 2.19.1    | 2.19.1 | 2.20.0 |" in result.stdout

    result = pdm(["outdated", "--json"], obj=project, strict=True, cleanup=False)
    json_output = json.loads(result.stdout)
    assert json_output == [
        {"package": "requests", "installed_version": "2.19.1", "pinned_version": "2.19.1", "latest_version": "2.20.0"}
    ]
