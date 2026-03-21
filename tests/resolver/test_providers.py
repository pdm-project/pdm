from __future__ import annotations

from collections.abc import Iterator

from resolvelib.resolvers import RequirementInformation

from pdm.models.candidates import Candidate
from pdm.models.requirements import parse_requirement
from pdm.resolver.providers import _CONFLICT_PRIORITY_THRESHOLD


def _build_candidates(identifier: str) -> dict[str, Iterator[Candidate]]:
    requirement = parse_requirement(identifier)
    candidate = Candidate(requirement, name=requirement.project_name, version="1.0")
    return {identifier: iter([candidate])}


def _build_information(identifier: str) -> dict[str, Iterator[RequirementInformation]]:
    requirement = parse_requirement(identifier)
    return {identifier: iter([RequirementInformation(requirement, None)])}


def test_narrow_requirement_selection_promotes_repeated_conflicts(project, repository):
    repository.add_candidate("conflict-pkg", "1.0")
    repository.add_candidate("other-pkg", "1.0")

    provider = project.get_provider()
    narrow = provider.narrow_requirement_selection
    causes = [RequirementInformation(parse_requirement("conflict-pkg"), None)]

    for _ in range(1, _CONFLICT_PRIORITY_THRESHOLD):
        result = list(narrow(["other-pkg"], {}, {}, {}, causes))
        assert result == ["other-pkg"]

    result = list(narrow(["other-pkg", "conflict-pkg"], {}, {}, {}, causes))
    assert result == ["conflict-pkg"]

    result = list(narrow(["other-pkg", "conflict-pkg"], {}, {}, {}, []))
    assert result == ["conflict-pkg"]

    other_causes = [RequirementInformation(parse_requirement("other-pkg"), None)]
    result = list(narrow(["other-pkg", "conflict-pkg"], {}, {}, {}, other_causes))
    assert result == ["other-pkg"]


def test_get_preference_prioritizes_promoted_conflicts(project, repository):
    repository.add_candidate("promoted-pkg", "1.0")
    repository.add_candidate("normal-pkg", "1.0")

    provider = project.get_provider()
    provider._conflict_promoted.add("promoted-pkg")

    promoted_preference = provider.get_preference(
        "promoted-pkg",
        {},
        _build_candidates("promoted-pkg"),
        _build_information("promoted-pkg"),
        [],
    )
    normal_preference = provider.get_preference(
        "normal-pkg",
        {},
        _build_candidates("normal-pkg"),
        _build_information("normal-pkg"),
        [],
    )

    assert promoted_preference < normal_preference
