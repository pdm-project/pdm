
# -*- coding: utf-8 -*-
from setuptools import setup

import codecs

with codecs.open('README.rst', encoding="utf-8") as fp:
    long_description = fp.read()
INSTALL_REQUIRES = [
    'requests>=2.6',
    'configparser; python_version == "2.7"',
]
EXTRAS_REQUIRE = {
    'test': [
        'pytest >=2.7.3',
        'pytest-cov',
    ],
    'doc': [
        'sphinx',
    ],
}
ENTRY_POINTS = {
    'console_scripts': [
        'flit = flit:main',
    ],
    'pygments.lexers': [
        'dogelang = dogelang.lexer:DogeLexer',
    ],
}

setup_kwargs = {
    'name': 'pyflit',
    'version': '0.1.0',
    'description': 'An awesome flit demo',
    'long_description': long_description,
    'license': None,
    'author': '',
    'author_email': 'Thomas Kluyver <thomas@kluyver.me.uk>',
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://github.com/takluyver/flit',
    'package_data': {'': ['*']},
    'long_description_content_type': 'text/x-rst',
    'classifiers': [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    'install_requires': INSTALL_REQUIRES,
    'extras_require': EXTRAS_REQUIRE,
    'python_requires': '>=3.5',
    'entry_points': ENTRY_POINTS,

}


setup(**setup_kwargs)
