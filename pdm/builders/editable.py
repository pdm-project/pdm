import os

from pdm.builders.base import Builder


class EditableBuilder(Builder):
    def build(self, build_dir: str, **kwargs) -> str:
        # Ignore destination since editable builds should be build locally
        ireq = self.ireq
        self.ensure_setup_py()
        # XXX: Disable PEP 517 temporarily since it doesn't support editable build yet.
        temp = ireq.use_pep517
        ireq.use_pep517 = False
        # Builds the egg-info in place.
        ireq.prepare_metadata()
        ireq.use_pep517 = temp
        return os.path.join(build_dir, ireq.metadata_directory)
