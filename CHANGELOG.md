Release v0.2.4 (2020-02-21)
---------------------------

### Bug Fixes

- Use the project local interpreter to build wheels. [#43](https://github.com/frostming/pdm/issues/43)
- Correctly merge Python specifiers when possible. [#4](https://github.com/frostming/pdm/issues/4)


Release v0.2.3 (2020-02-21)
---------------------------

### Bug Fixes

- Fix a bug that editable build generates a malformed `setup.py`.


Release v0.2.2 (2020-02-20)
---------------------------

### Features & Improvements

- Add a fancy greeting banner when user types `pdm --help`. [#42](https://github.com/frostming/pdm/issues/42)

### Bug Fixes

- Fix the RECORD file in built wheel. [#41](https://github.com/frostming/pdm/issues/41)

### Dependencies

- Add dependency `python-cfonts` to display banner. [#42](https://github.com/frostming/pdm/issues/42)


Release v0.2.1 (2020-02-18)
---------------------------

### Bug Fixes

- Fix a bug that short python_version markers can't be parsed correctly. [#38](https://github.com/frostming/pdm/issues/38)
- Make `_editable_intall.py` compatible with Py2.


Release v0.2.0 (2020-02-14)
---------------------------

### Features & Improvements

- New option: `pdm list --graph` to show a dependency graph of the working set. [#10](https://github.com/frostming/pdm/issues/10)
- New option: `pdm update --unconstrained` to ignore the version constraint of given packages. [#13](https://github.com/frostming/pdm/issues/13)
- Improve the error message when project is not initialized before running comands. [#19](https://github.com/frostming/pdm/issues/19)
- Pinned candidates in lock file are reused when relocking during `pdm install`. [#33](https://github.com/frostming/pdm/issues/33)
- Use the pyenv interperter value if pyenv is installed. [#36](https://github.com/frostming/pdm/issues/36)
- Introduce a new command `pdm info` to show project environment information. [#9](https://github.com/frostming/pdm/issues/9)

### Bug Fixes

- Fix a bug that candidate hashes will be lost when reused. [#11](https://github.com/frostming/pdm/issues/11)

### Dependencies

- Update `pip` to `20.0`, update `pip_shims` to `0.5.0`. [#28](https://github.com/frostming/pdm/issues/28)

### Miscellany

- Add a script named `setup_dev.py` for the convenience to setup pdm for development. [#29](https://github.com/frostming/pdm/issues/29)


Release v0.1.2 (2020-02-09)
---------------------------

### Features

- New command pdm use to switch python versions. [#8](https://github.com/frostming/pdm/issues/8)
- New option pdm list --graph to show a dependency graph. [#10](https://github.com/frostming/pdm/issues/10)
- Read metadata from lockfile when pinned candidate is reused.

Release v0.1.1 (2020-02-07)
---------------------------

### Features

- Get version from the specified file. [#6](https://github.com/frostming/pdm/issues/6)
- Add column header to pdm list output.

Release v0.1.0 (2020-02-07)
---------------------------

### Bugfixes

- Pass exit code to parent process in pdm run.
- Fix error handling for CLI. [#19](https://github.com/frostming/pdm/issues/19)

### Miscellany

- Refactor the installer mocking for tests.

Release v0.0.5 (2020-01-22)
---------------------------

### Improvements

- Ensure pypi index url is fetched in addition to the source settings. [#3](https://github.com/frostming/pdm/issues/3)

### Bugfixes

- Fix an issue that leading "c"s are mistakenly stripped. [#5](https://github.com/frostming/pdm/issues/5)
- Fix an error with PEP 517 building.

Release v0.0.4 (2020-01-22)
---------------------------

### Improvements

- Fix editable installation, now editable scripts can also be executed from outside!
- Content hash is calculated based on dependencies and sources, not other metadata.

### Bugfixes

- Fix an issue that editable distributions can not be removed.

Release v0.0.3 (2020-01-22)
---------------------------

### Features

- Add `pdm init` to bootstrap a project.

Release v0.0.2 (2020-01-22)
---------------------------

### Features

- A complete functioning PEP 517 build backend.
- `pdm builld` command.

### Miscellany

- Add a Chinese REAME

### Features

- Add `pdm init` to bootstrap a project.

Release v0.0.1 (2020-01-20)
---------------------------

### Features

- A dependency resolver that just works.
- A PEP 582 installer.
- PEP 440 version specifiers.
- PEP 508 environment markers.
- Running scripts with PEP 582 local packages.
- Console scripts are injected with local paths.
- A neet CLI.
- add, lock, list, update, remove commands.
- PEP 517 build backends.
- Continuous Integration.
