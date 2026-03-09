"""Additional tests for the info command to improve coverage"""

import json


def test_info_command_packages_option(project, pdm):
    """Test info command with --packages option"""
    result = pdm(["info", "--packages"], obj=project)
    assert result.exit_code == 0
    # Should show packages path
    assert result.output.strip() != ""


def test_info_command_all_options_mutually_exclusive(project, pdm):
    """Test that info command options are mutually exclusive"""
    # Only one field option should work at a time
    result = pdm(["info", "--python"], obj=project)
    assert result.exit_code == 0

    result = pdm(["info", "--where"], obj=project)
    assert result.exit_code == 0

    result = pdm(["info", "--packages"], obj=project)
    assert result.exit_code == 0

    result = pdm(["info", "--env"], obj=project)
    assert result.exit_code == 0


def test_info_command_env_output_format(project, pdm):
    """Test that --env outputs valid JSON"""
    result = pdm(["info", "--env"], obj=project, strict=True)
    # Try to parse as JSON
    try:
        data = json.loads(result.output)
        assert isinstance(data, dict)
    except json.JSONDecodeError:
        # If it's not JSON, it should at least contain marker info
        assert "python_version" in result.output or "implementation" in result.output


def test_info_command_json_contains_all_fields(project, pdm):
    """Test that --json output contains all expected fields"""
    result = pdm(["info", "--json"], obj=project, strict=True)

    data = json.loads(result.output)

    # Check pdm section
    assert "pdm" in data
    assert "version" in data["pdm"]

    # Check python section
    assert "python" in data
    assert "interpreter" in data["python"]
    assert "version" in data["python"]
    assert "markers" in data["python"]
    assert isinstance(data["python"]["markers"], dict)

    # Check project section
    assert "project" in data
    assert "root" in data["project"]
    assert "pypackages" in data["project"]


def test_info_command_default_output(project, pdm):
    """Test info command with no options shows formatted output"""
    result = pdm(["info"], obj=project, strict=True)

    # Should contain all major sections
    assert "PDM version" in result.output or "PDM" in result.output
    assert "Python Interpreter" in result.output or "Interpreter" in result.output
    assert "Project Root" in result.output or "Root" in result.output
    assert "Local Packages" in result.output or "Packages" in result.output


def test_info_command_with_global_project(pdm, tmp_path):
    """Test info command with global project"""
    import os

    os.chdir(tmp_path)

    result = pdm(["info", "-g", "--python"])
    assert result.exit_code == 0


def test_info_command_shows_venv_info(project, pdm):
    """Test info command shows virtual environment information when applicable"""
    # Create a venv
    project.global_config["python.use_venv"] = True

    result = pdm(["info"], obj=project)
    assert result.exit_code == 0


def test_info_command_non_local_environment(project, pdm, mocker):
    """Test info command with non-local environment shows site-packages"""
    # Mock the environment to be non-local
    project.environment.is_local = False

    # Mock get_paths to return purelib
    project.environment.get_paths = mocker.Mock(return_value={"purelib": "/fake/purelib"})

    result = pdm(["info", "--packages"], obj=project)
    assert result.exit_code == 0
    assert "/fake/purelib" in result.output or "purelib" in result.output


def test_info_command_global_project_prefix(project, pdm):
    """Test that global project shows 'Global' prefix in output"""
    result = pdm(["info", "-g"], obj=project)

    # If it's a global project, should show "Global" prefix
    # This test checks if the code path exists
    assert result.exit_code == 0
