from typing import List, Tuple, Union, Set

from packaging.specifiers import SpecifierSet

from pdm.exceptions import InvalidPyVersion


def get_specifier(version_str: str) -> SpecifierSet:
    if not version_str or version_str == "*":
        return SpecifierSet()
    return SpecifierSet(version_str)


def _parse_version_tuple(version: str) -> Tuple[Union[int, str], ...]:
    try:
        return tuple(int(v) if v != "*" else v for v in version.split("."))
    except ValueError:
        raise InvalidPyVersion(
            "Prereleases or postreleases are not supported for python version"
        )


def _bump_version(
    version: Tuple[Union[int, str], ...], index: int = -1
) -> Tuple[int, int, int]:
    head, value = version[:index], version[index]
    assert isinstance(value, int)
    new_version = _complete_version((*head, value + 1))
    return new_version  # type: ignore


def _complete_version(version, complete_with=0):
    assert len(version) <= 3
    return version + (3 - len(version)) * (complete_with,)


def _version_part_match(valid_version, target_version):
    return target_version[: len(valid_version)] == valid_version


def _convert_to_version(version_tuple):
    return ".".join(str(i) for i in version_tuple)


class PySpecSet(SpecifierSet):
    MAX_PY_VERSIONS = {
        (2,): 7,
        (2, 0): 1,
        (2, 1): 3,
        (2, 2): 3,
        (2, 3): 7,
        (2, 4): 6,
        (2, 5): 6,
        (2, 6): 9,
        (2, 7): 18,
        (3, 0): 1,
        (3, 1): 5,
        (3, 2): 6,
        (3, 3): 7,
        (3, 4): 10,
        (3, 5): 10,
        (3, 6): 10,
        (3, 7): 6,
    }
    MIN_VERSION = (-1, -1, -1)
    MAX_VERSION = (99, 99, 99)

    def __init__(self, version_str: str = "", analyze: bool = True) -> None:
        super().__init__(version_str)
        self._lower_bound = self.MIN_VERSION  # type: Tuple[int, int, int]
        self._upper_bound = self.MAX_VERSION  # type: Tuple[int, int, int]
        self._excludes = []  # type: List[Tuple[Union[int, str], ...]]
        if version_str and analyze:
            self._analyze_specifiers()

    def _analyze_specifiers(self) -> None:
        # XXX: Prerelease or postrelease specifiers will fail here, but I guess we can
        # just ignore them for now.
        lower_bound, upper_bound = self.MIN_VERSION, self.MAX_VERSION
        excludes = set()  # type: Set[Tuple[Union[int, str], ...]]
        for spec in self:
            op, version = spec.operator, spec.version
            version = _parse_version_tuple(version)
            if version[-1] == "*":
                if op == "==":
                    op = "~="
                    version = version[:-1] + (0,)
                elif op == "!=":
                    excludes.add(version)
                    continue
            if op != "~=":
                version = _complete_version(version)
            if op in ("==", "==="):
                lower_bound = version
                upper_bound = _bump_version(version)
                break
            if op == "!=":
                excludes.add(version)
            elif op[0] == ">":
                if op == ">=":
                    new_lower = version
                else:
                    new_lower = _bump_version(version)
                if new_lower > lower_bound:
                    lower_bound = new_lower
            elif op[0] == "<":
                if op == "<=":
                    new_upper = _bump_version(version)
                else:
                    new_upper = version
                if new_upper < upper_bound:
                    upper_bound = new_upper
            elif op == "~=":
                new_lower = _complete_version(version)
                new_upper = _bump_version(version, -2)
                if new_upper < upper_bound:
                    upper_bound = new_upper
                if new_lower > lower_bound:
                    lower_bound = new_lower
            else:
                raise InvalidPyVersion(
                    f"Unsupported version specifier: {spec.op}{spec.version}"
                )
        self._merge_bounds_and_excludes(lower_bound, upper_bound, excludes)

    def _merge_bounds_and_excludes(
        self,
        lower: Tuple[int, int, int],
        upper: Tuple[int, int, int],
        excludes: Set[Tuple[Union[int, str], ...]],
    ) -> None:
        def comp_key(item):
            # .* constraints are always considered before concrete constraints.
            return tuple(e if isinstance(e, int) else -1 for e in item)

        sorted_excludes = sorted(excludes, key=comp_key)
        if lower == self.MIN_VERSION and upper == self.MAX_VERSION:
            # Nothing we can do here, it is a non-constraint.
            self._lower_bound, self._upper_bound = lower, upper
            self._excludes = sorted_excludes
            return
        wildcard_excludes = set()
        for version in list(sorted_excludes):
            if any(_version_part_match(wv, version) for wv in wildcard_excludes):
                sorted_excludes.remove(version)
                continue
            if version[-1] == "*":
                valid_length = len(version) - 1
                valid_version = version[:valid_length]
                wildcard_excludes.add(valid_version)
                if (
                    valid_version < lower[:valid_length]
                    or valid_version > upper[:valid_length]
                ):
                    # Useless excludes
                    sorted_excludes.remove(version)
                elif _version_part_match(valid_version, lower):
                    # The lower bound is excluded
                    lower = _bump_version(version, -2)
                    sorted_excludes.remove(version)
                elif _version_part_match(valid_version, upper):
                    upper = _complete_version(valid_version)
                    sorted_excludes.remove(version)
            else:
                if version < lower or version >= upper:
                    sorted_excludes.remove(version)
                elif version == lower:
                    lower = _bump_version(version)
                    sorted_excludes.remove(version)
        self._lower_bound = lower
        self._upper_bound = upper
        self._excludes = sorted_excludes
        # Regenerate specifiers with merged bounds and excludes.
        if not self.is_impossible:
            super().__init__(str(self))

    @property
    def is_impossible(self):
        if (
            self._lower_bound is self.MIN_VERSION
            or self._upper_bound is self.MAX_VERSION
        ):
            return False
        return self._lower_bound >= self._upper_bound

    @property
    def is_allow_all(self):
        if self.is_impossible:
            return False
        return (
            self._lower_bound == self.MIN_VERSION
            and self._upper_bound == self.MAX_VERSION
            and not self._excludes
        )

    def __bool__(self):
        return not self.is_allow_all

    def __str__(self) -> str:
        if self.is_impossible:
            return "impossible"
        if self.is_allow_all:
            return ""
        lower = self._lower_bound
        upper = self._upper_bound
        if lower[-1] == 0:
            lower = lower[:-1]
        if upper[-1] == 0:
            upper = upper[:-1]
        lower = "" if lower == self.MIN_VERSION else f">={_convert_to_version(lower)}"
        upper = "" if upper == self.MAX_VERSION else f"<{_convert_to_version(upper)}"
        excludes = ",".join(
            f"!={_convert_to_version(version)}" for version in self._excludes
        )

        return ",".join(filter(None, [lower, upper, excludes]))

    def __repr__(self) -> str:
        return f"<PySpecSet {self}>"

    def copy(self) -> "PySpecSet":
        if self.is_impossible:
            return ImpossiblePySpecSet()
        instance = self.__class__(str(self), False)
        instance._lower_bound = self._lower_bound
        instance._upper_bound = self._upper_bound
        instance._excludes = self._excludes[:]
        return instance

    def __and__(self, other: "PySpecSet") -> "PySpecSet":
        if any(s.is_impossible for s in (self, other)):
            return ImpossiblePySpecSet()
        if self.is_allow_all:
            return other.copy()
        elif other.is_allow_all:
            return self.copy()
        rv = self.copy()
        excludes = set(rv._excludes) | set(other._excludes)
        lower = max(rv._lower_bound, other._lower_bound)
        upper = min(rv._upper_bound, other._upper_bound)
        rv._merge_bounds_and_excludes(lower, upper, excludes)
        return rv

    def __or__(self, other: "PySpecSet") -> "PySpecSet":
        if self.is_impossible:
            return other.copy()
        elif other.is_impossible:
            return self.copy()
        if self.is_allow_all:
            return self.copy()
        elif other.is_allow_all:
            return other.copy()
        rv = self.copy()
        left, right = sorted([rv, other], key=lambda x: x._lower_bound)
        excludes = set(left._excludes) & set(right._excludes)
        lower = left._lower_bound
        upper = max(left._upper_bound, right._upper_bound)
        if right._lower_bound > left._upper_bound:  # two ranges has no overlap
            excludes.update(
                self._populate_version_range(left._upper_bound, right._lower_bound)
            )
        rv._merge_bounds_and_excludes(lower, upper, excludes)
        return rv

    def _populate_version_range(self, lower, upper):
        assert lower and upper and lower < upper
        prev = lower
        while prev < upper:
            if prev[-2:] == (0, 0):
                cur = _bump_version(prev, 0)
                if cur <= upper:  # X.0.0 -> X+1.0.0
                    yield (prev[0], "*")
                    prev = cur
                    continue
            if prev[-1] == 0:
                cur = _bump_version(prev, 1)
                if cur <= upper:  # X.Y.0 -> X.Y+1.0
                    yield (*prev[:2], "*")
                    prev = (
                        _bump_version(prev, 0)
                        if cur[0] < 3 and cur[1] > self.MAX_PY_VERSIONS[(cur[0],)]
                        else cur
                    )
                    continue
                while prev < upper:  # X.Y.0 -> X.Y.Z
                    yield prev
                    prev = _bump_version(prev)
                break
            # no wildcard is available
            cur = _bump_version(prev, 1)
            if cur <= upper:  # X.Y.Z -> X.Y+1.0
                current_max = self.MAX_PY_VERSIONS[(*prev[:2],)]
                for z in range(prev[2], current_max + 1):
                    yield (*prev[:2], z)
                prev = (
                    _bump_version(prev, 0)
                    if cur[0] < 3 and cur[1] > self.MAX_PY_VERSIONS[(cur[0],)]
                    else cur
                )
            else:  # X.Y.Z -> X.Y.W
                while prev < upper:
                    yield prev
                    prev = _bump_version(prev)
                break


class ImpossiblePySpecSet(PySpecSet):
    def __init__(self, version_str: str = "", analyze: bool = True):
        pass

    @property
    def is_impossible(self):
        return True
