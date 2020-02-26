# Manage dependencies

PDM provides a bunch of handful commands to help manage your project and dependencies.
The following examples are run on Ubuntu 18.04, a few changes must be done if you are using Windows.

## Initialize a project

```bash
$ mkdir pdm-test && cd pdm-test
$ pdm init
```

Answer several questions asked by PDM and a `pyproject.toml` will be created for you in the project root:

```toml
[tool.pdm]
name = "pdm-test"
version = "0.0.0"
description = ""
author = "Frost Ming <mianghong@gmail.com>"
license = "MIT"
python_requires = ">=3.7"

[tool.pdm.dependencies]

[tool.pdm.dev-dependencies]
```

If `pyproject.toml` is already present, it will be updated with `tool.pdm` contents.

For details of the meaning of each field in `pyproject.toml`, please refer to [Project File](/pyproject).

## Add dependencies

```bash
$ pdm add requests
$ pdm add -d pytest
```

`pdm add` can be followed by one or several dependencies, and the dependency specification is described in
[PEP 508](https://www.python.org/dev/peps/pep-0508/).
There are two groups of dependencies: packages will be added to `[tool.pdm.dependencies]` by default or `[tool.pdm.dev-dependencies]`
if `-d/--dev` option is passed to the `pdm add` command.

PDM also allows custom dependency groups by providing `-s/--section <name>` option, and the dependencies will apear in
`[tool.pdm.<name>-dependencies]` in the project file, respectively.

After that, dependencies and sub-dependencies will be resolved properly and installed for you, you can view `pdm.lock` to see
the resolved result of all dependencies.

### Save version specifiers

If the package is given without a version specifier like `pdm add requests`. PDM provides three different behaviors of what version
specifier is saved for the dependency, which is given by `--save-<strategy>`(Assume `2.21.0` is the latest version that can be found
for the dependency):

- `compatible`: Save the compatible version specifier: `>=2.21.0,<3.0.0`(default).
- `exact`: Save the exact version specifier: `==2.21.0`.
- `wildcard`: Don't constrain version and leave the specifier to be wildcard: `*`.

## Update existing dependencies

To update all dependencies in the lock file:

```bash
$ pdm update
```

To update the specified package(s):
```bash
$ pdm update requests
```
### About update strategy
Similary, PDM also provides 2 different behaviors of updating dependencies and sub-dependencies，
which is given by `--update-<strategy>` option:

- `reuse`: Keep all locked dependencies except for those given in the command line.
- `eager`: Try to lock a newer version of the packages in command line and their recursive sub-dependencies
and keep other dependencies as they are.

## Remove existing dependencies

To remove existing dependencies from project file and the library directory:

```bash
$ pdm remove requests
```

## Synchronize the project packages with lock file

There are two similar commands to do this job with a slight difference:

- `pdm install` will check the lock file and relock if it mismatch with project file, then install.
- `pdm sync` install dependencies in the lock file and will error out if it doesn't exist.
Besides, `pdm sync` can also remove unneeded packages if `--clean` option is given.

## Show what packages are installed

Similar to `pip list`, you can list all packages installed in the packages directory:

```bash
$ pdm list
```
Or show a dependency graph by:
```
$ pdm list --graph
tempenv 0.0.0
└── click 7.0 [ required: <7.0.0,>=6.7 ]
black 19.10b0
├── appdirs 1.4.3 [ required: Any ]
├── attrs 19.3.0 [ required: >=18.1.0 ]
├── click 7.0 [ required: >=6.5 ]
├── pathspec 0.7.0 [ required: <1,>=0.6 ]
├── regex 2020.2.20 [ required: Any ]
├── toml 0.10.0 [ required: >=0.9.4 ]
└── typed-ast 1.4.1 [ required: >=1.4.0 ]
bump2version 1.0.0
```
