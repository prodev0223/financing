# -*- coding: utf-8 -*-
from odoo.api import Environment
import threading
import odoo
from odoo import models, fields, api, exceptions, _, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta
import csv
import base64
import xlrd
from xlrd import XLRDError
import logging
import StringIO
import re

_logger = logging.getLogger(__name__)
allowed_tax_calc_error = 0.1

cyrillic_headers_mapping = {
    'orders': ['\xc4\xe0\xf2\xe0 \xf3\xf7\xe5\xf2\xe0', '\xcd\xee\xec\xe5\xf0', '\xcf\xf0\xee\xe2\xe5\xe4\xe5\xed \xeb\xe8 \xe4\xee\xea\xf3\xec\xe5\xed\xf2', '\xd2\xe8\xef \xf1\xf2\xf0\xee\xea\xe8 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xf1\xf2\xf0\xee\xea\xe8 (\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5(\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xde\xcb (\xc8\xcd\xcd)', '\xde\xcb (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xf0 \xf1\xec\xe5\xed\xfb', '\xd4\xe8\xf1\xea\xe0\xeb\xfc\xed\xfb\xe9 \xed\xee\xec\xe5\xf0 \xf1\xec\xe5\xed\xfb', '\xcd\xee\xec\xe5\xf0 \xea\xe0\xf1\xf1\xfb', '\xd1\xe5\xf0\xe8\xe9\xed\xfb\xe9 \xed\xee\xec\xe5\xf0 \xea\xe0\xf1\xf1\xfb', '\xcd\xee\xec\xe5\xf0 \xe7\xe0\xea\xe0\xe7\xe0', 'Guid \xe7\xe0\xea\xe0\xe7\xe0', '\xcd\xee\xec\xe5\xf0 \xf7\xe5\xea\xe0', '\xc4\xe0\xf2\xe0 \xe8 \xe2\xf0\xe5\xec\xff \xf0\xe5\xe3\xe8\xf1\xf2\xf0\xe0\xf6\xe8\xe8', '\xc2\xe8\xe4 \xe4\xe5\xff\xf2\xe5\xeb\xfc\xed\xee\xf1\xf2\xe8 (\xea\xee\xe4)', '\xc2\xe8\xe4 \xe4\xe5\xff\xf2\xe5\xeb\xfc\xed\xee\xf1\xf2\xe8 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd0\xe5\xe6\xe8\xec \xee\xe1\xf1\xeb\xf3\xe6\xe8\xe2\xe0\xed\xe8\xff (\xea\xee\xe4)', '\xd0\xe5\xe6\xe8\xec \xee\xe1\xf1\xeb\xf3\xe6\xe8\xe2\xe0\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xea\xee\xe4)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xea\xee\xe4)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xea\xee\xe4)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd6\xe5\xeb\xe5\xe2\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xea\xee\xe4)', '\xd6\xe5\xeb\xe5\xe2\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd6\xe5\xed\xe0 \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb', '\xca\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee', '\xd1\xf3\xec\xec\xe0 \xef\xf0\xee\xe4\xe0\xe6\xe8', '\xd1\xf3\xec\xec\xe0 \xf1\xea\xe8\xe4\xea\xe8 \xef\xee \xef\xee\xe7\xe8\xf6\xe8\xe8', '\xd1\xf2\xe0\xe2\xea\xe0 \xcd\xc4\xd1 \xef\xee \xef\xee\xe7\xe8\xf6\xe8\xe8', '\xd1\xf3\xec\xec\xe0 \xcd\xc4\xd1 \xef\xee \xef\xee\xe7\xe8\xf6\xe8\xe8', '\xd2\xe8\xef \xee\xef\xeb\xe0\xf2\xfb (\xea\xee\xe4)', '\xd2\xe8\xef \xee\xef\xeb\xe0\xf2\xfb (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd1\xf3\xec\xec\xe0 \xee\xef\xeb\xe0\xf2\xfb', '\xd4\xe8\xf1\xea\xe0\xeb\xfc\xed\xe0\xff \xee\xef\xeb\xe0\xf2\xe0', '\xca\xee\xed\xf2\xf0\xe0\xe3\xe5\xed\xf2 (\xea\xee\xe4)', '\xca\xee\xed\xf2\xf0\xe0\xe3\xe5\xed\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xf1\xea\xe8\xe4\xea\xe8 (\xea\xee\xe4)', '\xd2\xe8\xef \xf1\xea\xe8\xe4\xea\xe8 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd1\xf3\xec\xec\xe0 \xf1\xea\xe8\xe4\xea\xe8', '\xcf\xf0\xe8\xf7\xe8\xed\xe0 \xf3\xe4\xe0\xeb\xe5\xed\xe8\xff (\xea\xee\xe4)', '\xcf\xf0\xe8\xf7\xe8\xed\xe0 \xf3\xe4\xe0\xeb\xe5\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xf1\xe5\xf0\xe2\xe8\xf1\xed\xee\xe3\xee \xf1\xe1\xee\xf0\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xf1\xe5\xf0\xe2\xe8\xf1\xed\xee\xe3\xee \xf1\xe1\xee\xf0\xe0 (\xea\xee\xe4)', '\xca\xee\xec\xec\xe5\xed\xf2\xe0\xf0\xe8\xe9', '\xc1\xe0\xed\xea\xee\xe2\xf1\xea\xe0\xff \xea\xe0\xf0\xf2\xe0 (\xf2\xe8\xef)'],
    'cash_flow_movements': ['\xc4\xe0\xf2\xe0', '\xcd\xee\xec\xe5\xf0', '\xd1\xf3\xec\xec\xe0 \xef\xf0\xee\xe2\xee\xe4\xea\xe8', '\xce\xef\xe5\xf0\xe0\xf6\xe8\xff', '\xc4\xe5\xe1\xe5\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc4\xe5\xe1\xe5\xf2 (\xea\xee\xe4)', '\xc4\xe5\xe1\xe5\xf2 (\xf2\xe8\xef)', '\xc4\xe5\xe1\xe5\xf2, \xef\xee\xe4\xf1\xf7\xe5\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc4\xe5\xe1\xe5\xf2, \xef\xee\xe4\xf1\xf7\xe5\xf2 (\xea\xee\xe4)', '\xce\xf0\xe3\xe0\xed\xe8\xe7\xe0\xf6\xe8\xff, \xe4\xe5\xe1\xe5\xf2 (\xc8\xcd\xcd)', '\xce\xf0\xe3\xe0\xed\xe8\xe7\xe0\xf6\xe8\xff, \xe4\xe5\xe1\xe5\xf2 (\xea\xee\xe4)', '\xce\xf0\xe3\xe0\xed\xe8\xe7\xe0\xf6\xe8\xff, \xe4\xe5\xe1\xe5\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xca\xf0\xe5\xe4\xe8\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xca\xf0\xe5\xe4\xe8\xf2 (\xea\xee\xe4)', '\xca\xf0\xe5\xe4\xe8\xf2 (\xf2\xe8\xef)', '\xca\xf0\xe5\xe4\xe8\xf2, \xef\xee\xe4\xf1\xf7\xe5\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xca\xf0\xe5\xe4\xe8\xf2, \xef\xee\xe4\xf1\xf7\xe5\xf2 (\xea\xee\xe4)', '\xce\xf0\xe3\xe0\xed\xe8\xe7\xe0\xf6\xe8\xff, \xea\xf0\xe5\xe4\xe8\xf2 (\xc8\xcd\xcd)', '\xce\xf0\xe3\xe0\xed\xe8\xe7\xe0\xf6\xe8\xff, \xea\xf0\xe5\xe4\xe8\xf2 (\xea\xee\xe4)', '\xce\xf0\xe3\xe0\xed\xe8\xe7\xe0\xf6\xe8\xff, \xea\xf0\xe5\xe4\xe8\xf2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xde\xcb (\xc8\xcd\xcd)', '\xde\xcb (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xea\xee\xe4)', '\xca\xee\xec\xec\xe5\xed\xf2\xe0\xf0\xe8\xe9'],
    'purchase_picking': ['\xc4\xe0\xf2\xe0', '\xcd\xee\xec\xe5\xf0', '\xcf\xf0\xee\xe2\xe5\xe4\xe5\xed \xeb\xe8 \xe4\xee\xea\xf3\xec\xe5\xed\xf2', '\xc2\xf5\xee\xe4. \xed\xee\xec\xe5\xf0', '\xc2\xf5\xee\xe4. \xe4\xe0\xf2\xe0', '\xcf\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea (\xc8\xcd\xcd)', '\xcf\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea (\xea\xee\xe4)', '\xcf\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xee\xf2\xf0\xf3\xe4\xed\xe8\xea (\xea\xee\xe4)', '\xd1\xee\xf2\xf0\xf3\xe4\xed\xe8\xea (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xea\xeb\xe0\xe4(\xea\xee\xe4)', '\xd1\xea\xeb\xe0\xe4 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xf7\xe5\xf2-\xf4\xe0\xea\xf2\xf3\xf0\xe0', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xea\xee\xe4)', '\xca\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee', '\xd6\xe5\xed\xe0 \xf1 \xcd\xc4\xd1', '\xd1\xf3\xec\xec\xe0 \xf1 \xcd\xc4\xd1', '\xd1\xf3\xec\xec\xe0 \xcd\xc4\xd1', '\xd1\xf2\xe0\xe2\xea\xe0 \xcd\xc4\xd1', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5(\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xde\xcb (\xc8\xcd\xcd)', '\xde\xcb (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xea\xee\xe4)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xea\xee\xe4)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 \xef\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea\xe0 (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 \xef\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd2\xe0\xf0\xe0 (\xea\xee\xe4)', '\xd2\xe0\xf0\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee \xe2 \xf2\xe0\xf0\xe5', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xea\xee\xe4)', '\xd1\xea\xeb\xe0\xe4 \xef\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xea\xeb\xe0\xe4 \xef\xee\xf1\xf2\xe0\xe2\xf9\xe8\xea (\xea\xee\xe4)', '\xca\xee\xec\xec\xe5\xed\xf2\xe0\xf0\xe8\xe9', '\xcd\xee\xec\xe5\xf0 \xf2\xee\xe2\xe0\xf0\xed\xee-\xf2\xf0\xe0\xed\xf1\xef\xee\xf0\xf2\xed\xee\xe9 \xed\xe0\xea\xeb\xe0\xe4\xed\xee\xe9', '\xcd\xee\xec\xe5\xf0 \xf2\xe0\xec\xee\xe6\xe5\xed\xed\xee\xe9 \xe4\xe5\xea\xeb\xe0\xf0\xe0\xf6\xe8\xe8', '\xca\xee\xe4 \xe2\xe8\xe4\xe0 \xe0\xeb\xea\xee\xe3\xee\xeb\xfc\xed\xee\xe9 \xef\xf0\xee\xe4\xf3\xea\xf6\xe8\xe8', '\xde\xcb \xef\xf0\xee\xe8\xe7\xe2\xee\xe4\xe8\xf2\xe5\xeb\xff', '\xc8\xcd\xcd \xef\xf0\xee\xe8\xe7\xe2\xee\xe4\xe8\xf2\xe5\xeb\xff', '\xca\xcf\xcf \xef\xf0\xee\xe8\xe7\xe2\xee\xe4\xe8\xf2\xe5\xeb\xff', '\xd1\xf0\xee\xea \xee\xef\xeb\xe0\xf2\xfb', '\xc4\xe0\xf2\xe0 \xee\xef\xeb\xe0\xf2\xfb', '\xc4\xee\xf1\xf2\xe0\xe2\xea\xe0 \xe2 \xf1\xf0\xee\xea', '\xd1\xee\xee\xf2\xe2\xe5\xf2\xf1\xf2\xe2\xf3\xe5\xf2 \xe7\xe0\xea\xe0\xe7\xf3'],
    'inventory': ['\xc4\xe0\xf2\xe0', '\xcd\xee\xec\xe5\xf0', '\xcf\xf0\xee\xe2\xe5\xe4\xe5\xed \xeb\xe8 \xe4\xee\xea\xf3\xec\xe5\xed\xf2', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5(\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xde\xcb (\xc8\xcd\xcd)', '\xde\xcb (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xea\xeb\xe0\xe4 (\xea\xee\xe4)', '\xd1\xea\xeb\xe0\xe4 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xea\xee\xe4)', '\xca\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee', '\xd1\xe5\xe1\xe5\xf1\xf2\xee\xe8\xec\xee\xf1\xf2\xfc \xe7\xe0 \xe5\xe4.', '\xd1\xe5\xe1\xe5\xf1\xf2\xee\xe8\xec\xee\xf1\xf2\xfc', '\xd1\xf2\xe0\xe2\xea\xe0 \xcd\xc4\xd1', '\xd1\xf7\xe5\xf2 \xed\xe5\xe4\xee\xf1\xf2\xe0\xf7\xe8 (\xea\xee\xe4)', '\xd1\xf7\xe5\xf2 \xed\xe5\xe4\xee\xf1\xf2\xe0\xf7\xe8 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xf7\xe5\xf2 \xe8\xe7\xeb\xe8\xf8\xea\xee\xe2 (\xea\xee\xe4)', '\xd1\xf7\xe5\xf2 \xe8\xe7\xeb\xe8\xf8\xea\xee\xe2 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xea\xee\xe4)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xea\xee\xe4)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc8\xe7\xeb\xe8\xf8\xea\xe8/\xcd\xe5\xe4\xee\xf1\xf2\xe0\xf7\xe0 (\xea\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee)', '\xc8\xe7\xeb\xe8\xf8\xea\xe8/\xcd\xe5\xe4\xee\xf1\xf2\xe0\xf7\xe0 (\xf1\xf3\xec\xec\xe0)', '\xca\xee\xec\xec\xe5\xed\xf2\xe0\xf0\xe8\xe9'],
    'write_off_act': ['\xc4\xe0\xf2\xe0', '\xcd\xee\xec\xe5\xf0', '\xcf\xf0\xee\xe2\xe5\xe4\xe5\xed \xeb\xe8 \xe4\xee\xea\xf3\xec\xe5\xed\xf2', '\xd1\xea\xeb\xe0\xe4 (\xea\xee\xe4)', '\xd1\xea\xeb\xe0\xe4 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xea\xee\xe4)', '\xca\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee', '\xd1\xe5\xe1\xe5\xf1\xf2\xee\xe8\xec\xee\xf1\xf2\xfc \xe7\xe0 \xe5\xe4. \xe1\xe5\xe7 \xcd\xc4\xd1', '\xd1\xe5\xe1\xe5\xf1\xf2\xee\xe8\xec\xee\xf1\xf2\xfc \xe1\xe5\xe7 \xcd\xc4\xd1', '\xd1\xf2\xe0\xe2\xea\xe0 \xcd\xc4\xd1', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5(\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xde\xcb (\xc8\xcd\xcd)', '\xde\xcb (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd1\xf2\xe0\xf2\xfc\xff \xf0\xe0\xf1\xf5\xee\xe4\xee\xe2', '\xd1\xf2\xe0\xf2\xfc\xff \xf0\xe0\xf1\xf5\xee\xe4\xee\xe2(\xea\xee\xe4)', '\xd2\xe8\xef \xf1\xef\xe8\xf1\xe0\xed\xe8\xff', '\xd2\xe8\xef \xf1\xef\xe8\xf1\xe0\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xce\xef\xe5\xf0\xe0\xf6\xe8\xff', '\xce\xef\xe5\xf0\xe0\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xea\xee\xe4)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd6\xe5\xeb\xe5\xe2\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xea\xee\xe4)', '\xd6\xe5\xeb\xe5\xe2\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xea\xee\xe4)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xf0 \xf1\xec\xe5\xed\xfb', '\xcd\xee\xec\xe5\xf0 \xea\xe0\xf1\xf1\xfb', '\xcf\xf0\xee\xe4\xe0\xed\xed\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xea\xee\xe4)', '\xcf\xf0\xee\xe4\xe0\xed\xed\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 \xef\xf0\xee\xe4\xe0\xed\xed\xee\xe3\xee \xe1\xeb\xfe\xe4\xe0 (\xea\xee\xe4)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 \xef\xf0\xee\xe4\xe0\xed\xed\xee\xe3\xee \xe1\xeb\xfe\xe4\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xec\xec\xe5\xed\xf2\xe0\xf0\xe8\xe9'],
    'realisation_act': ['\xc4\xe0\xf2\xe0', '\xcd\xee\xec\xe5\xf0', '\xcf\xf0\xee\xe2\xe5\xe4\xe5\xed \xeb\xe8 \xe4\xee\xea\xf3\xec\xe5\xed\xf2', '\xd1\xea\xeb\xe0\xe4(\xea\xee\xe4)', '\xd1\xea\xeb\xe0\xe4 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xce\xef\xe5\xf0\xe0\xf6\xe8\xff', '\xce\xef\xe5\xf0\xe0\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xea\xee\xe4)', '\xcd\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xe0 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 (\xea\xee\xe4)', '\xca\xee\xeb\xe8\xf7\xe5\xf1\xf2\xe2\xee', '\xd6\xe5\xed\xe0 \xef\xf0\xee\xe4\xe0\xe6\xe8 \xf1 \xcd\xc4\xd1', '\xd1\xf3\xec\xec\xe0 \xef\xf0\xee\xe4\xe0\xe6\xe8 \xf1 \xcd\xc4\xd1', '\xd1\xf3\xec\xec\xe0 \xcd\xc4\xd1 \xf1 \xef\xf0\xee\xe4\xe0\xe6', '\xd1\xf2\xe0\xe2\xea\xe0 \xcd\xc4\xd1 \xf1 \xef\xf0\xee\xe4\xe0\xe6', '\xd1\xe5\xe1\xe5\xf1\xf2\xee\xe8\xec\xee\xf1\xf2\xfc \xe7\xe0 \xe5\xe4. \xe1\xe5\xe7 \xcd\xc4\xd1', '\xd1\xe5\xe1\xe5\xf1\xf2\xee\xe8\xec\xee\xf1\xf2\xfc \xe1\xe5\xe7 \xcd\xc4\xd1', '\xd1\xf2\xe0\xe2\xea\xe0 \xcd\xc4\xd1', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5(\xea\xee\xe4)', '\xd2\xee\xf0\xe3\xee\xe2\xee\xe5 \xef\xf0\xe5\xe4\xef\xf0\xe8\xff\xf2\xe8\xe5 (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xde\xcb (\xc8\xcd\xcd)', '\xde\xcb (\xed\xe0\xe8\xec\xe5\xed\xee\xe2\xe0\xed\xe8\xe5)', '\xd2\xe8\xef \xf1\xef\xe8\xf1\xe0\xed\xe8\xff', '\xd2\xe8\xef \xf1\xef\xe8\xf1\xe0\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc4\xe2\xe8\xe6\xe5\xed\xe8\xe5 \xe4\xe5\xed\xe5\xe6\xed\xfb\xf5 \xf1\xf0\xe5\xe4\xf1\xf2\xe2 (\xea\xee\xe4)', '\xc4\xe2\xe8\xe6\xe5\xed\xe8\xe5 \xe4\xe5\xed\xe5\xe6\xed\xfb\xf5 \xf1\xf0\xe5\xe4\xf1\xf2\xe2', '\xd1\xf2\xe0\xf2\xfc\xff \xf0\xe0\xf1\xf5\xee\xe4\xee\xe2(\xea\xee\xe4)', '\xd1\xf2\xe0\xf2\xfc\xff \xf0\xe0\xf1\xf5\xee\xe4\xee\xe2', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xea\xee\xe4)', '\xd2\xe8\xef \xed\xee\xec\xe5\xed\xea\xeb\xe0\xf2\xf3\xf0\xfb (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xd6\xe5\xeb\xe5\xe2\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xea\xee\xe4)', '\xd6\xe5\xeb\xe5\xe2\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xea\xee\xe4)', '\xc5\xe4\xe8\xed\xe8\xf6\xe0 \xe8\xe7\xec\xe5\xf0\xe5\xed\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xcd\xee\xec\xe5\xf0 \xf1\xec\xe5\xed\xfb', '\xcd\xee\xec\xe5\xf0 \xea\xe0\xf1\xf1\xfb', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xed\xf6\xe5\xef\xf6\xe8\xff (\xea\xee\xe4)', '\xcf\xf0\xee\xe4\xe0\xed\xed\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xea\xee\xe4)', '\xcf\xf0\xee\xe4\xe0\xed\xed\xee\xe5 \xe1\xeb\xfe\xe4\xee (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 \xf6\xe5\xeb\xe5\xe2\xee\xe3\xee \xe1\xeb\xfe\xe4\xe0 (\xea\xee\xe4)', '\xc3\xf0\xf3\xef\xef\xe0 \xf3\xf7\xe5\xf2\xe0 \xf6\xe5\xeb\xe5\xe2\xee\xe3\xee \xe1\xeb\xfe\xe4\xe0 (\xed\xe0\xe7\xe2\xe0\xed\xe8\xe5)', '\xca\xee\xec\xec\xe5\xed\xf2\xe0\xf0\xe8\xe9'],
}

csv_headers_mapping = {
    'purchase_picking': ['Data', 'Numeris', 'Ar patvirtintas dokumentas', 'Ieinantis numeris',
                         'Ieinanti data',	'Tiekejas (PVM kodas)',	'Tiekejas (kodas)',	'Tiekejas (pavadinimas)',
                         'Darbuotojas (kodas)',	'Darbuotojas (vardas)',	'Sandelys (kodas)',	'Sandelys (pavadinimas)',
                         'Saskaita-faktura', 'Nomenklatura (kodas)', 'Nomenklatura (pavadinimas)',
                         'Apskaitos grupe (pavadinimas)', 'Apskaitos grupe (kodas)', 'Kiekis', 'Kaina su PVM',
                         'Suma su PVM',	'PVM suma',	'PVM tarifas',	'Prekybos imone (kodas)',
                         'Prekybos imone (pavadinimas)',	'Jur.asm. (PVM kodas)',	'LE (pavadinimas)',
                         'Nomenklaturos tipas (kodas)',	'Nomenklaturos tipas (pavadinimas)',
                         'Matavimo vienetas (kodas)',	'Matavimo vienetas (pavadinimas)',
                         'Tiekejo nomenklatura (kodas)', 'Tiekejo nomenklatura (pavadinimas)', 'Tara (kodas)',
                         'Tara (pavadinimas)',	'Kiekis pakuoteje',	'Koncepcija (pavadinimas)',	'Koncepcija (kodas)',
                         'Tiekejas sandelys (vardas)',	'Tiekejas sandelys (kodas)', 'Komentaras',
                         'Prekiu vaztarascio numeris',	'Muitines deklaracijos numeris',
                         'Alkoholio produktu rusies kodas',	'Gamintojo pavadinimas',
                         'Gamintojo PVM kodas',	'Gamintojo im.kodas', 'Apmokejimo terminas',
                         'Apmokejimo data',	'Pristatymas laiku', 'Atitinka uzsakymui',
                         ],
    'orders': ['Apskaitine data', 'Numeris', 'Ar patvirtintas dokumentas', 'Eilutes tipas (pavadinimas)',
                         'Eilutes tipas (kodas)', 'Prekybos imone (kodas)',	'Prekybos imone (pavadinimas)',
                          'Jur.asm. (PVM kodas)',
                         'LE (pavadinimas)', 'Koncepcija (pavadinimas)', 'Koncepcija (kodas)',	'Pamainos numeris',
                         'Fiskalinis pamainos numeris', 'Kasos numeris', 'Serijos kasos numeris',
                         'Uzsakymo numeris', 'Uzsakymo Guid', 'Kvito Nr', 'Registravimo data ir laikas',
                         'Veiklos rusis (kodas)',	'Veiklos rusis (pavadinimas)',	'Aptarnavimo rezimas (kodas)',
                         'Aptarnavimo rezimas (pavadinimas)',
                         'Nomenklatura (kodas)', 'Nomenklatura (pavadinimas)', 'Apskaitos grupe (kodas)',
                         'Apskaitos grupe (pavadinimas)',	'Nomenklaturos tipas (kodas)',
                         'Nomenklaturos tipas (pavadinimas)', 'Matavimo vienetas (kodas)',
                         'Matavimo vienetas (pavadinimas)', 'Tikslinis patiekalas (kodas)',
                         'Tikslinis patiekalas (pavadinimas)',
                         'Nomenklaturos kaina', 'Kiekis', 'Pardavimo suma', 'Nuolaidos suma pozicijomis',
                         'PVM tarifas pozicijomis', 'PVM suma pozicijomis',
                         'Mokejimo tipas (kodas)', 'Mokejimo tipas (pavadinimas)', 'Mokejimo suma',
                         'Fiskalinis mokejimas', 'Kontragentas (kodas)', 'Kontragentas (pavadinimas)',
                         'Nuolaidos tipas (kodas)', 'Nuolaidos tipas (pavadinimas)',
                         'Nuolaidos suma', 'Panaikinimo priezastis (kodas)', 'Panaikinimo priezastis (pavadinimas)',
                         'Serviso surinkimo tipas (pavadinimas)', 'Serviso surinkimas (kodas)', 'Komentaras',
                         'Banko kortele (tipas)',
                         ],

    'inventory': ['Data', 'Numeris', 'Ar patvirtintas dokumentas', 'Prekybos imone (kodas)',
                  'Prekybos imone (pavadinimas)', 'Jur.asm. (PVM kodas)', 'LE (pavadinimas)',
                  'Sandelys (kodas)', 'Sandelys (pavadinimas)', 'Nomenklatura (kodas)',
                  'Nomenklatura (pavadinimas)', 'Apskaitos grupe (pavadinimas)', 'Apskaitos grupe (kodas)',
                  'Kiekis', 'Savikaina uz vnt.', 'Savikaina', 'PVM tarifas',
                  'Trukumu saskaita (kodas)', 'Trukumu saskaita (pavadinimas)', 'Pertekliaus saskaita (kodas)',
                  'Pertekliaus saskaita (pavadinimas)', 'Nomenklaturos tipas (kodas)',
                  'Nomenklaturos tipas (pavadinimas)', 'Matavimo vienetas (kodas)', 'Matavimo vienetas (pavadinimas)',
                  'Perteklius/trukumas (kiekis)', 'Perteklius/trukumas (suma)', 'Komentaras'
                  ],

    'cash_flow_movements': ['Data', 'Numeris', 'Pervedama suma', 'Operacija',
                            'Debetas (pavadinimas)', 'Debetas (kodas)', 'Debetas (tipas)',
                            'Debetas, daline saskaita (pavadinimas)', 'Debetas, daline saskaita (kodas)',
                            'Organizacija, debetas (PVM kodas)',
                            'Organizacija, debetas (kodas)', 'Organizacija, debetas (pavadinimas)',
                            'Kreditas (pavadinimas)', 'Kreditas (kodas)', 'Kreditas (tipas)',
                            'Kreditas, daline saskaita (pavadinimas)',
                            'Kreditas, daline saskaita (kodas)', 'Organizacija, kreditas (PVM kodas)',
                            'Organizacija, kreditas (kodas)',
                            'Organizacija kreditas (pavadinimas)', 'Prekybos imone (kodas)',
                            'Prekybos imone (pavadinimas)', 'Jur.asm. (PVM kodas)', 'LE (pavadinimas)',
                            'Koncepcija (pavadinimas)', 'Koncepcija (kodas)', 'Komentaras'
                            ],

    'write_off_act': ['Data', 'Numeris', 'Ar patvirtintas dokumentas', 'Sandelys (kodas)',
                      'Sandelys (pavadinimas)', 'Nomenklatura (kodas)', 'Nomenklatura (pavadinimas)',
                      'Apskaitos grupe (pavadinimas)', 'Apskaitos grupe (kodas)',
                      'Kiekis', 'Vieneto savikaina be PVM', 'Savikaina be PVM',
                      'PVM tarifas', 'Prekybos imone (kodas)', 'Prekybos imone (pavadinimas)',
                      'Jur.asm. (PVM kodas)', 'LE (pavadinimas)', 'Islaidu straipsnis',
                      'Islaidu straipsnis (kodas)', 'Nurasymo tipas', 'Nurasymo tipas (pavadinimas)',
                      'Operacija', 'Operacija (pavadinimas)', 'Nomenklaturos tipas (kodas)',
                      'Nomenklaturos tipas (pavadinimas)', 'Tikslinis patiekalas (kodas)',
                      'Tikslinis patiekalas (pavadinimas)', 'Matavimo vienetas (kodas)',
                      'Matavimo vienetas (pavadinimas)', 'Koncepcija (pavadinimas)', 'Koncepcija (kodas)',
                      'Pamainos numeris', 'Kasos numeris', 'Parduotas patiekalas (kodas)',
                      'Parduotas patiekalas (pavadinimas)',
                      'Parduoto patiekalo apskaitos grupe (kodas)',
                      'Parduoto patiekalo apskaitos grupe (pavadinimas)', 'Komentaras'
                      ],

    'realisation_act': ['Data', 'Numeris', 'Ar patvirtintas dokumentas', 'Sandelys (kodas)',
                        'Sandelys (pavadinimas)', 'Operacija', 'Operacija (pavadinimas)',
                        'Nomenklatura (kodas)', 'Nomenklatura (pavadinimas)',
                        'Apskaitos grupe (pavadinimas)', 'Apskaitos grupe (kodas)',
                        'Kiekis', 'Pardavimu kaina su PVM', 'Pardavimu suma su PVM', 'Pardavimu PVM suma',
                        'Pardavimu PVM tarifas', 'Vieneto savikaina be PVM', 'Savikaina be PVM', 'PVM tarifas',
                        'Prekybos imone (kodas)', 'Prekybos imone (pavadinimas)', 'Jur.asm. (PVM kodas)',
                        'LE (pavadinimas)', 'Nurasymo tipas', 'Nurasymo tipas (pavadinimas)', 'Pinigu srautai (kodas)',
                        'Pinigu srautu judejimas', 'Islaidu straipsnis (kodas)', 'Islaidu straipsnis',
                        'Nomenklaturos tipas (kodas)',
                        'Nomenklaturos tipas (pavadinimas)', 'Tikslinis patiekalas (kodas)',
                        'Tikslinis patiekalas (pavadinimas)',
                        'Matavimo vienetas (kodas)', 'Matavimo vienetas (pavadinimas)', 'Pamainos numeris',
                        'Kasos numeris',
                        'Koncepcija (pavadinimas)', 'Koncepcija (kodas)', 'Parduotas patiekalas (kodas)',
                        'Parduotas patiekalas (pavadinimas)',
                        'Tikslinio patiekalo apskaitos grupe (kodas)',
                        'Tikslinio patiekalo apskaitos grupe (pavadinimas)', 'Komentaras'
                        ],
    'orders_invoice': ['Numeris', 'Data', 'Pavadinimas', 'Tiek-kodas', 'Tiekėjas', 'Suma', 'PVM suma', 'Kvito Nr'],

    'purchase_picking_refund': ['Data',	'Numeris', 'Ar patvirtintas dokumentas', 'Sandelys (kodas)',
                                'Sandelys (pavadinimas)', 'Nomenklatura (kodas)', 'Nomenklatura (pavadinimas)',
                                'Apskaitos grupe (pavadinimas)',	'Apskaitos grupe (kodas)',
                                'Kiekis', 'Pardavimu kaina su PVM',	'Pardavimu suma su PVM', 'Pardavimu PVM suma',
                                'Pardavimu PVM tarifas', 'Vieneto savikaina be PVM', 'Savikaina be PVM', 'PVM tarifas',
                                'Prekybos imone (kodas)', 'Prekybos imone (pavadinimas)', 'Jur.asm. (PVM kodas)',
                                'LE (pavadinimas)',	'Pinigu srautai (kodas)', 'Pinigu srautu judejimas',
                                'Islaidu straipsnis (kodas)', 'Islaidu straipsnis',	'Pirkejas (PVM moketojo kodas)',
                                'Pirkejas (kodas)',	'Pirkejas (pavadinimas)',	'Pirkimo saskaita (data)',
                                'Pirkimo saskaita (numeris)', 'Saskaita-faktura', 'Nomenklaturos tipas (kodas)',
                                'Nomenklaturos tipas (pavadinimas)', 'Matavimo vienetas (kodas)',
                                'Matavimo vienetas (pavadinimas)',	'Koncepcija (pavadinimas)',	'Koncepcija (kodas)',
                                'Komentaras', 'Alkoholio produktu rusies kodas', 'Gamintojo pavadinimas',
                                'Gamintojo PVM kodas', 'Gamintojo im.kodas'],
}

pythonic_mapping_csv = {
    'orders_invoice': ['invoice_number', 'date_invoice', 'partner_name', 'partner_code',
                       'partner_vat', 'amount_total', 'amount_vat', 'receipt_id'],

    'purchase_picking': ['date', 'number', 'is_confirmed', 'input_number', 'input_date', 'client_vat',
                         'client_code', 'client_name', 'employee_code', 'employee_name', 'warehouse_code',
                         'warehouse_name', 'invoice', 'nomenclature_code', 'nomenclature_name', 'accounting_group_name',
                         'accounting_group_code',
                         'quantity', 'price_unit_w_vat', 'sum_w_vat', 'vat_sum', 'vat_rate', 'seller_code',
                         'seller_name', 'seller_vat', 'le_name', 'nomenclature_type_code', 'nomenclature_type_name',
                         'uom_code', 'uom_name', 'client_nomenclature_code', 'client_nomenclature_name', 'tare_code',
                         'tare_name', 'quantity_per_pack', 'concept_name', 'concept_code', 'client_warehouse_name',
                         'client_warehouse_code', 'comment', 'picking_number', 'customs_number', 'alcohol_type_code',
                         'supplier_name', 'supplier_vat', 'supplier_code', 'date_due', 'paid_on',
                         'delivery_on_time', 'matching_order'],

    'purchase_picking_refund': ['date', 'invoice', 'is_confirmed', 'warehouse_code',
                                'warehouse_name', 'nomenclature_code', 'nomenclature_name',
                                'accounting_group_name', 'accounting_group_code',
                                'quantity', 'price_unit_w_vat', 'sum_w_vat', 'vat_sum',
                                'vat_rate', 'unit_prime_cost_wo_vat', 'prime_cost_wo_vat', 'vat_rate_sec',  # todo, check vat rate sec when we receive file with more data
                                'seller_code', 'seller_name', 'seller_vat',
                                'le_name', 'cash_flow_code', 'cash_flow_movement',
                                'expense_paper_code', 'expense_paper', 'client_vat',
                                'client_code', 'client_name', 'orig_invoice_date',
                                'orig_invoice_number', 'vat_inv', 'nomenclature_type_code',  # todo, check vat_inv
                                'nomenclature_type_name', 'uom_code',
                                'uom_name', 'concept_name', 'concept_code',
                                'comment', 'alcohol_type_code', 'supplier_name',
                                'supplier_vat', 'supplier_code'],


    'orders': ['line_date', 'line_number', 'is_valid', 'line_type', 'line_type_code', 'seller_code', 'seller_name',
               'seller_vat', 'le_name', 'concept_name', 'concept_code',	'shift_id', 'fixed_shift_id',
               'cash_register_number', 'cash_register_name', 'order_id', 'ext_order_id', 'receipt_id', 'line_datetime',
               'activity_type',	'activity_type_name', 'service_type_code',
               'service_type_name', 'nomenclature_code', 'nomenclature_name', 'accounting_group_code',
               'accounting_group_name',	'nomenclature_type_code', 'nomenclature_type_name', 'uom_id_code',
               'uom_id_name', 'dish_code', 'dish_name', 'price_unit', 'quantity', 'amount_total', 'discount_amount_pos',
               'vat_rate', 'vat_sum', 'payment_type_code', 'payment_type_name', 'payment_amount',
               'fixed_payment', 'counterpart_code', 'counterpart_name', 'discount_type_code', 'discount_type_name',
               'discount_amount', 'cancel_code', 'cancel_name',
               'service_assembly_name', 'service_assembly_code', 'comment', 'card_type',
                ],

    'inventory': ['date_inventory', 'number', 'is_valid', 'seller_code',
                  'seller_name', 'seller_vat', 'le_name',
                  'warehouse_code', 'warehouse_name', 'nomenclature_code',
                  'nomenclature_name', 'accounting_group_name', 'accounting_group_code',
                  'quantity', 'prime_cost_unit', 'prime_cost', 'vat_rate',
                  'deficit_account_code', 'deficit_account_name', 'abundance_account_code',
                  'abundance_account_name', 'nomenclature_type_code',
                  'nomenclature_type_name', 'uom_code', 'uom_name',
                  'balance_quantity', 'balance_sum', 'comment'
                  ],  # in this case abundance/deficit is balance

    'cash_flow_movements': ['date', 'number', 'transfer_amount', 'operation',
                            'debit_name', 'debit_code', 'debit_type',
                            'debit_partial_account_name', 'debit_partial_account_code',
                            'debit_organisation_vat',
                            'debit_organisation_code', 'debit_organisation_name',
                            'credit_name', 'credit_code', 'credit_type',
                            'credit_partial_account_name',
                            'credit_partial_account_code', 'credit_organisation_vat',
                            'credit_organisation_code',
                            'credit_organisation_name', 'seller_code',
                            'seller_name', 'seller_vat', 'le_name',
                            'concept_name', 'concept_code', 'comment'
                            ],

    'write_off_act': ['date', 'number', 'is_valid', 'warehouse_code',
                      'warehouse_name', 'nomenclature_code', 'nomenclature_name',
                      'accounting_group_name', 'accounting_group_code',
                      'quantity', 'prime_cost_unit_wo_vat', 'prime_cost_wo_vat',
                      'vat_rate', 'seller_code', 'seller_name',
                      'seller_vat', 'le_name', 'expense_paper',
                      'expense_paper_code', 'write_off_type', 'write_off_type_name',
                      'operation', 'operation_name', 'nomenclature_type_code',
                      'nomenclature_type_name', 'target_dish_code',
                      'target_dish_name', 'uom_code',
                      'uom_name', 'concept_name', 'concept_code',
                      'shift_id', 'cash_register_number', 'sold_dish_code',
                      'sold_dish_name',
                      'sold_dish_accounting_group_code',
                      'sold_dish_accounting_group_name', 'comment'
                      ],

    'realisation_act': ['date', 'number', 'is_valid', 'warehouse_code',
                        'warehouse_name', 'operation', 'operation_name',
                        'nomenclature_code', 'nomenclature_name',
                        'accounting_group_name', 'accounting_group_code',
                        'quantity', 'price_w_vat', 'sum_w_vat', 'vat_sum',
                        'sale_vat_rate', 'prime_cost_unit_wo_vat', 'prime_cost_wo_vat', 'vat_rate',
                        'seller_code', 'seller_name', 'seller_vat',
                        'le_name', 'write_off_type', 'write_off_type_name', 'cash_flow_code',
                        'cash_flow_movement', 'expense_paper_code', 'expense_paper',
                        'nomenclature_type_code',
                        'nomenclature_type_name', 'target_dish_code',
                        'target_dish_name',
                        'uom_code', 'uom_name', 'shift_id',
                        'cash_register_number',
                        'concept_name', 'concept_code', 'sold_dish_code',
                        'sold_dish_name',
                        'target_dish_accounting_group_code',
                        'target_dish_accounting_group_name', 'comment'
                        ],
}

xls_headers_mapping = {
    'invoice': ['Numeris', 'Data', 'Klientas', 'PVM kodas', 'Įm.kodas', 'Suma, €', 'PVM suma €', 'PVM tarifas,%']
}

pythonic_mapping_xls = {
    'invoice': ['number', 'date', 'client', 'client_vat_code', 'client_code', 'amount_total', 'amount_vat', 'vat_rate']
}


def pre_import_validator_xls(data):
    body = str()
    number = data.get('number', False)
    if not number:
        body += _('Nerastas saskaitos pavadinimas\n')

    date = data.get('date', False)
    if not date:
        body += _('Nerasta data\n')

    client = data.get('client', False)
    if not client:
        body += _('Nerastas klientas\n')

    client_code = data.get('client_code', False)
    if not client_code:
        body += _('Nerastas kliento kodas\n')

    amount_total = data.get('amount_total', False)
    if not amount_total:
        body += _('Nerasta galutinė suma\n')

    amount_total = data.get('amount_total', False)
    if not amount_total:
        body += _('Nerasta galutinė suma\n')

    amount_vat = data.get('amount_vat', False)
    if not amount_vat:
        body += _('Nerasta PVM suma\n')
    if body:
        body += 'Sąskaitos kūrimo klaida | %s eilutė Excel faile |' % data.get('row_number')
        _logger.info(body)
        return False
    return True


class IIkoXlsImportWizard(models.TransientModel):

    _name = 'iiko.xls.import.wizard'

    xls_data = fields.Binary(string='Excel failas', required=True)
    xls_name = fields.Char(string='Excel failo pavadinimas', size=128, required=False)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita')
    product_id = fields.Many2one('product.product', string='Naudojamas produktas')

    @api.multi
    def data_import(self):
        self.ensure_one()
        data = self.xls_data
        record_set = []
        try:
            wb = xlrd.open_workbook(file_contents=base64.decodestring(data))
        except XLRDError:
            raise exceptions.Warning(_('Netinkamas failo formatas!'))
        sheet = wb.sheets()[0]

        document_type = None
        data_row = False
        for row in range(sheet.nrows):
            if not data_row:
                for key in xls_headers_mapping.keys():
                    header_vals = xls_headers_mapping[key]
                    try:
                        value = sheet.cell(row, 0).value
                    except IndexError:
                        value = False
                    if value in header_vals:
                        matched = 0.0
                        for col in enumerate(header_vals):
                            try:
                                col_value = sheet.cell(row, col[0]).value
                            except IndexError:
                                col_value = False
                            if col_value in header_vals:
                                matched += 1.0
                        match_rate = matched / float(len(header_vals))
                        if match_rate > 0.8:  # todo, agree upon match rate
                            document_type = key
                            data_row = True
                    else:
                        continue
                continue
            col = 0
            record = {'row_number': str(row + 1)}
            for field in pythonic_mapping_xls[document_type]:
                try:
                    value = sheet.cell(row, col).value
                except IndexError:
                    value = False
                if field == 'date' and value:
                    value = datetime(*xlrd.xldate_as_tuple(value,
                                                           wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                record[field] = value
                col += 1
            record_set.append(record)

        if document_type is not None:
            if document_type == 'invoice':
                ext_invoices = self.create_records(record_set)
                ext_invoices = ext_invoices.filtered(lambda x: x.state == 'imported')
                ext_invoices.create_invoices()
        else:
            raise exceptions.Warning(_('Netinkamas duomenų tipas'))

    def create_records(self, record_set):
        invoice_ids = self.env['xls.iiko.invoice']
        for record in record_set:
            if not pre_import_validator_xls(record):
                continue

            invoice_lines = []
            line_vals = {
                'quantity': 1,
                'price_unit_w_vat': record.get('amount_total'),
                'vat_rate': record.get('vat_rate'),
                'amount_vat': record.get('amount_vat'),
                'amount_total': record.get('amount_total'),
            }
            invoice_lines.append((0, 0, line_vals))
            vals = {
                'number': record.get('number'),
                'date_invoice': record.get('date'),
                'amount_total': record.get('amount_total'),
                'amount_vat': record.get('amount_vat'),
                'partner_vat_code': record.get('client_vat_code'),
                'partner_name': record.get('client'),
                'partner_code': record.get('client_code'),
                'ext_invoice_line_ids': invoice_lines,
            }
            invoice = self.env['xls.iiko.invoice'].create(vals)
            invoice_ids += invoice
        invoice_ids.xls_invoice_validator()
        return invoice_ids


IIkoXlsImportWizard()


class BaseIIkoInvoiceLine(models.Model):
    _name = 'base.iiko.invoice.line'
    _inherit = ['mail.thread']

    quantity = fields.Float(string='Kiekis')
    price_unit_w_vat = fields.Float(string='Kaina')
    vat_rate = fields.Float(string='PVM procentas')
    amount_total = fields.Float(string='Sąskatos suma')
    amount_vat = fields.Float(string='PVM suma')
    tax_id = fields.Many2one('account.tax', string='Mokesčiai', compute='get_tax', store=True)
    product_id = fields.Many2one('product.product', string='Produktas',
                                 default=lambda self: self.env['product.product'].search(
                                     [('default_code', '=', 'IIKO-CONSUMED')], limit=1))

    state = fields.Selection([('imported', 'Objektas importuotas'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Objektas importuotas su įspėjimais')],
                             string='Būsena', track_visibility='onchange')
    line_type = fields.Char(compute='get_line_type')

    @api.multi
    def name_get(self):
        return [(x.id, 'Eilutė ' + str(x.id)) for x in self]

    @api.one
    @api.depends('amount_total', 'amount_vat')
    def get_line_type(self):
        if self.amount_total:
            self.line_type = 'out_invoice' if self.amount_total > 0 else 'in_invoice'
        elif self.amount_vat:
            self.line_type = 'out_invoice' if self.amount_vat > 0 else 'in_invoice'
        else:
            self.line_type = 'out_invoice'

    @api.one
    @api.depends('vat_rate', 'amount_vat', 'amount_total')
    def get_tax(self):
        if self.vat_rate:
            tax_id = self.env['account.tax'].search([('amount', '=', float(self.vat_rate)), ('type_tax_use', '=', 'sale'),
                                                     ('price_include', '=', True)], limit=1)
        else:
            tax_id = self.env['account.tax'].search(
                [('amount', '=', float(self.vat_rate)),
                 ('type_tax_use', '=', 'sale'),
                 ('nondeductible', '=', False)], limit=1)

        if not tax_id and self.amount_vat and self.amount_total:
            sum_wo_vat = self.amount_total - self.amount_vat
            percentage = round(((self.amount_total / sum_wo_vat) - 1) * 100, 0)
            tax_id = self.env['account.tax'].search([('amount', '=', percentage), ('type_tax_use', '=', 'sale'),
                                                     ('price_include', '=', False)], limit=1)
        self.tax_id = tax_id


BaseIIkoInvoiceLine()


class BaseIIkoInvoice(models.Model):
    _name = 'base.iiko.invoice'
    _inherit = ['mail.thread']

    number = fields.Char(string='Numeris')
    date_invoice = fields.Char(string='Sąskaitos data')
    partner_id = fields.Many2one('res.partner', string='Partneris')
    amount_total = fields.Float(string='Sąskatos suma')
    amount_vat = fields.Float(string='PVM suma')
    partner_vat_code = fields.Char(string='Partnerio pvm kodas')
    partner_code = fields.Char(string='Partnerio kodas', inverse='get_partner')
    partner_name = fields.Char(string='Partnerio vardas')
    state = fields.Selection([('imported', 'Objektas importuotas'),
                              ('created', 'Sąskaita sukurta sistemoje'),
                              ('failed', 'Klaida kuriant sąskaitą'),
                              ('warning', 'Objektas importuotas su įspėjimais')],
                             string='Būsena', track_visibility='onchange')
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita')

    @api.multi
    def name_get(self):
        return [(x.id, x.number) for x in self]

    @api.one
    def get_partner(self):
        partner_id = False
        if self.partner_code and self.partner_name:
            partner_id = self.env['res.partner'].search([('kodas', '=', self.partner_code)])
            if not partner_id and self.partner_vat_code:
                partner_id = self.env['res.partner'].search([('vat', '=', self.partner_vat_code)])
            if not partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': self.partner_name,
                    'is_company': True if self.partner_vat_code else False,
                    'kodas': self.partner_code,
                    'country_id': country_id.id,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')],
                        limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')],
                        limit=1).id,
                }
                partner_id = self.env['res.partner'].create(partner_vals)
        self.partner_id = partner_id

    def prep_values(self, rec):
        default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        account_obj = self.env['account.account']
        invoice_type = 'out_invoice' if rec.amount_total > 0 else 'out_refund'
        account_id = self.env['account.account'].search([('code', '=', '2410')])
        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'force_dates': True,
            'account_id': account_id.id,
            'partner_id': rec.partner_id.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': 'inc',
            'number': rec.number,
            'move_name': rec.number,
            'date_invoice': rec.date_invoice,
            'operacijos_data': rec.date_invoice,
            'imported_api': True,
        }
        for line in rec.ext_invoice_line_ids:
            product_id = line.product_id
            product_account = product_id.get_product_income_account(return_default=True)
            uom_id = product_id.product_tmpl_id.uom_id
            line_vals = {
                'product_id': product_id.id,
                'name': product_id.name,
                'quantity': 1,
                'price_unit': line.price_unit_w_vat,
                'uom_id': uom_id.id,
                'account_id': product_account.id,
                'invoice_line_tax_ids': [(6, 0, line.tax_id.ids)],
            }
            invoice_lines.append((0, 0, line_vals))
        return invoice_values

    @api.multi
    def create_invoices(self):
        recs = self.filtered(lambda x: not x.invoice_id)
        for rec in recs:
            invoice_obj = self.env['account.invoice']
            move_name = rec.number
            if move_name and invoice_obj.search_count([('number', '=', move_name)]):
                continue
            default_location = self.env['stock.location'].search([('usage', '=', 'internal')], order='create_date desc',
                                                                 limit=1)
            delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
            invoice_values = self.prep_values(rec)
            invoice_lines = invoice_values.pop('invoice_line_ids')
            try:
                invoice_id = invoice_obj.create(invoice_values)
                invoice_id.write({'invoice_line_ids': invoice_lines})
                for line in invoice_id.invoice_line_ids:
                    line.with_context(direct_trigger_amount_depends=True).onchange_amount_depends()
            except Exception as e:
                rec.write({'state': 'failed'})
                raise exceptions.Warning(_('Sąskaitos kūrimo klaida | klaidos pranešimas %s') % (str(e.args)))
            body = str()
            if tools.float_compare(rec.amount_total, abs(invoice_id.amount_total), precision_digits=2) != 0:
                diff = abs(invoice_id.amount_total - rec.amount_total)
                if diff > allowed_tax_calc_error:
                    body += _('Klaida kuriant sąskaitą | Sąskaitos suma nesutampa su paskaičiuota suma '
                              '(%s != %s). Numeris: %s') % \
                            (rec.amount_total, invoice_id.amount_total, rec.number)
            if body:
                raise exceptions.Warning(_(body))

            try:
                invoice_id.partner_data_force()
                invoice_id.with_context(skip_attachments=True).action_invoice_open()
            except Exception as e:
                raise exceptions.Warning(_('Nepavyko patvirtinti sąskaitos: %s. Numeris %s') %
                                         (str(e.args), move_name))

            rec.write({'state': 'created', 'invoice_id': invoice_id.id})
            rec.ext_invoice_line_ids.write({'state': 'created', 'invoice_id': invoice_id.id})

            rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
            if rec and rec.state in ['installed', 'to upgrade']:
                wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                    {'location_id': default_location.id})
                wizard_id.create_delivery()
                if invoice_id.picking_id:
                    invoice_id.picking_id.action_assign()
                    if invoice_id.picking_id.state == 'assigned':
                        invoice_id.picking_id.do_transfer()


BaseIIkoInvoice()


class IIkoGlobalProductMapping(models.Model):

    _name = 'iiko.global.product.mapping'

    name = fields.Char(string='Pavadinimas')
    accounting_group_code = fields.Char(string='Apskaitos grupė', readonly=False)
    product_id = fields.Many2one('product.template', string='Produktas')


IIkoGlobalProductMapping()


class XLSIIkoInvoiceLine(models.Model):
    _name = 'xls.iiko.invoice.line'
    _inherit = ['base.iiko.invoice.line']
    _description = 'Invoice Lines // XLS Import'

    ext_invoice_id = fields.Many2one('xls.iiko.invoice', string='Susijusi sąskaita faktūra')

    @api.one
    @api.depends('vat_rate', 'amount_vat', 'amount_total')
    def get_tax(self):
        if self.vat_rate:
            tax_id = self.env['account.tax'].search([('amount', '=', float(self.vat_rate)), ('type_tax_use', '=', 'sale'),
                                                     ('price_include', '=', True)], limit=1)
        else:
            tax_id = self.env['account.tax'].search(
                [('amount', '=', float(self.vat_rate)),
                 ('type_tax_use', '=', 'purchase'),
                 ('nondeductible', '=', False)], limit=1)

        if not tax_id and self.amount_vat and self.amount_total:
            sum_wo_vat = self.amount_total - self.amount_vat
            percentage = round(((self.amount_total / sum_wo_vat) - 1) * 100, 0)
            tax_id = self.env['account.tax'].search([('amount', '=', percentage), ('type_tax_use', '=', 'sale'),
                                                     ('price_include', '=', True)], limit=1)
        self.tax_id = tax_id


XLSIIkoInvoiceLine()


class XLSIIkoInvoice(models.Model):
    _name = 'xls.iiko.invoice'
    _inherit = ['base.iiko.invoice']
    _description = 'Invoice // XLS Import'

    ext_invoice_line_ids = fields.One2many('xls.iiko.invoice.line',
                                           'ext_invoice_id', string='Susijusi sąskaita faktūra')

    @api.multi
    def xls_invoice_validator(self):
        for rec in self:
            valid = True
            if not rec.partner_id:
                valid = False
            for line in rec.ext_invoice_line_ids:
                if not line.tax_id or not line.product_id:
                    valid = False
            rec.write({'state': 'imported'}) if valid else rec.write({'state': 'warning'})


XLSIIkoInvoiceLine()


class PPCSVIIkoInvoice(models.Model):
    _name = 'pp.csv.iiko.invoice'
    _inherit = ['base.iiko.invoice']
    _description = 'Invoice // CSV Purchase Picking Import'

    is_confirmed = fields.Boolean(string='Ar patvirtintas dokumentas')
    ext_number = fields.Char(string='Numeris')
    warehouse_code = fields.Char(string='Sandelis (kodas)')
    warehouse_name = fields.Char(string='Sandelis (pavadinimas)')
    seller_code = fields.Char(string='Prekybos įmone (kodas)')
    seller_name = fields.Char(string='Prekybos įmone (pavadinimas)')
    seller_vat = fields.Char(string='Jur.asm. (PVM kodas)')
    concept_code = fields.Char(string='Koncepcija (kodas)')
    concept_name = fields.Char(string='Koncepcija (pavadinimas)')
    ext_invoice_line_ids = fields.One2many('pp.csv.iiko.invoice.line', 'ext_invoice_id', string='Susijusi sąskaita')
    refund = fields.Boolean(default=False)

    # Fields used for refund invoices
    unit_prime_cost_wo_vat = fields.Float(string='Vnt. savikaina be PVM')
    prime_cost_wo_vat = fields.Float(string='Savikaina be PVM')
    orig_invoice_number = fields.Char(string='Pirkimo saskaita (numeris)')
    orig_invoice_date = fields.Date(string='Pirkimo saskaita (data)')

    @api.multi
    def validator(self):
        for rec in self:
            valid = True
            if not rec.partner_id:
                valid = False
            for line in rec.ext_invoice_line_ids:
                if not line.tax_id or not line.product_id or not line.uom_id:
                    valid = False
            rec.write({'state': 'imported'}) if valid else rec.write({'state': 'warning'})

    def prep_values(self, rec):
        default_journal = self.env['account.journal'].search([('type', '=', 'purchase')], limit=1)
        account_obj = self.env['account.account']
        invoice_type = 'in_refund' if rec.refund else 'in_invoice'
        account_id = self.env['account.account'].search([('code', '=', '4430')])
        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'account_id': account_id.id,
            'partner_id': rec.partner_id.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': 'inc',
            'reference': rec.number,
            'date_invoice': rec.date_invoice,
            'operacijos_data': rec.date_invoice,
        }

        total_price = 0.0
        line_ids = rec.ext_invoice_line_ids
        for product in line_ids.mapped('product_id'):
            product_map = line_ids.filtered(lambda x: x.product_id.id == product.id)
            for tax_id in product_map.mapped('tax_id'):
                corresponding = product_map.filtered(lambda x: x.tax_id.id == tax_id.id)
                for line in corresponding:
                    price = line.quantity * line.price_unit_w_vat
                    total_price += price

                product_id = corresponding[0].product_id
                product_account = product_id.get_product_expense_account(return_default=True)

                uom_id = product_id.product_tmpl_id.uom_id
                line_vals = {
                    'product_id': product_id.id,
                    'name': product_id.name,
                    'quantity': 1,
                    'price_unit': total_price,
                    'uom_id': uom_id.id,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                    'amount_depends': total_price,
                    'price_subtotal_make_force_step': True,
                    'price_subtotal_save_force_value': total_price,
                }
                invoice_lines.append((0, 0, line_vals))
                total_price = 0.0
        return invoice_values

    @api.multi
    def create_invoices(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'purchase_picking'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))
        else:
            super(PPCSVIIkoInvoice, self).create_invoices()


