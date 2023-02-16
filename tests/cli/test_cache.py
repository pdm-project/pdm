import pytest
from unearth import Link

from pdm.installers.packages import CachedPackage
from tests import FIXTURES


@pytest.fixture
def prepare_wheel_cache(project):
    cache_dir = project.cache("wheels")
    (cache_dir / "arbitrary/path").mkdir(parents=True)
    for name in (
        "foo-0.1.0.whl",
        "bar-0.2.0.whl",
        "baz-0.3.0.whl",
        "foo_bar-0.4.0.whl",
    ):
        (cache_dir / "arbitrary/path" / name).touch()


@pytest.fixture
def prepare_http_cache(project):
    cache_dir = project.cache("http")
    (cache_dir / "arbitrary/path").mkdir(parents=True)
    for name in (
        "foo-0.1.0.tar.gz",
        "bar-0.2.0.zip",
        "baz-0.3.0.tar.gz",
        "foobar-0.4.0.tar.gz",
    ):
        (cache_dir / "arbitrary/path" / name).touch()


@pytest.mark.usefixtures("prepare_wheel_cache")
def test_cache_list(project, invoke):
    result = invoke(["cache", "list"], obj=project)
    assert result.exit_code == 0

    for name in (
        "foo-0.1.0.whl",
        "bar-0.2.0.whl",
        "baz-0.3.0.whl",
        "foo_bar-0.4.0.whl",
    ):
        assert name in result.output


@pytest.mark.usefixtures("prepare_wheel_cache")
def test_cache_list_pattern(project, invoke):
    result = invoke(["cache", "list", "ba*"], obj=project)
    assert result.exit_code == 0

    for name in (
        "bar-0.2.0.whl",
        "baz-0.3.0.whl",
    ):
        assert name in result.output

    for name in (
        "foo-0.1.0.whl",
        "foo_bar-0.4.0.whl",
    ):
        assert name not in result.output


@pytest.mark.usefixtures("prepare_wheel_cache", "prepare_http_cache")
def test_cache_remove_pattern(project, invoke):
    result = invoke(["cache", "remove", "ba*"], obj=project)
    assert result.exit_code == 0

    for name in (
        "bar-0.2.0.whl",
        "baz-0.3.0.whl",
    ):
        assert not (project.cache("wheels") / "arbitrary/path" / name).exists()

    for name in (
        "foo-0.1.0.whl",
        "foo_bar-0.4.0.whl",
    ):
        assert (project.cache("wheels") / "arbitrary/path" / name).exists()

    assert (project.cache("http") / "arbitrary/path/foo-0.1.0.tar.gz").exists()


@pytest.mark.usefixtures("prepare_wheel_cache", "prepare_http_cache")
def test_cache_remove_wildcard(project, invoke):
    result = invoke(["cache", "remove", "*"], obj=project)
    assert result.exit_code == 0

    for name in (
        "bar-0.2.0.whl",
        "baz-0.3.0.whl",
        "foo-0.1.0.whl",
        "foo_bar-0.4.0.whl",
    ):
        assert not (project.cache("wheels") / "arbitrary/path" / name).exists()

    assert (project.cache("http") / "arbitrary/path/foo-0.1.0.tar.gz").exists()


@pytest.mark.usefixtures("prepare_wheel_cache", "prepare_http_cache")
def test_cache_clear(project, invoke):
    result = invoke(["cache", "clear"], obj=project)
    assert result.exit_code == 0

    for name in (
        "bar-0.2.0.whl",
        "baz-0.3.0.whl",
        "foo-0.1.0.whl",
        "foo_bar-0.4.0.whl",
    ):
        assert not (project.cache("wheels") / "arbitrary/path" / name).exists()

    assert not (project.cache("http") / "arbitrary/path/foo-0.1.0.tar.gz").exists()


@pytest.mark.usefixtures("prepare_wheel_cache", "prepare_http_cache")
def test_cache_remove_no_pattern(project, invoke):
    result = invoke(["cache", "remove"], obj=project)
    assert result.exit_code != 0


@pytest.mark.usefixtures("prepare_wheel_cache", "prepare_http_cache")
def test_cache_info(project, invoke):
    result = invoke(["cache", "info"], obj=project)
    assert result.exit_code == 0

    lines = result.output.splitlines()
    assert "Files: 4" in lines[4]
    assert "Files: 4" in lines[6]


@pytest.mark.parametrize(
    "url,hash",
    [
        (
            "http://fixtures.test/artifacts/demo-0.0.1.tar.gz",
            "sha256:d57bf5e3b8723e4fc68275159dcc4ca983d86d4c84220a4d715d491401f27db2",
        ),
        (
            f"file://{(FIXTURES / 'artifacts/demo-0.0.1.tar.gz').as_posix()}",
            "sha256:d57bf5e3b8723e4fc68275159dcc4ca983d86d4c84220a4d715d491401f27db2",
        ),
        (
            "http://fixtures.test/artifacts/demo-0.0.1.tar.gz#sha384=9130e5e4912bc78b"
            "1ffabbf406d56bc74b9165b0adc8c627168b7b563b80d5ff6c30e269398d01144ee52aa3"
            "3292682d",
            "sha384:9130e5e4912bc78b1ffabbf406d56bc74b9165b0adc8c627168b7b563b80d5ff6"
            "c30e269398d01144ee52aa33292682d",
        ),
        (
            "http://fixtures.test/artifacts/demo-0.0.1.tar.gz#md5=5218509812c9fcb4646adde8fd3307e1",
            "sha256:d57bf5e3b8723e4fc68275159dcc4ca983d86d4c84220a4d715d491401f27db2",
        ),
    ],
)
def test_hash_cache(project, url, hash):
    with project.environment.get_finder() as finder:
        hash_cache = project.make_hash_cache()
        assert hash_cache.get_hash(Link(url), finder.session) == hash


def test_clear_package_cache(project, invoke):
    pkg = CachedPackage(project.cache("packages") / "test_package")
    pkg.path.mkdir()
    refer_pkg = project.root / "refer_pkg"
    refer_pkg.mkdir()
    pkg.add_referrer(str(refer_pkg))
    assert len(pkg.referrers) == 1
    pkg._referrers = None

    refer_pkg.rmdir()
    invoke(["cache", "clear", "packages"], obj=project, strict=True)
    assert not pkg.path.exists()
