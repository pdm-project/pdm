from setuptools import setup
from mymodule import __version__

with open("AUTHORS") as f:
    authors = f.read().strip()

kwargs = {
    "name": "mymodule",
    "version": __version__,
    "author": authors,
}

if 1 + 1 >= 2:
    kwargs.update(license="MIT")


if __name__ == "__main__":
    setup(**kwargs)
