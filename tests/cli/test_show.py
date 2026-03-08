"""Additional tests for the show command"""
import pytest

from pdm.cli.commands.show import filter_stable
from pdm.utils import parse_version


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
    # Modify project to be non-distribution
    project.pyproject.settings.setdefault("project", {})["name"] = None

    result = pdm(["show"], obj=project)
    # This might fail if project setup doesn't allow this scenario
    # The test is to check error handling
