## Complexity of do_update@91-200@src/pdm/cli/commands/update.py

### Cyclomatic complexity number 
Using the formula explained [here](https://radon.readthedocs.io/en/latest/intro.html#cyclomatic-complexity), I get the cyclomatic complexity number (CCN) to be 37 while Lizard gets it to be 35.

### Information about do_update
pdm is a package manager and do_update is the function that is run to update the packages in `pyproject.toml`. Updating packages is a complicated task that requires much error handling which is one of the key reasons for the high CCN. The function checks for potential errors with rather complicated boolean expressions at four separate times which contributes immensely to the high CCN. The function is also rather long, about 100 lines, which also contributes to its high CCN. 


