# Lifecycle and hooks

As any Python deliverable, your project will go through the different phases
of a Python project lifecycle and PDM provides commands to perform the expected tasks for those phases.

It also provides hooks attached to these steps allowing for:

- plugins to listen to the [signals][pdm.signals] of the same name.
- developers to define custom scripts with the same name.

The built-in commands are currently split into 3 groups:

- the [initialization phase](#initialization)
- the [dependencies management](#dependencies-managment).
- the [publication phase](#publication).

You will most probably need to perform some recurrent tasks between the installation and publication phases (housekeeping, linting, testing, ...)
this is why PDM lets you define your own tasks/phases using [user scripts](#user-scripts).

To provides full flexibility, PDM allows to [skip some hooks and tasks](#skipping) on demand.

## Initialization

The initialization phase should occur only once in a project lifetime by running the [`pdm init`](cli_reference.md#exec-0--init)
command to initialize an existing project (prompt to fill the `pyproject.toml` file).

They trigger the following hooks:

- [`post_init`][pdm.signals.post_init]

```mermaid
flowchart LR
  subgraph pdm-init [pdm init]
    direction LR
    post-init{{Emit post_init}}
    init --> post-init
  end
```

## Dependencies management

The dependencies management is required for the developer to be able to work and perform the following:

- `lock`: compute a lock file from the `pyproject.toml` requirements.
- `sync`: synchronize (add/remove/update) PEP582 packages from the lock file and install the current project as editable.
- `add`: add a dependency
- `remove`: remove a dependency

All those steps are directly available with the following commands:

- [`pdm lock`](cli_reference.md#exec-0--lock): execute the `lock` task
- [`pdm sync`](cli_reference.md#exec-0--sync): execute the `sync` task
- [`pdm install`](cli_reference.md#exec-0--install): execute the `sync` task, preceded from `lock` if required
- [`pdm add`](cli_reference.md#exec-0--add): add a dependency requirement, re-lock and then sync
- [`pdm remove`](cli_reference.md#exec-0--remove): remove a dependency requirement, re-lock and then sync
- [`pdm update`](cli_reference.md#exec-0--update): re-lock dependencies from their latest versions and then sync

They trigger the following hooks:

- [`pre_install`][pdm.signals.pre_install]
- [`post_install`][pdm.signals.post_install]
- [`pre_lock`][pdm.signals.pre_lock]
- [`post_lock`][pdm.signals.post_lock]

```mermaid
flowchart LR
  subgraph pdm-install [pdm install]
    direction LR

    subgraph pdm-lock [pdm lock]
      direction TB
      pre-lock{{Emit pre_lock}}
      post-lock{{Emit post_lock}}
      pre-lock --> lock --> post-lock
    end

    subgraph pdm-sync [pdm sync]
      direction TB
      pre-install{{Emit pre_install}}
      post-install{{Emit post_install}}
      pre-install --> sync --> post-install
    end

    pdm-lock --> pdm-sync
  end
```

### Switching Python version

This is a special case in dependency management:
you can switch the current Python version using [`pdm use`](cli_reference.md#exec-0--use)
and it will emit the [`post_use`][pdm.signals.post_use] signal with the new Python interpreter.

```mermaid
flowchart LR
  subgraph pdm-use [pdm use]
    direction LR
    post-use{{Emit post_use}}
    use --> post-use
  end
```

## Publication

As soon as you are ready to publish your package/library, you will require the publication tasks:

- `build`: build/compile assets requiring it and package everything into a Python package (sdist, wheel)
- `upload`: upload/publish the package to a remote PyPI index

All those steps are available with the following commands:

- [`pdm build`](cli_reference.md#exec-0--build)
- [`pdm publish`](cli_reference.md#exec-0--publish)

They trigger the following hooks:

- [`pre_publish`][pdm.signals.pre_publish]
- [`post_publish`][pdm.signals.post_publish]
- [`pre_build`][pdm.signals.pre_build]
- [`post_build`][pdm.signals.post_build]


```mermaid
flowchart LR
  subgraph pdm-publish [pdm publish]
    direction LR
    pre-publish{{Emit pre_publish}}
    post-publish{{Emit post_publish}}

    subgraph pdm-build [pdm build]
      pre-build{{Emit pre_build}}
      post-build{{Emit post_build}}
      pre-build --> build --> post-build
    end

    %% subgraph pdm-upload [pdm upload]
    %%   pre-upload{{Emit pre_upload}}
    %%   post-upload{{Emit post_upload}}
    %%   pre-upload --> upload --> post-upload
    %% end

    pre-publish --> pdm-build --> upload --> post-publish
  end
```

Execution will stop at first failure, hooks included.

## User scripts

[User scripts are detailed in their own section](scripts.md) but you should know that:

- each user script can define a `pre_*` and `post_*` script, including composite scripts.
- each `run` execution will trigger the [`pre_run`][pdm.signals.pre_run] and [`post_run`][pdm.signals.post_run] hooks
- each script execution will trigger the [`pre_script`][pdm.signals.pre_script] and [`post_script`][pdm.signals.post_script] hooks

Given the following `scripts` definition:

```toml
[tool.pdm.scripts]
pre_script = ""
post_script = ""
pre_test = ""
post_test = ""
test = ""
pre_composite = ""
post_composite = ""
composite = {composite: ["test"]}
```

a `pdm run test` will have the following lifecycle:

```mermaid
flowchart LR
  subgraph pdm-run-test [pdm run test]
    direction LR
    pre-run{{Emit pre_run}}
    post-run{{Emit post_run}}
    subgraph run-test [test task]
      direction TB
      pre-script{{Emit pre_script}}
      post-script{{Emit post_script}}
      pre-test[Execute pre_test]
      post-test[Execute post_test]
      test[Execute test]

      pre-script --> pre-test --> test --> post-test --> post-script
    end

    pre-run --> run-test --> post-run
  end
```

while `pdm run composite` will have the following:

```mermaid
flowchart LR
  subgraph pdm-run-composite [pdm run composite]
    direction LR
    pre-run{{Emit pre_run}}
    post-run{{Emit post_run}}

    subgraph run-composite [composite task]
      direction TB
      pre-script-composite{{Emit pre_script}}
      post-script-composite{{Emit post_script}}
      pre-composite[Execute pre_composite]
      post-composite[Execute post_composite]

      subgraph run-test [test task]
        direction TB
        pre-script-test{{Emit pre_script}}
        post-script-test{{Emit post_script}}
        pre-test[Execute pre_test]
        post-test[Execute post_test]

        pre-script-test --> pre-test --> test --> post-test --> post-script-test
      end

      pre-script-composite --> pre-composite --> run-test --> post-composite --> post-script-composite
    end

     pre-run --> run-composite --> post-run
  end
```

## Skipping

It is possible to control which task and hook runs for any built-in command as well as custom user scripts
using the `--skip` option.

It accepts a comma-separated list of hooks/task names to skip
as well as the predefined `:all`, `:pre` and `:post` shortcuts
respectively skipping all hooks, all `pre_*` hooks and all `post_*` hooks.
You can also provide the skip list in `PDM_SKIP_HOOKS` environment variable
but it will be overridden as soon as the `--skip` parameter is provided.

Given the previous script block, running `pdm run --skip=:pre,post_test composite` will result in the following reduced lifecycle:

```mermaid
flowchart LR
  subgraph pdm-run-composite [pdm run composite]
    direction LR
    post-run{{Emit post_run}}

    subgraph run-composite [composite task]
      direction TB
      post-script-composite{{Emit post_script}}
      post-composite[Execute post_composite]

      subgraph run-test [test task]
        direction TB
        post-script-test{{Emit post_script}}

        test --> post-script-test
      end

      run-test --> post-composite --> post-script-composite
    end

     run-composite --> post-run
  end
```