PPCSVIIkoInvoice()


class PPCSVIIkoInvoiceLine(models.Model):
    _name = 'pp.csv.iiko.invoice.line'
    _inherit = ['base.iiko.invoice.line']
    _description = "Sale/Purchase lines."

    uom_code = fields.Char(string='Produkto vienetai (kodas)')
    uom_name = fields.Char(string='Produkto vienetai (pavadinimas)')
    nomenclature_code = fields.Char(string='Nomenklatura (kodas)')
    nomenclature_name = fields.Char(string='Nomenklatura (pavadinimas)')
    accounting_group_code = fields.Char(string='Apskaitos grupe (kodas)', inverse='get_global_code')
    accounting_group_name = fields.Char(string='Apskaitos grupe (pavadinimas)')
    nomenclature_type_code = fields.Char(string='Nomenklaturos tipas (kodas)')
    nomenclature_type_name = fields.Char(string='Nomenklaturos tipas (pavadinimas)')
    ext_invoice_id = fields.Many2one('pp.csv.iiko.invoice', string='Susijusi sąskaita')
    vat_sum = fields.Float(string='PVM Suma')
    uom_id = fields.Many2one('product.uom', string='Vienetai', compute='get_uom', store=True)
    price_unit_static = fields.Float(string='Paduoda/Fikstuota vieneto kaina')
    product_id = fields.Many2one('product.product')
    global_mapping_id = fields.Many2one('iiko.global.product.mapping')
    tax_id = fields.Many2one('account.tax', string='Mokesčiai', compute='get_tax', store=True)

    @api.one
    def get_global_code(self):
        if self.accounting_group_code:
            if self.accounting_group_code == '1MP':
                self.accounting_group_code = re.sub('[^0-9]', '', self.accounting_group_code)
            global_mapping = self.env['iiko.global.product.mapping'].search([('accounting_group_code', '=', self.accounting_group_code)])
            self.global_mapping_id = global_mapping
            if global_mapping:
                self.product_id = global_mapping.product_id.product_variant_ids[0]

    @api.one
    @api.depends('uom_code', 'uom_name')
    def get_uom(self):
        if self.uom_code:
            mapping = {
                '4': 'Vnt.',
                '3': 'Litras(ai)',
                '2': 'kg'
            }
            name = mapping.get(self.uom_code, False)
            self.uom_id = self.env['product.uom'].search([('name', '=', name)])
        elif self.uom_name:
            self.uom_id = self.env['product.uom'].search([('name', 'ilike', self.uom_name)])

    @api.one
    @api.depends('vat_rate', 'amount_vat', 'amount_total', 'global_mapping_id')
    def get_tax(self):
        if self.global_mapping_id.accounting_group_code == '6':
            if self.vat_rate:
                tax_id = self.env['account.tax'].search(
                    [('amount', '=', float(self.vat_rate)), ('type_tax_use', '=', 'purchase'),
                     ('price_include', '=', True), ('nondeductible', '=', False)], limit=1)
            else:
                tax_id = self.env['account.tax'].search(
                        [('code', '=', 'PVM100'), ('type_tax_use', '=', 'purchase'),
                         ('price_include', '=', False)], limit=1)

        else:
            if self.vat_rate:
                tax_id = self.env['account.tax'].search([('amount', '=', float(self.vat_rate)), ('type_tax_use', '=', 'purchase'),
                                                         ('price_include', '=', True), ('nondeductible', '=', False)], limit=1)
            else:
                tax_id = self.env['account.tax'].search(
                    [('amount', '=', float(self.vat_rate)),
                     ('type_tax_use', '=', 'purchase'),
                     ('nondeductible', '=', False)], limit=1)

            if not tax_id and self.amount_vat and self.amount_total:
                sum_wo_vat = self.amount_total - self.amount_vat
                percentage = round(((self.amount_total / sum_wo_vat) - 1) * 100, 0)
                tax_id = self.env['account.tax'].search([('amount', '=', percentage), ('type_tax_use', '=', 'purchase'),
                                                         ('price_include', '=', True), ('nondeductible', '=', False)], limit=1)
        self.tax_id = tax_id


