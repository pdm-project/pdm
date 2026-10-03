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
    assert "| requests | default | 2.19.1    | 2.19.1 | 2.20.0 |" in result.stdout

    result = pdm(["outdated", "re*"], obj=project, strict=True, cleanup=False)
    assert "| requests | default | 2.19.1    | 2.19.1 | 2.20.0 |" in result.stdout

    result = pdm(["outdated", "--json"], obj=project, strict=True, cleanup=False)
    json_output = json.loads(result.stdout)
    assert json_output == [
        {
            "package": "requests",
            "groups": ["default"],
            "installed_version": "2.19.1",
            "pinned_version": "2.19.1",
            "latest_version": "2.20.0",
        }
    ]


@pytest.mark.usefixtures("local_finder")
def test_outdated_in_given_venv(project, pdm):
    project.pyproject.metadata["requires-python"] = ">=3.7"
    project.pyproject.write()
    project.global_config["python.use_venv"] = True
    pdm(["venv", "create"], obj=project, strict=True)
    pdm(["venv", "create", "--name", "second"], obj=project, strict=True)
    project._saved_python = None
    pdm(["add", "first", "--no-self"], obj=project, strict=True)
    second_lockfile = str(project.root / "pdm.2.lock")
    pdm(
        ["add", "-G", "second", "--no-self", "-L", second_lockfile, "--venv", "second", "zipp==3.6.0"],
        obj=project,
        strict=True,
    )
    project.environment = None
    result1 = pdm(["outdated", "--json"], obj=project, strict=True)
    result2 = pdm(["outdated", "--json", "--venv", "second"], obj=project, strict=True)
    outdated_in_default = {p["package"]: p for p in json.loads(result1.stdout)}
    outdated_in_second = {p["package"]: p for p in json.loads(result2.stdout)}
    # zipp is only installed in the second venv
    assert outdated_in_default.get("zipp", {}).get("installed_version", "") == "", result1.stdout
    assert outdated_in_second["zipp"]["installed_version"] == "3.6.0", result2.stdout
    assert outdated_in_second["zipp"]["latest_version"] == "3.7.0", result2.stdout
