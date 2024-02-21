## Complexity of do_lock@39-132@src/pdm/cli/actions.py

### Cyclomatic complexity number
We have compared our calculations and we both get a CCN of 20 for the function `do_lock`. Lizard calculates a CCN of 19. 

### Information about do_lock
Locking in a package manager means locking down the versions of the dependencies that is used in the project. do_lock does that locking as well as updates the lock file. It is quite a long function of about 100 lines which is a reason for its high CCN. Another reason for the high CCN is the error handling to do with logging. 