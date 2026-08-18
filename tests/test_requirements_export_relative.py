from pdm.formats import requirements
from pdm.models.requirements import parse_requirement
from pdm.utils import cd


def test_export_editable_local_path_as_relative(project):
    package = project.root / "packages" / "pkg-core"
    package.mkdir(parents=True)
    package.joinpath("pyproject.toml").write_text(
        '[project]\nname = "pkg-core"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    with cd(project.root):
        req = parse_requirement("./packages/pkg-core", True)
    req.relocate(project.backend)

    options = type(
        "Options",
        (),
        {
            "expandvars": False,
            "hashes": False,
            "self": False,
            "editable_self": False,
        },
    )()
    result = requirements.export(project, [req], options)

    assert "-e ./packages/pkg-core#egg=pkg-core" in result.splitlines()
    assert "file://" not in result
