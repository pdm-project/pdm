import pytest

from pdm.models.versions import InvalidPyVersion, Version


def test_unsupported_post_version() -> None:
    with pytest.raises(InvalidPyVersion):
        Version("3.10.0post1")


def test_support_prerelease_version() -> None:
    assert not Version("3.9.0").is_prerelease
    v = Version("3.9.0a4")
    assert v.is_prerelease
    assert str(v) == "3.9.0a4"
    assert v.complete() == v
    assert v.bump() == Version("3.9.0a5")
    assert v.bump(2) == Version("3.9.1")


def test_normalize_non_standard_version():
    version = Version("3.9*")
    assert str(version) == "3.9.*"


def test_version_comparison():
    assert Version("3.9.0") < Version("3.9.1")
    assert Version("3.4") < Version("3.9.1")
    assert Version("3.7.*") < Version("3.7.5")
    assert Version("3.7") == Version((3, 7))

    assert Version("3.9.0a") != Version("3.9.0")
    assert Version("3.9.0a") == Version("3.9.0a0")
    assert Version("3.10.0a9") < Version("3.10.0a12")
    assert Version("3.10.0a12") < Version("3.10.0b1")
    assert Version("3.7.*") < Version("3.7.1b")


def test_version_is_wildcard():
    assert not Version("3").is_wildcard
    assert Version("3.*").is_wildcard


def test_version_is_py2():
    assert not Version("3.8").is_py2
    assert Version("2.7").is_py2


@pytest.mark.parametrize(
    "version,args,result",
    [("3.9", (), "3.9.0"), ("3.9", ("*",), "3.9.*"), ("3", (0, 2), "3.0")],
)
def test_version_complete(version, args, result):
    assert str(Version(version).complete(*args)) == result


@pytest.mark.parametrize(
    "version,idx,result",
    [
        ("3.8.0", -1, "3.8.1"),
        ("3.8", -1, "3.9.0"),
        ("3", 0, "4.0.0"),
        ("3.8.1", 1, "3.9.0"),
    ],
)
def test_version_bump(version, idx, result):
    assert str(Version(version).bump(idx)) == result


@pytest.mark.parametrize(
    "version,other,result",
    [
        ("3.8.0", "3.8", True),
        ("3.8.*", "3.8", True),
        ("3.8.1", "3.7", False),
        ("3.8", "3.8.2", False),
    ],
)
def test_version_startswith(version, other, result):
    assert Version(version).startswith(Version(other)) is result


def test_version_getitem():
    version = Version("3.8.6")
    assert version[0] == 3
    assert version[1] == 8
    assert version[2] == 6
    assert version[1:2] == Version("8")
    assert version[:-1] == Version("3.8")


def test_version_setitem():
    version = Version("3.8.*")
    version1 = version.complete()
    version1[-1] = 0
    assert version1 == Version("3.8.0")

    version2 = version.complete()
    version2[0] = 4
    assert version2 == Version("4.8.*")

    version3 = version.complete()
    with pytest.raises(TypeError):
        version3[:2] = (1, 2)
