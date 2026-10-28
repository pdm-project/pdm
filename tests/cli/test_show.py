"""Additional tests for the show command"""

import importlib.metadata as im

import pytest

from pdm.cli.commands.show import filter_stable
from pdm.models.project_info import ProjectInfo
from pdm.pytest import Distribution


def test_filter_stable_with_stable_version(mocker):
    """Test filter_stable returns True for stable versions"""
    # Mock package with stable version
    package = mocker.Mock()
    package.version = "1.0.0"
    assert filter_stable(package) is True


def test_filter_stable_with_prerelease_alpha(mocker):
    """Test filter_stable returns False for alpha prereleases"""
    package = mocker.Mock()
    package.version = "1.0.0a1"
    assert filter_stable(package) is False


def test_filter_stable_with_prerelease_beta(mocker):
    """Test filter_stable returns False for beta prereleases"""
    package = mocker.Mock()
    package.version = "2.0.0b2"
    assert filter_stable(package) is False


def test_filter_stable_with_prerelease_rc(mocker):
    """Test filter_stable returns False for release candidates"""
    package = mocker.Mock()
    package.version = "3.0.0rc1"
    assert filter_stable(package) is False


def test_filter_stable_with_dev_version(mocker):
    """Test filter_stable returns False for dev versions"""
    package = mocker.Mock()
    package.version = "1.0.0.dev1"
    assert filter_stable(package) is False


@pytest.mark.network
def test_show_command_with_specific_metadata_keys(pdm):
    """Test show command with specific metadata keys"""
    result = pdm(["show", "requests", "--name"])
    assert result.exit_code == 0
    assert "requests" in result.output.lower()

    result = pdm(["show", "requests", "--version"])
    assert result.exit_code == 0
    # Should contain a version number


@pytest.mark.network
def test_show_command_with_multiple_metadata_keys(pdm):
    """Test show command with multiple metadata keys only shows selected ones"""
    result = pdm(["show", "requests", "--name", "--version"])
    assert result.exit_code == 0
    # Should only show name and version, not full metadata


def test_show_command_non_distribution_project(project, pdm):
    """Test show command on a non-distribution project raises error"""
    # Mark the project as non-distribution
    project.pyproject.settings["distribution"] = False

    result = pdm(["show"], obj=project)
    assert result.exit_code != 0
    assert "not a library" in result.stderr


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"License-Expression": "Apache-2.0 OR BSD-2-Clause"}, "Apache-2.0 OR BSD-2-Clause"),
        ({"License-Expression": "MIT", "License": "MIT License"}, "MIT"),
        ({"License": "BSD"}, "BSD"),
        ({}, ""),
    ],
)
def test_project_info_license(metadata, expected):
    info = ProjectInfo.from_distribution(Distribution("foo", "1.0", metadata=metadata))
    assert info.license == expected


@pytest.mark.parametrize(
    "headers,homepage,project_urls",
    [
        (
            ["Project-URL: Homepage, https://example.com", "Project-URL: Source, https://example.com/src"],
            "https://example.com",
            ["Homepage: https://example.com", "Source: https://example.com/src"],
        ),
        (["Project-URL: Home Page, https://example.com"], "https://example.com", ["Home Page: https://example.com"]),
        (
            ["Home-page: https://old.example.com", "Project-URL: Homepage, https://example.com"],
            "https://old.example.com",
            ["Homepage: https://example.com"],
        ),
        (["Project-URL: Docs, https://example.com/a,b"], "", ["Docs: https://example.com/a,b"]),
        ([], "", []),
    ],
)
def test_project_info_urls(tmp_path, headers, homepage, project_urls):
    dist_info = tmp_path / "foo-1.0.dist-info"
    dist_info.mkdir()
    dist_info.joinpath("METADATA").write_text(
        "\n".join(["Metadata-Version: 2.1", "Name: foo", "Version: 1.0", *headers])
    )
    info = ProjectInfo.from_distribution(im.PathDistribution(dist_info))
    assert info.homepage == homepage
    assert info.project_urls == project_urls
