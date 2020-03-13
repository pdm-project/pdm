# Write a plugin

PDM is aiming at being a community driven package manager.
It is shipped with a full-featured and plug-in system, with which you can:

- Develop a new command for PDM
- Add additional options to existing PDM commands
- Change PDM's behavior by reading additional config items
- Control the process of dependency resolution or installation

## What should a plugin do

The core PDM project focuses on dependency management and package publishment. Other
functionalities you wish to integrate with PDM are preferred to lie in their own plugins
and released as standalone PyPI projects. In case the plugin is considered a good suplement
of the core project it may have a chance to be absorbed into PDM.

## Write your own plugin

In the following sections, I will show an example of adding a new command `hello` which reads `hello.name` config.

### Write the command

The PDM's CLI module is designed in a way that user can easily "inherit and modify". To write a new command:

```python
from pdm.cli.commands.base import BaseCommand

class HelloCommand(BaseCommand):
    """Say hello to the specified person.
    If none is given, will read from "hello.name" config.
    """

    def add_arguments(self, parser):
        parser.add_argument("-n", "--name", help="the person's name to whom you greet")

    def handle(self, project, options):
        if not options.name:
            name = project.config["hello.name"]
        else:
            name = options.name
        print(f"Hello, {name}")
```

First create a new `HelloCommand` class inherting from `pdm.cli.commands.base.BaseCommand`, it has two major functions:

- `add_arguments()` to manipulate the argument parser passed as the only argument,
  where you can add additional command line arguments to it
- `handle()` to do something when the subcommand is matched, you can do nothing by writing a single `pass` statement.
  It accepts two arguments: an `pdm.project.Project` object as the first one and the parsed `argparse.Namespace` object as the second.

The document string will serve as the command help text, which will be show in `pdm --help`.

Besides, PDM's subcommand has two default options: `-v/--verbose` to change the verbosity level and `-g/--global` to enable global project.
If you don't want these default options, override the `arguments` class attribute to a list of `pdm.cli.options.Option` objects.
Assign it to an empty list to have no default options:

```python hl_lines="3"
class HelloCommand(BaseCommand):

    arguments = []
```

!!! note
    The default options are loaded first, then `add_arguments()` is called.

### Register the command to the core object

Write a function somewhere in your plugin project. There is no limit on what the name of the function is. The function
should accept only one argument -- the PDM core object:

```python hl_lines="2"
def hello_plugin(core):
    core.register_command(HelloCommand, "hello")
```

Call `core.register_command()` to register the command, the second argument as the name of the subcommand is optional.
PDM will look for the `HelloCommand`'s `name` attribute if the name is not passed.

### Add a new config item

Remember in the first code snippet, `hello.name` config key is consulted for the name if not passed via the command line.

```python hl_lines="11"
class HelloCommand(BaseCommand):
    """Say hello to the specified person.
    If none is given, will read from "hello.name" config.
    """

    def add_arguments(self, parser):
        parser.add_argument("-n", "--name", help="the person's name to whom you greet")

    def handle(self, project, options):
        if not options.name:
            name = project.config["hello.name"]
        else:
            name = options.name
        print(f"Hello, {name}")
```

Till now, if you query the config value by `pdm config get hello.name`, an error will pop up saying it is not a valid config key.
You need to register the config item, too:

```python hl_lines="5"
from pdm.project.config import ConfigItem

def hello_plugin(core):
    core.register_command(HelloCommand, "hello")
    core.add_config("hello.name", ConfigItem("The person's name", "John"))
```

where `ConfigItem` class takes 4 parameters, in the following order:

- `description`: a description of the config item
- `default`: default value of the config item
- `global_only`: whether the config is allowed to set in home config only
- `env_var`: the name of environment variable which will be read as the config value

### Other plugin points

Besides commands and configurations, PDM provides some other plugin abilities
which are not covered in the above example:

- `core.project_class`: change the class of project object
- `core.repository_class`: change the class of repository object, which controls how to look for candidates and metadata of a package
- `core.resolver_class`: change the resolver class, to control the resolution process
- `core.synchronizer_class`: change the synchronizer_class, to control the installation process
- `core.parser = None`: add arguments to the **root** argument parser

## Publish your plugin

Now you have defined your plugin already, let's distribute it to PyPI. PDM's plugins are discovered by entry point types.
Create an `pdm.plugin` entry point and point to your plugin callable(yeah, it don't need to be a function, any callable object can work):

**setuptools**:

```python
# setup.py

setup(
    ...
    entry_points={"pdm.plugin": ["hello = my_plugin:hello_plugin"]}
    ...
)
```

**PDM**:

```toml
# pyproject.toml

[tool.pdm.entry_points."pdm.plugin"]
hello = "my_plugin:hello_plugin"
```
