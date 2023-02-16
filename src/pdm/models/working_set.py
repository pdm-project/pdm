from __future__ import annotations

import itertools
import sys
from pathlib import Path
from typing import Iterable, Iterator, Mapping

from pdm.compat import importlib_metadata as im
from pdm.utils import normalize_name

default_context = im.DistributionFinder.Context()


class EgglinkFinder(im.DistributionFinder):
    @classmethod
    def find_distributions(cls, context: im.DistributionFinder.Context = default_context) -> Iterable[im.Distribution]:
        found_links = cls._search_paths(context.name, context.path)
        # For Py3.7 compatibility, handle both classmethod and instance method
        meta_finder = im.MetadataPathFinder()
        for link in found_links:
            name = link.stem
            link_pointer = Path(link.open("rb").readline().decode().strip())
            dist = next(
                iter(
                    meta_finder.find_distributions(im.DistributionFinder.Context(name=name, path=[str(link_pointer)]))
                ),
                None,
            )
            if not dist:
                continue
            dist.link_file = link.absolute()  # type: ignore[attr-defined]
            yield dist

    @classmethod
    def _search_paths(cls, name: str | None, paths: list[str]) -> Iterable[Path]:
        for path in paths:
            if name:
                if Path(path).joinpath(f"{name}.egg-link").is_file():
                    yield Path(path).joinpath(f"{name}.egg-link")
            else:
                yield from Path(path).glob("*.egg-link")


def distributions(path: list[str]) -> Iterable[im.Distribution]:
    """Find distributions in the paths. Similar to `importlib.metadata`'s
    implementation but with the ability to discover egg-links.
    """
    context = im.DistributionFinder.Context(path=path)
    resolvers = itertools.chain(
        filter(
            None,
            (getattr(finder, "find_distributions", None) for finder in sys.meta_path),
        ),
        (EgglinkFinder.find_distributions,),
    )
    return itertools.chain.from_iterable(resolver(context) for resolver in resolvers)


class WorkingSet(Mapping[str, im.Distribution]):
    """A dictionary of currently installed distributions"""

    def __init__(self, paths: list[str] | None = None):
        if paths is None:
            paths = sys.path
        self._dist_map = {normalize_name(dist.metadata["Name"]): dist for dist in distributions(path=paths)}

    def __getitem__(self, key: str) -> im.Distribution:
        return self._dist_map[key]

    def __len__(self) -> int:
        return len(self._dist_map)

    def __iter__(self) -> Iterator[str]:
        return iter(self._dist_map)

    def __repr__(self) -> str:
        return repr(self._dist_map)
