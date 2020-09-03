from __future__ import annotations

import importlib
import subprocess
from typing import TYPE_CHECKING

import distlib.scripts
from pip._internal.utils import logging as pip_logging
from pip._vendor.pkg_resources import EggInfoDistribution
from pip_shims import shims

from pdm.iostream import stream
from pdm.models.requirements import parse_requirement
from pdm.utils import cd

if TYPE_CHECKING:
    from distlib.wheel import Wheel
    from pip._vendor.pkg_resources import Distribution

    from pdm.models.candidates import Candidate
    from pdm.models.environment import Environment


def is_dist_editable(dist: Distribution) -> bool:
    return isinstance(dist, EggInfoDistribution)


def format_dist(dist: Distribution) -> str:
    formatter = "{version}{path}"
    path = ""
    if is_dist_editable(dist):
        path = f" (-e {dist.location})"
    return formatter.format(version=stream.yellow(dist.version), path=path)


def _install_wheel(wheel, paths, maker, **kwargs):
    # TODO: This is a patched version of `wheel.install()` and to be deleted after
    # fixed in upstream.
    import codecs
    import json
    import os
    import posixpath
    import shutil
    import sys
    import tempfile
    from zipfile import ZipFile

    from distlib.wheel import (
        CSVReader,
        DistlibException,
        FileOperator,
        InstalledDistribution,
        convert_path,
        logger,
        message_from_file,
        read_exports,
        text_type,
    )

    METADATA_FILENAME = "pydist.json"

    dry_run = maker.dry_run
    warner = kwargs.get("warner")
    lib_only = kwargs.get("lib_only", False)
    bc_hashed_invalidation = kwargs.get("bytecode_hashed_invalidation", False)

    pathname = os.path.join(wheel.dirname, wheel.filename)
    name_ver = "%s-%s" % (wheel.name, wheel.version)
    data_dir = "%s.data" % name_ver
    info_dir = "%s.dist-info" % name_ver

    metadata_name = posixpath.join(info_dir, METADATA_FILENAME)
    wheel_metadata_name = posixpath.join(info_dir, "WHEEL")
    record_name = posixpath.join(info_dir, "RECORD")

    wrapper = codecs.getreader("utf-8")

    with ZipFile(pathname, "r") as zf:
        with zf.open(wheel_metadata_name) as bwf:
            wf = wrapper(bwf)
            message = message_from_file(wf)
        wv = message["Wheel-Version"].split(".", 1)
        file_version = tuple([int(i) for i in wv])
        if (file_version != wheel.wheel_version) and warner:
            warner(wheel.wheel_version, file_version)

        if message["Root-Is-Purelib"] == "true":
            libdir = paths["purelib"]
        else:
            libdir = paths["platlib"]

        records = {}
        with zf.open(record_name) as bf:
            with CSVReader(stream=bf) as reader:
                for row in reader:
                    p = row[0]
                    records[p] = row

        data_pfx = posixpath.join(data_dir, "")
        info_pfx = posixpath.join(info_dir, "")
        script_pfx = posixpath.join(data_dir, "scripts", "")

        # make a new instance rather than a copy of maker's,
        # as we mutate it
        fileop = FileOperator(dry_run=dry_run)
        fileop.record = True  # so we can rollback if needed

        bc = not sys.dont_write_bytecode  # Double negatives. Lovely!

        outfiles = []  # for RECORD writing

        # for script copying/shebang processing
        workdir = tempfile.mkdtemp()
        # set target dir later
        # we default add_launchers to False, as the
        # Python Launcher should be used instead
        maker.source_dir = workdir
        maker.target_dir = None
        try:
            for zinfo in zf.infolist():
                arcname = zinfo.filename
                if isinstance(arcname, text_type):
                    u_arcname = arcname
                else:
                    u_arcname = arcname.decode("utf-8")
                if wheel.skip_entry(u_arcname):
                    continue
                row = records[u_arcname]
                if row[2] and str(zinfo.file_size) != row[2]:
                    raise DistlibException("size mismatch for " "%s" % u_arcname)
                if row[1]:
                    kind, value = row[1].split("=", 1)
                    with zf.open(arcname) as bf:
                        data = bf.read()
                    _, digest = wheel.get_hash(data, kind)
                    if digest != value:
                        raise DistlibException("digest mismatch for " "%s" % arcname)

                if lib_only and u_arcname.startswith((info_pfx, data_pfx)):
                    logger.debug("lib_only: skipping %s", u_arcname)
                    continue
                is_script = u_arcname.startswith(script_pfx) and not u_arcname.endswith(
                    ".exe"
                )

                if u_arcname.startswith(data_pfx):
                    _, where, rp = u_arcname.split("/", 2)
                    outfile = os.path.join(paths[where], convert_path(rp))
                else:
                    # meant for site-packages.
                    if u_arcname in (wheel_metadata_name, record_name):
                        continue
                    outfile = os.path.join(libdir, convert_path(u_arcname))
                if not is_script:
                    with zf.open(arcname) as bf:
                        fileop.copy_stream(bf, outfile)
                    outfiles.append(outfile)
                    # Double check the digest of the written file
                    if not dry_run and row[1]:
                        with open(outfile, "rb") as bf:
                            data = bf.read()
                            _, newdigest = wheel.get_hash(data, kind)
                            if newdigest != digest:
                                raise DistlibException(
                                    "digest mismatch " "on write for " "%s" % outfile
                                )
                    if bc and outfile.endswith(".py"):
                        try:
                            pyc = fileop.byte_compile(
                                outfile, hashed_invalidation=bc_hashed_invalidation
                            )
                            outfiles.append(pyc)
                        except Exception:
                            # Don't give up if byte-compilation fails,
                            # but log it and perhaps warn the user
                            logger.warning("Byte-compilation failed", exc_info=True)
                else:
                    fn = os.path.basename(convert_path(arcname))
                    workname = os.path.join(workdir, fn)
                    with zf.open(arcname) as bf:
                        fileop.copy_stream(bf, workname)

                    dn, fn = os.path.split(outfile)
                    maker.target_dir = dn
                    filenames = maker.make(fn)
                    fileop.set_executable_mode(filenames)
                    outfiles.extend(filenames)

            if lib_only:
                logger.debug("lib_only: returning None")
                dist = None
            else:
                # Generate scripts

                # Try to get pydist.json so we can see if there are
                # any commands to generate. If this fails (e.g. because
                # of a legacy wheel), log a warning but don't give up.
                commands = None
                file_version = wheel.info["Wheel-Version"]
                if file_version == "1.0":
                    # Use legacy info
                    ep = posixpath.join(info_dir, "entry_points.txt")
                    try:
                        with zf.open(ep) as bwf:
                            epdata = read_exports(bwf)
                        commands = {}
                        for key in ("console", "gui"):
                            k = "%s_scripts" % key
                            if k in epdata:
                                commands["wrap_%s" % key] = d = {}
                                for v in epdata[k].values():
                                    s = "%s:%s" % (v.prefix, v.suffix)
                                    if v.flags:
                                        s += " [%s]" % ",".join(v.flags)
                                    d[v.name] = s
                    except Exception:
                        logger.warning(
                            "Unable to read legacy script "
                            "metadata, so cannot generate "
                            "scripts"
                        )
                else:
                    try:
                        with zf.open(metadata_name) as bwf:
                            wf = wrapper(bwf)
                            commands = json.load(wf).get("extensions")
                            if commands:
                                commands = commands.get("python.commands")
                    except Exception:
                        logger.warning(
                            "Unable to read JSON metadata, so "
                            "cannot generate scripts"
                        )
                if commands:
                    console_scripts = commands.get("wrap_console", {})
                    gui_scripts = commands.get("wrap_gui", {})
                    if console_scripts or gui_scripts:
                        script_dir = paths.get("scripts", "")
                        if not os.path.isdir(script_dir):
                            raise ValueError("Valid script path not " "specified")
                        maker.target_dir = script_dir
                        for k, v in console_scripts.items():
                            script = "%s = %s" % (k, v)
                            filenames = maker.make(script)
                            fileop.set_executable_mode(filenames)

                        if gui_scripts:
                            options = {"gui": True}
                            for k, v in gui_scripts.items():
                                script = "%s = %s" % (k, v)
                                filenames = maker.make(script, options)
                                fileop.set_executable_mode(filenames)

                p = os.path.join(libdir, info_dir)
                dist = InstalledDistribution(p)

                # Write SHARED
                paths = dict(paths)  # don't change passed in dict
                del paths["purelib"]
                del paths["platlib"]
                paths["lib"] = libdir
                p = dist.write_shared_locations(paths, dry_run)
                if p:
                    outfiles.append(p)

                # Write RECORD
                dist.write_installed_files(outfiles, paths["prefix"], dry_run)
            return dist
        except Exception:  # pragma: no cover
            logger.exception("installation failed.")
            fileop.rollback()
            raise
        finally:
            shutil.rmtree(workdir)


