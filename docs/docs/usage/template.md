# Create Project From a Template

Similar to `yarn create` and `npm create`, PDM also supports initializing or creating a project from a template.
The template is given as a positional argument of `pdm init`, in one of the following forms:

- `pdm init flask` - Initialize the project from the template `https://github.com/pdm-project/template-flask`
- `pdm init https://github.com/frostming/pdm-template-flask` - Initialize the project from a Git URL. Both HTTPS and SSH URL are acceptable.
- `pdm init /path/to/template` - Initialize the project from a template directory on local filesystem.

And `pdm init` will use the default template built in.

The project will be initialized at the current directory, existing files with the same name will be overwritten. You can also use the `-p <path>` option to create a project at a new path.

## Contribute a template

According to the first form of the template argument, `pdm init <name>` will refer to the template repository located at `https://github.com/pdm-project/template-<name>`. To contribute a template, you can create a template repository and establish a request to transfer the
ownership to `pdm-project` organization(it can be found at the bottom of the repository settings page). The administrators of the organization will review the request and complete the subsequent steps. You will be added as the repository maintainer if the transfer is accepted.

## Requirements for a template

A template repository must be a pyproject-based project, which contains a `pyproject.toml` file with PEP-621 compliant metadata.
No other special config files are required.
