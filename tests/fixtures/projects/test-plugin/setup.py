from setuptools import setup


setup(
    name="test-plugin",
    version="0.0.1",
    py_modules=["hello"],
    entry_points={"pdm.plugin": ["hello = hello:main"]},
)
