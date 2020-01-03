from setuptools import setup


setup(
    name="demo",
    version="0.0.1",
    description="test demo",
    py_modules=["demo"],
    install_requires=["idna", "chardet"],
    extras_require={'tests': ['pytest'], 'security': ['requests']},
)
