import os

import pytest

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