PPCSVIIkoInvoiceLine()


class OrderCSVIIkoLine(models.Model):

    _name = 'order.csv.iiko.line'
    _inherit = ['base.iiko.invoice.line']
    _description = "Sale/Purchase lines."

    is_valid = fields.Boolean(string='Ar patvirtintas dokumentas')
    ext_type = fields.Integer(string='Eilutės tipas') # todo ar reikia?
    seller_name = fields.Char(string='Prekybos įmone (pavadinimas)') # todo ar reikia?
    seller_vat = fields.Char(string='Jur.asm. (PVM kodas)') # todo ar reikia?
    seller_code = fields.Char(string='Prekybos įmone (kodas)') # todo ar reikia?
    shift_id = fields.Integer(string='Pamainos numeris')
    activity_type = fields.Char(string='Veiklos rūšis') # todo ar reikia?
    nomenclature_code = fields.Char(string='Nomenklatura (kodas)') # todo ar reikia?
    nomenclature_name = fields.Char(string='Nomenklatura (pavadinimas)') # todo ar reikia?
    accounting_group_code = fields.Char(string='Apskaitos grupe (kodas)', inverse='get_global_code')
    accounting_group_name = fields.Char(string='Apskaitos grupe (pavadinimas)')
    uom_code = fields.Char(string='Produkto vienetai (kodas)') # todo ar reikia?
    uom_name = fields.Char(string='Produkto vienetai (pavadinimas)') # todo ar reikia?
    nomenclature_type_code = fields.Char(string='Nomenklaturos tipas (kodas)') # todo ar reikia?
    nomenclature_type_name = fields.Char(string='Nomenklaturos tipas (pavadinimas)') # todo ar reikia?
    discount_amount = fields.Float(string='Nuolaidos suma')
    discount_amount_pos = fields.Float(string='Nuolaidos suma pozicijoms')
    line_number = fields.Integer(sting='Numeris')

    cash_register_number = fields.Char(string='Kasos aparato numeris', inverse='get_cash_register')
    cash_register_name = fields.Char(string='Kasos aparato pavadinimas', inverse='get_cash_register')
    cash_register_id = fields.Many2one('iiko.cash.register', string='Kasos aparatas')
    receipt_id = fields.Integer(string='Kvito nr.', inverse='get_order_invoice')
    line_date = fields.Datetime(string='Registravimo Data')
    nomenclature_text = fields.Char(string='Nomenklatūra (tekstas)')
    order_payment_ids = fields.Many2many('order.csv.iiko.payment', string='Susijęs mokėjimas')
    ext_order_id = fields.Char(inverse='get_payments', string='Užsakymo numeris')
    order_id = fields.Integer(string='Užsakymo numeris')

    invoice_line_id = fields.Many2one('account.invoice.line', string='Susijusi sąskaitos eilutė')
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita', compute='get_invoice', store=True)
    line_day = fields.Date(compute='get_line_day')
    partner_id = fields.Many2one('res.partner', compute='get_partner', string='Partneris', store=True)
    product_id = fields.Many2one('product.product')
    global_mapping_id = fields.Many2one('iiko.global.product.mapping')
    order_invoice_id = fields.Many2one('order.csv.iiko.invoice', string='Užsakymo sąskaita')

    corrected_line_id = fields.Many2one('account.invoice.line', string='Susijusi sąskaitos eilutė')
    corrected_invoice_id = fields.Many2one('account.invoice', string='Koreguota sąskaita',
                                           compute='get_invoice_corrected', store=True)

    refund_line_id = fields.Many2one('account.invoice.line', string='Susijusi sąskaitos eilutė')
    refund_invoice_id = fields.Many2one('account.invoice', string='Kreditinė sąskaita',
                                        compute='get_invoice_refund', store=True)

    discount = fields.Boolean(string='Nuolaida', default=False, inverse='get_global_code', readonly=True)

    @api.one
    @api.depends('corrected_line_id')
    def get_invoice_corrected(self):
        self.corrected_invoice_id = self.corrected_line_id.invoice_id

    @api.one
    @api.depends('refund_line_id')
    def get_invoice_refund(self):
        self.refund_invoice_id = self.refund_line_id.invoice_id

    @api.one
    def get_order_invoice(self):
        if self.receipt_id:
            order_invoice = self.env['order.csv.iiko.invoice'].search([('receipt_id', '=', self.receipt_id)])
            if order_invoice:
                if len(order_invoice) > 1:
                    raise exceptions.Warning(_('Rastos dvi sąskaitos su %s čekio numeriu!' % self.receipt_id))
                self.order_invoice_id = order_invoice

    @api.one
    @api.depends('invoice_line_id')
    def get_invoice(self):
        self.invoice_id = self.invoice_line_id.invoice_id

    @api.one
    def get_global_code(self):
        if self.discount:
            global_mapping = self.env['iiko.global.product.mapping'].search([('accounting_group_code', '=', 'DSCNT')])
            if global_mapping:
                self.product_id = global_mapping.product_id.product_variant_ids[0]
        else:
            if self.accounting_group_code:
                if self.accounting_group_code == '1MP':
                    self.accounting_group_code = re.sub('[^0-9]', '', self.accounting_group_code)
                global_mapping = self.env['iiko.global.product.mapping'].search([('accounting_group_code', '=', self.accounting_group_code)])
                self.global_mapping_id = global_mapping
                if global_mapping:
                    self.product_id = global_mapping.product_id.product_variant_ids[0]

    @api.multi
    def validator(self):
        self.recompute_fields()
        initial = self._context.get('initial', False)
        warning = self.env['order.csv.iiko.line']
        imported = self.env['order.csv.iiko.line']
        failed = self.env['order.csv.iiko.line']
        for rec in self:
            valid = True
            if not rec.partner_id:
                valid = False
            if not rec.tax_id:
                valid = False
            if not rec.product_id:
                valid = False
            if not rec.line_day:
                valid = False
            if not rec.cash_register_id:
                valid = False
            if valid:
                imported += rec
            elif not valid and initial:
                warning += rec
            else:
                failed += rec
        imported.write({'state': 'imported'})
        warning.write({'state': 'warning'})
        failed.write({'state': 'failed'})

    @api.multi
    def recompute_fields(self):
        self.get_partner()
        self.get_tax()
        self.get_line_day()
        self.get_line_type()

    @api.multi
    def name_get(self):
        return [(x.id, 'Eilutė ' + str(x.id)) for x in self]

    @api.one
    @api.depends('order_payment_ids.payment_type_id.partner_id', 'cash_register_id')
    def get_partner(self):
        partner_id = self.order_payment_ids.mapped('payment_type_id.partner_id')
        if len(partner_id) > 1:
            payment = max(self.order_payment_ids, key=lambda x: x.payment_amount)
            partner_id = payment.payment_type_id.partner_id
        if not partner_id:
            partner_id = self.cash_register_id.partner_id
        self.partner_id = partner_id

    @api.one
    @api.depends('line_date')
    def get_line_day(self):
        if self.line_date:
            self.line_day = self.line_date[:10]

    @api.one
    def get_payments(self):
        if self.ext_order_id:
            payments = self.env['order.csv.iiko.payment'].search([('ext_order_id', '=', self.ext_order_id)])
            self.write({'order_payment_ids': [(4, res.id) for res in payments]})

    @api.one
    def get_cash_register(self):
        register = False
        if self.cash_register_number:
            register = self.env['iiko.cash.register'].search([('cash_register_number', '=', self.cash_register_number)])
        if self.cash_register_name:
            register = self.env['iiko.cash.register'].search([('cash_register_name', '=', self.cash_register_name)])
        if not register:
            vals = {
                'cash_register_name': self.cash_register_name,
                'cash_register_number': self.cash_register_number,
            }
            register = self.env['iiko.cash.register'].create(vals)
        self.cash_register_id = register

    @api.multi
    def create_invoices_action(self):
        numbers = self.mapped('line_number')
        recs = self.env['order.csv.iiko.line'].search([('line_number', 'in', numbers)])
        recs.invoice_creation_prep()

    @api.multi
    def invoice_creation_prep(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'orders'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(
                _('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        self.validator()
        line_ids = self.filtered(
            lambda x: not x.invoice_id and not x.invoice_line_id and x.state in ['imported'])
        if line_ids:
            for register in line_ids.mapped('cash_register_id'):
                reg_map = line_ids.filtered(lambda x: x.cash_register_id.id == register.id)
                for partner in reg_map.mapped('partner_id'):
                    partner_map = line_ids.filtered(lambda x: x.partner_id.id == partner.id)
                    for day in set(partner_map.mapped('line_day')):
                        day_map = partner_map.filtered(lambda s_line: s_line.line_day == day)
                        for line_type in set(day_map.mapped('line_type')):
                            type_map = day_map.filtered(lambda s_line: s_line.line_type == line_type)
                            self.create_invoices(type_map)

    def create_invoices(self, line_ids):
        invoice_obj = self.env['account.invoice']
        default_location = self.env['stock.location'].search([('usage', '=', 'internal')], order='create_date desc',
                                                             limit=1)
        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
        default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        account_obj = self.env['account.account']
        invoice_type = line_ids[0].line_type
        account_id = self.env['account.account'].search([('code', '=', '2410')])
        invoice_lines = []
        invoice_values = {
            'external_invoice': True,
            'account_id': account_id.id,
            'partner_id': line_ids[0].partner_id.id,
            'journal_id': default_journal.id,
            'invoice_line_ids': invoice_lines,
            'type': invoice_type,
            'price_include_selection': 'inc',
            'date_invoice': line_ids[0].line_day,
            'operacijos_data': line_ids[0].line_day,
            'imported_api': True,
        }
        total_price = 0.0
        # group by tax
        line_price = 0.0

        discount_lines = line_ids.filtered(lambda x: x.discount)
        if discount_lines:
            batches = discount_lines.mapped('ext_order_id')
            for batch in batches:
                corresponding_lines = line_ids.filtered(lambda x: x.ext_order_id == batch)
                discount_checksum = 0.0
                for product in corresponding_lines.mapped('product_id'):
                    product_map = corresponding_lines.filtered(lambda x: x.product_id.id == product.id)
                    for tax_id in product_map.mapped('tax_id'):
                        corresponding = product_map.filtered(lambda x: x.tax_id.id == tax_id.id)
                        for line in corresponding:
                            price = line.quantity * line.price_unit_w_vat
                            if not line.discount:
                                total_price += price
                            price += line.discount_amount_pos
                            discount_checksum += line.discount_amount_pos
                            line_price += price
                        product_id = corresponding[0].product_id
                        reverse_sign = False
                        if product_id.default_code == 'IIKO-NUOLAIDOS':
                            reverse_sign = True

                        product_account = product_id.get_product_income_account(return_default=True)
                        line_vals = {
                            'product_id': product_id.id,
                            'name': product_id.name,
                            'quantity': 1,
                            'price_unit': line_price * -1 if reverse_sign else line_price,
                            'uom_id': product_id.product_tmpl_id.uom_id.id,
                            'account_id': product_account.id,
                            'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                            'order_line_ids': [(6, 0, corresponding.ids)],
                        }
                        invoice_lines.append((0, 0, line_vals))
                        line_price = 0.0
                discount_lines_f = corresponding_lines.filtered(lambda x: x.discount)
                batch_total_discount = sum(x.discount_amount for x in discount_lines_f)
                if tools.float_compare(discount_checksum, batch_total_discount, precision_digits=2) != 0:
                    raise exceptions.Warning(_('Paskaičiuotos nuolaidos ir nuolaidos eilutės sumos nesutampa! %s != %s.'
                                               ' Išorinis identifikatorius %s') %
                                             (str(discount_checksum), str(batch_total_discount), batch))
        else:
            for product in line_ids.mapped('product_id'):
                product_map = line_ids.filtered(lambda x: x.product_id.id == product.id)
                for tax_id in product_map.mapped('tax_id'):
                    corresponding = product_map.filtered(lambda x: x.tax_id.id == tax_id.id)
                    for line in corresponding:
                        price = line.quantity * line.price_unit_w_vat
                        line_price += price

                    product_id = corresponding[0].product_id
                    product_account = product_id.get_product_income_account(return_default=True)
                    line_vals = {
                        'product_id': product_id.id,
                        'name': product_id.name,
                        'quantity': 1,
                        'price_unit': line_price,
                        'uom_id': product_id.product_tmpl_id.uom_id.id,
                        'account_id': product_account.id,
                        'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                        'order_line_ids': [(6, 0, corresponding.ids)],
                    }
                    invoice_lines.append((0, 0, line_vals))
                    total_price += line_price
                    line_price = 0.0
        try:
            invoice_id = invoice_obj.create(invoice_values)
        except Exception as e:
            line_ids.write({'state': 'failed'})
            raise exceptions.Warning(_('Sąskaitos kūrimo klaida | klaidos pranešimas %s') % (str(e.args)))
        body = str()
        if tools.float_compare(total_price, abs(invoice_id.amount_total), precision_digits=2) != 0:
            diff = abs(invoice_id.amount_total - total_price)
            if diff > allowed_tax_calc_error:
                body += _('Klaida kuriant sąskaitą | Sąskaitos suma nesutampa su paskaičiuota suma '
                          '(%s != %s), Numeris: %s') % \
                        (total_price, invoice_id.amount_total, invoice_id.move_name)
        if body:
            raise exceptions.Warning(_(body))

        try:
            invoice_id.partner_data_force()
            invoice_id.action_invoice_open()
        except Exception as e:
            raise exceptions.Warning(_('Nepavyko patvirtinti sąskaitos | Administratoriai informuoti %s') %
                                     (str(e.args)))

        line_ids.write({'state': 'created'})
        rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
        if rec and rec.state in ['installed', 'to upgrade']:
            wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                {'location_id': default_location.id})
            wizard_id.create_delivery()
            if invoice_id.picking_id:
                invoice_id.picking_id.action_assign()
                if invoice_id.picking_id.state == 'assigned':
                    invoice_id.picking_id.do_transfer()


OrderCSVIIkoLine()


class OrderCSVIIkoInvoice(models.Model):
    _name = 'order.csv.iiko.invoice'
    _description = "Payments for order lines"
    _inherit = ['mail.thread']

    invoice_number = fields.Char(string='Sąskaitos numeris')
    date_invoice = fields.Date(string='Sąskaitos data')
    partner_name = fields.Char(string='Partnerio pavadinimas')
    partner_code = fields.Char(string='Partnerio kodas', inverse='get_partner')
    partner_vat = fields.Char(string='Partnerio PVM kodas')
    amount_total = fields.Float(string='Sąskaitos suma')
    receipt_id = fields.Integer(string='Kvito nr.', inverse='get_related_entries')
    amount_vat = fields.Float(string='PVM suma')

    partner_id = fields.Many2one('res.partner', string='Partneris')
    invoice_id = fields.Many2one('account.invoice', string='Sisteminė sąskaita')

    order_line_ids = fields.One2many('order.csv.iiko.line', 'order_invoice_id')
    order_payment_ids = fields.One2many('order.csv.iiko.payment', 'order_invoice_id')

    state = fields.Selection([('created', 'Sąskaita sukurta sistemoje.'),
                              ('warning', 'Importuota su ispėjimais.'),
                              ('failed', 'Klaida kuriant sąskaitą.'),
                              ('imported', 'Sąskaita importuota.'),
                              ('fix_children', 'Susijusios eilutės turi kitą saskaitą.'),
                              ], string='Būsena')

    @api.one
    def get_related_entries(self):
        if self.receipt_id:
            lines = self.env['order.csv.iiko.line'].search([('receipt_id', '=', self.receipt_id)])
            payments = self.env['order.csv.iiko.payment'].search([('receipt_id', '=', self.receipt_id)])
            self.write({'order_line_ids': [(4, res.id) for res in lines],
                        'order_payment_ids': [(4, res.id) for res in payments]})

    @api.multi
    def name_get(self):
        return [(x.id, 'Sąskaita ' + str(x.invoice_number)) for x in self]

    @api.one
    def get_partner(self):
        partner_id = False
        if self.partner_code and self.partner_name:
            partner_id = self.env['res.partner'].search([('kodas', '=', self.partner_code)])
            if not partner_id and self.partner_vat:
                partner_id = self.env['res.partner'].search([('vat', '=', self.partner_vat)])
            if not partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': self.partner_name,
                    'is_company': True if self.partner_vat else False,
                    'kodas': self.partner_code,
                    'country_id': country_id.id,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')],
                        limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')],
                        limit=1).id,
                }
                partner_id = self.env['res.partner'].create(partner_vals)
        self.partner_id = partner_id

    @api.multi
    def validator(self):
        recs = self.filtered(lambda x: not x.invoice_id)
        for rec in recs:
            if rec.order_line_ids:
                if not rec.partner_id or not rec.invoice_number:
                    rec.state = 'warning'
                    self.post_message(i_body='Importavimo įspėjimai, trūksta partnerio arba sąskaitos numerio',
                                      l_body='Susijusi sąskaita neturi partnerio arba sąskaitos numerio',
                                      state='warning', invoice=rec, lines=rec.order_line_ids)
                elif rec.order_line_ids.mapped('invoice_id'):
                    rec.state = 'fix_children'
                elif any(x.state in ['warning'] for x in rec.order_line_ids):
                    self.post_message(i_body='Importavimo įspėjimai, nesukonfigūruotos sąskaitos eilutės',
                                      state='warning', invoice=rec)
                else:
                    rec.state = 'imported'
            else:
                self.post_message(i_body='Importavimo įspėjimai, sąskaita neturi susijusių eilučių',
                                  state='warning', invoice=rec)

    @api.multi
    def invoice_creation_prep(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'orders_invoice'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(
                _('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        self.validator()
        rewrite_links = self.filtered(lambda x: x.state == 'fix_children' and not x.invoice_id)
        normal_invoices = self.filtered(lambda x: x.state == 'imported' and not x.invoice_id)
        if normal_invoices:
            normal_invoices.create_invoices()
        if rewrite_links:
            rewrite_links.with_context(rewrite_links=True).create_invoices()

    @api.multi
    def create_invoices(self):
        rewrite_links = self._context.get('rewrite_links', False)
        default_location = self.env['stock.location'].search([('usage', '=', 'internal')], order='create_date desc',
                                                             limit=1)
        delivery_wizard = self.env['invoice.delivery.wizard'].sudo()
        default_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        account_id = self.env['account.account'].search([('code', '=', '2410')])
        account_obj = self.env['account.account']
        for rec in self:
            invoice_obj = self.env['account.invoice']
            if rec.invoice_number and invoice_obj.search_count([('number', '=', rec.invoice_number)]):
                continue
            invoice_type = 'out_invoice' if rec.amount_total > 0 else 'out_refund'
            invoice_lines = []
            invoice_values = {
                'external_invoice': True,
                'account_id': account_id.id,
                'partner_id': rec.partner_id.id,
                'journal_id': default_journal.id,
                'invoice_line_ids': invoice_lines,
                'type': invoice_type,
                'price_include_selection': 'inc',
                'number': rec.invoice_number,
                'move_name': rec.invoice_number,
                'date_invoice': rec.date_invoice,
                'operacijos_data': rec.date_invoice,
                'imported_api': True,
            }

            line_ids = rec.order_line_ids
            if rewrite_links:
                key_name = 'corrected_order_line_ids'
            else:
                key_name = 'order_line_ids'
            total_price = 0.0
            # group by tax
            line_price = 0.0
            for product in line_ids.mapped('product_id'):
                product_map = line_ids.filtered(lambda x: x.product_id.id == product.id)
                for tax_id in product_map.mapped('tax_id'):
                    corresponding = product_map.filtered(lambda x: x.tax_id.id == tax_id.id)
                    for line in corresponding:
                        price = line.quantity * line.price_unit_w_vat
                        line_price += price

                    product_id = corresponding[0].product_id
                    product_account = product_id.get_product_income_account(return_default=True)
                    line_vals = {
                        'product_id': product_id.id,
                        'name': product_id.name,
                        'quantity': 1,
                        'price_unit': line_price,
                        'uom_id': product_id.product_tmpl_id.uom_id.id,
                        'account_id': product_account.id,
                        'invoice_line_tax_ids': [(6, 0, tax_id.ids)],
                        key_name: [(6, 0, corresponding.ids)],
                    }
                    invoice_lines.append((0, 0, line_vals))
                    total_price += line_price
                    line_price = 0.0
            try:
                invoice_id = invoice_obj.create(invoice_values)
            except Exception as e:
                line_ids.write({'state': 'failed'})
                rec.write({'state': 'failed'})
                raise exceptions.Warning(_('Sąskaitos kūrimo klaida | klaidos pranešimas %s') % (str(e.args)))
            body = str()

            if tools.float_compare(rec.amount_total, abs(invoice_id.amount_total), precision_digits=2) != 0:
                diff = abs(invoice_id.amount_total - total_price)
                if diff > allowed_tax_calc_error:
                    body += _('Klaida kuriant sąskaitą | Sąskaitos PVM suma nesutampa su paskaičiuota suma '
                              '(%s != %s), Numeris: %s') % \
                            (total_price, invoice_id.amount_total, rec.invoice_number)
            if body:
                raise exceptions.Warning(_(body))

            try:
                invoice_id.partner_data_force()
                invoice_id.action_invoice_open()
            except Exception as e:
                raise exceptions.Warning(_('Nepavyko patvirtinti sąskaitos | Administratoriai informuoti %s') %
                                         (str(e.args)))

            line_ids.write({'state': 'created'})
            rec.write({'invoice_id': invoice_id.id, 'state': 'created'})
            rec = self.sudo().env['ir.module.module'].search([('name', '=', 'robo_stock')])
            if rec and rec.state in ['installed', 'to upgrade']:
                wizard_id = delivery_wizard.with_context(invoice_id=invoice_id.id).create(
                    {'location_id': default_location.id})
                wizard_id.create_delivery()
                if invoice_id.picking_id:
                    invoice_id.picking_id.action_assign()
                    if invoice_id.picking_id.state == 'assigned':
                        invoice_id.picking_id.do_transfer()

            if rewrite_links:
                for line in invoice_lines:
                    line[2]['refund_order_line_ids'] = line[2].pop('corrected_order_line_ids')
                invoice_values = {
                    'external_invoice': True,
                    'account_id': account_id.id,
                    'partner_id': rec.partner_id.id,
                    'journal_id': default_journal.id,
                    'invoice_line_ids': invoice_lines,
                    'type': 'out_refund',
                    'price_include_selection': 'inc',
                    'number': 'K/' + rec.invoice_number,
                    'move_name': 'K/' + rec.invoice_number,
                    'date_invoice': rec.date_invoice,
                    'operacijos_data': rec.date_invoice,
                }
                try:
                    credit_invoice_id = self.env['account.invoice'].create(invoice_values)
                except Exception as e:
                    raise exceptions.Warning(_('Sąskaitos kūrimo klaida | klaidos pranešimas %s') % (str(e.args)))

                try:
                    credit_invoice_id.partner_data_force()
                    credit_invoice_id.action_invoice_open()
                except Exception as e:
                    raise exceptions.Warning(_('Nepavyko patvirtinti sąskaitos | Administratoriai informuoti %s') %
                                             (str(e.args)))

                credit_move = credit_invoice_id.move_id
                move_id = invoice_id.move_id
                line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == credit_invoice_id.account_id.id)
                line_ids |= credit_move.line_ids.filtered(
                    lambda r: r.account_id.id == invoice_id.account_id.id)
                if len(line_ids) > 1:
                    line_ids.with_context(reconcile_v2=True).reconcile()

    def post_message(self, lines=None,
                     l_body=None, state=None, invoice=None, i_body=None):
        if lines is None:
            lines = self.env['order.csv.iiko.line']
        if invoice is None:
            invoice = self.env['order.csv.iiko.invoice']
        if lines:
            msg = {'body': l_body}
            for line in lines:
                line.message_post(**msg)
            if state is not None:
                lines.write({'state': state})
        if invoice:
            msg = {'body': i_body}
            invoice.message_post(**msg)
            if state is not None:
                invoice.state = state


OrderCSVIIkoInvoice()


class OrderCSVIIkoPayment(models.Model):
    _name = 'order.csv.iiko.payment'
    _description = "Payments for order lines"

    order_line_ids = fields.Many2many('order.csv.iiko.line', string='Eilutės už kurias mokėta')
    ext_order_id = fields.Char(inverse='get_order_lines', string='Užsakymo numeris')
    payment_type_code = fields.Char(string='Mokėjimo tipo kodas', inverse='create_payment_type')
    payment_type_name = fields.Char(string='Mokėjimo tipo pavadinimas', inverse='create_payment_type')
    payment_type_id = fields.Many2one('iiko.payment.type', string='Mokėjimo tipas')
    payment_amount = fields.Float(string='Mokėjimo suma')
    fixed_payment = fields.Boolean(string='Fiksalinis mokėjimas')
    activity_type = fields.Char(string='Veiklos rūšis')
    payment_date = fields.Datetime(string='Mokėjimo data')
    receipt_id = fields.Integer(string='Kvito nr.', inverse='get_order_invoice')
    order_id = fields.Integer(string='Užsakymo numeris')
    cash_register_number = fields.Char(string='Kasos aparato numeris', inverse='get_cash_register')
    cash_register_name = fields.Char(string='Kasos aparato pavadinimas', inverse='get_cash_register')
    cash_register_id = fields.Many2one('iiko.cash.register', string='Kasos aparatas')
    shift_id = fields.Integer(string='Pamainos numeris')
    seller_name = fields.Char(string='Prekybos įmone (pavadinimas)')
    seller_vat = fields.Char(string='Jur.asm. (PVM kodas)')
    seller_code = fields.Char(string='Prekybos įmone (kodas)')
    is_valid = fields.Boolean(string='Patvirtintas dokumentas')
    ext_number = fields.Integer(string='Numeris')
    ext_type = fields.Integer(string='Eilutės tipas')
    has_entries = fields.Boolean(compute='get_has_entries')

    move_id = fields.Many2one('account.move', string='Žurnalo įrašas')
    state = fields.Selection([('open', 'Sukurta, Laukiama sudengimo'),
                              ('reconciled', 'Mokėjimas sudengtas'),
                              ('partially_reconciled', 'Mokėjimas sudengtas dalinai'),
                              ('active', 'Panaudojamas'),
                              ('warning', 'Trūksta konfigūracijos'),
                              ], string='Būsena', compute='set_state', store=True)
    residual = fields.Float(string='Mokėjimo likutis', compute='get_residual', store=True)
    reconciliation_move = fields.Many2one('account.move', string='Sudengimo įrašas')
    adaptive_payment = fields.Boolean(compute='is_adaptive_payment')
    adapted_payment_type = fields.Many2one('iiko.payment.type', compute='get_adapted_payment_type')
    order_invoice_id = fields.Many2one('order.csv.iiko.invoice', string='Užsakymo sąskaita')

    @api.one
    def get_order_invoice(self):
        if self.receipt_id:
            order_invoice = self.env['order.csv.iiko.invoice'].search([('receipt_id', '=', self.receipt_id)])
            if order_invoice:
                self.order_invoice_id = order_invoice

    @api.one
    @api.depends('adaptive_payment', 'reconciliation_move')
    def get_adapted_payment_type(self):
        if self.adaptive_payment and self.reconciliation_move:
            partner_id = self.reconciliation_move.partner_id
            self.adapted_payment_type = self.env['iiko.payment.type'].search([('partner_id', '=', partner_id.id)])

    @api.multi
    def recompute_fields(self):
        self.is_adaptive_payment()
        self.get_residual()
        self.set_state()
        self.get_has_entries()
        self.get_cash_register()
        self.get_adapted_payment_type()

    @api.one
    @api.depends('order_line_ids.order_payment_ids')
    def is_adaptive_payment(self):
        payment_group = self.order_line_ids.mapped('order_payment_ids')
        if len(payment_group) > 1:
            payment = max(payment_group, key=lambda x: x.payment_amount)
            if self.id != payment.id:
                self.adaptive_payment = True

    @api.multi
    def name_get(self):
        return [(rec.id, 'Mokėjimas ' + str(rec.ext_order_id)) for rec in self]

    @api.one
    @api.depends('payment_type_id.journal_id', 'move_id', 'residual', 'payment_type_id.partner_id')
    def set_state(self):
        if not self.move_id:
            if self.payment_type_id.journal_id and self.payment_type_id.partner_id:
                self.state = 'active'
            else:
                self.state = 'warning'
        else:
            if self.residual == self.payment_amount:
                self.state = 'open'
            elif self.residual == 0:
                self.state = 'reconciled'
            else:
                self.state = 'partially_reconciled'

    @api.one
    @api.depends('move_id', 'payment_amount',
                 'move_id.line_ids.currency_id', 'move_id.line_ids.amount_residual', 'adaptive_payment', 'reconciliation_move')
    def get_residual(self):
        account = self.env['account.account'].search([('code', '=', '2410')])
        if self.adaptive_payment:
            if self.reconciliation_move:
                residual = 0.0
                lines = self.reconciliation_move.line_ids.filtered(lambda x: x.account_id.id == account.id)
                if not lines:
                    self.residual = self.payment_amount
                else:
                    for line in lines:
                        if line.account_id.id == account.id:
                            residual += line.amount_residual
                    self.residual = abs(residual)
            else:
                self.residual = self.payment_amount
        else:
            if self.move_id:
                residual = 0.0
                lines = self.move_id.line_ids.filtered(lambda x: x.account_id.id == account.id)
                if not lines:
                    self.residual = self.payment_amount
                else:
                    for line in lines:
                        if line.account_id.id == account.id:
                            residual += line.amount_residual
                    self.residual = abs(residual)
            else:
                self.residual = self.payment_amount

    @api.one
    @api.depends('order_line_ids')
    def get_has_entries(self):
        if self.order_line_ids.mapped('invoice_id'):
            self.has_entries = True
        else:
            self.has_entries = False

    @api.one
    def get_cash_register(self):
        register = False
        if self.cash_register_number:
            register = self.env['iiko.cash.register'].search([('cash_register_number', '=', self.cash_register_number)])
        if self.cash_register_name:
            register = self.env['iiko.cash.register'].search([('cash_register_name', '=', self.cash_register_name)])
        if not register:
            vals = {
                'cash_register_name': self.cash_register_name,
                'cash_register_number': self.cash_register_number,
            }
            register = self.env['iiko.cash.register'].create(vals)
        self.cash_register_id = register

    @api.one
    def get_order_lines(self):
        if self.ext_order_id:
            order_lines = self.env['order.csv.iiko.line'].search([('ext_order_id', '=', self.ext_order_id)])
            self.write({'order_line_ids': [(4, res.id) for res in order_lines]})

    @api.one
    def create_payment_type(self):
        payment_journal_mapping = {
            13: 'IKWOLT',
            5: 'IKCSH',
            11: 'IKCRD',
            '13': 'IKWOLT',
            '5': 'IKCSH',
            '11': 'IKCRD'
        }
        payment_type_id = False
        if self.payment_type_code:
            payment_type_id = self.env['iiko.payment.type'].search(
                [('payment_type_code', '=', self.payment_type_code)])

        if not payment_type_id and self.payment_type_name:
            payment_type_id = self.env['iiko.payment.type'].search(
                [('payment_type_name', '=', self.payment_type_name)])

        if not payment_type_id:
            journal_code = payment_journal_mapping.get(self.payment_type_code, False)
            if journal_code:
                journal_id = self.env['account.journal'].search([('code', '=', journal_code)], limit=1).id
            else:
                journal_id = False
            payment = {
                'payment_type_code': self.payment_type_code,
                'payment_type_name': self.payment_type_name,
                'journal_id': journal_id,
                'do_reconcile': True,
            }
            self.payment_type_id = self.env['iiko.payment.type'].create(payment)
        else:
            self.payment_type_id = payment_type_id

    @api.multi
    def move_creation_prep(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'orders'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(
                _('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        payment_ids = self.filtered(
            lambda x: not x.move_id and x.state in ['active'] and x.payment_type_id.is_active)
        reconcile = payment_ids.filtered(lambda x: x.payment_type_id.do_reconcile)
        not_reconcile = payment_ids.filtered(lambda x: not x.payment_type_id.do_reconcile)

        if reconcile:
            self.with_context(do_reconcile=True).create_moves(reconcile)
        if not_reconcile:
            self.with_context(do_reconcile=False).create_moves(not_reconcile)

    def create_moves(self, payment_ids):
        do_reconcile = self._context.get('do_reconcile', False)
        account_code = self._context.get('account_code', '2410')

        account_move_obj = self.env['account.move'].sudo()
        for payment in payment_ids:
            if tools.float_is_zero(payment.payment_amount, precision_digits=2):
                continue
            partner_id = payment.payment_type_id.partner_id.id
            account = self.env['account.account'].search([('code', '=', account_code)])
            move_lines = []
            credit_line = {
                'name': 'Mokėjimas ' + str(payment.ext_order_id),
            }
            if payment.payment_amount > 0:
                credit_line['credit'] = payment.payment_amount
                credit_line['debit'] = 0.0
                credit_line['account_id'] = account.id
            else:
                credit_line['debit'] = payment.payment_amount
                credit_line['credit'] = 0.0
                credit_line['account_id'] = account.id

            debit_line = {
                'name': 'Mokėjimas ' + str(payment.ext_order_id),
            }
            if payment.payment_amount > 0:
                debit_line['debit'] = payment.payment_amount
                debit_line['credit'] = 0.0
                debit_line['account_id'] = payment.payment_type_id.journal_id.default_debit_account_id.id
            else:
                debit_line['credit'] = payment.payment_amount
                debit_line['debit'] = 0.0
                debit_line['account_id'] = payment.payment_type_id.journal_id.default_credit_account_id.id

            credit_line['partner_id'] = partner_id
            debit_line['partner_id'] = partner_id
            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': payment.payment_type_id.journal_id.id,
                'date': payment.payment_date,
            }
            move_id = account_move_obj.create(move_vals)
            move_id.post()
            payment.move_id = move_id.id
            if do_reconcile and payment.payment_type_id.do_reconcile and not payment.adaptive_payment:
                payment.get_residual()
                if payment.residual:
                    invoice_ids = payment.order_line_ids.mapped('invoice_id').filtered(lambda x: x.residual > 0)
                    for invoice_id in invoice_ids:
                        if payment.payment_type_id.partner_id.id == invoice_id.partner_id.id:
                            line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice_id.account_id.id)
                            line_ids |= invoice_id.move_id.line_ids.filtered(lambda r: r.account_id.id == invoice_id.account_id.id)
                            if len(line_ids) > 1:
                                line_ids.with_context(reconcile_v2=True).reconcile()
                            payment.get_residual()
            self.env.cr.commit()

    @api.multi
    def re_reconcile(self):
        self.get_has_entries()
        payment_ids = self.filtered(
            lambda x: x.move_id and x.state in ['open', 'partially_reconciled'] and
                      x.payment_type_id.is_active and x.has_entries)

        non_adaptive = payment_ids.filtered(lambda x: not x.adaptive_payment)
        adaptive = payment_ids.filtered(lambda x: x.adaptive_payment and x.reconciliation_move)

        for payment in non_adaptive:
            payment.get_residual()
            move_id = payment.move_id
            if payment.residual:
                invoice_ids = payment.order_line_ids.mapped('invoice_id').filtered(lambda x: x.residual > 0)
                for invoice_id in invoice_ids:
                    if payment.payment_type_id.partner_id.id == invoice_id.partner_id.id:
                        line_ids = move_id.line_ids.filtered(lambda r: r.account_id.id == invoice_id.account_id.id)
                        line_ids |= invoice_id.move_id.line_ids.filtered(
                            lambda r: r.account_id.id == invoice_id.account_id.id)
                        if len(line_ids) > 1:
                            line_ids.with_context(reconcile_v2=True).reconcile()

        # reconcile adaptive payments
        for payment in adaptive:
            payment.get_residual()
            payment.get_adapted_payment_type()
            if payment.residual:
                invoice_ids = payment.order_line_ids.mapped('invoice_id').filtered(lambda x: x.residual > 0)
                for invoice_id in invoice_ids:
                    if payment.adapted_payment_type.partner_id.id == invoice_id.partner_id.id and \
                            payment.adapted_payment_type.do_reconcile:
                        line_ids = payment.reconciliation_move.line_ids.filtered(lambda r: r.account_id.id == invoice_id.account_id.id)
                        line_ids |= invoice_id.move_id.line_ids.filtered(
                            lambda r: r.account_id.id == invoice_id.account_id.id)
                        if len(line_ids) > 1:
                            line_ids.with_context(reconcile_v2=True).reconcile()

    @api.multi
    def adjust_multi_payments(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'orders'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        lines = self.env['order.csv.iiko.line'].search([('order_payment_ids.move_id', '!=', False)])
        multi_payment_order_lines = lines.filtered(lambda x: len(x.order_payment_ids) > 1)
        for line in multi_payment_order_lines:
            if len(line.mapped('order_payment_ids.payment_type_id')) > 1:
                line.order_payment_ids.get_has_entries()
                parent_payment = max(line.order_payment_ids, key=lambda x: x.payment_amount)
                account = parent_payment.payment_type_id.journal_id.default_debit_account_id
                child_payments = line.order_payment_ids.filtered(
                    lambda x: x.id != parent_payment.id and x.state in ['open', 'partially_reconciled'])
                if not parent_payment.move_id or not all(x.move_id for x in child_payments):
                    continue
                for payment in child_payments:
                    if payment.reconciliation_move:
                        continue
                    account = self.env['account.account'].search([('code', '=', '2410')])
                    line_id = payment.move_id.line_ids.filtered(
                        lambda r: r.account_id.id == account.id)
                    orig_line = {
                        'name': 'Mokėjimo tipo keitimas ' + str(payment.ext_order_id),
                        'debit': line_id.credit,
                        'credit': line_id.debit,
                        'account_id': line_id.account_id.id,
                        'partner_id': line_id.partner_id.id
                    }
                    changed_line = {
                        'name': 'Mokėjimo tipo keitimas ' + str(payment.ext_order_id),
                        'debit': line_id.debit,
                        'credit': line_id.credit,
                        'account_id': line_id.account_id.id,
                        'partner_id': parent_payment.payment_type_id.partner_id.id
                    }

                    move_lines = [(0, 0, orig_line), (0, 0, changed_line)]
                    move_vals = {
                        'line_ids': move_lines,
                        'journal_id': parent_payment.payment_type_id.journal_id.id,
                        'date': payment.payment_date,
                    }
                    reconciliation_move = self.env['account.move'].create(move_vals)
                    reconciliation_move.post()

                    payment.reconciliation_move = reconciliation_move.id
                    new_partner_id = parent_payment.payment_type_id.partner_id
                    orig_partner_id = payment.payment_type_id.partner_id

                    # reconcile new and old move
                    move_id = payment.move_id
                    line_ids = reconciliation_move.line_ids.filtered(
                        lambda r: r.account_id.id == account.id and r.partner_id.id == orig_partner_id.id)
                    line_ids |= move_id.line_ids.filtered(
                        lambda r: r.account_id.id == account.id and r.partner_id.id == orig_partner_id.id)
                    if len(line_ids) > 1:
                        line_ids.with_context(reconcile_v2=True).reconcile()

                    # reconcile new move with invoices
                    if parent_payment.payment_type_id.do_reconcile:
                        payment.get_residual()
                        if payment.residual:
                            invoice_ids = payment.order_line_ids.mapped('invoice_id').filtered(lambda x: x.residual > 0)
                            for invoice_id in invoice_ids:
                                line_ids = reconciliation_move.line_ids.filtered(
                                    lambda r: r.account_id.id == invoice_id.account_id.id and r.partner_id.id == new_partner_id.id)
                                line_ids |= invoice_id.move_id.line_ids.filtered(
                                    lambda r: r.account_id.id == invoice_id.account_id.id and r.partner_id.id == new_partner_id.id)
                                if len(line_ids) > 1:
                                    line_ids.with_context(reconcile_v2=True).reconcile()
                                payment.get_residual()


class IIkoCashRegister(models.Model):
    _name = 'iiko.cash.register'

    cash_register_number = fields.Char(required=True, string='Kasos aparato numeris')
    cash_register_name = fields.Char(string='Kasos aparato pavadinimas', inverse='create_partner')
    location_id = fields.Many2one('stock.location',
                                  default=lambda self: self.env['stock.location'].search(
                                      [('usage', '=', 'internal')], order='create_date desc', limit=1),
                                  domain="[('usage','=','internal')]", string='Kasos aparato lokacija')
    partner_id = fields.Many2one('res.partner', string='Susijęs partneris')

    @api.multi
    def name_get(self):
        return [(rec.id, str(rec.cash_register_name)) for rec in self]

    @api.one
    def create_partner(self):
        self.partner_id = self.env['res.partner'].search([('kodas', '=', self.cash_register_name)])
        if not self.partner_id:
            country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
            partner_vals = {
                'name': self.cash_register_name + ' Kasos operacijos',
                'is_company': True,
                'kodas': self.cash_register_name,
                'country_id': country_id.id,
                'property_account_receivable_id': self.env['account.account'].sudo().search(
                    [('code', '=', '2410')], limit=1).id,
                'property_account_payable_id': self.env['account.account'].sudo().search(
                    [('code', '=', '4430')], limit=1).id,
            }
            self.write({'partner_id': self.env['res.partner'].sudo().create(partner_vals).id})
        else:
            self.partner_id.name = self.cash_register_name + ' Kasos operacijos'
            self.partner_id.kodas = self.cash_register_name


IIkoCashRegister()


class IIkoPaymentType(models.Model):
    _name = 'iiko.payment.type'

    payment_type_code = fields.Integer(string='Mokėjimo tipo kodas', inverse='create_partner')
    payment_type_name = fields.Char(string='Mokėjimo tipo pavadinimas', inverse='create_partner')
    is_active = fields.Boolean(string='Aktyvus', default=True)
    do_reconcile = fields.Boolean(string='Automatiškai dengti sąskaitas', default=True)
    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas', inverse='set_state')
    partner_id = fields.Many2one('res.partner', string='Susietas partneris')
    state = fields.Selection([('active', 'Veikiantis'),
                              ('warning', 'Trūksta konfigūracijos')], string='Būsena', compute='set_state', store=True)

    @api.multi
    def recompute_fields(self):
        self.force_journal()

    @api.multi
    def force_journal(self):
        payment_journal_mapping = {
            13: 'IKWOLT',
            5: 'IKCSH',
            11: 'IKCRD'
        }
        for rec in self:
            if not rec.journal_id:
                journal_code = payment_journal_mapping.get(rec.payment_type_code, False)
                if journal_code:
                    journal_id = self.env['account.journal'].search([('code', '=', journal_code)], limit=1).id
                else:
                    journal_id = False
                rec.journal_id = journal_id

    @api.multi
    def name_get(self):
        return [(rec.id, str(rec.payment_type_name)) for rec in self]

    @api.one
    @api.depends('journal_id', 'partner_id')
    def set_state(self):
        if not self.journal_id or not self.partner_id:
            self.state = 'warning'
        else:
            self.state = 'active'

    @api.one
    def create_partner(self):
        if self.payment_type_name and self.payment_type_code and not self.partner_id:
            code = str(self.payment_type_code) + 'DramaburgerPartner'
            self.partner_id = self.env['res.partner'].search([('kodas', '=', code)])
            if not self.partner_id:
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': self.payment_type_name + '// Partneris',
                    'is_company': True,
                    'kodas': code,
                    'country_id': country_id.id,
                    'property_account_receivable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '2410')], limit=1).id,
                    'property_account_payable_id': self.env['account.account'].sudo().search(
                        [('code', '=', '4430')], limit=1).id,
                }
                self.write({'partner_id': self.env['res.partner'].sudo().create(partner_vals).id})

    @api.multi
    def write(self, vals):
        if 'payment_type_code' in vals:
            vals.pop('payment_type_code')
        if 'payment_type_name' in vals:
            vals.pop('payment_type_name')
        return super(IIkoPaymentType, self).write(vals)

    @api.one
    def set_state(self):
        if self.journal_id:
            self.state = 'active'
        else:
            self.state = 'warning'

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti mokėjimo tipo!'))
        return super(IIkoPaymentType, self).unlink()


IIkoPaymentType()


class IIkoCSVBaseActLine(models.Model):
    _name = 'iiko.csv.base.act.line'
    _description = 'Fields Shared between Inventory, Realisation Act and Writeoff Act'

    date = fields.Datetime(string='Data')
    number = fields.Char(string='Numeris')
    is_valid = fields.Boolean(string='Patvirtintas')
    warehouse_code = fields.Char(string='Sandėlio kodas')
    warehouse_name = fields.Char(string='Sandėlio pavadinimas')
    seller_code = fields.Char(string='Pardavėjo kodas')
    seller_name = fields.Char(string='Pardavėjo pavadinimas')
    seller_vat = fields.Char(string='Pardavėjo PVM')
    nomenclature_code = fields.Char(string='Nomenklatūros kodas')
    nomenclature_name = fields.Char(string='Nomeklatūros pavadinimas')
    accounting_group_name = fields.Char(string='Apskaitos grupės pavadinimas')
    accounting_group_code = fields.Char(string='Apskaitos grupės kodas', inverse='get_global_code')
    quantity = fields.Float(string='Kiekis')
    vat_rate = fields.Float(string='PVM tarifas')
    nomenclature_type_code = fields.Char(string='Nomeklatūros tipo kodas')
    nomenclature_type_name = fields.Char(string='Nomeklatūros tipo pavadinimas')
    uom_code = fields.Char(string='Matavimo vieneto kodas')
    uom_name = fields.Char(string='Matavimo vieneto pavadinimas')

    product_id = fields.Many2one('product.product', string='Produktas')
    global_mapping_id = fields.Many2one('iiko.global.product.mapping', string='Kategorija')
    line_day = fields.Date(compute='get_line_day')

    @api.one
    def get_global_code(self):
        if self.accounting_group_code:
            if self.accounting_group_code == '1MP':
                self.accounting_group_code = re.sub('[^0-9]', '', self.accounting_group_code)
            global_mapping = self.env['iiko.global.product.mapping'].search([('accounting_group_code', '=', self.accounting_group_code)])
            self.global_mapping_id = global_mapping
            if global_mapping:
                self.product_id = global_mapping.product_id.product_variant_ids[0]

    @api.one
    @api.depends('date')
    def get_line_day(self):
        if self.date:
            date_dt = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(hours=3)
            self.line_day = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)


IIkoCSVBaseActLine()


class IIkoCSVInventoryLine(models.Model):
    _name = 'iiko.csv.inventory.line'
    _inherit = ['iiko.csv.base.act.line']

    prime_cost_unit = fields.Float(string='Vieneto savikaina')
    prime_cost = fields.Float(string='Savikaina')
    deficit_account_code = fields.Char(string='Trūkumų sąskaitos kodas')
    deficit_account_name = fields.Char(string='Trūmumų sąskaitos pavadinimas')
    abundance_account_code = fields.Char(string='Pertėkliaus sąskaitos kodas')
    abundance_account_name = fields.Char(string='Pertėkliaus sąskaitos pavadinimas')
    balance_quantity = fields.Float(string='Pertekliaus/Trūkumo kiekis')
    balance_sum = fields.Float(string='Pertekliaus/Trūkumo suma')
    act_move_id = fields.Many2one('iiko.csv.act.move', string='Tėvinis įrašas')
    move_id = fields.Many2one('account.move', string='Įrašas apskaitoje', compute='get_move_id', store=True)

    state = fields.Selection([('waiting', 'Laukiama įtraukimo'),
                              ('active', 'Įtrauka į tėvinį įrašą'),
                              ('created', 'Buhalterinis įrašas sukurtas')], string='Būsena', compute='set_state', store=True)

    @api.one
    @api.depends('act_move_id', 'move_id')
    def set_state(self):
        if self.move_id:
            self.state = 'created'
        else:
            if self.act_move_id:
                self.state = 'active'
            else:
                self.state = 'waiting'

    @api.multi
    def name_get(self):
        return [(x.id, 'Inventorizacijos akto eilutė ' + str(x.id)) for x in self]

    @api.one
    @api.depends('act_move_id.move_id')
    def get_move_id(self):
        self.move_id = self.act_move_id.move_id

    @api.multi
    def create_parent_acts(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'inventory'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        self.get_move_id()
        self.get_global_code()
        acts = self.env['iiko.csv.act.move']
        no_move_lines = self.filtered(lambda x: not x.move_id)
        for global_type in no_move_lines.mapped('global_mapping_id'):
            global_map = no_move_lines.filtered(lambda x: x.global_mapping_id.id == global_type.id)
            for day in set(global_map.mapped('line_day')):
                day_map = global_map.filtered(lambda s_line: s_line.line_day == day)
                vals = {
                    'date': day,
                    'inventory_line_ids': [(6, 0, day_map.ids)],
                    'act_type': 'inventory',
                    'global_mapping_id': global_type.id,
                }
                act = self.env['iiko.csv.act.move'].create(vals)
                acts += act
        acts.prepare_moves()


IIkoCSVInventoryLine()


class IIkoCSVWriteOffActLine(models.Model):
    _name = 'iiko.csv.writeoff.act.line'
    _inherit = ['iiko.csv.base.act.line']

    prime_cost_unit_wo_vat = fields.Float(string='Vieneto savikaina')
    prime_cost_wo_vat = fields.Float(string='Savikaina')
    expense_paper = fields.Char(string='Išlaidų straipsnis')
    expense_paper_code = fields.Char(string='Išlaidų straipsnio kodas')
    write_off_type = fields.Char(string='Nurašymo tipas')
    write_off_type_name = fields.Char(string='Nurašymo tipo pavadinimas')
    operation = fields.Char(string='Operacija')
    operation_name = fields.Char(string='Operacijos pavadinimas')
    target_dish_code = fields.Char(string='Tikslinio patiekalo kodas')
    target_dish_name = fields.Char(string='Tikslinio patiekalo pavadinimas')
    concept_name = fields.Char(string='Koncepcijos pavadinimas')
    concept_code = fields.Float(string='Koncepcijos kodas')
    shift_id = fields.Float(string='Pamainos numeris')
    cash_register_number = fields.Char(string='Kasos aparato numeris')
    sold_dish_code = fields.Char(string='Parduoto patiekalo kodas')
    sold_dish_name = fields.Char(string='Parduoto patiekalo pavadinimas')
    sold_dish_accounting_group_code = fields.Char(string='Parduoto patiekalo apskaitos grupės kodas')
    sold_dish_accounting_group_name = fields.Char(string='Parduoto patiekalo apskaitos grupės kodas')
    act_move_id = fields.Many2one('iiko.csv.act.move', string='Tėvinis įrašas')
    move_id = fields.Many2one('account.move', string='Įrašas apskaitoje', compute='get_move_id', store=True)

    state = fields.Selection([('waiting', 'Laukiama įtraukimo'),
                              ('active', 'Įtrauka į tėvinį įrašą'),
                              ('created', 'Buhalterinis įrašas sukurtas')], string='Būsena', compute='set_state', store=True)

    @api.one
    @api.depends('act_move_id', 'move_id')
    def set_state(self):
        if self.move_id:
            self.state = 'created'
        else:
            if self.act_move_id:
                self.state = 'active'
            else:
                self.state = 'waiting'

    @api.multi
    def name_get(self):
        return [(x.id, 'Nurašymo akto eilutė ' + str(x.id)) for x in self]

    @api.one
    @api.depends('act_move_id.move_id')
    def get_move_id(self):
        self.move_id = self.act_move_id.move_id

    @api.multi
    def create_parent_acts(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'write_off_act'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        self.get_move_id()
        self.get_global_code()
        acts = self.env['iiko.csv.act.move']
        no_move_lines = self.filtered(lambda x: not x.move_id)
        for global_type in no_move_lines.mapped('global_mapping_id'):
            global_map = no_move_lines.filtered(lambda x: x.global_mapping_id.id == global_type.id)
            for day in set(global_map.mapped('line_day')):
                day_map = global_map.filtered(lambda s_line: s_line.line_day == day)
                vals = {
                    'date': day,
                    'writeoff_line_ids': [(6, 0, day_map.ids)],
                    'act_type': 'writeoff',
                    'global_mapping_id': global_type.id,
                }
                act = self.env['iiko.csv.act.move'].create(vals)
                acts += act
            acts.prepare_moves()


IIkoCSVWriteOffActLine()


class IIkoCSVRealisationActLine(models.Model):
    _name = 'iiko.csv.realisation.act.line'
    _inherit = ['iiko.csv.base.act.line']

    operation = fields.Char(string='Operacija')
    operation_name = fields.Char(string='Operacijos pavadinimas')
    price_w_vat = fields.Float(string='Kaina su PVM')
    sum_w_vat = fields.Float(string='Suma su PVM')
    vat_sum = fields.Float(string='PVM suma')
    sale_vat_rate = fields.Float(string='Pardavimo PVM tarifas')
    prime_cost_unit_wo_vat = fields.Float(string='Vieneto Savikaina be PVM')
    prime_cost_wo_vat = fields.Float(string='Savikaina be PVM')
    cash_flow_code = fields.Char(string='Pinigų srautų kodas')
    cash_flow_movement = fields.Char(string='Pinigų srautų judėjimas')
    expense_paper = fields.Char(string='Išlaidų straipsnis')
    expense_paper_code = fields.Char(string='Išlaidų straipsnio kodas')
    write_off_type = fields.Char(string='Nurašymo tipas')
    write_off_type_name = fields.Char(string='Nurašymo tipo pavadinimas')
    target_dish_code = fields.Char(string='Tikslinio patiekalo kodas')
    target_dish_name = fields.Char(string='Tikslinio patiekalo pavadinimas')
    concept_name = fields.Char(string='Koncepcijos pavadinimas')
    concept_code = fields.Float(string='Koncepcijos kodas')
    shift_id = fields.Float(string='Pamainos numeris')
    cash_register_number = fields.Char(string='Kasos aparato numeris')
    sold_dish_code = fields.Char(string='Parduoto patiekalo kodas')
    sold_dish_name = fields.Char(string='Parduoto patiekalo pavadinimas')
    target_dish_accounting_group_code = fields.Char(string='Tikslinio patiekalo apskaitos grupės kodas')
    target_dish_accounting_group_name = fields.Char(string='Tikslinio patiekalo apskaitos grupės kodas')
    act_move_id = fields.Many2one('iiko.csv.act.move', string='Tėvinis įrašas')
    move_id = fields.Many2one('account.move', string='Įrašas apskaitoje', compute='get_move_id', store=True)

    state = fields.Selection([('waiting', 'Laukiama įtraukimo'),
                              ('active', 'Įtrauka į tėvinį įrašą'),
                              ('created', 'Buhalterinis įrašas sukurtas')], string='Būsena', compute='set_state', store=True)

    @api.one
    @api.depends('act_move_id', 'move_id')
    def set_state(self):
        if self.move_id:
            self.state = 'created'
        else:
            if self.act_move_id:
                self.state = 'active'
            else:
                self.state = 'waiting'

    @api.one
    @api.depends('act_move_id.move_id')
    def get_move_id(self):
        self.move_id = self.act_move_id.move_id

    @api.multi
    def name_get(self):
        return [(x.id, 'Realizacijos akto eilutė ' + str(x.id)) for x in self]

    @api.multi
    def create_parent_acts(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'realisation_act'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        self.get_move_id()
        self.get_global_code()
        no_move_lines = self.filtered(lambda x: not x.move_id)

        acts = self.env['iiko.csv.act.move']
        for global_type in no_move_lines.mapped('global_mapping_id'):
            global_map = no_move_lines.filtered(lambda x: x.global_mapping_id.id == global_type.id)
            for day in set(global_map.mapped('line_day')):
                day_map = global_map.filtered(lambda s_line: s_line.line_day == day)
                vals = {
                    'date': day,
                    'realisation_line_ids': [(6, 0, day_map.ids)],
                    'act_type': 'realisation',
                    'global_mapping_id': global_type.id,
                }
                act = self.env['iiko.csv.act.move'].create(vals)
                acts += act
        acts.prepare_moves()


IIkoCSVRealisationActLine()


class IIkoCSVCashFlowMovements(models.Model):
    _name = 'iiko.csv.cashflow.movements'

    date = fields.Datetime(string='Data')
    number = fields.Char(string='Numeris')
    transfer_amount = fields.Float(string='Suma')
    operation = fields.Char(string='Operacija')
    debit_name = fields.Char(string='Debeto pavadinimas')
    debit_code = fields.Char(string='Debeto kodas', inverse='set_operation_type')
    debit_type = fields.Char(string='Debeto tipas')
    debit_partial_account_name = fields.Char(string='Debeto dalinės sąskaitos pavadinimas')
    debit_partial_account_code = fields.Char(string='Debeto dalinės sąskaitos kodas')
    debit_organisation_vat = fields.Char(string='Organizacijos PVM, debetas')
    debit_organisation_code = fields.Char(string='Organizacijos PVM, kodas')
    debit_organisation_name = fields.Char(string='Organizacijos PVM, pavadinimas')
    credit_name = fields.Char(string='Kredito pavadinimas')
    credit_code = fields.Char(string='Kredito kodas')
    credit_type = fields.Char(string='Kredito tipas')
    credit_partial_account_name = fields.Char(string='Debeto dalinės sąskaitos pavadinimas')
    credit_partial_account_code = fields.Char(string='Debeto dalinės sąskaitos kodas')
    credit_organisation_vat = fields.Char(string='Organizacijos PVM, debetas')
    credit_organisation_code = fields.Char(string='Organizacijos PVM, kodas')
    credit_organisation_name = fields.Char(string='Organizacijos PVM, pavadinimas')
    seller_code = fields.Char(string='Pardavėjo kodas')
    seller_name = fields.Char(string='Pardavėjo pavadinimas')
    seller_vat = fields.Char(string='Pardavėjo pvm')
    le_name = fields.Char(string='LE Pavadinimas')
    concept_name = fields.Char(string='Koncepto pavadinimas')
    concept_code = fields.Char(string='Koncepto kodas')
    date_sanitized = fields.Date(compute='_date_sanitized')
    operation_type = fields.Selection([('in', 'Pinigų įnešimas'),
                                       ('out', 'Pinigų išėmimas')], string='Operacijos tipas', default='out')

    state = fields.Selection([('active', 'Laukiantis'),
                              ('created', 'Sukurtas')], string='Būsena', compute='set_state', store=True)
    move_id = fields.Many2one('account.move', string='Žurnalo įrašas')

    @api.one
    @api.depends('date')
    def _date_sanitized(self):
        if self.date:
            date_dt = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(hours=3)
            self.date_sanitized = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def name_get(self):
        return [(x.id, 'Operacija ' + str(x.number)) for x in self]

    @api.one
    def set_operation_type(self):
        if self.debit_code:
            if self.debit_code == '1.13':
                self.operation_type = 'out'
            else:
                self.operation_type = 'in'
        else:
            self.operation_type = 'out'

    @api.one
    @api.depends('move_id')
    def set_state(self):
        self.state = 'created' if self.move_id else 'active'

    @api.multi
    def create_moves(self):
        active_jobs = self.env['iiko.jobs'].search([('file_code', '=', 'cash_flow_movements'),
                                                    ('state', '=', 'in_progress')])
        if active_jobs and not self._context.get('ignore_jobs', False):
            raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))

        config_obj = self.sudo().env['ir.config_parameter']
        cashier_name = config_obj.get_param('iiko_cashier')
        for rec in self:
            partner_id = self.env['res.partner'].search([('name', '=', cashier_name)]) if \
                rec.operation_type == 'out' else self.env['res.partner']
            if partner_id:
                account = self.env['account.account'].search([('code', '=', '24450')])
            else:
                account = self.env['account.account'].search([('code', '=', '273')])
            journal_id = self.env['account.journal'].search([('code', '=', 'IKINC')])
            move_lines = []
            name = 'Pinigų inešimas į kasą' if rec.operation_type == 'in' else 'Pinigų išėmimas iš kasos'
            credit_line = {
                'name': name,
            }
            if rec.operation_type != 'out':
                credit_line['credit'] = rec.transfer_amount
                credit_line['debit'] = 0.0
                credit_line['account_id'] = account.id
            else:
                credit_line['debit'] = rec.transfer_amount
                credit_line['credit'] = 0.0
                credit_line['account_id'] = account.id

            debit_line = {
                'name': name,
            }
            if rec.operation_type != 'out':
                debit_line['debit'] = rec.transfer_amount
                debit_line['credit'] = 0.0
                debit_line['account_id'] = journal_id.default_debit_account_id.id
            else:
                debit_line['credit'] = rec.transfer_amount
                debit_line['debit'] = 0.0
                debit_line['account_id'] = journal_id.default_credit_account_id.id

            credit_line['partner_id'] = partner_id.id
            debit_line['partner_id'] = partner_id.id
            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': journal_id.id,
                'date': rec.date_sanitized,
            }
            move_id = self.env['account.move'].create(move_vals)
            move_id.post()
            rec.move_id = move_id


IIkoCSVCashFlowMovements()


class IIkoCSVActMove(models.Model):

    _name = 'iiko.csv.act.move'

    act_type = fields.Selection([
        ('realisation', 'Realizacijos aktas'),
        ('inventory', 'Inventorizacijos aktas'),
        ('writeoff', 'Nurašymo aktas'),
        ], string='Akto Tipas', required=True, inverse='set_data')

    date = fields.Date(string='Data')
    move_id = fields.Many2one('account.move', string='Žurnalo įrašas')
    realisation_line_ids = fields.One2many('iiko.csv.realisation.act.line', 'act_move_id')
    writeoff_line_ids = fields.One2many('iiko.csv.writeoff.act.line', 'act_move_id')
    inventory_line_ids = fields.One2many('iiko.csv.inventory.line', 'act_move_id')
    state = fields.Selection([('active', 'Laukiantis'),
                              ('created', 'Sukurtas')], string='Būsena', compute='set_state', store=True)
    global_mapping_id = fields.Many2one('iiko.global.product.mapping', string='Produktų kategorija')
    forced_account_id = fields.Many2one('account.account', string='Priverstinė sąskaita')
    total_amount = fields.Float(string='Akto balansas', compute='get_total_amount')
    journal_id = fields.Many2one('account.journal')

    @api.one
    @api.depends('act_type', 'writeoff_line_ids', 'inventory_line_ids', 'realisation_line_ids')
    def get_total_amount(self):
        if self.act_type == 'realisation':
            lines_to_use = self.realisation_line_ids
            amount = sum(x.prime_cost_wo_vat for x in lines_to_use)
        elif self.act_type == 'writeoff':
            lines_to_use = self.writeoff_line_ids
            amount = sum(x.prime_cost_wo_vat for x in lines_to_use)
        else:
            lines_to_use = self.inventory_line_ids
            amount = sum(x.balance_sum for x in lines_to_use)
        self.total_amount = amount

    @api.one
    def set_data(self):
        if self.act_type == 'inventory':
            self.forced_account_id = self.env['account.account'].search([('code', '=', '652')])
            self.journal_id = self.env['account.journal'].search([('code', '=', 'IKINV')])
        elif self.act_type == 'writeoff':
            self.forced_account_id = self.env['account.account'].search([('code', '=', '60062')])
            self.journal_id = self.env['account.journal'].search([('code', '=', 'IKWRO')])
        else:
            self.journal_id = self.env['account.journal'].search([('code', '=', 'IKREA')])

    @api.multi
    def name_get(self):
        return [(x.id, 'Aktas ' + str(x.date)) for x in self]

    @api.one
    @api.depends('move_id')
    def set_state(self):
        self.state = 'created' if self.move_id else 'active'

    @api.multi
    def prepare_moves(self):
        for rec in self:
            if rec.act_type == 'realisation':
                lines_to_use = rec.realisation_line_ids
                amount = sum(x.prime_cost_wo_vat for x in lines_to_use)
            elif rec.act_type == 'writeoff':
                lines_to_use = rec.writeoff_line_ids
                amount = sum(x.prime_cost_wo_vat for x in lines_to_use)
            else:
                lines_to_use = rec.inventory_line_ids
                amount = sum(x.balance_sum for x in lines_to_use)
                amount *= -1

            account_credit = rec.global_mapping_id.product_id.property_account_expense_id # 2
            if rec.forced_account_id:
                account_debit = rec.forced_account_id
            else:
                account_debit = rec.global_mapping_id.product_id.property_account_prime_cost_id # 6

            move_lines = []
            name = str(dict(rec._fields['act_type'].selection).get(rec.act_type))
            credit_line = {
                'name': name + ' ' + str(rec.date),
            }
            if amount > 0:
                credit_line['credit'] = abs(amount)
                credit_line['debit'] = 0.0
                credit_line['account_id'] = account_credit.id
            else:
                credit_line['debit'] = abs(amount)
                credit_line['credit'] = 0.0
                credit_line['account_id'] = account_credit.id

            debit_line = {
                'name': name + ' ' + str(rec.date),
            }
            if amount > 0:
                debit_line['debit'] = abs(amount)
                debit_line['credit'] = 0.0
                debit_line['account_id'] = account_debit.id
            else:
                debit_line['credit'] = abs(amount)
                debit_line['debit'] = 0.0
                debit_line['account_id'] = account_debit.id

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': rec.journal_id.id,
                'date': rec.date,
            }
            move_id = self.env['account.move'].create(move_vals)
            move_id.post()
            rec.move_id = move_id


