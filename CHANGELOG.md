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
