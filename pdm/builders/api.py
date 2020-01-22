"""
PEP-517 compliant buildsystem API
"""
from pathlib import Path

from pdm.builders import WheelBuilder, SdistBuilder
from pdm.models.requirements import parse_requirement


def get_requires_for_build_wheel(config_settings=None):
    """
    Returns an additional list of requirements for building, as PEP508 strings,
    above and beyond those specified in the pyproject.toml file.

    This implementation is optional. At the moment it only returns an empty list,
    which would be the same as if not define. So this is just for completeness
    for future implementation.
    """
    return []


# For now, we require all dependencies to build either a wheel or an sdist.
get_requires_for_build_sdist = get_requires_for_build_wheel


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    ireq = parse_requirement(".").as_ireq()
    ireq.source_dir = "."
    builder = WheelBuilder(ireq)

    dist_info = Path(metadata_directory, builder.dist_info_name)
    dist_info.mkdir(exist_ok=True)
    with builder:
        if builder.meta.entry_points:
            with (dist_info / "entry_points.txt").open("w", encoding="utf-8") as f:
                builder._write_entry_points(f)

        with (dist_info / "WHEEL").open("w", encoding="utf-8") as f:
            builder._write_wheel_file(f)

        with (dist_info / "METADATA").open("w", encoding="utf-8") as f:
            builder._write_metadata_file(f)

    return dist_info.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    """Builds a wheel, places it in wheel_directory"""
    ireq = parse_requirement(".").as_ireq()
    ireq.source_dir = "."
    with WheelBuilder(ireq) as builder:
        return builder.build(wheel_directory)


def build_sdist(sdist_directory, config_settings=None):
    """Builds an sdist, places it in sdist_directory"""
    ireq = parse_requirement(".").as_ireq()
    ireq.source_dir = "."
    with SdistBuilder(ireq) as builder:
        return builder.build(sdist_directory)