IIkoCSVActMove()


class IIKoCSVImportWizard(models.TransientModel):

    _name = 'iiko.csv.import.wizard'

    csv_data = fields.Binary(string='CSV failas', required=True)
    csv_name = fields.Char(string='CSV failo pavadinimas', size=128, required=False)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita')

    @api.multi
    def data_import(self):
        self.ensure_one()
        data = self.csv_data
        record_set = []
        string_io = StringIO.StringIO(base64.decodestring(data))
        csv_reader = csv.reader(string_io, delimiter=';', quotechar='"')
        header = csv_reader.next()
        cyrillic = False
        try:
            header = [x.decode('utf-8-sig').encode('utf-8') for x in header]
        except UnicodeDecodeError:
            cyrillic = True
        document_type = False
        for key in csv_headers_mapping.keys():
            if document_type:
                break
            if cyrillic:
                header_vals = cyrillic_headers_mapping.get(key)
            else:
                header_vals = csv_headers_mapping[key]
            if header == header_vals:
                document_type = key
        if document_type:
            active_jobs = self.env['iiko.jobs'].search([('file_code', '=', document_type),
                                                        ('state', '=', 'in_progress')])
            if active_jobs:
                raise exceptions.Warning(_('Negalite atlikti šio veiksmo, šio tipo failas yra importuojamas šiuo metu!'))
            header = pythonic_mapping_csv[document_type]
            for row in csv_reader:
                mapped_results = dict(zip(header, row))
                record_set.append(mapped_results)

            vals = {
                'file_code': document_type,
                'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'state': 'in_progress'
            }
            job_id = self.env['iiko.jobs'].create(vals)
            self.env.cr.commit()
            fix = self._context.get('fix', False)
            threaded_calculation = threading.Thread(target=self.create_thread, args=(document_type, record_set, job_id.id, fix))
            threaded_calculation.start()

    def create_thread(self, document_type, records, job_id, fix):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            job_id = env['iiko.jobs'].browse(job_id)
            try:
                if document_type == 'purchase_picking':
                    invoice_ids = self.create_records_purchase_picking(env, records)
                    invoice_ids.with_context(ignore_jobs=True).create_invoices()
                if document_type == 'purchase_picking_refund':
                    invoice_ids = self.create_records_purchase_picking(env, records, refunds=True)
                    invoice_ids.with_context(ignore_jobs=True).create_invoices()
                if document_type == 'orders':
                    order_lines, order_payments = self.create_records_orders(env, records, fix)
                    order_lines.with_context(initial=True, ignore_jobs=True).invoice_creation_prep()
                    order_payments.with_context(ignore_jobs=True).move_creation_prep()
                    order_payments.with_context(ignore_jobs=True).adjust_multi_payments()
                if document_type == 'inventory':
                    recs = self.create_records_inventory(env, records)
                    recs.with_context(ignore_jobs=True).create_parent_acts()
                if document_type == 'cash_flow_movements':
                    recs = self.create_records_cashflow(env, records)
                    recs.with_context(ignore_jobs=True).create_moves()
                if document_type == 'write_off_act':
                    recs = self.create_records_writeoff(env, records)
                    recs.with_context(ignore_jobs=True).create_parent_acts()
                if document_type == 'realisation_act':
                    recs = self.create_records_realisation(env, records)
                    recs.with_context(ignore_jobs=True).create_parent_acts()
                if document_type == 'orders_invoice':
                    recs = self.create_records_orders_invoice(env, records)
                    recs.with_context(ignore_jobs=True).invoice_creation_prep()
            except Exception as exc:
                new_cr.rollback()
                job_id.write({'state': 'failed',
                              'fail_message': str(exc.args[0]),
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                job_id.write({'state': 'finished',
                              'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            new_cr.commit()
            new_cr.close()
            _logger.info('IIKO %s IMPORT FINISHED' % document_type)

    def convert_date(self, date, formatting='%d.%m.%Y %H:%M:%S', expected_return_format='datetime', raise_exc=True):
        try:
            if expected_return_format in ['datetime']:
                to_return = datetime.strptime(date, formatting).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            else:
                to_return = datetime.strptime(date, formatting).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        except ValueError:
            try:
                to_return = datetime.strptime(date, '%Y.%m.%d').strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            except ValueError:
                try:
                    to_return = datetime.strptime(date, '%d.%m.%Y').strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                except ValueError:
                    try:
                        to_return = datetime.strptime(date, '%m.%d.%Y').strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    except ValueError:
                        if not raise_exc:
                            return False
                        raise exceptions.Warning(_('Incorrect Date format!'))
        return to_return

    def create_records_purchase_picking(self, env, record_set, refunds=False):
        invoice_ids = env['pp.csv.iiko.invoice']
        invoices = list(set([x['invoice'] for x in record_set]))
        for invoice in invoices:
            if env['pp.csv.iiko.invoice'].search_count([('number', '=', invoice)]):
                continue
            lines = filter(lambda r: r['invoice'] == invoice, record_set)
            invoice_data = lines[0]
            if refunds:
                date = self.convert_date(invoice_data.get('date'), expected_return_format='date')
            else:
                date = self.convert_date(invoice_data.get('input_date'))
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_dt < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            invoice_lines = []
            amount_total = 0.0
            amount_vat = 0.0
            for inv_line in lines:
                sum_w_vat = float(inv_line.get('sum_w_vat').replace(',', '.'))
                vat_sum = float(inv_line.get('vat_sum').replace(',', '.'))
                price_unit = float(inv_line.get('price_unit_w_vat').replace(',', '.'))
                quantity = float(inv_line.get('quantity').replace(',', '.'))
                try:
                    price_unit_artificial = sum_w_vat / quantity
                except ZeroDivisionError:
                    raise exceptions.Warning(_('Float Division By zero: Invoice number - %s, Quantity - %s' %
                                               (invoice_data.get('invoice'), quantity)))

                line_vals = {
                    'quantity': float(inv_line.get('quantity').replace(',', '.')),
                    'price_unit_w_vat': price_unit_artificial,
                    'vat_rate': inv_line.get('vat_rate').replace(',', '.'),
                    'amount_total': sum_w_vat,
                    'vat_sum': vat_sum,
                    'nomenclature_code': inv_line.get('nomenclature_code'),
                    'nomenclature_name': inv_line.get('nomenclature_name'),
                    'accounting_group_code': inv_line.get('accounting_group_code'),
                    'accounting_group_name': inv_line.get('accounting_group_name'),
                    'nomenclature_type_code': inv_line.get('nomenclature_type_code'),
                    'nomenclature_type_name': inv_line.get('nomenclature_type_name'),
                    'uom_code': inv_line.get('uom_code'),
                    'uom_name': inv_line.get('uom_name'),
                    'price_unit_static': price_unit,
                }
                invoice_lines.append((0, 0, line_vals))
                amount_total += sum_w_vat
                amount_vat += vat_sum
            vals = {
                'number': invoice_data.get('invoice'),
                'date_invoice': date,
                'amount_total': amount_total,
                'amount_vat': amount_vat,
                'partner_vat_code': invoice_data.get('client_vat'),
                'partner_name': invoice_data.get('client_name'),
                'partner_code': invoice_data.get('client_code'),
                'is_confirmed': invoice_data.get('is_confirmed'),
                'ext_number': invoice_data.get('number'),
                'warehouse_code': invoice_data.get('warehouse_code'),
                'warehouse_name': invoice_data.get('warehouse_name'),
                'seller_code': invoice_data.get('seller_code'),
                'seller_name': invoice_data.get('seller_name'),
                'seller_vat': invoice_data.get('seller_vat'),
                'concept_code': invoice_data.get('concept_code'),
                'concept_name': invoice_data.get('concept_name'),
                'ext_invoice_line_ids': invoice_lines,
            }
            if refunds:
                vals.update({'refund': True,
                             'unit_prime_cost_wo_vat': float(invoice_data.get('unit_prime_cost_wo_vat', '0').replace(',', '.')),
                             'prime_cost_wo_vat': float(invoice_data.get('prime_cost_wo_vat', '0').replace(',', '.')),
                             'orig_invoice_number': invoice_data.get('orig_invoice_number'),
                             'orig_invoice_date': self.convert_date(
                                 invoice_data.get('orig_invoice_date'), raise_exc=False) or date})

            invoice = env['pp.csv.iiko.invoice'].create(vals)
            system_rec = env['account.invoice'].search([('reference', '=', invoice.number)])
            if system_rec:
                if tools.float_compare(invoice.amount_total, abs(system_rec.amount_total), precision_digits=2) != 0:
                    raise exceptions.Warning(_('Sistemoje rasta jau sukurta sąskaita su numeriu %s. '
                                               'Nesutampa sumos: %s != %s' % (invoice.number, invoice.amount_total, system_rec.amount_total)))
                invoice.write({'invoice_id': system_rec.id})
            invoice_ids += invoice
        invoice_ids.validator()
        return invoice_ids

    def create_records_orders(self, env, record_set, fix):
        order_lines = env['order.csv.iiko.line']
        order_payments = env['order.csv.iiko.payment']

        ext_id_line_set = []
        ext_id_payment_set = []
        for record in record_set:
            code = int(record.get('line_type_code', 0))
            ext_ord_id = record.get('ext_order_id')
            if not code or not ext_ord_id:
                continue
            date = self.convert_date(record.get('line_date'),  formatting='%d.%m.%Y')
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_dt < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            if code == 1:
                if env['order.csv.iiko.line'].search_count([('ext_order_id', '=', ext_ord_id)]) \
                        and ext_ord_id not in ext_id_line_set:
                    continue
                if ext_ord_id not in ext_id_line_set:
                    ext_id_line_set.append(ext_ord_id)
                sum_w_vat = float(record.get('amount_total').replace(',', '.'))
                quantity = float(record.get('quantity').replace(',', '.'))
                price_unit_artificial = sum_w_vat / quantity
                vat_rate = record.get('vat_rate').replace(',', '.')

                vals = {
                    'quantity': quantity,
                    'price_unit_w_vat': price_unit_artificial,
                    'vat_rate': vat_rate,
                    'amount_total': sum_w_vat,
                    'amount_vat': record.get('vat_sum').replace(',', '.'),
                    'line_date': date,
                    'is_valid': record.get('is_valid'),
                    'seller_name': record.get('seller_name'),
                    'seller_vat': record.get('seller_vat'),
                    'seller_code': record.get('seller_code'),
                    'shift_id': record.get('shift_id'),
                    'activity_type': record.get('activity_type'),
                    'nomenclature_code': record.get('nomenclature_code'),
                    'nomenclature_name': record.get('nomenclature_name'),
                    'accounting_group_code': record.get('accounting_group_code'),
                    'accounting_group_name': record.get('accounting_group_name'),
                    'uom_code': record.get('uom_code'),
                    'uom_name': record.get('uom_name'),
                    'nomenclature_type_code': record.get('nomenclature_type_code'),
                    'nomenclature_type_name': record.get('nomenclature_type_name'),
                    'discount_amount': record.get('discount_amount').replace(',', '.'),
                    'discount_amount_pos': record.get('discount_amount_pos').replace(',', '.'),
                    'line_number': record.get('line_number'),
                    'cash_register_number': record.get('cash_register_number'),
                    'cash_register_name': record.get('cash_register_name'),
                    'receipt_id': record.get('receipt_id'),
                    'nomenclature_text': record.get('nomenclature_text'),
                    'ext_order_id': ext_ord_id,
                    'order_id': record.get('order_id'),
                    'ext_type': code,
                    'discount': False
                }
                order_line = env['order.csv.iiko.line'].create(vals)
                order_lines += order_line

            elif code == 2:
                if fix:
                    to_fix = env['order.csv.iiko.payment'].search([('ext_order_id', '=', ext_ord_id),
                                                                   ('payment_date', '!=', date)])
                    if to_fix:
                        to_fix.write({'payment_date': date})
                        if to_fix.mapped('move_id'):
                            line_ids = to_fix.mapped('move_id.line_ids')
                            env.cr.execute('''update account_move set date = %s where id in %s''',
                                           (date, tuple(to_fix.mapped('move_id.id')),))
                            env.cr.execute('''update account_move_line set date_maturity = %s, date = %s where id in %s''',
                                           (date, date, tuple(line_ids.ids),))
                    continue
                if env['order.csv.iiko.payment'].search_count([('ext_order_id', '=', ext_ord_id)]) \
                        and ext_ord_id not in ext_id_payment_set:
                    continue
                if ext_ord_id not in ext_id_payment_set:
                    ext_id_payment_set.append(ext_ord_id)
                vals = {
                    'ext_order_id': ext_ord_id,
                    'payment_type_code': record.get('payment_type_code'),
                    'payment_type_name': record.get('payment_type_name'),
                    'payment_amount': record.get('payment_amount').replace(',', '.'),
                    'fixed_payment': record.get('fixed_payment'),
                    'activity_type': record.get('activity_type'),
                    'payment_date': date,
                    'receipt_id': record.get('receipt_id'),
                    'order_id': record.get('order_id'),
                    'cash_register_number': record.get('cash_register_number'),
                    'cash_register_name': record.get('cash_register_name'),
                    'shift_id': record.get('shift_id'),
                    'seller_name': record.get('seller_name'),
                    'seller_vat': record.get('seller_vat'),
                    'seller_code': record.get('seller_code'),
                    'is_valid': record.get('is_valid'),
                    'ext_number': record.get('ext_number'),
                    'ext_type': code,
                }
                order_payment = env['order.csv.iiko.payment'].create(vals)
                order_payments += order_payment
        return order_lines, order_payments

    def create_records_inventory(self, env, record_set):
        inventory_lines = env['iiko.csv.inventory.line']
        number_set = []
        for record in record_set:
            number = record.get('number')
            if env['iiko.csv.inventory.line'].search_count([('number', '=', number)]) \
                    and number not in number_set:
                continue
            date = self.convert_date(record.get('date_inventory'))
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_dt < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            if number not in number_set:
                number_set.append(number)
            vals = {
                'date': date,
                'number': number,
                'is_valid': record.get('is_valid'),
                'warehouse_code': record.get('warehouse_code'),
                'warehouse_name': record.get('warehouse_name'),
                'seller_code': record.get('seller_code'),
                'seller_name': record.get('seller_name'),
                'seller_vat': record.get('seller_vat'),
                'nomenclature_code': record.get('nomenclature_code'),
                'nomenclature_name': record.get('nomenclature_name'),
                'accounting_group_name': record.get('accounting_group_name'),
                'accounting_group_code': record.get('accounting_group_code'),
                'quantity': record.get('quantity').replace(',', '.'),
                'vat_rate': record.get('vat_rate').replace(',', '.'),
                'nomenclature_type_code': record.get('nomenclature_type_code'),
                'nomenclature_type_name': record.get('nomenclature_type_name'),
                'uom_code': record.get('uom_code'),
                'uom_name': record.get('uom_name'),
                'prime_cost_unit': record.get('prime_cost_unit').replace(',', '.'),
                'prime_cost': record.get('prime_cost').replace(',', '.'),
                'deficit_account_code': record.get('deficit_account_code'),
                'deficit_account_name': record.get('deficit_account_name'),
                'abundance_account_code': record.get('abundance_account_code'),
                'abundance_account_name': record.get('abundance_account_name'),
                'balance_quantity': record.get('balance_quantity').replace(',', '.'),
                'balance_sum': record.get('balance_sum').replace(',', '.'),
            }
            inventory_line = env['iiko.csv.inventory.line'].create(vals)
            inventory_lines += inventory_line
        return inventory_lines

    def create_records_writeoff(self, env, record_set):
        writeoff_lines = env['iiko.csv.writeoff.act.line']
        number_set = []
        for record in record_set:
            number = record.get('number')
            if env['iiko.csv.writeoff.act.line'].search_count([('number', '=', number)]) \
                    and number not in number_set:
                continue
            operation = record.get('operation')
            if operation != '1':
                continue
            date = self.convert_date(record.get('date'))
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_dt < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            if number not in number_set:
                number_set.append(number)
            vals = {
                'date': date,
                'number': number,
                'is_valid': record.get('is_valid'),
                'warehouse_code': record.get('warehouse_code'),
                'warehouse_name': record.get('warehouse_name'),
                'seller_code': record.get('seller_code'),
                'seller_name': record.get('seller_name'),
                'seller_vat': record.get('seller_vat'),
                'nomenclature_code': record.get('nomenclature_code'),
                'nomenclature_name': record.get('nomenclature_name'),
                'accounting_group_name': record.get('accounting_group_name'),
                'accounting_group_code': record.get('accounting_group_code'),
                'quantity': record.get('quantity').replace(',', '.'),
                'vat_rate': record.get('vat_rate').replace(',', '.'),
                'nomenclature_type_code': record.get('nomenclature_type_code'),
                'nomenclature_type_name': record.get('nomenclature_type_name'),
                'uom_code': record.get('uom_code'),
                'uom_name': record.get('uom_name'),
                'prime_cost_unit_wo_vat': record.get('prime_cost_unit_wo_vat').replace(',', '.'),
                'prime_cost_wo_vat': record.get('prime_cost_wo_vat').replace(',', '.'),
                'expense_paper': record.get('expense_paper'),
                'expense_paper_code': record.get('expense_paper_code'),
                'write_off_type': record.get('write_off_type'),
                'write_off_type_name': record.get('write_off_type_name'),
                'operation': record.get('operation'),
                'operation_name': record.get('operation_name'),
                'target_dish_code': record.get('target_dish_code'),
                'target_dish_name': record.get('target_dish_name'),
                'concept_name': record.get('concept_name'),
                'concept_code': record.get('concept_code'),
                'shift_id': record.get('shift_id'),
                'cash_register_number': record.get('cash_register_number'),
                'sold_dish_code': record.get('sold_dish_code'),
                'sold_dish_name': record.get('sold_dish_name'),
                'sold_dish_accounting_group_code': record.get('sold_dish_accounting_group_code'),
                'sold_dish_accounting_group_name': record.get('sold_dish_accounting_group_name'),
            }
            writeoff_line = env['iiko.csv.writeoff.act.line'].create(vals)
            writeoff_lines += writeoff_line
        return writeoff_lines

    def create_records_realisation(self, env, record_set):
        realisation_lines = env['iiko.csv.realisation.act.line']
        number_set = []
        for record in record_set:
            number = record.get('number')
            if env['iiko.csv.realisation.act.line'].search_count([('number', '=', number)]) \
                    and number not in number_set:
                continue
            date = self.convert_date(record.get('date'))
            operation = record.get('operation')
            if operation != '2':
                continue
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_dt < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            if number not in number_set:
                number_set.append(number)
            vals = {
                'date': date,
                'number': number,
                'is_valid': record.get('is_valid'),
                'warehouse_code': record.get('warehouse_code'),
                'warehouse_name': record.get('warehouse_name'),
                'seller_code': record.get('seller_code'),
                'seller_name': record.get('seller_name'),
                'seller_vat': record.get('seller_vat'),
                'nomenclature_code': record.get('nomenclature_code'),
                'nomenclature_name': record.get('nomenclature_name'),
                'accounting_group_name': record.get('accounting_group_name'),
                'accounting_group_code': record.get('accounting_group_code'),
                'quantity': record.get('quantity').replace(',', '.'),
                'vat_rate': record.get('vat_rate').replace(',', '.'),
                'nomenclature_type_code': record.get('nomenclature_type_code'),
                'nomenclature_type_name': record.get('nomenclature_type_name'),
                'uom_code': record.get('uom_code'),
                'uom_name': record.get('uom_name'),
                'operation': record.get('operation'),
                'operation_name': record.get('operation_name'),
                'price_w_vat': record.get('price_w_vat').replace(',', '.'),
                'sum_w_vat': record.get('sum_w_vat').replace(',', '.'),
                'vat_sum': record.get('vat_sum').replace(',', '.'),
                'sale_vat_rate': record.get('sale_vat_rate').replace(',', '.'),
                'prime_cost_unit_wo_vat': record.get('prime_cost_unit_wo_vat').replace(',', '.'),
                'prime_cost_wo_vat': record.get('prime_cost_wo_vat').replace(',', '.'),
                'cash_flow_code': record.get('cash_flow_code'),
                'cash_flow_movement': record.get('cash_flow_movement'),
                'expense_paper': record.get('expense_paper'),
                'expense_paper_code': record.get('expense_paper_code'),
                'write_off_type': record.get('write_off_type'),
                'write_off_type_name': record.get('write_off_type_name'),
                'target_dish_code': record.get('target_dish_code'),
                'target_dish_name': record.get('target_dish_name'),
                'concept_name': record.get('concept_name'),
                'concept_code': record.get('concept_code'),
                'shift_id': record.get('shift_id'),
                'cash_register_number': record.get('cash_register_number'),
                'sold_dish_code': record.get('sold_dish_code'),
                'sold_dish_name': record.get('sold_dish_name'),
                'target_dish_accounting_group_code': record.get('target_dish_accounting_group_code'),
                'target_dish_accounting_group_name': record.get('target_dish_accounting_group_name'),
            }
            realisation_line = env['iiko.csv.realisation.act.line'].create(vals)
            realisation_lines += realisation_line
        return realisation_lines

    def create_records_cashflow(self, env, record_set):
        operation_to_import = 'Prekybos kasos/Pagrindine kasa'  # todo, looks sketchy hardcoded here
        cashflow_lines = env['iiko.csv.cashflow.movements']
        number_set = []
        for record in record_set:
            number = record.get('number')
            if env['iiko.csv.cashflow.movements'].search_count([('number', '=', number)]) \
                    and number not in number_set:
                continue
            operation = record.get('operation')
            date = self.convert_date(record.get('date'))
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_dt < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            if not operation or operation != operation_to_import:
                continue
            if number not in number_set:
                number_set.append(number)
            vals = {
                'date': date,
                'number': number,
                'transfer_amount': record.get('transfer_amount').replace(',', '.'),
                'operation': record.get('operation'),
                'debit_name': record.get('debit_name'),
                'debit_code': record.get('debit_code'),
                'debit_type': record.get('debit_type'),
                'debit_partial_account_name': record.get('debit_partial_account_name'),
                'debit_partial_account_code': record.get('debit_partial_account_code'),
                'debit_organisation_vat': record.get('debit_organisation_vat'),
                'debit_organisation_code': record.get('debit_organisation_code'),
                'debit_organisation_name': record.get('debit_organisation_name'),
                'credit_name': record.get('credit_name'),
                'credit_code': record.get('credit_code'),
                'credit_type': record.get('credit_type'),
                'credit_partial_account_name': record.get('credit_partial_account_name'),
                'credit_partial_account_code': record.get('credit_partial_account_code'),
                'credit_organisation_vat': record.get('credit_organisation_vat'),
                'credit_organisation_code': record.get('credit_organisation_code'),
                'credit_organisation_name': record.get('credit_organisation_name'),
                'seller_code': record.get('seller_code'),
                'seller_name': record.get('seller_name'),
                'seller_vat': record.get('seller_vat'),
                'le_name': record.get('le_name'),
                'concept_name': record.get('concept_name'),
                'concept_code': record.get('concept_code'),
            }
            cashflow_line = env['iiko.csv.cashflow.movements'].create(vals)
            cashflow_lines += cashflow_line
        return cashflow_lines

    def create_records_orders_invoice(self, env, record_set):
        invoices = env['order.csv.iiko.invoice']
        for record in record_set:
            if env['order.csv.iiko.invoice'].search_count([('invoice_number', '=', record.get('invoice_number'))]):
                continue
            date_invoice = self.convert_date(record.get('date_invoice'))
            iiko_accounting_threshold = datetime(2019, 04, 01)
            try:
                date_invoice_id = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if date_invoice_id < iiko_accounting_threshold:
                    continue
            except ValueError:
                try:
                    date_invoice_id = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_invoice_id < iiko_accounting_threshold:
                        continue
                except ValueError:
                    continue
            partner_vat = record.get('partner_vat')
            partner_code = record.get('partner_code')
            if 'LT' in partner_code.upper():
                partner_code, partner_vat = partner_vat, partner_code
            vals = {
                'invoice_number': record.get('invoice_number'),
                'date_invoice': self.convert_date(record.get('date_invoice')),
                'partner_name': record.get('partner_name'),
                'partner_code': partner_code,
                'partner_vat': partner_vat,
                'amount_total': record.get('amount_total').replace(',', '.'),
                'receipt_id': record.get('receipt_id'),
                'amount_vat': record.get('amount_total').replace(',', '.'),

            }
            invoice = env['order.csv.iiko.invoice'].create(vals)
            invoices += invoice
        return invoices

    @api.model
    def cron_recreate(self):
        order_payments = self.env['order.csv.iiko.payment'].search([('state', '!=', 'reconciled')])
        order_payments.move_creation_prep()
        order_payments.adjust_multi_payments()
        order_payments.re_reconcile()

        order_lines = self.env['order.csv.iiko.line'].search([('state', '!=', 'created')])
        order_lines.invoice_creation_prep()

        invoices = self.env['pp.csv.iiko.invoice'].search([('state', '!=', 'created')])
        invoices.validator()
        invoices.create_invoices()


IIKoCSVImportWizard()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    order_line_ids = fields.One2many('order.csv.iiko.line', 'invoice_line_id', string='Order line')
    refund_order_line_ids = fields.One2many('order.csv.iiko.line', 'refund_line_id', string='Order line')
    corrected_order_line_ids = fields.One2many('order.csv.iiko.line', 'corrected_line_id', string='Order line')


AccountInvoiceLine()


class ProductTemplate(models.Model):

    _inherit = 'product.template'

    property_account_prime_cost_id = fields.Many2one('account.account', string='Savikainos sąskaita')


ProductTemplate()


class IIkoJobs(models.Model):
    _name = 'iiko.jobs'

    file_code = fields.Char(string='Failo tipo identifikatorius')
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')
    state = fields.Selection([('in_progress', 'Vykdomas'),
                              ('finished', 'Sėkmingai įvykdytas'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')
    fail_message = fields.Char(string='Klaidos pranešimas')


IIkoJobs()
