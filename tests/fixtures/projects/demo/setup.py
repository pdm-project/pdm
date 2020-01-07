from setuptools import setup


setup(
    name="demo",
    version="0.0.1",
    description="test demo",
    py_modules=["demo"],
    python_requires=">=3.3",
    install_requires=["idna", "chardet; os_name=='nt'"],
    extras_require={
        "tests": ["pytest"],
        "security": ['requests; python_version>="3.6"'],
    },
)
