from pdm.cli.actions import do_add


def test_add_package(project, repository, synchronizer, is_dev):
    do_add(project, is_dev, packages=["requests"])
    section = "dev-dependencies" if is_dev else "dependencies"

    assert project.pyproject[section]["requests"] == "<3.0.0,>=2.19.1"
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in synchronizer.working_set


def test_add_package_to_custom_package(project, repository, synchronizer):
    do_add(project, section="test", packages=["requests"])

    assert "requests" in project.pyproject["test-dependencies"]
    locked_candidates = project.get_locked_candidates("test")
    assert locked_candidates["idna"].version == "2.7"
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package in synchronizer.working_set


def test_add_editable_package(project, repository, synchronizer, is_dev, vcs):
    do_add(
        project, is_dev, editables=[
            "git+https://github.com/test-root/demo.git#egg=demo"
        ]
    )
    section = "dev-dependencies" if is_dev else "dependencies"
    assert "demo" in project.pyproject[section]
    locked_candidates = project.get_locked_candidates("dev" if is_dev else "default")
    assert locked_candidates["idna"].version == "2.7"
    assert "idna" in synchronizer.working_set


def test_add_no_install(project, repository, synchronizer):
    do_add(project, install=False, packages=["requests"])
    for package in ("requests", "idna", "chardet", "urllib3", "certifi"):
        assert package not in synchronizer.working_set


def test_add_package_save_exact(project, repository):
    do_add(project, install=False, save="exact", packages=["requests"])
    assert project.pyproject["dependencies"]["requests"] == "==2.19.1"


def test_add_package_save_wildcard(project, repository):
    do_add(project, install=False, save="wildcard", packages=["requests"])
    assert project.pyproject["dependencies"]["requests"] == "*"


def test_add_package_update_reuse(project, repository):
    do_add(project, install=False, save="wildcard", packages=["requests", "pytz"])

    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"

    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies("requests", "2.20.0", [
        "certifi>=2017.4.17",
        "chardet<3.1.0,>=3.0.2",
        "idna<2.8,>=2.5",
        "urllib3<1.24,>=1.21.1"
    ])
    do_add(
        project, install=False, save="wildcard", packages=["requests"], strategy="reuse"
    )
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"


def test_add_package_update_eager(project, repository):
    do_add(project, install=False, save="wildcard", packages=["requests", "pytz"])

    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.19.1"
    assert locked_candidates["chardet"].version == "3.0.4"
    assert locked_candidates["pytz"].version == "2019.3"

    repository.add_candidate("pytz", "2019.6")
    repository.add_candidate("chardet", "3.0.5")
    repository.add_candidate("requests", "2.20.0")
    repository.add_dependencies("requests", "2.20.0", [
        "certifi>=2017.4.17",
        "chardet<3.1.0,>=3.0.2",
        "idna<2.8,>=2.5",
        "urllib3<1.24,>=1.21.1"
    ])
    do_add(
        project, install=False, save="wildcard", packages=["requests"], strategy="eager"
    )
    locked_candidates = project.get_locked_candidates()
    assert locked_candidates["requests"].version == "2.20.0"
    assert locked_candidates["chardet"].version == "3.0.5"
    assert locked_candidates["pytz"].version == "2019.3"
