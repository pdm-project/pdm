# Create Project From a Template

Similar to `yarn create` and `npm create`, PDM also supports initializing or creating a project from a template.
The template is given as a positional argument of `pdm init`, in one of the following forms:

- `pdm init django` - Initialize the project from the template `https://github.com/pdm-project/template-django`
- `pdm init https://github.com/frostming/pdm-template-django` - Initialize the project from a Git URL. Both HTTPS and SSH URL are acceptable.
- `pdm init django@v2` - To check out the specific branch or tag. Full Git URL also supports it.
- `pdm init /path/to/template` - Initialize the project from a template directory on local filesystem.
- `pdm init minimal` - Initialize with the builtin "minimal" template, that only generates a `pyproject.toml`.

And `pdm init` will use the default template built in.

The project will be initialized at the current directory, existing files with the same name will be overwritten. You can also use the `-p <path>` option to create a project at a new path.

## Contribute a template

According to the first form of the template argument, `pdm init <name>` will refer to the template repository located at `https://github.com/pdm-project/template-<name>`. To contribute a template, you can create a template repository and establish a request to transfer the
ownership to `pdm-project` organization(it can be found at the bottom of the repository settings page). The administrators of the organization will review the request and complete the subsequent steps. You will be added as the repository maintainer if the transfer is accepted.

## Requirements for a template

A template repository must be a pyproject-based project, which contains a `pyproject.toml` file with PEP-621 compliant metadata.
No other special config files are required.

## Project name replacement

On initialization, the project name in the template will be replaced by the name of the new project. This is done by a recursive full-text search and replace. The import name, which is derived from the project name by replacing all non-alphanumeric characters with underscores and lowercasing, will also be replaced in the same way.

For example, if the project name is `foo-project` in the template and you want to initialize a new project named `bar-project`, the following replacements will be made:

- `foo-project` -> `bar-project` in all `.md` files and `.rst` files
- `foo_project` -> `bar_project` in all `.py` files
- `foo_project` -> `bar_project` in the directory name
- `foo_project.py` -> `bar_project.py` in the file name

Therefore, we don't support name replacement if the import name isn't derived from the project name.

## Use other project generators

If you are seeking for a more powerful project generator, you can use [cookiecutter](https://github.com/cookiecutter/cookiecutter) via `--cookiecutter` option and [copier](https://github.com/copier-org/copier) via `--copier` option.

You need to install `cookiecutter` and `copier` respectively to use them. You can do this by running `pdm self add <package>`.
To use them:

```bash
pdm init --cookiecutter gh:cjolowicz/cookiecutter-hypermodern-python
# or
pdm init --copier gh:pawamoy/copier-pdm --UNSAFE
```
