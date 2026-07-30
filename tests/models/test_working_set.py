from __future__ import annotations

from types import SimpleNamespace

from pdm.models.working_set import EgglinkFinder, WorkingSet


def make_dist(name):
    return SimpleNamespace(metadata={"Name": name})


def test_egglink_finder_reads_link_target(tmp_path, mocker):
    site_packages = tmp_path / "site-packages"
    target = tmp_path / "target"
    site_packages.mkdir()
    target.mkdir()
    (site_packages / "demo.egg-link").write_text(f"{target}\n")
    distribution = mocker.sentinel.distribution
    finder = mocker.patch("pdm.models.working_set.im.MetadataPathFinder").return_value
    finder.find_distributions.return_value = [distribution]

    result = list(
        EgglinkFinder.find_distributions(
            SimpleNamespace(name="demo", path=[str(site_packages)]),
        )
    )

    assert result == [distribution]
    assert distribution.link_file == (site_packages / "demo.egg-link").absolute()


def test_egglink_finder_skips_missing_distribution(tmp_path, mocker):
    (tmp_path / "demo.egg-link").write_text(f"{tmp_path}\n")
    finder = mocker.patch("pdm.models.working_set.im.MetadataPathFinder").return_value
    finder.find_distributions.return_value = []

    result = list(EgglinkFinder.find_distributions(SimpleNamespace(name=None, path=[str(tmp_path)])))

    assert result == []


def test_working_set_prefers_owned_distribution_and_normalizes_names(mocker):
    owned = make_dist("Demo_Package")
    shared = make_dist("demo-package")
    unnamed = SimpleNamespace(metadata={})
    mocker.patch(
        "pdm.models.working_set.distributions",
        side_effect=[[owned, unnamed], [shared]],
    )

    working_set = WorkingSet(["owned", "owned"], ["shared", "shared"])

    assert list(working_set) == ["demo-package"]
    assert len(working_set) == 1
    assert working_set["demo-package"] is owned
    assert working_set.is_owned("demo-package")
    assert not working_set.is_owned("missing")


def test_working_set_uses_default_paths(mocker):
    distributions = mocker.patch("pdm.models.working_set.distributions", side_effect=[[], []])

    working_set = WorkingSet()

    assert len(working_set) == 0
    assert distributions.call_args_list[0].kwargs["path"]
    assert distributions.call_args_list[1].kwargs["path"] == []


def test_search_paths_ignores_missing_named_egglink(tmp_path):
    assert list(EgglinkFinder._search_paths("missing", [str(tmp_path)])) == []
