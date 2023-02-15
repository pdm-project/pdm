# Contributing to PDM

First off, thanks for taking the time to contribute! Contributions include but are not restricted to:

- Reporting bugs
- Contributing to code
- Writing tests
- Writing documentation

The following is a set of guidelines for contributing.

## A recommended flow of contributing to an Open Source project

This section is for beginners to OSS. If you are an experienced OSS developer, you can skip
this section.

1. First, fork this project to your own namespace using the fork button at the top right of the repository page.
2. Clone the **upstream** repository to local:
   ```bash
   git clone https://github.com/pdm-project/pdm.git
   # Or if you prefer SSH clone:
   git clone git@github.com:pdm-project/pdm.git
   ```
3. Add the fork as a new remote:
   ```bash
   git remote add fork https://github.com/yourname/pdm.git
   git fetch fork
   ```
   where `fork` is the remote name of the fork repository.

**ProTips:**

1. Don't modify code on the main branch, the main branch should always keep track of origin/main.

   To update main branch to date:

   ```bash
   git pull origin main
   # In rare cases that your local main branch diverges from the remote main:
   git fetch origin && git reset --hard main
   ```

2. Create a new branch based on the up-to-date main branch for new patches.
3. Create a Pull Request from that patch branch.

## Local development

We recommend working in a virtual environment.
Feel free to create a virtual environment with either the `venv` module or the `virtualenv` tool.
For example:

```bash
python -m venv .venv
. .venv/bin/activate  # linux
.venv/Scripts/activate  # windows
```

Make sure your `pip` is newer than `21.3` to install PDM in develop/editable mode.

```bash
python -m pip install -U "pip>=21.3"
python -m pip install -e .
```

Make sure PDM uses the virtual environment you just created:

```bash
pdm config -l python.use_venv true
pdm config -l venv.in_project true
```

Install PDM development dependencies:

```bash
pdm install
```

Now, all dependencies are installed into the Python environment you chose, which will be used for development after this point.

### Run tests

```bash
pdm run test
```

The test suite is still simple and needs expansion! Please help write more test cases.

!!! note
    You can also run your test suite against all supported Python version using `tox` with the `tox-pdm` plugin.
    You can either run it by yourself with:

    ```shell
    tox
    ```

    or from `pdm` with:

    ```shell
    pdm run tox
    ```

### Code style

PDM uses `pre-commit` for linting. Install `pre-commit` first, for example with pip or [pipx](https://github.com/pypa/pipx):

```bash
python -m pip install pre-commit
```

```bash
pipx install pre-commit
```

Then initialize `pre-commit`:

```bash
pre-commit install
```

You can now lint the code with:

```bash
pdm run lint
```

PDM uses `black` for code style and `isort` for sorting import statements. If you are not following them,
the CI will fail and your Pull Request will not be merged.

### News fragments

When you make changes such as fixing a bug or adding a feature, you must add a news fragment describing
your change. News fragments are placed in the `news/` directory, and should be named according to this pattern: `<issue_num>.<issue_type>.md` (e.g., `566.bugfix.md`).

#### Issue Types

- `feature`: Features and improvements
- `bugfix`: Bug fixes
- `refactor`: Code restructures
- `doc`: Added or improved documentation
- `dep`: Changes to dependencies
- `removal`: Removals or deprecations in the API
- `misc`: Miscellaneous changes that don't fit any of the other categories

The contents of the file should be a single sentence in the imperative
mood that describes your changes. (e.g., `Deduplicate the plugins list.` ) See entries in the [Change Log](/CHANGELOG.md) for more examples.

### Preview the documentation

If you make some changes to the `docs/` and you want to preview the build result, simply do:

```bash
pdm run doc
```

## Release

Once all changes are done and ready to release, you can preview the changelog contents by running:

```bash
pdm run release --dry-run
```

Make sure the next version and the changelog are as expected in the output.

Then cut a release on the **main** branch:

```bash
pdm run release
```

GitHub action will create the release and upload the distributions to PyPI.

Read more options about version bumping by `pdm run release --help`.
