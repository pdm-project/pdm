from setuptools import setup


setup(
    name="demo-extras",
    version="0.0.1",
    description="test demo",
    py_modules=["demo"],
    install_requires=[],
    extras_require={"extra1": ["requests[security]"], "extra2": ["requests[socks]"]},
)
