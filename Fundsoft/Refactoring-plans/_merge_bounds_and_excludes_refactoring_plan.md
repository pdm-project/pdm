# Refactoring plan - _merge_bounds_and_excludes
The complexity of the function isn't needed. It comes mainly from two parts with distinct tasks that can be moved to two separate functions.

The first of these is a for-loop that iterates over the sorted excluded versions from low to high (line `153` to line `179`). This piece of code removes unnecessary versions and updates the lower version. This can easily be refactored to its own function called remove_versions_and_update_lower which in addition to reducing complexity would also increase readability. To do this, I would need to take in the sorted excluded versions, the lower version, and the upper version as parameters. Since the function would modify the lower version and the sorted excluded versions, I would have to return those at the end.

The other part of the function which adds a lot of complexity is the for-loop that iterates over the sorted excluded versions from high to low (line `180` to line `199`). Just as the previous piece of code, it removes unnecessary excluded versions but unlike the previous one, it modifies the upper version instead of the lower one. This could be refactored into a function called remove_versions_and_update_upper. Here I would need to input the sorted excluded versions and the upper version and return the updated excluded versions and the updated upper version.

Doing this should bring down the cyclomatic complexity number from 21 to just 9. _merge_bounds_and_excludes would then look like

```python
    @classmethod
    def _merge_bounds_and_excludes(
        cls,
        lower: Version,
        upper: Version,
        excludes: Iterable[Version],
    ) -> tuple[Version, Version, list[Version]]:
        sorted_excludes = sorted(excludes)
        wildcard_excludes = {version[:-1] for version in sorted_excludes if version.is_wildcard}
        # Remove versions that are already excluded by another wildcard exclude.
        sorted_excludes = [
            version
            for version in sorted_excludes
            if version.is_wildcard or not any(version.startswith(wv) for wv in wildcard_excludes)
        ]

        if lower == Version.MIN and upper == Version.MAX:
            # Nothing we can do here, it is a non-constraint.
            return lower, upper, sorted_excludes

        sorted_excludes, lower = remove_versions_and_update_lower(sorted_excludes, lower, upper)
        sorted_excludes, upper = remove_versions_and_update_upper(sorted_excludes, upper)

        return lower, upper, sorted_excludes
```