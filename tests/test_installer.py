from pdm.installers import Installer
from pdm.models.candidates import Candidate
from pdm.models.pip_shims import Link
from pdm.models.requirements import parse_requirement


def test_install_wheel_with_inconsistent_dist_info(project):
    req = parse_requirement("pyfunctional")
    candidate = Candidate(
        req,
        project.environment,
        link=Link("http://fixtures.test/artifacts/PyFunctional-1.4.3-py3-none-any.whl"),
    )
    installer = Installer(project.environment)
    installer.install(candidate)
    assert "pyfunctional" in project.environment.get_working_set()
