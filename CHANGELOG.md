Release v2.4.7 (2023-03-02)
---------------------------

### Bug Fixes

- Abort if lockfile isn't generated when executing `pdm export`. [#1730](https://github.com/pdm-project/pdm/issues/1730)
- Ignore `venv.prompt` configuration when using `conda` as the backend. [#1734](https://github.com/pdm-project/pdm/issues/1734)
- Fix a bug of finding local packages in the parent folder when it exists in the current folder. [#1736](https://github.com/pdm-project/pdm/issues/1736)
- Ensure UTF-8 encoding when generating README.md. [#1739](https://github.com/pdm-project/pdm/issues/1739)
- Fix a bug of show command not showing metadata of the current project. [#1740](https://github.com/pdm-project/pdm/issues/1740)
- Replace `.` with `-` when normalizing package name. [#1745](https://github.com/pdm-project/pdm/issues/1745)

### Documentation

- Support using `pdm venv activate` without specifying `env_name` to activate in project venv created by conda [#1735](https://github.com/pdm-project/pdm/issues/1735)


Release v2.4.6 (2023-02-20)
---------------------------

### Bug Fixes

- Fix a resolution failure when the project has cascading relative path dependencies. [#1702](https://github.com/pdm-project/pdm/issues/1702)
- Don't crash when trying to update the shebang in a binary script. [#1709](https://github.com/pdm-project/pdm/issues/1709)
- Handle the legacy specifiers that is unable to parse with packaging>22.0. [#1719](https://github.com/pdm-project/pdm/issues/1719)
- Fix the setup.py parser to ignore the expressions unable to parse as a string. This is safe for initializing a requirement. [#1720](https://github.com/pdm-project/pdm/issues/1720)
- Fix a bug converting from flit metadata when the source file can't be found. [#1726](https://github.com/pdm-project/pdm/issues/1726)

### Documentation

- Add config example for Emacs using eglot + pyright [#1721](https://github.com/pdm-project/pdm/issues/1721)

### Miscellany

- Use `ruff` as the linter. [#1715](https://github.com/pdm-project/pdm/issues/1715)
- Document installation via `asdf`. [#1725](https://github.com/pdm-project/pdm/issues/1725)


Release v2.4.5 (2023-02-10)
---------------------------

### Bug Fixes

- Fix a bug that built wheels are prioritized over source distributions with higher version number. [#1698](https://github.com/pdm-project/pdm/issues/1698)


Release v2.4.4 (2023-02-10)
---------------------------

### Features & Improvements

- Add more intuitive error message when the `requires-python` doesn't work for all dependencies. [#1690](https://github.com/pdm-project/pdm/issues/1690)

### Bug Fixes

- Prefer built distributions when finding packages for metadata extraction. [#1535](https://github.com/pdm-project/pdm/issues/1535)


Release v2.4.3 (2023-02-06)
---------------------------

### Features & Improvements

- Allow creating venv in project forcely if it already exists. [#1666](https://github.com/pdm-project/pdm/issues/1666)
- Always ignore remembered selection in pdm init. [#1672](https://github.com/pdm-project/pdm/issues/1672)

### Bug Fixes

- Fix the fallback build backend to `pdm-pep517` instead of `setuptools`. [#1658](https://github.com/pdm-project/pdm/issues/1658)
- Eliminate the deprecation warnings from `importlib.resources`. [#1660](https://github.com/pdm-project/pdm/issues/1660)
- Don't crash when failed to get the latest version of PDM for checking update. [#1663](https://github.com/pdm-project/pdm/issues/1663)
- Fix the priorities of importable formats to make sure the correct format is used. [#1669](https://github.com/pdm-project/pdm/issues/1669)
- Import editable requirements into dev dependencies. [#1674](https://github.com/pdm-project/pdm/issues/1674)


Release v2.4.2 (2023-01-31)
---------------------------

### Bug Fixes

- Skip some tests on packaging < 22. [#1649](https://github.com/pdm-project/pdm/issues/1649)
- Fix a bug that sources from the project config are not loaded. [#1651](https://github.com/pdm-project/pdm/issues/1651)
- Set VIRTUAL_ENV in `pdm run`. [#1652](https://github.com/pdm-project/pdm/issues/1652)


Release v2.4.1 (2023-01-28)
---------------------------

### Features & Improvements

- Add proper display for the extra pypi sources in `pdm config`. [#1622](https://github.com/pdm-project/pdm/issues/1622)
- Support running python scripts without prefixing with `python`. [#1626](https://github.com/pdm-project/pdm/issues/1626)

### Bug Fixes

- Ignore the python requirement for overriden packages. [#1575](https://github.com/pdm-project/pdm/issues/1575)
- Fix the wildcards in requirement specifiers to make it pass the new parser of `packaging>=22`. [#1619](https://github.com/pdm-project/pdm/issues/1619)
- Add the missing `subdirectory` attribute to the lockfile entry. [#1630](https://github.com/pdm-project/pdm/issues/1630)
- Fix a bug that VCS locks don't update when the rev part changes. [#1640](https://github.com/pdm-project/pdm/issues/1640)
- Redirect the spinner output to stderr. [#1646](https://github.com/pdm-project/pdm/issues/1646)
- Ensure the destination directory exists before building the packages. [#1647](https://github.com/pdm-project/pdm/issues/1647)


Release v2.4.0 (2023-01-12)
---------------------------

### Features & Improvements

- Support multiple PyPI indexes in the configuration. They will be tried after the sources in `pyproject.toml`. [#1310](https://github.com/pdm-project/pdm/issues/1310)
- Accept yanked versions when the requirement version is pinned. [#1575](https://github.com/pdm-project/pdm/issues/1575)
- - Expose PDM fixtures as a `pytest` plugin `pdm.pytest` for plugin developers. [#1594](https://github.com/pdm-project/pdm/issues/1594)
- Show message in the status when fetching package hashes.
  Fetch hashes from the JSON API response as well. [#1609](https://github.com/pdm-project/pdm/issues/1609)
- Mark `pdm.lock` with an `@generated` comment. [#1611](https://github.com/pdm-project/pdm/issues/1611)

### Bug Fixes

- Exclude site-packages for symlinks of the python interpreter as well. [#1598](https://github.com/pdm-project/pdm/issues/1598)
- Fix a bug that error output can't be decoded correctly on Windows. [#1602](https://github.com/pdm-project/pdm/issues/1602)


Release v2.3.4 (2022-12-27)
---------------------------

### Features & Improvements

- Detect PDM inside a zipapp and disable some functions. [#1578](https://github.com/pdm-project/pdm/issues/1578)

### Bug Fixes

- Don't write `sitecustomize` to the home directory if it exists in the filesystem(not packed in a zipapp). [#1572](https://github.com/pdm-project/pdm/issues/1572)
- Fix a bug that a directory is incorrectly marked as to be deleted when it contains symlinks. [#1580](https://github.com/pdm-project/pdm/issues/1580)


Release v2.3.3 (2022-12-15)
---------------------------

### Bug Fixes

- Allow relative paths in `build-system.requires`, since `build` and `hatch` both support it. Be aware it is not allowed in the standard. [#1560](https://github.com/pdm-project/pdm/issues/1560)
- Strip the local part when building a specifier for comparison with the package version. This is not permitted by PEP 508 as implemented by `packaging 22.0`. [#1562](https://github.com/pdm-project/pdm/issues/1562)
- Update the version for check_update after self update [#1563](https://github.com/pdm-project/pdm/issues/1563)
- Replace the `__file__` usages with `importlib.resources`, to make PDM usable in a zipapp. [#1567](https://github.com/pdm-project/pdm/issues/1567)
- Fix the matching problem of packages in the lockfile. [#1569](https://github.com/pdm-project/pdm/issues/1569)

### Dependencies

- Exclude `package==22.0` from the dependencies to avoid some breakages to the end users. [#1568](https://github.com/pdm-project/pdm/issues/1568)


Release v2.3.2 (2022-12-08)
---------------------------

### Bug Fixes

- Fix an installation failure when the RECORD file contains commas in the file path. [#1010](https://github.com/pdm-project/pdm/issues/1010)
- Fallback to `pdm.pep517` as the metadata transformer for unknown custom build backends. [#1546](https://github.com/pdm-project/pdm/issues/1546)
- Fix a bug that Ctrl + C kills the python interactive session instead of clearing the current line. [#1547](https://github.com/pdm-project/pdm/issues/1547)
- Fix a bug with egg segment for local dependency [#1552](https://github.com/pdm-project/pdm/issues/1552)

### Dependencies

- Update `installer` to `0.6.0`. [#1550](https://github.com/pdm-project/pdm/issues/1550)
- Update minimum version of `unearth` to `0.6.3` and test against `packaging==22.0`. [#1555](https://github.com/pdm-project/pdm/issues/1555)


Release v2.3.1 (2022-12-05)
---------------------------

### Bug Fixes

- Fix a resolution loop issue when the current project depends on itself and it uses the dynamic version from SCM. [#1541](https://github.com/pdm-project/pdm/issues/1541)
- Don't give duplicate results when specifying a relative path for `pdm use`. [#1542](https://github.com/pdm-project/pdm/issues/1542)


Release v2.3.0 (2022-12-02)
---------------------------

### Features & Improvements

- Beautify the error message of build errors. Default to showing the last 10 lines of the build output. [#1491](https://github.com/pdm-project/pdm/issues/1491)
- Rename the `tool.pdm.overrides` table to `tool.pdm.resolution.overrides`. The old name is deprecated at the same time. [#1503](https://github.com/pdm-project/pdm/issues/1503)
- Add backend selection and `--backend` option to `pdm init` command, users can choose a favorite backend from `setuptools`, `flit`, `hatchling` and `pdm-pep517`(default), since they all support PEP 621 standards. [#1504](https://github.com/pdm-project/pdm/issues/1504)
- Allows specifying the insertion position of user provided arguments in scripts with the `{args[:default]}` placeholder. [#1507](https://github.com/pdm-project/pdm/issues/1507)

### Bug Fixes

- The local package is now treated specially during installation and locking. This means it will no longer be included in the lockfile, and should never be installed twice even when using nested extras. This will ensure the lockdown stays relevant when the version changes. [#1481](https://github.com/pdm-project/pdm/issues/1481)
- Fix the version diff algorithm of installed packages to consider local versions as compatible. [#1497](https://github.com/pdm-project/pdm/issues/1497)
- Fix the confusing message when detecting a Python interpreter under `python.use_venv=False` [#1508](https://github.com/pdm-project/pdm/issues/1508)
- Fix the test failure with the latest `findpython` installed. [#1516](https://github.com/pdm-project/pdm/issues/1516)
- Fix the module missing error of pywin32 in a virtualenv with `install.cache` set to `true` and caching method is `pth`. [#863](https://github.com/pdm-project/pdm/issues/863)

### Dependencies

- Drop the dependency `pdm-pep517`. [#1504](https://github.com/pdm-project/pdm/issues/1504)
- Replace `pep517` with `pyproject-hooks` because of the rename. [#1528](https://github.com/pdm-project/pdm/issues/1528)

### Removals and Deprecations

- Remove the support for exporting the project file to a `setup.py` format, users are encouraged to migrate to the PEP 621 metadata. [#1504](https://github.com/pdm-project/pdm/issues/1504)


Release v2.2.1 (2022-11-03)
---------------------------

### Features & Improvements

- Make `sitecustomize.py` respect the `PDM_PROJECT_MAX_DEPTH` environment variable [#1471](https://github.com/pdm-project/pdm/issues/1471)

### Bug Fixes

- Fix the comparison of `python_version` in the environment marker. When the version contains only one digit, the result was incorrect. [#1484](https://github.com/pdm-project/pdm/issues/1484)


Release v2.2.0 (2022-10-31)
---------------------------

### Features & Improvements

- Add `venv.prompt` configuration to allow customizing prompt when a virtualenv is activated [#1332](https://github.com/pdm-project/pdm/issues/1332)
- Allow the use of custom CA certificates per publish repository using `ca_certs` or from the command line via `pdm publish --ca-certs <path> ...`. [#1392](https://github.com/pdm-project/pdm/issues/1392)
- Rename the `plugin` command to `self`, and it can not only manage plugins but also all dependencies. Add a subcommand `self update` to update PDM itself. [#1406](https://github.com/pdm-project/pdm/issues/1406)
- Allow `pdm init` to receive a Python path or version via `--python` option. [#1412](https://github.com/pdm-project/pdm/issues/1412)
- Add a default value for `requires-python` when importing from other formats. [#1426](https://github.com/pdm-project/pdm/issues/1426)
- Use `pdm` instead of `pip` to resolve and install build requirements. So that PDM configurations can control the process. [#1429](https://github.com/pdm-project/pdm/issues/1429)
- Customizable color theme via `pdm config` command. [#1450](https://github.com/pdm-project/pdm/issues/1450)
- A new `pdm lock --check` flag to validate whether the lock is up to date. [#1459](https://github.com/pdm-project/pdm/issues/1459)
- Add both option and config item to ship `pip` when creating a new venv. [#1463](https://github.com/pdm-project/pdm/issues/1463)
- Issue warning and skip the requirement if it has the same name as the current project. [#1466](https://github.com/pdm-project/pdm/issues/1466)
- Enhance the `pdm list` command with new formats: `--csv,--markdown` and add options `--fields,--sort` to control the output contents. Users can also include `licenses` in the `--fields` option to display the package licenses. [#1469](https://github.com/pdm-project/pdm/issues/1469)
- A new pre-commit hook to run `pdm lock --check` in pre-commit. [#1471](https://github.com/pdm-project/pdm/issues/1471)

### Bug Fixes

- Fix the issue that relative paths don't work well with `--project` argument. [#1220](https://github.com/pdm-project/pdm/issues/1220)
- It is now possible to refer to a package from outside the project with relative paths in dependencies. [#1381](https://github.com/pdm-project/pdm/issues/1381)
- Ensure `pypi.[ca,client]_cert[s]` config items are passed to distribution builder install steps to allow for custom PyPI index sources with self signed certificates. [#1396](https://github.com/pdm-project/pdm/issues/1396)
- Fix a crash issue when depending on editable packages with extras. [#1401](https://github.com/pdm-project/pdm/issues/1401)
- Do not save the python path when using non-interactive mode in `pdm init`. [#1410](https://github.com/pdm-project/pdm/issues/1410)
- Fix the matching of `python*` command in `pdm run`. [#1414](https://github.com/pdm-project/pdm/issues/1414)
- Show the Python path, instead of the real executable, in the Python selection menu. [#1418](https://github.com/pdm-project/pdm/issues/1418)
- Fix the HTTP client of package publishment to prompt for password and read PDM configurations correctly. [#1430](https://github.com/pdm-project/pdm/issues/1430)
- Ignore the unknown fields when constructing a requirement object. [#1445](https://github.com/pdm-project/pdm/issues/1445)
- Fix a bug of unrelated candidates being fetched if the requirement is matching wildcard versions(e.g. `==1.*`). [#1465](https://github.com/pdm-project/pdm/issues/1465)
- Use `importlib-metadata` from PyPI for Python < 3.10. [#1467](https://github.com/pdm-project/pdm/issues/1467)

### Documentation

- Clarify the difference between a library and an application. Update the guide of multi-stage docker build. [#1371](https://github.com/pdm-project/pdm/issues/1371)

### Removals and Deprecations

- Remove all top-level imports, users should import from the submodules instead. [#1404](https://github.com/pdm-project/pdm/issues/1404)
- Remove the usages of old config names deprecated since 2.0. [#1422](https://github.com/pdm-project/pdm/issues/1422)
- Remove the deprecated color functions, use [rich's console markup](https://rich.readthedocs.io/en/latest/markup.html) instead. [#1452](https://github.com/pdm-project/pdm/issues/1452)


Release v2.1.5 (2022-10-05)
---------------------------

### Bug Fixes

- Ensure `pypi.[ca,client]_cert[s]` config items are passed to distribution builder install steps to allow for custom PyPI index sources with self signed certificates. [#1396](https://github.com/pdm-project/pdm/issues/1396)
- Fix a crash issue when depending on editable packages with extras. [#1401](https://github.com/pdm-project/pdm/issues/1401)
- Do not save the python path when using non-interactive mode in `pdm init`. [#1410](https://github.com/pdm-project/pdm/issues/1410)
- Restrict importlib-metadata (<5.0.0) for Python <3.8 [#1411](https://github.com/pdm-project/pdm/issues/1411)


Release v2.1.4 (2022-09-17)
---------------------------

### Bug Fixes

- Fix a lock failure when depending on self with URL requirements. [#1347](https://github.com/pdm-project/pdm/issues/1347)
- Ensure list to concatenate args for composite scripts. [#1359](https://github.com/pdm-project/pdm/issues/1359)
- Fix an error in `pdm lock --refresh` if some packages has URLs. [#1361](https://github.com/pdm-project/pdm/issues/1361)
- Fix unnecessary package downloads and VCS clones for certain commands. [#1370](https://github.com/pdm-project/pdm/issues/1370)
- Fix a conversion error when converting a list of conditional dependencies from a Poetry format. [#1383](https://github.com/pdm-project/pdm/issues/1383)

### Documentation

- Adds a section to the docs on how to correctly work with PDM and version control systems. [#1364](https://github.com/pdm-project/pdm/issues/1364)


Release v2.1.3 (2022-08-30)
---------------------------

### Features & Improvements

- When adding a package to (or removing from) a group, enhance the formatting of the group name in the printed message. [#1329](https://github.com/pdm-project/pdm/issues/1329)

### Bug Fixes

- Fix a bug of missing hashes for packages with `file://` links the first time they are added. [#1325](https://github.com/pdm-project/pdm/issues/1325)
- Ignore invalid values of `data-requires-python` when parsing package links. [#1334](https://github.com/pdm-project/pdm/issues/1334)
- Leave an incomplete project metadata if PDM fails to parse the project files, but emit a warning. [#1337](https://github.com/pdm-project/pdm/issues/1337)
- Fix the bug that `editables` package isn't installed for self package. [#1344](https://github.com/pdm-project/pdm/issues/1344)
- Fix a decoding error for non-ASCII characters in package description when publishing it. [#1345](https://github.com/pdm-project/pdm/issues/1345)

### Documentation

- Clarify documentation explaining `setup-script`, `run-setuptools`, and `is-purelib`. [#1327](https://github.com/pdm-project/pdm/issues/1327)


Release v2.1.2 (2022-08-15)
---------------------------

### Bug Fixes

- Fix a bug that dependencies from different versions of the same package override each other. [#1307](https://github.com/pdm-project/pdm/issues/1307)
- Forward SIGTERM to child processes in `pdm run`. [#1312](https://github.com/pdm-project/pdm/issues/1312)
- Fix errors when running on FIPS 140-2 enabled systems using Python 3.9 and newer. [#1313](https://github.com/pdm-project/pdm/issues/1313)
- Fix the build failure when the subprocess outputs with non-UTF8 characters. [#1319](https://github.com/pdm-project/pdm/issues/1319)
- Delay the trigger of `post_lock` for `add` and `update` operations, to ensure the `pyproject.toml` is updated before the hook is run. [#1320](https://github.com/pdm-project/pdm/issues/1320)


Release v2.1.1 (2022-08-05)
---------------------------

### Features & Improvements

- Add a env_file.override option that allows the user to specify that
  the env_file should override any existing environment variables. This
  is not the default as the environment the code runs it should take
  precedence. [#1299](https://github.com/pdm-project/pdm/issues/1299)

### Bug Fixes

- Fix a bug that unnamed requirements can't override the old ones in either `add` or `update` command. [#1287](https://github.com/pdm-project/pdm/issues/1287)
- Support mutual TLS to private repositories via pypi.client_cert and pypi.client_key config options. [#1290](https://github.com/pdm-project/pdm/issues/1290)
- Set a minimum version for the `packaging` dependency to ensure that `packaging.utils.parse_wheel_filename` is available. [#1293](https://github.com/pdm-project/pdm/issues/1293)
- Fix a bug that checking for PDM update creates a venv. [#1301](https://github.com/pdm-project/pdm/issues/1301)
- Prefer compatible packages when fetching metadata. [#1302](https://github.com/pdm-project/pdm/issues/1302)


Release v2.1.0 (2022-07-29)
---------------------------

### Features & Improvements

- Allow the use of custom CA certificates using the `pypi.ca_certs` config entry. [#1240](https://github.com/pdm-project/pdm/issues/1240)
- Add `pdm export` to available pre-commit hooks. [#1279](https://github.com/pdm-project/pdm/issues/1279)

### Bug Fixes

- Skip incompatible requirements when installing build dependencies. [#1264](https://github.com/pdm-project/pdm/issues/1264)
- Fix a crash when pdm tries to publish a package with non-ASCII characters in the metadata. [#1270](https://github.com/pdm-project/pdm/issues/1270)
- Try to read the lock file even if the lock version is incompatible. [#1273](https://github.com/pdm-project/pdm/issues/1273)
- For packages that are only available as source distribution, the `summary` field in `pdm.lock` contains the `description` from the package's `pyproject.toml`. [#1274](https://github.com/pdm-project/pdm/issues/1274)
- Do not crash when calling `pdm show` for a package that is only available as source distribution. [#1276](https://github.com/pdm-project/pdm/issues/1276)
- Fix a bug that completion scripts are interpreted as rich markups. [#1283](https://github.com/pdm-project/pdm/issues/1283)

### Dependencies

- Remove the dependency of `pip`. [#1268](https://github.com/pdm-project/pdm/issues/1268)

### Removals and Deprecations

- Deprecate the top-level imports from `pdm` module, it will be removed in the future. [#1282](https://github.com/pdm-project/pdm/issues/1282)


Release v2.0.3 (2022-07-22)
---------------------------

### Bug Fixes

- Support Conda environments when detecting the project environment. [#1253](https://github.com/pdm-project/pdm/issues/1253)
- Fix the interpreter resolution to first try `python` executable in the `PATH`. [#1255](https://github.com/pdm-project/pdm/issues/1255)
- Stabilize sorting of URLs in `metadata.files` in `pdm.lock`. [#1256](https://github.com/pdm-project/pdm/issues/1256)
- Don't expand credentials in the file URLs in the `[metada.files]` table of the lock file. [#1259](https://github.com/pdm-project/pdm/issues/1259)


Release v2.0.2 (2022-07-20)
---------------------------

### Features & Improvements

- `env_file` variables no longer override existing environment variables. [#1235](https://github.com/pdm-project/pdm/issues/1235)
- Support referencing other optional groups in optional-dependencies with `<this_package_name>[group1, group2]` [#1241](https://github.com/pdm-project/pdm/issues/1241)

### Bug Fixes

- Respect `requires-python` when creating the default venv. [#1237](https://github.com/pdm-project/pdm/issues/1237)


Release v2.0.1 (2022-07-17)
---------------------------

### Bug Fixes

- Write lockfile before calling 'post_lock' hook [#1224](https://github.com/pdm-project/pdm/issues/1224)
- Suppress errors when cache dir isn't accessible. [#1226](https://github.com/pdm-project/pdm/issues/1226)
- Don't save python path for venv commands. [#1230](https://github.com/pdm-project/pdm/issues/1230)


Release v2.0.0 (2022-07-15)
---------------------------

### Bug Fixes

- Fix a bug that the running env overrides the PEP 582 `PYTHONPATH`. [#1211](https://github.com/pdm-project/pdm/issues/1211)
- Add [`pwsh`](https://github.com/PowerShell/PowerShell) as an alias of `powershell` for shell completion. [#1216](https://github.com/pdm-project/pdm/issues/1216)
- Fixed a bug with `zsh` completion regarding `--pep582` flag. [#1218](https://github.com/pdm-project/pdm/issues/1218)
- Fix a bug of requirement checking under non-isolated mode. [#1219](https://github.com/pdm-project/pdm/issues/1219)
- Fix a bug when removing packages, TOML document might become invalid. [#1221](https://github.com/pdm-project/pdm/issues/1221)


Release v2.0.0b2 (2022-07-08)
-----------------------------

### Breaking Changes

- Store file URLs instead of filenames in the lock file, bump lock version to `4.0`. [#1203](https://github.com/pdm-project/pdm/issues/1203)

### Features & Improvements

- Read site-wide configuration, which serves as the lowest-priority layer.
  This layer will be read-only in the CLI. [#1200](https://github.com/pdm-project/pdm/issues/1200)
- Get package links from the urls stored in the lock file. [#1204](https://github.com/pdm-project/pdm/issues/1204)

### Bug Fixes

- Fix a bug that the host pip(installed with pdm) may not be compatible with the project python. [#1196](https://github.com/pdm-project/pdm/issues/1196)
- Update `unearth` to fix a bug that install links with weak hashes are skipped. This often happens on self-hosted PyPI servers. [#1202](https://github.com/pdm-project/pdm/issues/1202)


Release v2.0.0b1 (2022-07-02)
-----------------------------

### Features & Improvements

- Integrate `pdm venv` commands into the main program. Make PEP 582 an opt-in feature. [#1162](https://github.com/pdm-project/pdm/issues/1162)
- Add config `global_project.fallback_verbose` defaulting to `True`. When set to `False` disables message `Project is not found, fallback to the global project` [#1188](https://github.com/pdm-project/pdm/issues/1188)
- Add `--only-keep` option to `pdm sync` to keep only selected packages. Originally requested at #398. [#1191](https://github.com/pdm-project/pdm/issues/1191)

### Bug Fixes

- Fix a bug that requirement extras and underlying are resolved to the different version [#1173](https://github.com/pdm-project/pdm/issues/1173)
- Update `unearth` to `0.4.1` to skip the wheels with invalid version parts. [#1178](https://github.com/pdm-project/pdm/issues/1178)
- Fix reading `PDM_RESOLVE_MAX_ROUNDS` environment variable (was spelled `…ROUDNS` before). [#1180](https://github.com/pdm-project/pdm/issues/1180)
- Deduplicate the list of found Python versions. [#1182](https://github.com/pdm-project/pdm/issues/1182)
- Use the normal stream handler for logging, to fix some display issues under non-tty environments. [#1184](https://github.com/pdm-project/pdm/issues/1184)

### Removals and Deprecations

- Remove the useless `--no-clean` option from `pdm sync` command. [#1191](https://github.com/pdm-project/pdm/issues/1191)


Release v2.0.0a1 (2022-06-29)
-----------------------------

### Breaking Changes

- Editable dependencies in the `[project]` table is not allowed, according to PEP 621. They are however still allowed in the `[tool.pdm.dev-dependencies]` table. PDM will emit a warning when it finds editable dependencies in the `[project]` table, or will abort when you try to add them into the `[project]` table via CLI. [#1083](https://github.com/pdm-project/pdm/issues/1083)
- Now the paths to the global configurations and global project are calculated according to platform standards. [#1161](https://github.com/pdm-project/pdm/issues/1161)

### Features & Improvements

- Add support for importing from a `setup.py` project. [#1062](https://github.com/pdm-project/pdm/issues/1062)
- Switch the UI backend to `rich`. [#1091](https://github.com/pdm-project/pdm/issues/1091)
- Improved the terminal UI and logging. Disable live progress under verbose mode. The logger levels can be controlled by the `-v` option. [#1096](https://github.com/pdm-project/pdm/issues/1096)
- Use `unearth` to replace `pip`'s `PackageFinder` and related data models. PDM no longer relies on `pip` internals, which are unstable across updates. [#1096](https://github.com/pdm-project/pdm/issues/1096)
- Lazily load the candidates returned by `find_matches()` to speed up the resolution. [#1098](https://github.com/pdm-project/pdm/issues/1098)
- Add a new command `publish` to PDM since it is required for so many people and it will make the workflow easier. [#1107](https://github.com/pdm-project/pdm/issues/1107)
- Add a `composite` script kind allowing to run multiple defined scripts in a single command as well as reusing scripts but overriding `env` or `env_file`. [#1117](https://github.com/pdm-project/pdm/issues/1117)
- Add a new execution option `--skip` to opt-out some scripts and hooks from any execution (both scripts and PDM commands). [#1127](https://github.com/pdm-project/pdm/issues/1127)
- Add the `pre/post_publish`, `pre/post_run` and `pre/post_script` hooks as well as an extensive lifecycle and hooks documentation. [#1147](https://github.com/pdm-project/pdm/issues/1147)
- Shorter scripts listing, especially for multilines and composite scripts. [#1151](https://github.com/pdm-project/pdm/issues/1151)
- Build configurations have been moved to `[tool.pdm.build]`, according to `pdm-pep517 1.0.0`. At the same time, warnings will be shown against old usages. [#1153](https://github.com/pdm-project/pdm/issues/1153)
- Improve the lock speed by parallelizing the hash fetching. [#1154](https://github.com/pdm-project/pdm/issues/1154)
- Retrieve the candidate metadata by parsing the `pyproject.toml` rather than building it. [#1156](https://github.com/pdm-project/pdm/issues/1156)
- Update the format converters to support the new `[tool.pdm.build]` table. [#1157](https://github.com/pdm-project/pdm/issues/1157)
- Scripts are now available as root command if they don't conflict with any builtin or plugin-contributed command. [#1159](https://github.com/pdm-project/pdm/issues/1159)
- Add a `post_use` hook triggered after successfully switching Python version. [#1163](https://github.com/pdm-project/pdm/issues/1163)
- Add project configuration `respect-source-order` under `[tool.pdm.resolution]` to respect the source order in the `pyproject.toml` file. Packages will be returned by source earlier in the order or later ones if not found. [#593](https://github.com/pdm-project/pdm/issues/593)

### Bug Fixes

- Fix a bug that candidates with local part in the version can't be found and installed correctly. [#1093](https://github.com/pdm-project/pdm/issues/1093)

### Dependencies

- Prefer `tomllib` on Python 3.11 [#1072](https://github.com/pdm-project/pdm/issues/1072)
- Drop the vendored libraries `click`, `halo`, `colorama` and `log_symbols`. PDM has no vendors now. [#1091](https://github.com/pdm-project/pdm/issues/1091)
- Update dependency version `pdm-pep517` to `1.0.0`. [#1153](https://github.com/pdm-project/pdm/issues/1153)

### Removals and Deprecations

- PDM legacy metadata format(from `pdm 0.x`) is no longer supported. [#1157](https://github.com/pdm-project/pdm/issues/1157)

### Miscellany

- Provide a `tox.ini` file for easier local testing against all Python versions. [#1160](https://github.com/pdm-project/pdm/issues/1160)


Release v1.15.4 (2022-06-28)
----------------------------

### Bug Fixes

- Revert #1106: Do not use `venv` scheme for `prefix` kind install scheme. [#1158](https://github.com/pdm-project/pdm/issues/1158)
- Fix a bug when updating a package with extra requirements, the package version doesn't get updated correctly. [#1166](https://github.com/pdm-project/pdm/issues/1166)

### Miscellany

- Add additional installation option via [asdf-pdm](https://github.com/1oglop1/asdf-pdm).
  Add `skip-add-to-path` option to installer in order to prevent changing `PATH`.
  Replace `bin` variable name with `bin_dir`. [#1145](https://github.com/pdm-project/pdm/issues/1145)


Release v1.15.3 (2022-06-14)
----------------------------

### Bug Fixes

- Fix a defect in the resolution preferences that causes an infinite resolution loop. [#1119](https://github.com/pdm-project/pdm/issues/1119)
- Update the poetry importer to support the new `[tool.poetry.build]` config table. [#1131](https://github.com/pdm-project/pdm/issues/1131)

### Improved Documentation

- Add support for multiple versions of documentations. [#1126](https://github.com/pdm-project/pdm/issues/1126)


Release v1.15.2 (2022-06-06)
----------------------------

### Bug Fixes

- Fix bug where SIGINT is sent to the main `pdm` process and not to the process actually being run. [#1095](https://github.com/pdm-project/pdm/issues/1095)
- Fix a bug due to the build backend fallback, which causes different versions of the same requirement to exist in the build environment, making the building unstable depending on which version being used. [#1099](https://github.com/pdm-project/pdm/issues/1099)
- Don't include the `version` in the cache key of the locked candidates if they are from a URL requirement. [#1099](https://github.com/pdm-project/pdm/issues/1099)
- Fix a bug where dependencies with `requires-python` pre-release versions caused `pdm update` to fail with `InvalidPyVersion`. [#1111](https://github.com/pdm-project/pdm/issues/1111)


Release v1.15.1 (2022-06-02)
----------------------------

### Bug Fixes

- Fix a bug that dependencies are missing from the dep graph when they are depended by a requirement with extras. [#1097](https://github.com/pdm-project/pdm/issues/1097)
- Give a default version if the version is dynamic in `setup.cfg` or `setup.py`. [#1101](https://github.com/pdm-project/pdm/issues/1101)
- Fix a bug that the hashes for file URLs are not included in the lock file. [#1103](https://github.com/pdm-project/pdm/issues/1103)
- Fix a bug that package versions are updated even when they are excluded by `pdm update` command. [#1104](https://github.com/pdm-project/pdm/issues/1104)
- Prefer `venv` install scheme when available. This scheme is more stable than `posix_prefix` scheme since the latter is often patched by distributions. [#1106](https://github.com/pdm-project/pdm/issues/1106)

### Miscellany

- Move the test artifacts to a submodule. It will make it easier to package this project. [#1084](https://github.com/pdm-project/pdm/issues/1084)


Release v1.15.0 (2022-05-16)
----------------------------

### Features & Improvements

- Allow specifying lockfile other than `pdm.lock` by `--lockfile` option or `PDM_LOCKFILE` env var. [#1038](https://github.com/pdm-project/pdm/issues/1038)

### Bug Fixes

- Replace the editable entry in `pyproject.toml` when running `pdm add --no-editable <package>`. [#1050](https://github.com/pdm-project/pdm/issues/1050)
- Ensure the pip module inside venv in installation script. [#1053](https://github.com/pdm-project/pdm/issues/1053)
- Fix the py2 compatibility issue in the in-process `get_sysconfig_path.py` script. [#1056](https://github.com/pdm-project/pdm/issues/1056)
- Fix a bug that file paths in URLs are not correctly unquoted. [#1073](https://github.com/pdm-project/pdm/issues/1073)
- Fix a bug on Python 3.11 that overriding an existing command from plugins raises an error. [#1075](https://github.com/pdm-project/pdm/issues/1075)
- Replace the `${PROJECT_ROOT}` variable in the result of `export` command. [#1079](https://github.com/pdm-project/pdm/issues/1079)

### Removals and Deprecations

- Show a warning if Python 2 interpreter is being used and remove the support on 2.0. [#1082](https://github.com/pdm-project/pdm/issues/1082)


Release v1.14.1 (2022-04-21)
----------------------------

### Features & Improvements

- Ask for description when doing `pdm init` and create default README for libraries. [#1041](https://github.com/pdm-project/pdm/issues/1041)

### Bug Fixes

- Fix a bug of missing subdirectory fragment when importing from a `requirements.txt`. [#1036](https://github.com/pdm-project/pdm/issues/1036)
- Fix use_cache.json with corrupted python causes `pdm use` error. [#1039](https://github.com/pdm-project/pdm/issues/1039)
- Ignore the `optional` key when converting from Poetry's dependency entries. [#1042](https://github.com/pdm-project/pdm/issues/1042)

### Improved Documentation

- Clarify documentation on enabling PEP582 globally. [#1033](https://github.com/pdm-project/pdm/issues/1033)


Release v1.14.0 (2022-04-08)
----------------------------

### Features & Improvements

- Editable installations won't be overridden unless `--no-editable` is passed.
  `pdm add --no-editable` will now override the `editable` mode of the given packages. [#1011](https://github.com/pdm-project/pdm/issues/1011)
- Re-calculate the file hashes when running `pdm lock --refresh`. [#1019](https://github.com/pdm-project/pdm/issues/1019)

### Bug Fixes

- Fix a bug that requirement with extras isn't resolved to the version as specified by the range. [#1001](https://github.com/pdm-project/pdm/issues/1001)
- Replace the `${PROJECT_ROOT}` in the output of `pdm list`. [#1004](https://github.com/pdm-project/pdm/issues/1004)
- Further fix the python path issue of MacOS system installed Python. [#1023](https://github.com/pdm-project/pdm/issues/1023)
- Fix the install path issue on Python 3.10 installed from homebrew. [#996](https://github.com/pdm-project/pdm/issues/996)

### Improved Documentation

- Document how to install PDM inside a project with Pyprojectx. [#1004](https://github.com/pdm-project/pdm/issues/1004)

### Dependencies

- Support `installer 0.5.x`. [#1002](https://github.com/pdm-project/pdm/issues/1002)


Release v1.13.6 (2022-03-28)
----------------------------

### Bug Fixes

- Default the optional `license` field to "None". [#991](https://github.com/pdm-project/pdm/issues/991)
- Don't create project files in `pdm search` command. [#993](https://github.com/pdm-project/pdm/issues/993)
- Fix a bug that the env vars in source urls in exported result are not expanded. [#997](https://github.com/pdm-project/pdm/issues/997)


Release v1.13.5 (2022-03-23)
----------------------------

### Features & Improvements

- Users can change the install destination of global project to the user site(`~/.local`) with `global_project.user_site` config. [#885](https://github.com/pdm-project/pdm/issues/885)
- Make the path to the global project configurable. Rename the configuration `auto_global` to `global_project.fallback` and deprecate the old name. [#986](https://github.com/pdm-project/pdm/issues/986)

### Bug Fixes

- Fix the compatibility when fetching license information in `show` command. [#966](https://github.com/pdm-project/pdm/issues/966)
- Don't follow symlinks for the paths in the requirement strings. [#976](https://github.com/pdm-project/pdm/issues/976)
- Use the default install scheme when installing build requirements. [#983](https://github.com/pdm-project/pdm/issues/983)
- Fix a bug that `_.site_packages` is overridden by default option value. [#985](https://github.com/pdm-project/pdm/issues/985)


Release v1.13.4 (2022-03-09)
----------------------------

### Features & Improvements

- Update the dependency `pdm-pep517` to support PEP 639. [#959](https://github.com/pdm-project/pdm/issues/959)

### Bug Fixes

- Filter out the unmatched python versions when listing the available versions. [#941](https://github.com/pdm-project/pdm/issues/941)
- Fix a bug displaying the available python versions. [#943](https://github.com/pdm-project/pdm/issues/943)
- Fix a bug under non-UTF8 console encoding. [#960](https://github.com/pdm-project/pdm/issues/960)
- Fix a bug that data files are not copied to the destination when using installation cache. [#961](https://github.com/pdm-project/pdm/issues/961)


Release v1.13.3 (2022-02-24)
----------------------------

### Bug Fixes

- Fix a bug that VCS repo name are parsed as the package name. [#928](https://github.com/pdm-project/pdm/issues/928)
- Support prerelease versions for global projects. [#932](https://github.com/pdm-project/pdm/issues/932)
- Fix a bug that VCS revision in the lock file isn't respected when installing. [#933](https://github.com/pdm-project/pdm/issues/933)

### Dependencies

- Switch from `pythonfinder` to `findpython` as the Python version finder. [#930](https://github.com/pdm-project/pdm/issues/930)


Release v1.13.2 (2022-02-20)
----------------------------

### Bug Fixes

- Fix a regression issue that prereleases can't be installed if the version specifier of the requirement doesn't imply that. [#920](https://github.com/pdm-project/pdm/issues/920)


Release v1.13.1 (2022-02-18)
----------------------------

### Bug Fixes

- Fix a bug that bad pip cache dir value breaks PDM's check update function. [#922](https://github.com/pdm-project/pdm/issues/922)
- Fix a race condition in parallel installation by changing metadata to a lazy property.
  This fixes a bug that incompatible wheels are installed unexpectedly. [#924](https://github.com/pdm-project/pdm/issues/924)


Release v1.13.0.post0 (2022-02-18)
----------------------------------

### Bug Fixes

- Fix a bug that incompatible platform-specific wheels are installed. [#921](https://github.com/pdm-project/pdm/issues/921)


Release v1.13.0 (2022-02-18)
----------------------------

### Features & Improvements

- Support `pre_*` and `post_*` scripts for task composition. Pre- and Post- scripts for `init`, `build`, `install` and `lock` will be run if present. [#789](https://github.com/pdm-project/pdm/issues/789)
- Support `--config/-c` option to specify another global configuration file. [#883](https://github.com/pdm-project/pdm/issues/883)
- Packages with extras require no longer inherit the dependencies from the same package without extras. It is because the package without extras are returned as one of the dependencies. This change won't break the existing lock files nor dependency cache. [#892](https://github.com/pdm-project/pdm/issues/892)
- Support version ranges in `[tool.pdm.overrides]` table. [#909](https://github.com/pdm-project/pdm/issues/909)
- Rename config `use_venv` to `python.use_venv`;
  rename config `feature.install_cache` to `install.cache`;
  rename config `feature.install_cache_method` to `install.cache_method`;
  rename config `parallel_install` to `install.parallel`. [#914](https://github.com/pdm-project/pdm/issues/914)

### Bug Fixes

- Fix a bug that file URLs or VCS URLs don't work in `[tool.pdm.overrides]` table. [#861](https://github.com/pdm-project/pdm/issues/861)
- Fix a bug of identifier mismatch for URL requirements without an explicit name. [#901](https://github.com/pdm-project/pdm/issues/901)
- No `requires-python` should be produced if ANY(`*`) is given. [#917](https://github.com/pdm-project/pdm/issues/917)
- Fix a bug that `pdm.lock` gets created when `--dry-run` is passed to `pdm add`. [#918](https://github.com/pdm-project/pdm/issues/918)

### Improved Documentation

- The default editable backend becomes `path`. [#904](https://github.com/pdm-project/pdm/issues/904)

### Removals and Deprecations

- Stop auto-migrating projects from PDM 0.x format. [#912](https://github.com/pdm-project/pdm/issues/912)

### Refactor

- Rename `ExtrasError` to `ExtrasWarning` for better understanding. Improve the warning message. [#892](https://github.com/pdm-project/pdm/issues/892)
- Extract the environment related code from `Candidate` into a new class `PreparedCandidate`.
  `Candidate` no longer holds an `Environment` instance. [#920](https://github.com/pdm-project/pdm/issues/920)


Release v1.12.8 (2022-02-06)
----------------------------

### Features & Improvements

- Print the error and continue if a plugin fails to load. [#878](https://github.com/pdm-project/pdm/issues/878)

### Bug Fixes

- PDM now ignores configuration of uninstalled plugins. [#872](https://github.com/pdm-project/pdm/issues/872)
- Fix the compatibility issue with `pip>=22.0`. [#875](https://github.com/pdm-project/pdm/issues/875)


Release v1.12.7 (2022-01-31)
----------------------------

### Features & Improvements

- If no command is given to `pdm run`, it will run the Python REPL. [#856](https://github.com/pdm-project/pdm/issues/856)

### Bug Fixes

- Fix the hash calculation when generating `direct_url.json` for a local pre-built wheel. [#861](https://github.com/pdm-project/pdm/issues/861)
- PDM no longer migrates project meta silently. [#867](https://github.com/pdm-project/pdm/issues/867)

### Dependencies

- Pin `pip<22.0`. [#874](https://github.com/pdm-project/pdm/issues/874)

### Miscellany

- Reduce the number of tests that require network, and mark the rest with `network` marker. [#858](https://github.com/pdm-project/pdm/issues/858)


Release v1.12.6 (2022-01-12)
----------------------------

### Bug Fixes

- Fix a bug that cache dir isn't created. [#843](https://github.com/pdm-project/pdm/issues/843)


Release v1.12.5 (2022-01-11)
----------------------------

### Bug Fixes

- Fix a resolution error that dots in the package name are normalized to `-` unexpectedly. [#853](https://github.com/pdm-project/pdm/issues/853)


Release v1.12.4 (2022-01-11)
----------------------------

### Features & Improvements

- Remember the last selection in `use` command to save the human effort.
  And introduce an `-i` option to ignored that remembered value. [#846](https://github.com/pdm-project/pdm/issues/846)

### Bug Fixes

- Fix a bug of uninstall crash when the package has directories in `RECORD`. [#847](https://github.com/pdm-project/pdm/issues/847)
- Fix the `ModuleNotFoundError` during uninstall when the modules required are removed. [#850](https://github.com/pdm-project/pdm/issues/850)


Release v1.12.3 (2022-01-07)
----------------------------

### Features & Improvements

- Support setting Python path in global configuration. [#842](https://github.com/pdm-project/pdm/issues/842)

### Bug Fixes

- Lowercase the package names in the lock file make it more stable. [#836](https://github.com/pdm-project/pdm/issues/836)
- Show the packages to be updated in dry run mode of `pdm update` even if `--no-sync` is passed. [#837](https://github.com/pdm-project/pdm/issues/837)
- Improve the robustness of update check code. [#841](https://github.com/pdm-project/pdm/issues/841)
- Fix a bug that export result has environment markers that don't apply for all requirements. [#843](https://github.com/pdm-project/pdm/issues/843)


Release v1.12.2 (2021-12-30)
----------------------------

### Features & Improvements

- Allow changing the installation linking method by `feature.install_cache_method` config. [#822](https://github.com/pdm-project/pdm/issues/822)

### Bug Fixes

- Fix a bug that namespace packages can't be symlinked to the cache due to existing links. [#820](https://github.com/pdm-project/pdm/issues/820)
- Make PDM generated pth files processed as early as possible. [#821](https://github.com/pdm-project/pdm/issues/821)
- Fix a UnicodeDecodeError for subprocess logger under Windows/GBK. [#823](https://github.com/pdm-project/pdm/issues/823)


Release v1.12.1 (2021-12-24)
----------------------------

### Bug Fixes

- Don't symlink pycaches to the target place. [#817](https://github.com/pdm-project/pdm/issues/817)


Release v1.12.0 (2021-12-22)
----------------------------

### Features & Improvements

- Add `lock --refresh` to update the hash stored with the lock file without updating the pinned versions. [#642](https://github.com/pdm-project/pdm/issues/642)
- Support resolution overriding in the `[tool.pdm.overrides]` table. [#790](https://github.com/pdm-project/pdm/issues/790)
- Add support for signals for basic operations, now including `post_init`, `pre_lock`, `post_lock`, `pre_install` and `post_install`. [#798](https://github.com/pdm-project/pdm/issues/798)
- Add `install --check` to check if the lock file is up to date. [#810](https://github.com/pdm-project/pdm/issues/810)
- Use symlinks to cache installed packages when it is supported by the file system. [#814](https://github.com/pdm-project/pdm/issues/814)

### Bug Fixes

- Fix a bug that candidates from urls are rejected by the `allow_prereleases` setting.
  Now non-named requirements are resolved earlier than pinned requirements. [#799](https://github.com/pdm-project/pdm/issues/799)

### Improved Documentation

- Add a new doc page: **API reference**. [#802](https://github.com/pdm-project/pdm/issues/802)

### Dependencies

- Switch back from `atoml` to `tomlkit` as the style-preserving TOML parser. The latter has supported TOML v1.0.0. [#809](https://github.com/pdm-project/pdm/issues/809)

### Miscellany

- Cache the latest version of PDM for one week to reduce the request frequency. [#800](https://github.com/pdm-project/pdm/issues/800)


Release v1.11.3 (2021-12-15)
----------------------------

### Features & Improvements

- Change the default version save strategy to `minimum`, without upper bounds. [#787](https://github.com/pdm-project/pdm/issues/787)

### Bug Fixes

- Fix the patching of sysconfig in PEP 582 initialization script. [#796](https://github.com/pdm-project/pdm/issues/796)

### Miscellany

- Fix an installation failure of the bootstrap script on MacOS Catalina. [#793](https://github.com/pdm-project/pdm/issues/793)
- Add a basic benchmarking script. [#794](https://github.com/pdm-project/pdm/issues/794)


Release v1.11.2 (2021-12-10)
----------------------------

### Bug Fixes

- Fix the resolution order to reduce the loop number to find a conflict. [#781](https://github.com/pdm-project/pdm/issues/781)
- Patch the functions in `sysconfig` to return the PEP 582 scheme in `pdm run`. [#784](https://github.com/pdm-project/pdm/issues/784)

### Dependencies

- Remove the upper bound of version constraints for most dependencies, except for some zero-versioned ones. [#787](https://github.com/pdm-project/pdm/issues/787)


Release v1.11.1 (2021-12-08)
----------------------------

### Features & Improvements

- Support `--pre/--prelease` option for `pdm add` and `pdm update`. It will allow prereleases to be pinned. [#774](https://github.com/pdm-project/pdm/issues/774)
- Improve the error message when python is found but not meeting the python requirement. [#777](https://github.com/pdm-project/pdm/issues/777)

### Bug Fixes

- Fix a bug that `git+https` candidates cannot be resolved. [#771](https://github.com/pdm-project/pdm/issues/771)
- Fix an infinite resolution loop by resolving the top-level packages first. Also deduplicate the lines from the same requirement in the error output. [#776](https://github.com/pdm-project/pdm/issues/776)

### Miscellany

- Fix the install script to use a zipapp of virtualenv when it isn't installed. [#780](https://github.com/pdm-project/pdm/issues/780)


Release v1.11.0 (2021-11-30)
----------------------------

### Features & Improvements

- Move `version` from `[project]` table to `[tool.pdm]` table, delete `classifiers` from `dynamic`, and warn usage about the deprecated usages. [#748](https://github.com/pdm-project/pdm/issues/748)
- Add support for Conda environments in addition to Python virtual environments. [#749](https://github.com/pdm-project/pdm/issues/749)
- Add support for saving only the lower bound `x >= VERSION` when adding dependencies. [#752](https://github.com/pdm-project/pdm/issues/752)
- Improve the error message when resolution fails. [#754](https://github.com/pdm-project/pdm/issues/754)

### Bug Fixes

- Switch to self-implemented `pdm list --freeze` to fix a bug due to Pip's API change. [#533](https://github.com/pdm-project/pdm/issues/533)
- Fix an infinite loop issue when resolving candidates with incompatible `requires-python`. [#744](https://github.com/pdm-project/pdm/issues/744)
- Fix the python finder to support pyenv-win. [#745](https://github.com/pdm-project/pdm/issues/745)
- Fix the ANSI color output for Windows cmd and Powershell terminals. [#753](https://github.com/pdm-project/pdm/issues/753)

### Removals and Deprecations

- Remove `-s/--section` option from all previously supported commands. Use `-G/--group` instead. [#756](https://github.com/pdm-project/pdm/issues/756)


Release v1.10.3 (2021-11-18)
----------------------------

### Bug Fixes

- Use `importlib` to replace `imp` in the `sitecustomize` module for Python 3. [#574](https://github.com/pdm-project/pdm/issues/574)
- Fix the lib paths under non-isolated build. [#740](https://github.com/pdm-project/pdm/issues/740)
- Exclude the dependencies with extras in the result of `pdm export`. [#741](https://github.com/pdm-project/pdm/issues/741)


Release v1.10.2 (2021-11-14)
----------------------------

### Features & Improvements

- Add a new option `-s/--site-packages` to `pdm run` as well as a script config item. When it is set to `True`, site-packages from the selected interpreter will be loaded into the running environment. [#733](https://github.com/pdm-project/pdm/issues/733)

### Bug Fixes

- Now `NO_SITE_PACKAGES` isn't set in `pdm run` if the executable is out of local packages. [#733](https://github.com/pdm-project/pdm/issues/733)


Release v1.10.1 (2021-11-09)
----------------------------

### Features & Improvements

- Isolate the project environment with system site packages in `pdm run`, but keep them seen when PEP 582 is enabled. [#708](https://github.com/pdm-project/pdm/issues/708)

### Bug Fixes

- Run `pip` with `--isolated` when building wheels. In this way some env vars like `PIP_REQUIRE_VIRTUALENV` can be ignored. [#669](https://github.com/pdm-project/pdm/issues/669)
- Fix the install script to ensure `pip` is not DEBUNDLED. [#685](https://github.com/pdm-project/pdm/issues/685)
- Fix a bug that when `summary` is `None`, the lockfile can't be generated. [#719](https://github.com/pdm-project/pdm/issues/719)
- `${PROJECT_ROOT}` should be written in the URL when relative path is given. [#721](https://github.com/pdm-project/pdm/issues/721)
- Fix a bug that when project table already exists, `pdm import` can't merge the settings correctly. [#723](https://github.com/pdm-project/pdm/issues/723)


Release v1.10.0 (2021-10-25)
----------------------------

### Features & Improvements

- Add `--no-sync` option to `update` command. [#684](https://github.com/pdm-project/pdm/issues/684)
- Support `find_links` source type. It can be specified via `type` key of `[[tool.pdm.source]]` table. [#694](https://github.com/pdm-project/pdm/issues/694)
- Add `--dry-run` option to `add`, `install` and `remove` commands. [#698](https://github.com/pdm-project/pdm/issues/698)

### Bug Fixes

- Remove trailing whitespace with terminal output of tables (via `project.core.ui.display_columns`), fixing unnecessary wrapping due to / with empty lines full of spaces in case of long URLs in the last column. [#680](https://github.com/pdm-project/pdm/issues/680)
- Include files should be installed under venv's base path. [#682](https://github.com/pdm-project/pdm/issues/682)
- Ensure the value of `check_update` is boolean. [#689](https://github.com/pdm-project/pdm/issues/689)

### Improved Documentation

- Update the contributing guide, remove the usage of `setup_dev.py` in favor of `pip install`. [#676](https://github.com/pdm-project/pdm/issues/676)


Release v1.9.0 (2021-10-12)
---------------------------

### Bug Fixes

- Fix a bug that `requires-python` is not recognized in candidates evaluation. [#657](https://github.com/pdm-project/pdm/issues/657)
- Fix the path order when pdm run so that executables in local packages dir are found first. [#678](https://github.com/pdm-project/pdm/issues/678)

### Dependencies

- Update `installer` to `0.3.0`, fixing a bug that broke installation of some packages with unusual wheel files. [#653](https://github.com/pdm-project/pdm/issues/653)
- Change `packaging` and `typing-extensions` to direct dependencies. [#674](https://github.com/pdm-project/pdm/issues/674)

### Refactor

- `requires-python` now participates in the resolution as a dummy requirement. [#658](https://github.com/pdm-project/pdm/issues/658)


Release v1.8.5 (2021-09-16)
---------------------------

### Bug Fixes

- Fix the error of regex to find the shebang line. [#656](https://github.com/pdm-project/pdm/issues/656)


Release v1.8.4 (2021-09-15)
---------------------------

### Features & Improvements

- Support `--no-isolation` option for `install`, `lock`, `update`, `remove`, `sync` commands. [#640](https://github.com/pdm-project/pdm/issues/640)
- Make `project_max_depth` configurable and default to `5`. [#643](https://github.com/pdm-project/pdm/issues/643)

### Bug Fixes

- Don't try `pdm-pep517` backend on Python 2.7 when installing self as editable. [#640](https://github.com/pdm-project/pdm/issues/640)
- Fix a bug that existing shebang can't be replaced correctly. [#651](https://github.com/pdm-project/pdm/issues/651)
- Fix the version range saving for prerelease versions. [#654](https://github.com/pdm-project/pdm/issues/654)


Release v1.8.3 (2021-09-07)
---------------------------

### Features & Improvements

- Allow to build in non-isolated environment, to enable optional speedups depending on the environment. [#635](https://github.com/pdm-project/pdm/issues/635)

### Bug Fixes

- Don't copy `*-nspkg.pth` files in `install_cache` mode. It will still work without them. [#623](https://github.com/pdm-project/pdm/issues/623)


Release v1.8.2 (2021-09-01)
---------------------------

### Bug Fixes

- Fix the removal issue of standalone pyc files [#633](https://github.com/pdm-project/pdm/issues/633)


Release v1.8.1 (2021-08-26)
---------------------------

### Features & Improvements

- Add `-r/--reinstall` option to `sync` command to force re-install the existing dependencies. [#601](https://github.com/pdm-project/pdm/issues/601)
- Show update hint after every pdm command. [#603](https://github.com/pdm-project/pdm/issues/603)
- `pdm cache clear` can clear cached installations if not needed any more. [#604](https://github.com/pdm-project/pdm/issues/604)

### Bug Fixes

- Fix the editable install script so that `setuptools` won't see the dependencies under local packages. [#601](https://github.com/pdm-project/pdm/issues/601)
- Preserve the executable bit when installing wheels. [#606](https://github.com/pdm-project/pdm/issues/606)
- Write PEP 610 metadata `direct_url.json` when installing wheels. [#607](https://github.com/pdm-project/pdm/issues/607)
- Fix a bug that `*` fails to be converted as `SpecifierSet`. [#609](https://github.com/pdm-project/pdm/issues/609)

### Refactor

- Build editable packages are into wheels via PEP 660 build backend. Now all installations are unified into wheels. [#612](https://github.com/pdm-project/pdm/issues/612)


Release v1.8.0 (2021-08-16)
---------------------------

### Features & Improvements

- Added a new mode `--json` to the list command which outputs the dependency graph as a JSON document. [#583](https://github.com/pdm-project/pdm/issues/583)
- Add a new config `feature.install_cache`. When it is turned on, wheels will be installed into a centralized package repo and create `.pth` files under project packages directory to link to the cached package. [#589](https://github.com/pdm-project/pdm/issues/589)

### Bug Fixes

- Fix env vars in source URLs not being expanded in all cases. [#570](https://github.com/pdm-project/pdm/issues/570)
- Fix the weird output of `pdm show`. [#580](https://github.com/pdm-project/pdm/issues/580)
- Prefer `~/.pyenv/shims/python3` as the pyenv interpreter. [#590](https://github.com/pdm-project/pdm/issues/590)
- Fix a bug that installing will download candidates that do not match the locked hashes. [#596](https://github.com/pdm-project/pdm/issues/596)

### Improved Documentation

- Added instructions to the Contributing section for creating news fragments [#573](https://github.com/pdm-project/pdm/issues/573)

### Removals and Deprecations

- Deprecate `-s/--section` option in favor of `-G/--group`. [#591](https://github.com/pdm-project/pdm/issues/591)

### Refactor

- Switch to a self-implemented version of uninstaller. [#586](https://github.com/pdm-project/pdm/issues/586)
- `pdm/installers/installers.py` is renamed to `pdm/installers/manager.py` to be more accurate. The `Installer` class under that file is renamed to `InstallerManager` and is exposed in the `pdm.core.Core` object for overriding. The new `pdm/installers/installers.py` contains some installation implementations. [#589](https://github.com/pdm-project/pdm/issues/589)
- Switch from `pkg_resources.Distribution` to the implementation of `importlib.metadata`. [#592](https://github.com/pdm-project/pdm/issues/592)


Release v1.7.2 (2021-07-30)
---------------------------

### Bug Fixes

- Remove the existing files before installing. [#565](https://github.com/pdm-project/pdm/issues/565)
- Deduplicate the plugins list. [#566](https://github.com/pdm-project/pdm/issues/566)


Release v1.7.1 (2021-07-29)
---------------------------

### Bug Fixes

- Accept non-canonical distribution name in the wheel's dist-info directory name. [#529](https://github.com/pdm-project/pdm/issues/529)
- Prefer requirements with narrower version constraints or allowing prereleases to find matches. [#551](https://github.com/pdm-project/pdm/issues/551)
- Use the underlying real executable path for writing shebangs. [#553](https://github.com/pdm-project/pdm/issues/553)
- Fix a bug that extra markers cannot be extracted when combined with other markers with "and". [#559](https://github.com/pdm-project/pdm/issues/559)
- Fix a bug that redacted credentials in source urls get overwritten with the plain text after locking. [#561](https://github.com/pdm-project/pdm/issues/561)

### Refactor

- Use installer as the wheel installer, replacing `distlib`. [#519](https://github.com/pdm-project/pdm/issues/519)


Release v1.7.0 (2021-07-20)
---------------------------

### Features & Improvements

- Support showing individual fields by `--<field-name>` options in pdm show. When no package is given, show this project. [#527](https://github.com/pdm-project/pdm/issues/527)
- Add `--freeze` option to `pdm list` command which shows the dependencies list as pip's requirements.txt format. [#531](https://github.com/pdm-project/pdm/issues/531)

### Bug Fixes

- Fix the path manipulation on Windows, now the PEP 582 path is prepended to the `PYTHONPATH`. [#522](https://github.com/pdm-project/pdm/issues/522)
- Fix the handling of auth prompting: will try keyring in non-verbose mode. [#523](https://github.com/pdm-project/pdm/issues/523)
- Recognize old entry point name "pdm.plugin" for backward-compatibility. [#530](https://github.com/pdm-project/pdm/issues/530)
- Match the VCS scheme in case-insensitive manner. [#537](https://github.com/pdm-project/pdm/issues/537)
- Use the default permission bits when writing project files. [#542](https://github.com/pdm-project/pdm/issues/542)
- Fix the VCS url to be consistent between lock and install. [#547](https://github.com/pdm-project/pdm/issues/547)

### Improved Documentation

- Add installation instructions for Scoop. [#522](https://github.com/pdm-project/pdm/issues/522)

### Dependencies

- Update `pdm-pep517` to `0.8.0`. [#524](https://github.com/pdm-project/pdm/issues/524)
- Switch from `toml` to `tomli`. [#541](https://github.com/pdm-project/pdm/issues/541)

### Refactor

- Separate the build env into two different levels for better caching. [#541](https://github.com/pdm-project/pdm/issues/541)
- Refactor the build part into smaller functions. [#543](https://github.com/pdm-project/pdm/issues/543)


Release v1.6.4 (2021-06-23)
---------------------------

### Features & Improvements

- Extract package name from egg-info in filename when eligible. Remove the patching code of resolvelib's inner class. [#441](https://github.com/pdm-project/pdm/issues/441)
- Support installing packages from subdiretories of VCS repository. [#507](https://github.com/pdm-project/pdm/issues/507)
- Add an install script to bootstrap PDM quickly without help of other tools. Modify docs to recommend this installation method. [#508](https://github.com/pdm-project/pdm/issues/508)
- Add a new subcommand `plugin` to manage pdm plugins, including `add`, `remove` and `list` commands. [#510](https://github.com/pdm-project/pdm/issues/510)

### Bug Fixes

- Don't monkeypatch the internal class of `resolvelib` any more. This makes PDM more stable across updates of sub-dependencies. [#515](https://github.com/pdm-project/pdm/issues/515)

### Miscellany

- Clear the type errors from mypy. [#261](https://github.com/pdm-project/pdm/issues/261)


Release v1.6.3 (2021-06-17)
---------------------------

### Features & Improvements

- Add an option `-u/--unconstrained` to support unconstraining version specifiers when adding packages. [#501](https://github.com/pdm-project/pdm/issues/501)

### Bug Fixes

- Fix the format of dependency arrays when a new value is appended. [#487](https://github.com/pdm-project/pdm/issues/487)
- Allow missing email attribute for authors and maintainers. [#492](https://github.com/pdm-project/pdm/issues/492)
- Fix a bug that editable install shouldn't require pyproject.toml to be valid. [#497](https://github.com/pdm-project/pdm/issues/497)
- Fix a bug on MacOS that purelib and platlib paths of isolated build envs cannot be substituted correctly if the Python is a framework build. [#502](https://github.com/pdm-project/pdm/issues/502)
- Fix the version sort of candidates. [#506](https://github.com/pdm-project/pdm/issues/506)


Release v1.6.2 (2021-05-31)
---------------------------

No significant changes.


Release v1.6.1 (2021-05-31)
---------------------------

No significant changes.


Release v1.6.0 (2021-05-31)
---------------------------

### Features & Improvements

- Use a new approach to determine the packages to be installed. This requires a quick resolution step before installation. [#456](https://github.com/pdm-project/pdm/issues/456)
- `pdm export` no longer produces requirements file applicable for all platforms due to the new approach. [#456](https://github.com/pdm-project/pdm/issues/456)
- Add structural typing for requirements module. Refactor the requirements module for that purpose. [#433](https://github.com/pdm-project/pdm/issues/433)
- Introduce `--no-editable` option to install non-editable versions of all packages. [#443](https://github.com/pdm-project/pdm/issues/443)
- Introduce `--no-self` option to prevent the project itself from being installed. [#444](https://github.com/pdm-project/pdm/issues/444)
- Add a default `.gitignore` file in the `__pypackages__` directory. [#446](https://github.com/pdm-project/pdm/issues/446)
- Check if the lock file version is compatible with PDM program before installation. [#463](https://github.com/pdm-project/pdm/issues/463)
- Expose the project root path via `PDM_PROJECT_ROOT` env var. Change to the project root when executing scripts. [#470](https://github.com/pdm-project/pdm/issues/470)
- Fix a bug that installation resolution doesn't respect the requirement markers from pyproject config. [#480](https://github.com/pdm-project/pdm/issues/480)

### Bug Fixes

- Changing to multiline breaks the parsing of TOML document. [#462](https://github.com/pdm-project/pdm/issues/462)
- Fix a bug that transient dependencies of conditional requirements can't be resolved. [#472](https://github.com/pdm-project/pdm/issues/472)
- Fix a bug that invalid wheels are rejected while they are acceptable for resolution. [#473](https://github.com/pdm-project/pdm/issues/473)
- Fix a bug that build environment is not fully isolated with the hosted environment. [#477](https://github.com/pdm-project/pdm/issues/477)
- Ensure the lock file is compatible before looking for the locked candidates. [#484](https://github.com/pdm-project/pdm/issues/484)

### Improved Documentation

- Fix 404 links in documentation. [#472](https://github.com/pdm-project/pdm/issues/472)

### Dependencies

- Migrate from `tomlkit` to `atoml` as the style-preserving TOML parser and writer. [#465](https://github.com/pdm-project/pdm/issues/465)

### Removals and Deprecations

- Remove the warning of `--dev` flag for older versions of PDM. [#444](https://github.com/pdm-project/pdm/issues/444)

### Miscellany

- Add Python 3.10 beta CI job. [#457](https://github.com/pdm-project/pdm/issues/457)


Release v1.5.3 (2021-05-10)
---------------------------

### Features & Improvements

- Support passing options to the build backends via `--config-setting`. [#452](https://github.com/pdm-project/pdm/issues/452)

### Bug Fixes

- Seek for other sitecustomize.py to import. [#422](https://github.com/pdm-project/pdm/issues/422)
- Fix an unescaped single quote in fish completion script. [#423](https://github.com/pdm-project/pdm/issues/423)
- The hashes of a remote file candidate should be calculated from the link itself. [#450](https://github.com/pdm-project/pdm/issues/450)

### Dependencies

- Remove `keyring` as a dependency and guide users to install it when it is not available. [#442](https://github.com/pdm-project/pdm/issues/442)
- Specify the minimum version of `distlib`. [#447](https://github.com/pdm-project/pdm/issues/447)

### Miscellany

- Add log output about found candidates and their origin. [#421](https://github.com/pdm-project/pdm/issues/421)
- Add [mypy](https://github.com/python/mypy) pre-commit hook [#427](https://github.com/pdm-project/pdm/issues/427)
- Improve type safety of `pdm.cli.actions` [#428](https://github.com/pdm-project/pdm/issues/428)
- Fix wrong mypy configuration. [#451](https://github.com/pdm-project/pdm/issues/451)


Release v1.5.2 (2021-04-27)
---------------------------

### Features & Improvements

- Allow `pdm use` with no argument given, which will list all available pythons for pick. [#409](https://github.com/pdm-project/pdm/issues/409)

### Bug Fixes

- Inform user to enable PEP 582 for development script to work. [#404](https://github.com/pdm-project/pdm/issues/404)
- Check the existence of pyenv shim Python interpreter before using it. [#406](https://github.com/pdm-project/pdm/issues/406)
- Fix a bug that executing `setup.py` failed for NameError. [#407](https://github.com/pdm-project/pdm/issues/407)
- Check before setting the PYTHONPATH environment variable for PEP582 [#410](https://github.com/pdm-project/pdm/issues/410)
- Fix development setup error. [#415](https://github.com/pdm-project/pdm/issues/415)

### Dependencies

- Update pip to 21.1 and fix compatibility issues. [#412](https://github.com/pdm-project/pdm/issues/412)


Release v1.5.1 (2021-04-22)
---------------------------

### Bug Fixes

- Make func translate_sections pure to avoid exporting requirements in random order. [#401](https://github.com/pdm-project/pdm/issues/401)
- Expand the variables in install requirements' attributes for build. [#402](https://github.com/pdm-project/pdm/issues/402)


Release v1.5.0 (2021-04-20)
---------------------------

### Features & Improvements

- Include dev dependencies by default for `install` and `sync` commands. Add a new option `--prod/--production` to exclude them. Improve the dependency selection logic to be more convenient to use — the more common the usage is, the shorter the command is. [#391](https://github.com/pdm-project/pdm/issues/391)

### Bug Fixes

- Enquote executable path to ensure generating valid scripts. [#387](https://github.com/pdm-project/pdm/issues/387)
- Consider hashes when fetching artifact link for build. [#389](https://github.com/pdm-project/pdm/issues/389)
- Considier the sources settings when building. [#399](https://github.com/pdm-project/pdm/issues/399)

### Improved Documentation

- New pdm setting `source-includes` to mark files to be included only in sdist builds. [#390](https://github.com/pdm-project/pdm/issues/390)

### Dependencies

- Update `pdm-pep517` to `0.7.0`; update `resolvelib` to` 0.7.0`. [#390](https://github.com/pdm-project/pdm/issues/390)

### Removals and Deprecations

- Deprecate the usage of `-d/--dev` option in `install` and `sync` commands. [#391](https://github.com/pdm-project/pdm/issues/391)


Release v1.5.0b1 (2021-04-12)
-----------------------------

### Features & Improvements

- Improve the env builder to run in isolated mode. [#384](https://github.com/pdm-project/pdm/issues/384)

### Bug Fixes

- Remove the incompatible code from the files that will be run in-process. [#375](https://github.com/pdm-project/pdm/issues/375)
- Get the correct Python ABI tag of selected interpreter [#378](https://github.com/pdm-project/pdm/issues/378)
- Error out when doing `pdm run` on a directory not initialized yet.
- Give warning message when the project automatically fallbacks to the global project.

### Dependencies

- Upgrade `resolvelib` to `0.6.0`. [#381](https://github.com/pdm-project/pdm/issues/381)

### Miscellany

- refactor `pdm.models.readers` to improve typing support [#321](https://github.com/pdm-project/pdm/issues/321)
- Add a basic integration test for cross-python check. [#377](https://github.com/pdm-project/pdm/issues/377)
- Refactor the `project.python_executable` to `project.python` that contains all info of the interpreter. [#382](https://github.com/pdm-project/pdm/issues/382)
- Continue refactoring Python info to extract to its own module. [#383](https://github.com/pdm-project/pdm/issues/383)
- Refactor the creation of project.


Release v1.5.0b0 (2021-04-03)
-----------------------------

### Features & Improvements

- Add hand-written zsh completion script. [#188](https://github.com/pdm-project/pdm/issues/188)
- Add a special value `:all` given to `-s/--section` to refer to all sections under the same species.
  Adjust `add`, `sync`, `install`, `remove` and `update` to support the new `dev-dependencies` groups. Old behavior will be kept the same. [#351](https://github.com/pdm-project/pdm/issues/351)
- `dev-dependencies` is now a table of dependencies groups, where key is the group name and value is an array of dependencies. These dependencies won't appear in the distribution's metadata. `dev-depedencies` of the old format will turn into `dev` group under `dev-dependencies`. [#351](https://github.com/pdm-project/pdm/issues/351)
- Move `dev-dependencies`, `includes`, `excludes` and `package-dir` out from `[project]` table to `[tool.pdm]` table. The migration will be done automatically if old format is detected. [#351](https://github.com/pdm-project/pdm/issues/351)
- Throws an error with meaningful message when no candidate is found for one requirement. [#357](https://github.com/pdm-project/pdm/issues/357)
- Support `--dry-run` option for `update` command to display packages that need update, install or removal. Add `--top` option to limit to top level packages only. [#358](https://github.com/pdm-project/pdm/issues/358)
- Full-featured completion scripts for Zsh and Powershell - section selection, package name autocompletion and so on. Windows is a first-class citizen! [#367](https://github.com/pdm-project/pdm/issues/367)
- Support non-interactive `init` command via `-n/--non-interactive` option. No question will be asked in this mode. [#368](https://github.com/pdm-project/pdm/issues/368)
- Show project packages path(PEP 582) in the output of `pdm info`, also add an option `--packages` to show that value only. [#372](https://github.com/pdm-project/pdm/issues/372)

### Bug Fixes

- Fix a bug that pure python libraries are not loaded to construct the WorkingSet. [#346](https://github.com/pdm-project/pdm/issues/346)
- Don't write `<script>-X.Y` variant to the bin folder. [#365](https://github.com/pdm-project/pdm/issues/365)
- Python is now run in isolated mode via subprocess to avoid accidentally importing user packages. [#369](https://github.com/pdm-project/pdm/issues/369)
- Don't overwrite existing dependencies when importing from requirements.txt. [#370](https://github.com/pdm-project/pdm/issues/370)

### Improved Documentation

- Add instructions of how to integrate PDM with Emacs, contributed by @linw1995. [#372](https://github.com/pdm-project/pdm/issues/372)

### Removals and Deprecations

- Remove the support of project path following `-g/--global` that was deprecated in `1.4.0`. One should use `-g -p <project_path>` for that purpose. [#361](https://github.com/pdm-project/pdm/issues/361)

### Miscellany

- Add test coverage to PDM. [#109](https://github.com/pdm-project/pdm/issues/109)
- Add type annotations into untyped functions to start using mypy. [#354](https://github.com/pdm-project/pdm/issues/354)
- Refactor the format converter code to be more explicit. [#360](https://github.com/pdm-project/pdm/issues/360)


Release v1.4.5 (2021-03-30)
---------------------------

### Features & Improvements

- Skip the first prompt of `pdm init` [#352](https://github.com/pdm-project/pdm/issues/352)

### Bug Fixes

- Fix a test failure when using homebrew installed python. [#348](https://github.com/pdm-project/pdm/issues/348)
- Get revision from the VCS URL if source code isn't downloaded to local. [#349](https://github.com/pdm-project/pdm/issues/349)

### Dependencies

- Update dependency `pdm-pep517` to `0.6.1`. [#353](https://github.com/pdm-project/pdm/issues/353)


Release v1.4.4 (2021-03-27)
---------------------------

### Features & Improvements

- Emit warning if version or description can't be retrieved when importing from flit metadata. [#342](https://github.com/pdm-project/pdm/issues/342)
- Add `type` argument to `pdm cache clear` and improve its UI. [#343](https://github.com/pdm-project/pdm/issues/343)
- Always re-install the editable packages when syncing the working set. This can help tracking the latest change of `entry-points`. [#344](https://github.com/pdm-project/pdm/issues/344)

### Bug Fixes

- Make installer quit early if a wheel isn't able to build. [#338](https://github.com/pdm-project/pdm/issues/338)

### Miscellany

- ignore type checking in `models.project_info.ProjectInfo`, which indexes `distlib.metadata._data` [#335](https://github.com/pdm-project/pdm/issues/335)


Release v1.4.3 (2021-03-24)
---------------------------

### Features & Improvements

- Change the group name of entry points from `pdm.plugins` to `pdm`.
  Export some useful objects and models for shorter import path. [#318](https://github.com/pdm-project/pdm/issues/318)
- Field `cmd` in `tools.pdm.scripts` configuration items now allows specifying an argument array instead of a string.
- Refactor: Remove the reference of `stream` singleton, improve the UI related code. [#320](https://github.com/pdm-project/pdm/issues/320)
- Support dependencies managed by poetry and flit being installed as editable packages. [#324](https://github.com/pdm-project/pdm/issues/324)
- Refactor: Extract the logic of finding interpreters to method for the sake of subclass overriding. [#326](https://github.com/pdm-project/pdm/issues/326)
- Complete the `cache` command, add `list`, `remove` and `info` subcommands. [#329](https://github.com/pdm-project/pdm/issues/329)
- Refactor: Unify the code about selecting interpreter to reduce the duplication. [#331](https://github.com/pdm-project/pdm/issues/331)
- Retrieve the version and description of a flit project by parsing the AST of the main file. [#333](https://github.com/pdm-project/pdm/issues/333)

### Bug Fixes

- Fix a parsing error when non-ascii characters exist in `pyproject.toml`. [#308](https://github.com/pdm-project/pdm/issues/308)
- Fix a bug that non-editable VCS candidates can't satisfy their requirements once locked in the lock file. [#314](https://github.com/pdm-project/pdm/issues/314)
- Fix a bug of import-on-init that fails when requirements.txt is detected. [#328](https://github.com/pdm-project/pdm/issues/328)

### Miscellany

- refactor `pdm.iostream` to improve 'typing' support [#301](https://github.com/pdm-project/pdm/issues/301)
- fix some typos [#323](https://github.com/pdm-project/pdm/issues/323)


Release v1.4.2 (2021-03-18)
---------------------------

### Features & Improvements

- Refactor the code, extract the version related logic from `specifiers.py` to a separated module. [#303](https://github.com/pdm-project/pdm/issues/303)

### Bug Fixes

- Fix a bug that get_dependencies() returns error when the `setup.py` has no `intall_requires` key. [#299](https://github.com/pdm-project/pdm/issues/299)
- Pin the VCS revision for non-editable VCS candidates in the lock file. [#305](https://github.com/pdm-project/pdm/issues/305)
- Fix a bug that editable build hits the cached wheel unexpectedly. [#307](https://github.com/pdm-project/pdm/issues/307)

### Miscellany

- replace 'typing comments' with type annotations throughout [#298](https://github.com/pdm-project/pdm/issues/298)


Release v1.4.1 (2021-03-12)
---------------------------

### Features & Improvements

- Support importing dependencies from requirements.txt to dev-dependencies or sections. [#291](https://github.com/pdm-project/pdm/issues/291)

### Bug Fixes

- Fallback to static parsing when building was failed to find the dependencies of a candidate. [#293](https://github.com/pdm-project/pdm/issues/293)
- Fix a bug that `pdm init` fails when `pyproject.toml` exists but has no `[project]` section. [#295](https://github.com/pdm-project/pdm/issues/295)

### Improved Documentation

- Document about how to use PDM with Nox. [#281](https://github.com/pdm-project/pdm/issues/281)


Release v1.4.0 (2021-03-05)
---------------------------

### Features & Improvements

- When `-I/--ignore-python` passed or `PDM_IGNORE_SAVED_PYTHON=1`, ignore the interpreter set in `.pdm.toml` and don't save to it afterwards. [#283](https://github.com/pdm-project/pdm/issues/283)
- A new option `-p/--project` is introduced to specify another path for the project base. It can also be combined with `-g/--global` option.
  The latter is changed to a flag only option that does not accept values. [#286](https://github.com/pdm-project/pdm/issues/286)
- Support `-f setuppy` for `pdm export` to export the metadata as setup.py [#289](https://github.com/pdm-project/pdm/issues/289)

### Bug Fixes

- Fix a bug that editable local package requirements cannot be parsed rightly. [#285](https://github.com/pdm-project/pdm/issues/285)
- Change the priority of metadata files to parse so that PEP 621 metadata will be parsed first. [#288](https://github.com/pdm-project/pdm/issues/288)

### Improved Documentation

- Add examples of how to integrate with CI pipelines (and tox). [#281](https://github.com/pdm-project/pdm/issues/281)


Release v1.3.4 (2021-03-01)
---------------------------

### Improved Documentation

- added documentation on a [task provider for vscode](https://marketplace.visualstudio.com/items?itemName=knowsuchagency.pdm-task-provider) [#280](https://github.com/pdm-project/pdm/issues/280)

### Bug Fixes

- Ignore the python requires constraints when fetching the link from the PyPI index.

Release v1.3.3 (2021-02-26)
---------------------------

### Bug Fixes

- Fix the requirement string of a VCS requirement to comply with PEP 508. [#275](https://github.com/pdm-project/pdm/issues/275)
- Fix a bug that editable packages with `src` directory can't be uninstalled correctly. [#277](https://github.com/pdm-project/pdm/issues/277)
- Fix a bug that editable package doesn't override the non-editable version in the working set. [#278](https://github.com/pdm-project/pdm/issues/278)


Release v1.3.2 (2021-02-25)
---------------------------

### Features & Improvements

- Abort and tell user the selected section following `pdm sync` or `pdm install` is not present in the error message. [#274](https://github.com/pdm-project/pdm/issues/274)

### Bug Fixes

- Fix a bug that candidates' sections cannot be retrieved rightly when circular dependencies exist. [#270](https://github.com/pdm-project/pdm/issues/270)
- Don't pass the help argument into the run script method. [#272](https://github.com/pdm-project/pdm/issues/272)


Release v1.3.1 (2021-02-19)
---------------------------

### Bug Fixes

- Use the absolute path when importing from a Poetry pyproject.toml. [#262](https://github.com/pdm-project/pdm/issues/262)
- Fix a bug that old toml table head is kept when converting to PEP 621 metadata format. [#263](https://github.com/pdm-project/pdm/issues/263)
- Postpone the evaluation of `requires-python` attribute when fetching the candidates of a package. [#264](https://github.com/pdm-project/pdm/issues/264)


Release v1.3.0 (2021-02-09)
---------------------------

### Features & Improvements

- Increase the default value of the max rounds of resolution to 1000, make it configurable. [#238](https://github.com/pdm-project/pdm/issues/238)
- Rewrite the project's `egg-info` directory when dependencies change. So that `pdm list --graph` won't show invalid entries. [#240](https://github.com/pdm-project/pdm/issues/240)
- When importing requirements from a `requirements.txt` file, build the package to find the name if not given in the URL. [#245](https://github.com/pdm-project/pdm/issues/245)
- When initializing the project, prompt user for whether the project is a library, and give empty `name` and `version` if not. [#253](https://github.com/pdm-project/pdm/issues/253)

### Bug Fixes

- Fix the version validator of wheel metadata to align with the implementation of `packaging`. [#130](https://github.com/pdm-project/pdm/issues/130)
- Preserve the `sections` value of a pinned candidate to be reused. [#234](https://github.com/pdm-project/pdm/issues/234)
- Strip spaces in user input when prompting for the python version to use. [#252](https://github.com/pdm-project/pdm/issues/252)
- Fix the version parsing of Python requires to allow `>`, `>=`, `<`, `<=` to combine with star versions. [#254](https://github.com/pdm-project/pdm/issues/254)


Release v1.2.0 (2021-01-26)
---------------------------

### Features & Improvements

- Change the behavior of `--save-compatible` slightly. Now the version specifier saved is using the REAL compatible operator `~=` as described in PEP 440. Before: `requests<3.0.0,>=2.19.1`, After: `requests~=2.19`. The new specifier accepts `requests==2.19.0` as compatible version. [#225](https://github.com/pdm-project/pdm/issues/225)
- Environment variable `${PROJECT_ROOT}` in the dependency specification can be expanded to refer to the project root in pyproject.toml.
  The environment variables will be kept as they are in the lock file. [#226](https://github.com/pdm-project/pdm/issues/226)
- Change the dependencies of a package in the lock file to a list of PEP 508 strings [#236](https://github.com/pdm-project/pdm/issues/236)

### Bug Fixes

- Ignore user's site and `PYTHONPATH`(with `python -I` mode) when executing pip commands. [#231](https://github.com/pdm-project/pdm/issues/231)

### Improved Documentation

- Document about how to activate and use a plugin. [#227](https://github.com/pdm-project/pdm/issues/227)

### Dependencies

- Test project on `pip 21.0`. [#235](https://github.com/pdm-project/pdm/issues/235)


Release v1.1.0 (2021-01-18)
---------------------------

### Features & Improvements

- Allow users to hide secrets from the `pyproject.toml`.
  - Dynamically expand env variables in the URLs in dependencies and indexes.
  - Ask whether to store the credentials provided by the user.
  - A user-friendly error will show when credentials are not provided nor correct. [#198](https://github.com/pdm-project/pdm/issues/198)
- Use a different package dir for 32-bit installation(Windows). [#212](https://github.com/pdm-project/pdm/issues/212)
- Auto disable PEP 582 when a venv-like python is given as the interpreter path. [#219](https://github.com/pdm-project/pdm/issues/219)
- Support specifying Python interpreter by `pdm use <path-to-python-root>`. [#221](https://github.com/pdm-project/pdm/issues/221)

### Bug Fixes

- Fix a bug of `PYTHONPATH` manipulation under Windows platform. [#215](https://github.com/pdm-project/pdm/issues/215)

### Removals and Deprecations

- Remove support of the old PEP 517 backend API path. [#217](https://github.com/pdm-project/pdm/issues/217)


Release v1.0.0 (2021-01-05)
---------------------------

### Bug Fixes

- Correctly build wheels for dependencies with build-requirements but without a specified build-backend [#213](https://github.com/pdm-project/pdm/issues/213)


Release v1.0.0b2 (2020-12-29)
-----------------------------

### Features & Improvements

- Fallback to pypi.org when `/search` endpoint is not available on given index. [#211](https://github.com/pdm-project/pdm/issues/211)

### Bug Fixes

- Fix a bug that PDM fails to parse python version specifiers with more than 3 parts. [#210](https://github.com/pdm-project/pdm/issues/210)


Release v1.0.0b0 (2020-12-24)
-----------------------------

### Features & Improvements

- Fully support of PEP 621 specification.
  - Old format is deprecated at the same time.
  - PDM will migrate the project file for you when old format is detected.
  - Other metadata formats(`Poetry`, `Pipfile`, `flit`) can also be imported as PEP 621 metadata. [#175](https://github.com/pdm-project/pdm/issues/175)
- Re-implement the `pdm search` to query the `/search` HTTP endpoint. [#195](https://github.com/pdm-project/pdm/issues/195)
- Reuse the cached built wheels to accelerate the installation. [#200](https://github.com/pdm-project/pdm/issues/200)
- Make update strategy and save strategy configurable in pdm config. [#202](https://github.com/pdm-project/pdm/issues/202)
- Improve the error message to give more insight on what to do when resolution fails. [#207](https://github.com/pdm-project/pdm/issues/207)
- Set `classifiers` dynamic in `pyproject.toml` template for autogeneration. [#209](https://github.com/pdm-project/pdm/issues/209)

### Bug Fixes

- Fix a bug that distributions are not removed clearly in parallel mode. [#204](https://github.com/pdm-project/pdm/issues/204)
- Fix a bug that python specifier `is_subset()` returns incorrect result. [#206](https://github.com/pdm-project/pdm/issues/206)


Release v0.12.3 (2020-12-21)
----------------------------

### Dependencies

- Pin `pdm-pep517` to `<0.3.0`, this is the last version to support legacy project metadata format.

Release v0.12.2 (2020-12-17)
----------------------------

### Features & Improvements

- Update the lock file schema, move the file hashes to `[metadata.files]` table. [#196](https://github.com/pdm-project/pdm/issues/196)
- Retry failed jobs when syncing packages. [#197](https://github.com/pdm-project/pdm/issues/197)

### Removals and Deprecations

- Drop `pip-shims` package as a dependency. [#132](https://github.com/pdm-project/pdm/issues/132)

### Miscellany

- Fix the cache path for CI. [#199](https://github.com/pdm-project/pdm/issues/199)


Release v0.12.1 (2020-12-14)
----------------------------

### Features & Improvements

- Provide an option to export requirements from pyproject.toml [#190](https://github.com/pdm-project/pdm/issues/190)
- For Windows users, `pdm --pep582` can enable PEP 582 globally by manipulating the WinReg. [#191](https://github.com/pdm-project/pdm/issues/191)

### Bug Fixes

- Inject `__pypackages__` into `PATH` env var during `pdm run`. [#193](https://github.com/pdm-project/pdm/issues/193)


Release v0.12.0 (2020-12-08)
----------------------------

### Features & Improvements

- Improve the user experience of `pdm run`:
  - Add a special key in tool.pdm.scripts that holds configurations shared by all scripts.
  - Support loading env var from a dot-env file.
  - Add a flag `-s/--site-packages` to include system site-packages when running. [#178](https://github.com/pdm-project/pdm/issues/178)
- Now PEP 582 can be enabled in the Python interpreter directly! [#181](https://github.com/pdm-project/pdm/issues/181)

### Bug Fixes

- Ensure `setuptools` is installed before invoking editable install script. [#174](https://github.com/pdm-project/pdm/issues/174)
- Require `wheel` not `wheels` for global projects [#182](https://github.com/pdm-project/pdm/issues/182)
- Write a `sitecustomize.py` instead of a `.pth` file to enable PEP 582. Thanks @Aloxaf.
  Update `get_package_finder()` to be compatible with `pip 20.3`. [#185](https://github.com/pdm-project/pdm/issues/185)
- Fix the help messages of commands "cache" and "remove" [#187](https://github.com/pdm-project/pdm/issues/187)


Release v0.11.0 (2020-11-20)
----------------------------

### Features & Improvements

- Support custom script shortcuts in `pyproject.toml`.
  - Support custom script shortcuts defined in `[tool.pdm.scripts]` section.
  - Add `pdm run --list/-l` to show the list of script shortcuts. [#168](https://github.com/pdm-project/pdm/issues/168)
- Patch the halo library to support parallel spinners.
- Change the looking of `pdm install`. [#169](https://github.com/pdm-project/pdm/issues/169)

### Bug Fixes

- Fix a bug that package's marker fails to propagate to its grandchildren if they have already been resolved. [#170](https://github.com/pdm-project/pdm/issues/170)
- Fix a bug that bare version specifiers in Poetry project can't be converted correctly. [#172](https://github.com/pdm-project/pdm/issues/172)
- Fix the build error that destination directory is not created automatically. [#173](https://github.com/pdm-project/pdm/issues/173)


Release v0.10.2 (2020-11-05)
----------------------------

### Bug Fixes

- Building editable distribution does not install `build-system.requires` anymore. [#167](https://github.com/pdm-project/pdm/issues/167)


Release v0.10.1 (2020-11-04)
----------------------------

### Bug Fixes

- Switch the PEP 517 build frontend from `build` to a home-grown version. [#162](https://github.com/pdm-project/pdm/issues/162)
- Synchronize the output of `LogWrapper`. [#164](https://github.com/pdm-project/pdm/issues/164)
- Fix a bug that `is_subset` and `is_superset` may return wrong result when wildcard excludes overlaps with the upper bound. [#165](https://github.com/pdm-project/pdm/issues/165)


Release v0.10.0 (2020-10-20)
----------------------------

### Features & Improvements

- Change to Git style config command. [#157](https://github.com/pdm-project/pdm/issues/157)
- Add a command to generate scripts for autocompletion, which is backed by `pycomplete`. [#159](https://github.com/pdm-project/pdm/issues/159)

### Bug Fixes

- Fix a bug that `sitecustomize.py` incorrectly gets injected into the editable console scripts. [#158](https://github.com/pdm-project/pdm/issues/158)


Release v0.9.2 (2020-10-13)
---------------------------

### Features & Improvements

- Cache the built wheels to accelerate resolution and installation process. [#153](https://github.com/pdm-project/pdm/issues/153)

### Bug Fixes

- Fix a bug that no wheel is matched when finding candidates to install. [#155](https://github.com/pdm-project/pdm/issues/155)
- Fix a bug that installation in parallel will cause encoding initialization error on Ubuntu. [#156](https://github.com/pdm-project/pdm/issues/156)


Release v0.9.1 (2020-10-13)
---------------------------

### Features & Improvements

- Display plain text instead of spinner bar under verbose mode. [#150](https://github.com/pdm-project/pdm/issues/150)

### Bug Fixes

- Fix a bug that the result of `find_matched()` is exhausted when accessed twice. [#149](https://github.com/pdm-project/pdm/issues/149)


Release v0.9.0 (2020-10-08)
---------------------------

### Features & Improvements

- Allow users to combine several dependency sections to form an extra require. [#131](https://github.com/pdm-project/pdm/issues/131)
- Split the PEP 517 backend to its own(battery included) package. [#134](https://github.com/pdm-project/pdm/issues/134)
- Add a new option to list command to show reverse dependency graph. [#137](https://github.com/pdm-project/pdm/issues/137)

### Bug Fixes

- Fix a bug that spaces in path causes requirement parsing error. [#138](https://github.com/pdm-project/pdm/issues/138)
- Fix a bug that requirement's python constraint is not respected when resolving. [#141](https://github.com/pdm-project/pdm/issues/141)

### Dependencies

- Update `pdm-pep517` to `0.2.0` that supports reading version from SCM. [#146](https://github.com/pdm-project/pdm/issues/146)

### Miscellany

- Add Python 3.9 to the CI version matrix to verify. [#144](https://github.com/pdm-project/pdm/issues/144)


Release v0.8.7 (2020-09-04)
---------------------------

### Bug Fixes

- Fix a compatibility issue with `wheel==0.35`. [#135](https://github.com/pdm-project/pdm/issues/135)


Release v0.8.6 (2020-07-09)
---------------------------

### Bug Fixes

- Fix a bug that extra sources are not respected when fetching distributions. [#127](https://github.com/pdm-project/pdm/issues/127)


Release v0.8.5 (2020-06-24)
---------------------------

### Bug Fixes

- Fix a bug that `pdm export` fails when the project doesn't have `name` property. [#126](https://github.com/pdm-project/pdm/issues/126)

### Dependencies

- Upgrade dependency `pip` to `20.1`. [#125](https://github.com/pdm-project/pdm/issues/125)


Release v0.8.4 (2020-05-21)
---------------------------

### Features & Improvements

- Add a new command `export` to export to alternative formats. [#117](https://github.com/pdm-project/pdm/issues/117)

### Miscellany

- Add Dockerfile and pushed to Docker Hub. [#122](https://github.com/pdm-project/pdm/issues/122)


Release v0.8.3 (2020-05-15)
---------------------------

### Bug Fixes

- Fix the version constraint parsing of wheel metadata. [#120](https://github.com/pdm-project/pdm/issues/120)


Release v0.8.2 (2020-05-03)
---------------------------

### Bug Fixes

- Update resolvers to `resolvelib` 0.4.0. [#118](https://github.com/pdm-project/pdm/issues/118)


Release v0.8.1 (2020-04-22)
---------------------------

### Dependencies

- Switch to upstream `resolvelib 0.3.0`. [#116](https://github.com/pdm-project/pdm/issues/116)


Release v0.8.0 (2020-04-20)
---------------------------

### Features & Improvements

- Add a new command to search for packages [#111](https://github.com/pdm-project/pdm/issues/111)
- Add `show` command to show package metadata. [#114](https://github.com/pdm-project/pdm/issues/114)

### Bug Fixes

- Fix a bug that environment markers cannot be evaluated correctly if extras are connected with "or". [#107](https://github.com/pdm-project/pdm/issues/107)
- Don't consult PyPI JSON API by default for package metadata. [#112](https://github.com/pdm-project/pdm/issues/112)
- Eliminate backslashes in markers for TOML documents. [#115](https://github.com/pdm-project/pdm/issues/115)


Release v0.7.1 (2020-04-13)
---------------------------

### Bug Fixes

- Editable packages requires `setuptools` to be installed in the isolated environment.

Release v0.7.0 (2020-04-12)
---------------------------

### Features & Improvements

- Disable loading of site-packages under PEP 582 mode. [#100](https://github.com/pdm-project/pdm/issues/100)

### Bug Fixes

- Fix a bug that TOML parsing error is not correctly captured. [#101](https://github.com/pdm-project/pdm/issues/101)
- Fix a bug of building wheels with C extensions that the platform in file name is incorrect. [#99](https://github.com/pdm-project/pdm/issues/99)


Release v0.6.5 (2020-04-07)
---------------------------

### Bug Fixes

- Unix style executable script suffix is missing.


Release v0.6.4 (2020-04-07)
---------------------------

### Features & Improvements

- Update shebang lines in the executable scripts when doing `pdm use`. [#96](https://github.com/pdm-project/pdm/issues/96)
- Auto-detect commonly used venv directories. [#97](https://github.com/pdm-project/pdm/issues/97)


Release v0.6.3 (2020-03-30)
---------------------------

### Bug Fixes

- Fix a bug of moving files across different file system. [#95](https://github.com/pdm-project/pdm/issues/95)


Release v0.6.2 (2020-03-29)
---------------------------

### Bug Fixes

- Validate user input for `python_requires` when initializing project. [#89](https://github.com/pdm-project/pdm/issues/89)
- Ensure `wheel` package is available before building packages. [#90](https://github.com/pdm-project/pdm/issues/90)
- Fix an issue of remove command that will unexpectedly uninstall packages in default section. [#92](https://github.com/pdm-project/pdm/issues/92)

### Dependencies

- Update dependencies `pythonfinder`, `python-cfonts`, `pip-shims` and many others.
  Drop dependency `vistir`. [#89](https://github.com/pdm-project/pdm/issues/89)


Release v0.6.1 (2020-03-25)
---------------------------

### Features & Improvements

- Redirect output messages to log file for installation and locking. [#84](https://github.com/pdm-project/pdm/issues/84)

### Bug Fixes

- Fix a bug that parallel installation fails due to setuptools reinstalling. [#83](https://github.com/pdm-project/pdm/issues/83)


Release v0.6.0 (2020-03-20)
---------------------------

### Features & Improvements

- Support specifying build script for C extensions. [#23](https://github.com/pdm-project/pdm/issues/23)
- Add test cases for `pdm build`. [#81](https://github.com/pdm-project/pdm/issues/81)
- Make it configurable whether to consult PyPI JSON API since it may be not trustable.
- Support parallel installation.
- Add new command `pmd import` to import project metadata from `Pipfile`, `poetry`, `flit`, `requirements.txt`.
  [#79](https://github.com/pdm-project/pdm/issues/79)
- `pdm init` and `pdm install` will auto-detect possible files that can be imported.

### Bug Fixes

- Fix wheel builds when `package_dir` is mapped. [#81](https://github.com/pdm-project/pdm/issues/81)
- `pdm init` will use the current directory rather than finding the parents when
global project is not activated.


Release v0.5.0 (2020-03-14)
---------------------------

### Features & Improvements

- Introduce a super easy-to-extend plug-in system to PDM. [#75](https://github.com/pdm-project/pdm/issues/75)

### Improved Documentation

- Documentation on how to write a plugin. [#75](https://github.com/pdm-project/pdm/issues/75)

### Bug Fixes

- Fix a typo in metadata parsing from `plugins` to `entry_points`


Release v0.4.2 (2020-03-13)
---------------------------

### Features & Improvements

- Refactor the CLI part, switch from `click` to `argparse`, for better extensibility. [#73](https://github.com/pdm-project/pdm/issues/73)
- Allow users to configure to install packages into venv when it is activated. [#74](https://github.com/pdm-project/pdm/issues/74)


Release v0.4.1 (2020-03-11)
---------------------------

### Features & Improvements

- Add a minimal dependency set for global project. [#72](https://github.com/pdm-project/pdm/issues/72)


Release v0.4.0 (2020-03-10)
---------------------------

### Features & Improvements

- Global project support
  - Add a new option `-g/--global` to manage global project. The default location is at `~/.pdm/global-project`.
  - Use the virtualenv interpreter when detected inside an activated venv.
  - Add a new option `-p/--project` to select project root other than the default one. [#30](https://github.com/pdm-project/pdm/issues/30)
- Add a new command `pdm config del` to delete an existing config item. [#71](https://github.com/pdm-project/pdm/issues/71)

### Bug Fixes

- Fix a URL parsing issue that username will be dropped in the SSH URL. [#68](https://github.com/pdm-project/pdm/issues/68)

### Improved Documentation

- Add docs for global project and selecting project path. [#30](https://github.com/pdm-project/pdm/issues/30)


Release v0.3.2 (2020-03-08)
---------------------------

### Features & Improvements

- Display all available Python interpreters if users don't give one in `pdm init`. [#67](https://github.com/pdm-project/pdm/issues/67)

### Bug Fixes

- Regard `4.0` as infinite upper bound when checking subsetting. [#66](https://github.com/pdm-project/pdm/issues/66)


Release v0.3.1 (2020-03-07)
---------------------------

### Bug Fixes

- Fix a bug that `ImpossiblePySpec`'s hash clashes with normal one.


Release v0.3.0 (2020-02-28)
---------------------------

### Features & Improvements

- Add a new command `pdm config` to inspect configurations. [#26](https://github.com/pdm-project/pdm/issues/26)
- Add a new command `pdm cache clear` to clean caches. [#63](https://github.com/pdm-project/pdm/issues/63)

### Bug Fixes

- Correctly show dependency graph when circular dependencies exist. [#62](https://github.com/pdm-project/pdm/issues/62)

### Improved Documentation

- Write the initial documentation for PDM. [#14](https://github.com/pdm-project/pdm/issues/14)


Release v0.2.6 (2020-02-25)
---------------------------

### Features & Improvements

- Improve the user interface of selecting Python interpreter. [#54](https://github.com/pdm-project/pdm/issues/54)

### Bug Fixes

- Fix the wheel installer to correctly unparse the flags of console scripts. [#56](https://github.com/pdm-project/pdm/issues/56)
- Fix a bug that OS-dependent hashes are not saved. [#57](https://github.com/pdm-project/pdm/issues/57)


Release v0.2.5 (2020-02-22)
---------------------------

### Features & Improvements

- Allow specifying Python interpreter via `--python` option in `pdm init`. [#49](https://github.com/pdm-project/pdm/issues/49)
- Set `python_requires` when initializing and defaults to `>={current_version}`. [#50](https://github.com/pdm-project/pdm/issues/50)

### Bug Fixes

- Always consider wheels before tarballs; correctly merge markers from different parents. [#47](https://github.com/pdm-project/pdm/issues/47)
- Filter out incompatible wheels when installing. [#48](https://github.com/pdm-project/pdm/issues/48)


Release v0.2.4 (2020-02-21)
---------------------------

### Bug Fixes

- Use the project local interpreter to build wheels. [#43](https://github.com/pdm-project/pdm/issues/43)
- Correctly merge Python specifiers when possible. [#4](https://github.com/pdm-project/pdm/issues/4)


Release v0.2.3 (2020-02-21)
---------------------------

### Bug Fixes

- Fix a bug that editable build generates a malformed `setup.py`.


Release v0.2.2 (2020-02-20)
---------------------------

### Features & Improvements

- Add a fancy greeting banner when user types `pdm --help`. [#42](https://github.com/pdm-project/pdm/issues/42)

### Bug Fixes

- Fix the RECORD file in built wheel. [#41](https://github.com/pdm-project/pdm/issues/41)

### Dependencies

- Add dependency `python-cfonts` to display banner. [#42](https://github.com/pdm-project/pdm/issues/42)


Release v0.2.1 (2020-02-18)
---------------------------

### Bug Fixes

- Fix a bug that short python_version markers can't be parsed correctly. [#38](https://github.com/pdm-project/pdm/issues/38)
- Make `_editable_intall.py` compatible with Py2.


Release v0.2.0 (2020-02-14)
---------------------------

### Features & Improvements

- New option: `pdm list --graph` to show a dependency graph of the working set. [#10](https://github.com/pdm-project/pdm/issues/10)
- New option: `pdm update --unconstrained` to ignore the version constraint of given packages. [#13](https://github.com/pdm-project/pdm/issues/13)
- Improve the error message when project is not initialized before running commands. [#19](https://github.com/pdm-project/pdm/issues/19)
- Pinned candidates in lock file are reused when relocking during `pdm install`. [#33](https://github.com/pdm-project/pdm/issues/33)
- Use the pyenv interpreter value if pyenv is installed. [#36](https://github.com/pdm-project/pdm/issues/36)
- Introduce a new command `pdm info` to show project environment information. [#9](https://github.com/pdm-project/pdm/issues/9)

### Bug Fixes

- Fix a bug that candidate hashes will be lost when reused. [#11](https://github.com/pdm-project/pdm/issues/11)

### Dependencies

- Update `pip` to `20.0`, update `pip_shims` to `0.5.0`. [#28](https://github.com/pdm-project/pdm/issues/28)

### Miscellany

- Add a script named `setup_dev.py` for the convenience to setup pdm for development. [#29](https://github.com/pdm-project/pdm/issues/29)


Release v0.1.2 (2020-02-09)
---------------------------

### Features

- New command pdm use to switch python versions. [#8](https://github.com/pdm-project/pdm/issues/8)
- New option pdm list --graph to show a dependency graph. [#10](https://github.com/pdm-project/pdm/issues/10)
- Read metadata from lockfile when pinned candidate is reused.

Release v0.1.1 (2020-02-07)
---------------------------

### Features

- Get version from the specified file. [#6](https://github.com/pdm-project/pdm/issues/6)
- Add column header to pdm list output.

Release v0.1.0 (2020-02-07)
---------------------------

### Bugfixes

- Pass exit code to parent process in pdm run.
- Fix error handling for CLI. [#19](https://github.com/pdm-project/pdm/issues/19)

### Miscellany

- Refactor the installer mocking for tests.

Release v0.0.5 (2020-01-22)
---------------------------

### Improvements

- Ensure pypi index url is fetched in addition to the source settings. [#3](https://github.com/pdm-project/pdm/issues/3)

### Bugfixes

- Fix an issue that leading "c"s are mistakenly stripped. [#5](https://github.com/pdm-project/pdm/issues/5)
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

- Add a Chinese README

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
- A neat CLI.
- add, lock, list, update, remove commands.
- PEP 517 build backends.
- Continuous Integration.
