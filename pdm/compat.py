import sys

if sys.version_info >= (3, 11):
    import tomllib as tomllib
else:
    import tomli

    tomllib = tomli
