# -*- coding: utf-8 -*-
__author__ = 'Manraj Singh'
__email__ = 'manrajsinghgrover@gmail.com'

import logging

from .halo import Halo
from .halo_notebook import HaloNotebook

logging.getLogger(__name__).addHandler(logging.NullHandler())
