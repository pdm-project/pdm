# Write a plugin

PDM is aiming at being a community driven package manager.
It is shipped with a full-featured plug-in system, with which you can:

- Develop a new command for PDM
- Add additional options to existing PDM commands
- Change PDM's behavior by reading additional config items
- Control the process of dependency resolution or installation

## What should a plugin do

The core PDM project focuses on dependency management and package publishing. Other
functionalities you wish to integrate with PDM are preferred to lie in their own plugins
and released as standalone PyPI projects. In case the plugin is considered a good supplement
of the core project it may have a chance to be absorbed into PDM.

## Write your own plugin

In the following sections, I will show an example of adding a new command `hello` which reads the `hello.name` config.

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

First, let's create a new `HelloCommand` class inheriting from `pdm.cli.commands.base.BaseCommand`. It has two major functions:

- `add_arguments()` to manipulate the argument parser passed as the only argument,
  where you can add additional command line arguments to it
- `handle()` to do something when the subcommand is matched, you can do nothing by writing a single `pass` statement.
  It accepts two arguments: an `pdm.project.Project` object as the first one and the parsed `argparse.Namespace` object as the second.

The document string will serve as the command help text, which will be shown in `pdm --help`.

Besides, PDM's subcommand has two default options: `-v/--verbose` to change the verbosity level and `-g/--global` to enable global project.
If you don't want these default options, override the `arguments` class attribute to a list of `pdm.cli.options.Option` objects, or
assign it to an empty list to have no default options:

```python hl_lines="3"
class HelloCommand(BaseCommand):

    arguments = []
```

!!! note
    The default options are loaded first, then `add_arguments()` is called.

### Register the command to the core object

Write a function somewhere in your plugin project. There is no limit on what the name of the function is,
but the function should take only one argument -- the PDM core object:

```python hl_lines="2"
def hello_plugin(core):
    core.register_command(HelloCommand, "hello")
```

Call `core.register_command()` to register the command. The second argument as the name of the subcommand is optional.
PDM will look for the `HelloCommand`'s `name` attribute if the name is not passed.

### Add a new config item

Let's recall the first code snippet, `hello.name` config key is consulted for the name if not passed via the command line.

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

Besides of commands and configurations, the `core` object exposes some other methods and attributes to override.
PDM also provides some signals you can listen to.
Please read the [API reference](reference.md) for more details.

### Tips about developing a PDM plugin.

When developing a plugin, one hopes to activate and plugin in development and get updated when the code changes. This is usually done
by `pip install -e .` or `python setup.py develop` in the **traditional** Python packaging world which leverages `setup.py` to do so. However,
as there is no such `setup.py` in a PDM project, how can we do that?

Fortunately, it becomes even easier with PDM and PEP 582. First, you should enable PEP 582 globally following the
[corresponding part of this doc](../index.md#enable-pep-582-globally). Then you just need to install all dependencies into the `__pypackages__` directory by:

```bash
pdm install
```

After that, all the dependencies are available with a compatible Python interpreter, including the plugin itself, in editable mode. That means any change
to the codebase will take effect immediately without re-installation. The `pdm` executable also uses a Python interpreter under the hood,
so if you run `pdm` from inside the plugin project, the plugin in development will be activated automatically, and you can do some testing to see how it works.
That is how PEP 582 benefits our development workflow.

## Publish your plugin

Now you have defined your plugin already, let's distribute it to PyPI. PDM's plugins are discovered by entry point types.
Create an `pdm` entry point and point to your plugin callable (yeah, it doesn't need to be a function, any callable object can work):

**PEP 621**:

```toml
# pyproject.toml

[project.entry-points.pdm]
hello = "my_plugin:hello_plugin"
```

**setuptools**:

```python
# setup.py

setup(
    ...
    entry_points={"pdm": ["hello = my_plugin:hello_plugin"]}
    ...
)
```

## Activate the plugin

As plugins are loaded via entry points, they can be activated with no more steps than just installing the plugin.
For convenience, PDM provides a `plugin` command group to manage plugins.

Assume your plugin is published as `pdm-hello`:

```bash
pdm plugin add pdm-hello
```

Now type `pdm --help` in the terminal, you will see the new added `hello` command and use it:

```bash
$ pdm hello Jack
Hello, Jack
```

See more plugin management subcommands by typing `pdm plugin --help` in the terminal.
