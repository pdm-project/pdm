import os
import shutil
from argparse import Namespace

import pytest
import requests

from pdm.cli.commands.publish import Command as PublishCommand
from pdm.cli.commands.publish.package import PackageFile
from pdm.cli.commands.publish.repository import Repository
from tests import FIXTURES


@pytest.fixture(autouse=True)
def mock_run_gpg(mocker):
    def mock_run_gpg(args):
        signature_file = args[-1] + ".asc"
        with open(signature_file, "wb") as f:
            f.write(b"fake signature")

    mocker.patch.object(PackageFile, "_run_gpg", side_effect=mock_run_gpg)


@pytest.fixture()
def prepare_packages(tmp_path):
    dist_path = tmp_path / "dist"
    dist_path.mkdir()
    for filename in [
        "demo-0.0.1-py2.py3-none-any.whl",
        "demo-0.0.1.tar.gz",
        "demo-0.0.1.zip",
    ]:
        shutil.copy2(FIXTURES / "artifacts" / filename, dist_path)


@pytest.fixture()
def mock_pypi(mocker):
    def post(url, *, data, **kwargs):
        # consume the data body to make the progress complete
        data.read()
        resp = requests.Response()
        resp.status_code = 200
        resp.reason = "OK"
        resp.url = url
        return resp

    return mocker.patch("pdm.models.session.PDMSession.post", side_effect=post)


@pytest.fixture()
def uploaded(mocker):
    packages = []

    def fake_upload(package, progress):
        packages.append(package)
        resp = requests.Response()
        resp.status_code = 200
        resp.reason = "OK"
        resp.url = "https://upload.pypi.org/legacy/"
        return resp

    mocker.patch.object(Repository, "upload", side_effect=fake_upload)
    return packages


@pytest.mark.parametrize(
    "filename",
    ["demo-0.0.1-py2.py3-none-any.whl", "demo-0.0.1.tar.gz", "demo-0.0.1.zip"],
)
def test_package_parse_metadata(filename):
    fullpath = FIXTURES / "artifacts" / filename
    package = PackageFile.from_filename(str(fullpath), None)
    assert package.base_filename == filename
    meta = package.metadata_dict
    assert meta["name"] == "demo"
    assert meta["version"] == "0.0.1"
    assert all(
        f"{hash_name}_digest" in meta for hash_name in ["md5", "sha256", "blake2_256"]
    )

    if filename.endswith(".whl"):
        assert meta["pyversion"] == "py2.py3"
        assert meta["filetype"] == "bdist_wheel"
    else:
        assert meta["pyversion"] == "source"
        assert meta["filetype"] == "sdist"


def test_package_add_signature(tmp_path):
    package = PackageFile.from_filename(
        str(FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl"), None
    )
    tmp_path.joinpath("signature.asc").write_bytes(b"test gpg signature")
    package.add_gpg_signature(str(tmp_path / "signature.asc"), "signature.asc")
    assert package.gpg_signature == ("signature.asc", b"test gpg signature")


def test_package_call_gpg_sign():
    package = PackageFile.from_filename(
        str(FIXTURES / "artifacts/demo-0.0.1-py2.py3-none-any.whl"), None
    )
    try:
        package.sign(None)
    finally:
        try:
            os.unlink(package.filename + ".asc")
        except OSError:
            pass
    assert package.gpg_signature == (package.base_filename + ".asc", b"fake signature")


def test_repository_get_release_urls(project):
    package_files = [
        PackageFile.from_filename(str(FIXTURES / "artifacts" / fn), None)
        for fn in [
            "demo-0.0.1-py2.py3-none-any.whl",
            "demo-0.0.1.tar.gz",
            "demo-0.0.1.zip",
        ]
    ]
    repository = Repository(project, "https://upload.pypi.org/legacy/", None, None)
    assert repository.get_release_urls(package_files) == {
        "https://pypi.org/project/demo/0.0.1/"
    }

    repository = Repository(project, "https://example.pypi.org/legacy/", None, None)
    assert not repository.get_release_urls(package_files)


@pytest.mark.usefixtures("prepare_packages")
def test_publish_pick_up_asc_files(project, uploaded, invoke):
    for p in list(project.root.joinpath("dist").iterdir()):
        with open(str(p) + ".asc", "w") as f:
            f.write("fake signature")

    invoke(["publish", "--no-build"], obj=project, strict=True)
    # Test wheels are uploaded first
    assert uploaded[0].base_filename.endswith(".whl")
    for package in uploaded:
        assert package.gpg_signature == (
            package.base_filename + ".asc",
            b"fake signature",
        )


@pytest.mark.usefixtures("prepare_packages")
def test_publish_package_with_signature(project, uploaded, invoke):
    invoke(["publish", "--no-build", "-S"], obj=project, strict=True)
    for package in uploaded:
        assert package.gpg_signature == (
            package.base_filename + ".asc",
            b"fake signature",
        )


@pytest.mark.usefixtures("local_finder")
def test_publish_and_build_in_one_run(fixture_project, invoke, mock_pypi):
    project = fixture_project("demo-module")
    result = invoke(["publish"], obj=project, strict=True).output

    mock_pypi.assert_called()
    assert "Uploading demo_module-0.1.0-py3-none-any.whl" in result
    assert "Uploading demo-module-0.1.0.tar.gz" in result
    assert "https://pypi.org/project/demo-module/0.1.0/" in result


def test_publish_cli_args_and_env_var_precedence(project, monkeypatch):
    repo = PublishCommand.get_repository(
        project, Namespace(repository=None, username="foo", password="bar")
    )
    assert repo.url == "https://upload.pypi.org/legacy/"
    assert repo.session.auth == ("foo", "bar")

    with monkeypatch.context() as m:
        m.setenv("PDM_PUBLISH_USERNAME", "bar")
        m.setenv("PDM_PUBLISH_PASSWORD", "secret")
        m.setenv("PDM_PUBLISH_REPO", "testpypi")

        repo = PublishCommand.get_repository(
            project, Namespace(repository=None, username=None, password=None)
        )
        assert repo.url == "https://test.pypi.org/legacy/"
        assert repo.session.auth == ("bar", "secret")

        repo = PublishCommand.get_repository(
            project, Namespace(repository="pypi", username="foo", password=None)
        )
        assert repo.url == "https://upload.pypi.org/legacy/"
        assert repo.session.auth == ("foo", "secret")
