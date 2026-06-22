# Workspaces

!!! warning "Experimental"
    Workspace support is experimental. The configuration format and command behavior may change in future releases.

!!! tip
    Added in 2.28.0.

PDM can manage a workspace made of a root project and multiple member projects under the same repository.
This is useful for monorepos where packages depend on each other and should be resolved from the local checkout.

## Configure a workspace

Workspace members are configured in the root project's `pyproject.toml`:

```toml
[tool.pdm.workspace]
members = ["packages/foo", "packages/bar", "tools/*"]
```

The `members` list accepts direct paths and glob patterns. Each matched member must be a directory with a `pyproject.toml` file.

Workspace members are treated as implicit editable dependencies of the workspace root. When the root project is locked,
member packages are resolved from the current checkout instead of from package indexes.

## Add a member

You can add a local subdirectory dependency from the workspace root:

```bash
pdm add packages/foo
```

If `packages/foo` is under the project root and contains a `pyproject.toml`, PDM also adds it to `[tool.pdm.workspace].members`.
The dependency is still recorded in the normal project dependency table, while the lock result uses the workspace member as an editable package.

You can also initialize a new project under an existing project:

```bash
pdm new packages/foo
```

When a project is initialized as a workspace member, PDM reuses the root project's `requires-python` default,
does not select a separate Python interpreter, does not write `.pdm-python`, and does not initialize a nested Git repository or `.gitignore`.

## Remove a member

To remove a workspace member, pass the member path:

```bash
pdm remove packages/foo
```

This removes the exact `packages/foo` entry from `[tool.pdm.workspace].members` and updates the root lock file.
PDM only removes exact path entries. It does not remove glob entries such as `packages/*`.

If the member is also listed as a normal dependency, removing the package name only removes that dependency line:

```bash
pdm remove foo
```

Use the member path when you want to remove the workspace membership itself.

## Locking and installing

Workspace members share the workspace root's environment and lock file. Running dependency-changing commands against a member
updates the root lock file unless a custom lock file is explicitly selected.

The following commands must be run from the workspace root:

- `pdm install`
- `pdm lock`
- `pdm sync`
- `pdm outdated`
- `pdm info`

Commands such as `pdm add`, `pdm remove`, `pdm update`, `pdm run`, `pdm build`, and `pdm publish` can still target a member project.

## Member dependencies

Workspace members can depend on each other by package name:

```toml
[project]
name = "foo"
version = "0.1.0"
dependencies = ["bar"]
```

If `bar` is another workspace member, PDM resolves it from the workspace checkout as an editable package.

## uv mode

When `use_uv` is enabled, PDM generates uv-compatible workspace metadata in the temporary `pyproject.toml` used for uv lock and sync operations.
PDM does not persist `[tool.uv.workspace]` into your root `pyproject.toml` when adding workspace members.

The temporary uv configuration uses uv workspace sources:

```toml
[tool.uv.workspace]
members = ["packages/foo"]

[tool.uv.sources]
foo = { workspace = true }
```

See [Use uv](./uv.md) for the general limitations of uv mode.
