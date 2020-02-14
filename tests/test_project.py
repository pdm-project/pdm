import os


def test_project_python_with_pyenv_support(project, mocker):
    from pythonfinder.environment import PYENV_ROOT

    pyenv_python = os.path.join(PYENV_ROOT, "shims", "python")

    mocker.patch("pdm.models.environment.PYENV_INSTALLED", True)
    assert project.environment.python_executable == pyenv_python

    project.config["python.use_pyenv"] = False
    assert project.environment.python_executable != pyenv_python
