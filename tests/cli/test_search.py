"""Tests for the search command utilities"""

from pdm._types import SearchResult
from pdm.cli.commands.search import print_results
from pdm.environments import BareEnvironment
from pdm.models.repositories.pypi import PyPIRepository


def test_print_results_empty_hits(mocker):
    """Test print_results with empty hits returns early"""
    ui = mocker.Mock()
    working_set = mocker.Mock()

    # Should return early without calling echo
    print_results(ui, [], working_set)

    ui.echo.assert_not_called()


def test_print_results_with_hits(mocker):
    """Test print_results with search hits"""
    ui = mocker.Mock()
    working_set = {}

    # Create mock search hits
    hit1 = mocker.Mock()
    hit1.name = "test-package"
    hit1.version = "1.0.0"
    hit1.summary = "A test package"

    hit2 = mocker.Mock()
    hit2.name = "another-package"
    hit2.version = "2.0.0"
    hit2.summary = "Another test package"

    hits = [hit1, hit2]

    print_results(ui, hits, working_set)

    # Should call echo for each hit
    assert ui.echo.call_count >= 2


def test_print_results_with_installed_package(mocker):
    """Test print_results shows INSTALLED for packages in working set"""
    ui = mocker.Mock()
    working_set = mocker.Mock()

    # Mock a package that's installed
    hit = mocker.Mock()
    hit.name = "installed-package"
    hit.version = "1.0.0"
    hit.summary = "An installed package"

    # Mock working set to return a distribution
    dist = mocker.Mock()
    dist.version = "1.0.0"
    working_set.__contains__ = mocker.Mock(return_value=True)
    working_set.__getitem__ = mocker.Mock(return_value=dist)

    print_results(ui, [hit], working_set)

    # Should show INSTALLED label
    calls = [str(call) for call in ui.echo.call_args_list]
    assert any("INSTALLED" in str(call) for call in calls)


def test_print_results_with_terminal_width(mocker):
    """Test print_results respects terminal width for wrapping"""
    ui = mocker.Mock()
    working_set = {}

    hit = mocker.Mock()
    hit.name = "test-package"
    hit.version = "1.0.0"
    hit.summary = "This is a very long summary that should be wrapped when terminal width is specified"

    print_results(ui, [hit], working_set, terminal_width=40)

    # Should call echo
    ui.echo.assert_called()


def test_print_results_unicode_error(mocker):
    """Test print_results handles UnicodeEncodeError gracefully"""
    ui = mocker.Mock()
    working_set = {}

    hit = mocker.Mock()
    hit.name = "test-package"
    hit.version = "1.0.0"
    hit.summary = "Test summary"

    # Make echo raise UnicodeEncodeError
    ui.echo.side_effect = UnicodeEncodeError("utf-8", "", 0, 1, "test")

    # Should not raise exception
    print_results(ui, [hit], working_set)


def test_pypi_repository_search(project, mocker):
    environment = BareEnvironment(project)
    session = mocker.Mock()
    environment.__dict__["session"] = session
    response = session.get.return_value
    response.json.return_value = {
        "results": [
            {
                "name": "test-package",
                "latest_version": "1.2.3",
                "description": "A test package",
            }
        ]
    }
    repository = PyPIRepository(project.sources, environment)

    result = repository.search("test query")

    session.get.assert_called_once_with("https://pyoven.org/api/search", params={"q": "test query"})
    response.raise_for_status.assert_called_once_with()
    assert result == [SearchResult("test-package", "1.2.3", "A test package")]


def test_search_command(project, pdm, mocker):
    search = mocker.patch.object(
        PyPIRepository,
        "search",
        return_value=[SearchResult("test-package", "1.2.3", "A test package")],
    )

    result = pdm(["search", "test"], obj=project)

    assert result.exit_code == 0
    assert "test-package" in result.stdout
    assert "A test package" in result.stdout
    assert "deprecated" not in result.outputs.lower()
    search.assert_called_once_with("test")
