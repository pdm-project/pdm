# Contributing to PDM

First off, thanks for taking the time to contribute! Contributions include but are not restricted to:

- Reporting bugs
- Contributing to code
- Writing tests
- Writing documents

The following is a set of guidelines for contributing.

## A recommended flow of contributing to an Open Source project.

This guideline is for new beginners of OSS. If you are an experienced OSS developer, you can skip
this section.

1. First, fork this project to your own namespace using the fork button at the top right of the repository page.
2. Clone the **upstream** repository to local:
   ```bash
   $ git clone https://github.com/pdm-project/pdm.git
   # Or if you prefer SSH clone:
   $ git clone git@github.com:pdm-project/pdm.git
   ```
3. Add the fork as a new remote:
   ```bash
   $ git remote add fork https://github.com/yourname/pdm.git
   $ git fetch fork
   ```
   where `fork` is the remote name of the fork repository.

**ProTips:**
1. Don't modify code on the main branch, the main branch should always keep track of origin/main.

   To update main branch to date:
   ```bash
   $ git pull origin main
   # In rare cases that your local main branch diverges from the remote main:
   $ git fetch origin && git reset --hard main
   ```
2. Create a new branch based on the up-to-date main branch for new patches.
3. Create a Pull Request from that patch branch.

## Local development

To make sure the tests suites can run rightly, you need to install [Git LFS](https://git-lfs.github.com/), then
```bash
$ git lfs install
# If you have already cloned the repository, execute the below command as well.
$ git lfs pull
```

Then, you need to install base dependencies in a venv. Although PDM uses local package directory to install
dependencies, venv is still needed to start up PDM at the first time:

```bash
$ python setup_dev.py
```

Now, all dependencies are installed into local `__pypackages__` directory, which will be used for development
after this point. The `pdm` executable located at `__pypackages__/<VERSION>/bin` can be run directly from outside,
which is installed in editable mode, or you can use `python -m pdm` from inside the venv.

### Run tests

```bash
$ pdm run test
```

The test suite is still simple and requires to be supplied, please help write more test cases.

### Code style

PDM uses `pre-commit` for linting, you need to install `pre-commit` first, then:

```bash
$ pre-commit install
$ pdm run lint
```

PDM uses `black` coding style and `isort` for sorting import statements, if you are not following them,
the CI will fail, and your Pull Request will not be merged.


### Preview the documentation

If you do some changes to the `docs/` and you may want to preview the build result, simply do:

```bash
$ pdm run doc
```
