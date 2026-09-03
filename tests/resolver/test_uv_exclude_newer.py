from datetime import datetime, timezone

from pdm.resolver.uv import UvResolver


def test_uv_exclude_newer_overrides(project):
    project.core.__dict__["uv_cmd"] = ["uv"]
    project.core.state.exclude_newer = datetime(2024, 1, 1, tzinfo=timezone.utc)
    project.core.state.exclude_newer_overrides = {
        "foo": None,
        "bar": datetime(2024, 2, 1, tzinfo=timezone.utc),
    }
    resolver = UvResolver(
        project.environment,
        requirements=[],
        target=project.environment.spec,
        update_strategy="all",
        strategies=set(),
    )

    command = resolver._build_lock_command()

    assert command[-6:] == [
        "--exclude-newer",
        "2024-01-01T00:00:00+00:00",
        "--exclude-newer-package",
        "foo=false",
        "--exclude-newer-package",
        "bar=2024-02-01T00:00:00+00:00",
    ]
