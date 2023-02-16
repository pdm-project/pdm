from __future__ import annotations

import email
import email.message
import email.policy
import hashlib
import io
import os
import re
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from typing import IO, Any, cast

from unearth.preparer import has_leading_dir, split_leading_dir

from pdm.exceptions import PdmUsageError, ProjectError
from pdm.termui import logger
from pdm.utils import normalize_name

DIST_EXTENSIONS = {
    ".whl": "bdist_wheel",
    ".tar.bz2": "sdist",
    ".tar.gz": "sdist",
    ".zip": "sdist",
}
wheel_file_re = re.compile(
    r"""^(?P<namever>(?P<name>.+?)(-(?P<ver>\d.+?))?)
        ((-(?P<build>\d.*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)
        \.whl|\.dist-info)$""",
    re.VERBOSE,
)


def parse_metadata(fp: IO[bytes]) -> email.message.Message:
    return email.message_from_file(io.TextIOWrapper(fp, encoding="utf-8", errors="surrogateescape"))


@dataclass
class PackageFile:
    """A distribution file for upload.

    XXX: currently only supports sdist and wheel.
    """

    filename: str
    metadata: email.message.Message
    comment: str | None
    py_version: str | None
    filetype: str

    def __post_init__(self) -> None:
        self.base_filename = os.path.basename(self.filename)
        self.gpg_signature: tuple[str, bytes] | None = None

    def get_hashes(self) -> dict[str, str]:
        hashers = {"sha256_digest": hashlib.sha256()}
        try:
            hashers["md5_digest"] = hashlib.md5()
        except ValueError:
            pass
        try:
            hashers["blake2_256_digest"] = hashlib.blake2b(digest_size=256 // 8)
        except (TypeError, ValueError):
            pass
        with open(self.filename, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                for hasher in hashers.values():
                    hasher.update(chunk)
        return {k: v.hexdigest() for k, v in hashers.items()}

    @classmethod
    def from_filename(cls, filename: str, comment: str | None) -> PackageFile:
        filetype = ""
        for ext, dtype in DIST_EXTENSIONS.items():
            if filename.endswith(ext):
                filetype = dtype
                break
        else:
            raise PdmUsageError(f"Unknown distribution file type: {filename}")
        if filetype == "bdist_wheel":
            metadata = cls.read_metadata_from_wheel(filename)
            match = wheel_file_re.match(os.path.basename(filename))
            if match is None:
                py_ver = "any"
            else:
                py_ver = match.group("pyver")
        elif filename.endswith(".zip"):
            metadata = cls.read_metadata_from_zip(filename)
            py_ver = "source"
        else:
            metadata = cls.read_metadata_from_tar(filename)
            py_ver = "source"
        return cls(filename, metadata, comment, py_ver, filetype)

    @staticmethod
    def read_metadata_from_tar(filename: str) -> email.message.Message:
        if filename.endswith(".gz"):
            mode = "r:gz"
        elif filename.endswith(".bz2"):
            mode = "r:bz2"
        else:
            logger.warning(f"Can't determine the compression mode for {filename}")
            mode = "r:*"
        with tarfile.open(filename, mode) as tar:
            members = tar.getmembers()
            has_leading = has_leading_dir(m.name for m in members)
            for m in members:
                fn = split_leading_dir(m.name)[1] if has_leading else m.name
                if fn == "PKG-INFO":
                    return parse_metadata(cast(IO[bytes], tar.extractfile(m)))
        raise ProjectError(f"No PKG-INFO found in {filename}")

    @staticmethod
    def read_metadata_from_zip(filename: str) -> email.message.Message:
        with zipfile.ZipFile(filename, allowZip64=True) as zip:
            filenames = zip.namelist()
            has_leading = has_leading_dir(filenames)
            for name in filenames:
                fn = split_leading_dir(name)[1] if has_leading else name
                if fn == "PKG-INFO":
                    return parse_metadata(zip.open(name))
        raise ProjectError(f"No PKG-INFO found in {filename}")

    @staticmethod
    def read_metadata_from_wheel(filename: str) -> email.message.Message:
        with zipfile.ZipFile(filename, allowZip64=True) as zip:
            for fn in zip.namelist():
                if fn.replace("\\", "/").endswith(".dist-info/METADATA"):
                    return parse_metadata(zip.open(fn))
        raise ProjectError(f"No egg-info is found in {filename}")

    def add_gpg_signature(self, filename: str, signature_name: str) -> None:
        if self.gpg_signature is not None:
            raise PdmUsageError("GPG signature already added")
        with open(filename, "rb") as f:
            self.gpg_signature = (signature_name, f.read())

    def sign(self, identity: str | None) -> None:
        logger.info("Signing %s with gpg", self.base_filename)
        gpg_args = ["gpg", "--detach-sign"]
        if identity is not None:
            gpg_args.extend(["--local-user", identity])
        gpg_args.extend(["-a", self.filename])
        self._run_gpg(gpg_args)
        self.add_gpg_signature(self.filename + ".asc", self.base_filename + ".asc")

    @staticmethod
    def _run_gpg(gpg_args: list[str]) -> None:
        try:
            subprocess.run(gpg_args, check=True)
            return
        except FileNotFoundError:
            logger.warning("gpg executable not available. Attempting fallback to gpg2.")

        gpg_args[0] = "gpg2"
        try:
            subprocess.run(gpg_args, check=True)
        except FileNotFoundError:
            raise PdmUsageError(
                "'gpg' or 'gpg2' executables not available.\n"
                "Try installing one of these or specifying an executable "
                "with the --sign-with flag."
            ) from None

    @property
    def metadata_dict(self) -> dict[str, Any]:
        meta = self.metadata
        data = {
            # identify release
            "name": normalize_name(meta["Name"]),
            "version": meta["Version"],
            # file content
            "filetype": self.filetype,
            "pyversion": self.py_version,
            # additional meta-data
            "metadata_version": meta["Metadata-Version"],
            "summary": meta["Summary"],
            "home_page": meta["Home-page"],
            "author": meta["Author"],
            "author_email": meta["Author-email"],
            "maintainer": meta["Maintainer"],
            "maintainer_email": meta["Maintainer-email"],
            "license": meta["License"],
            "description": meta.get_payload(),
            "keywords": meta["Keywords"],
            "platform": meta.get_all("Platform") or (),
            "classifiers": meta.get_all("Classifier") or [],
            "download_url": meta["Download-URL"],
            "supported_platform": meta.get_all("Supported-Platform") or (),
            "comment": self.comment,
            # Metadata 1.2
            "project_urls": meta.get_all("Project-URL") or (),
            "provides_dist": meta.get_all("Provides-Dist") or (),
            "obsoletes_dist": meta.get_all("Obsoletes-Dist") or (),
            "requires_dist": meta.get_all("Requires-Dist") or (),
            "requires_external": meta.get_all("Requires-External") or (),
            "requires_python": meta.get_all("Requires-Python") or (),
            # Metadata 2.1
            "provides_extras": meta.get_all("Provides-Extra") or (),
            "description_content_type": meta.get("Description-Content-Type"),
            # Metadata 2.2
            "dynamic": meta.get_all("Dynamic") or (),
            # Hashes
            **self.get_hashes(),
        }
        if self.gpg_signature is not None:
            data["gpg_signature"] = self.gpg_signature
        return data
