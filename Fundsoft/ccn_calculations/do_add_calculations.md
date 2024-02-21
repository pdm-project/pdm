## Complexity of `do_add@87-187@src/pdm/cli/commands/add.py`

### Cyclomatic complexity number 
Using the formula explained [here](https://radon.readthedocs.io/en/latest/intro.html#cyclomatic-complexity), I get the cyclomatic complexity number (CCN) to be 36 while Lizard gets it to be 34. This is probably because of the ambiguity of how boolean operations are treated. 

### Information about do_add
pdm is a package manager and do_add is the function that is run to add packages to the project, i.e. to `pyproject.toml`. The process of adding requirements requires checking dependecies (updating the lockfile, checking the dependecy group), adding dependencies, and even parsing dependencies. The function also normalizes names and has different logic
depending on what flag is given to the command. The function has a lot of list comprehension, error checking and different behaviour depending on flags which increases the complexity
quite a bit. 

