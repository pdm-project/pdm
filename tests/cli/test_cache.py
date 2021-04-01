import pytest


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

    assert not (project.cache("http") / "arbitrary/path/foo-0.1.0.tar.gz").exists()


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