class Installer:  # pragma: no cover
    """The installer that performs the installation and uninstallation actions."""

    def __init__(self, environment: Environment, auto_confirm: bool = True) -> None:
        self.environment = environment
        self.auto_confirm = auto_confirm
        # XXX: Patch pip to make it work under multi-thread mode
        pip_logging._log_state.indentation = 0

    def install(self, candidate: Candidate) -> None:
        candidate.get_metadata(allow_all_wheels=False)
        if candidate.req.editable:
            self.install_editable(candidate.ireq)
        else:
            self.install_wheel(candidate.wheel)

    def install_wheel(self, wheel: Wheel) -> None:
        paths = self.environment.get_paths()
        maker = distlib.scripts.ScriptMaker(None, None)
        maker.executable = self.environment.python_executable
        if not self.environment.is_global:
            maker.script_template = maker.script_template.replace(
                "import sys",
                "import sys\nsys.path.insert(0, {!r})".format(paths["platlib"]),
            )
        _install_wheel(wheel, paths, maker)

    def install_editable(self, ireq: shims.InstallRequirement) -> None:
        setup_path = ireq.setup_py_path
        paths = self.environment.get_paths()
        install_script = importlib.import_module(
            "pdm._editable_install"
        ).__file__.rstrip("co")
        install_args = [
            self.environment.python_executable,
            "-u",
            install_script,
            setup_path,
            paths["prefix"],
            paths["purelib"],
            paths["scripts"],
        ]
        with self.environment.activate(True), cd(ireq.unpacked_source_directory):
            result = subprocess.run(install_args, capture_output=True, check=True)
            stream.logger.debug(result.stdout.decode("utf-8"))

    def uninstall(self, dist: Distribution) -> None:
        req = parse_requirement(dist.project_name)
        if is_dist_editable(dist):
            ireq = shims.install_req_from_editable(dist.location)
        else:
            ireq = shims.install_req_from_line(dist.project_name)
        ireq.req = req

        with self.environment.activate():
            pathset = ireq.uninstall(auto_confirm=self.auto_confirm)
            if pathset:
                pathset.commit()
