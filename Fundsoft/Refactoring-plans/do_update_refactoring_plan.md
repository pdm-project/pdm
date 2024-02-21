 
# REFACTORING PLAN:
1. Move out the logic for matching names: 
   from line `133` to line `148` there is a fair bit of complexity
   when matching all the package names with the dependencies for 
   the given group. This could be moved out to a seperate function.
   Moreover, the if-else statement which encapsulates this call can 
   be reduced by replacing the if-body with a function generalising
   these statements. A function named `update_groups_only` or similar
   as this branch deals with unspecified updates (no explicitly named
   package).
2. Move out the logic for handling dry_run: The code for "dry running"
   the command can be moved out into a seperate function. We could 
   have a simple 
   ```python 
    if dry_run: 
        do_dry_run()
   ```
3. The calculation for `reqs` can be moved out into a function 
   with a clear name such as `get_locked_reqs`
4. The double for at line `155` can be moved out into a function 
   called `reset_specifiers`. i.e. this:
   ```python 
    if unconstrained:
        for deps in updated_deps.values():
            for dep in deps.values():
                dep.specifier = get_specifier("")

   ``` 
   can be refactored to this: 
   ```python 
    if unconstrained: 
        reset_specifiers(updated_deps)
   ```

1 8 
2 2
3 3
4 4 

These changes should reduce the total complexity of the function by 15, which, 
depending on what count of the original complexity we use, 35 (lizard) or 37 
(manual), would decrease the complexity by either `42.8%` or `40.5%`. 

## Example of how `match_name` would look
```python
    @staticmethod
    def match_names(name,selection,group,dependencies): 
        from pdm.utils import normalize_name
        from pdm.models.requirements import strip_extras
        group = selection.one()
        if locked_groups and group not in locked_groups:
            raise ProjectError(f"Requested group not in lockfile: {group}")
        dependencies = all_dependencies[group]
        matched_name = next(
            (k for k in dependencies if normalize_name(strip_extras(k)[0]) 
                                        == normalize_name(name)),
            None,
        )
        if not matched_name:
            if selection.dev: 
                raise ProjectError(
                    f"[req]{name}[/] does not exist in [primary]{group}[/] "
                    f"{'dev-' if selection.dev else ''}dependencies."
                )
        #dependencies[matched_name].prerelease = prerelease
        #updated_deps[group][matched_name] = dependencies[matched_name]
        return matched_name
```
