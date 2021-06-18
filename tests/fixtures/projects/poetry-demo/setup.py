
# -*- coding: utf-8 -*-
from setuptools import setup

long_description = None
INSTALL_REQUIRES = [
    'requests<3.0,>=2.6',
]
EXTRAS_REQUIRE = {
    'test': [
        'pytest<3.0.0,>=2.7.3',
        'pytest-covNone',
    ],
    'doc': [
        'sphinxNone',
    ],
}

setup_kwargs = {
    'name': 'poetry-demo',
    'version': '0.1.0',
    'description': None,
    'long_description': long_description,
    'license': None,
    'author': '',
    'author_email': 'Thomas Kluyver <thomas@kluyver.me.uk>',
    'maintainer': None,
    'maintainer_email': None,
    'url': 'https://github.com/takluyver/flit',
    'package_data': {'': ['*']},
    'classifiers': [
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    'install_requires': INSTALL_REQUIRES,
    'extras_require': EXTRAS_REQUIRE,
    'python_requires': '>=3.6,<4.0',

}


setup(**setup_kwargs)
