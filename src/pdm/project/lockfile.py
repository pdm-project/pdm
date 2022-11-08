from pdm.project.toml_file import TOMLBase


class Lockfile(TOMLBase):
    spec_version = "4.1"

    @property
    def hash(self) -> str:
        return self._data.get("metadata", {}).get("content_hash", "")

    @property
    def file_version(self) -> str:
        return self._data.get("metadata", {}).get("lock_version", "")

    def write(self, show_message: bool = True) -> None:
        super().write()
        if show_message:
            self.ui.echo(f"Changes are written to [success]{self._path.name}[/].")

    def __getitem__(self, key: str) -> dict:
        return self._data[key]
