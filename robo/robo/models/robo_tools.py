# -*- encoding: utf-8 -*-
import re
from datetime import datetime

from odoo import _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as SERVER_DATETIME_FORMAT, \
    DEFAULT_SERVER_DATE_FORMAT as SERVER_DATE_FORMAT

MONTH_TO_STRING_MAPPING = {
    1: _('Sausis'),
    2: _('Vasaris'),
    3: _('Kovas'),
    4: _('Balandis'),
    5: _('Gegužė'),
    6: _('Birželis'),
    7: _('Liepa'),
    8: _('Rugpjūtis'),
    9: _('Rugsėjis'),
    10: _('Spalis'),
    11: _('Lapkritis'),
    12: _('Gruodis')
}


def _strf(date_dt):
    try:
        return date_dt.strftime(SERVER_DATE_FORMAT)
    except:
        try:
            return date_dt.strftime(SERVER_DATETIME_FORMAT)[:10]
        except:
            return date_dt


def _strft(date_dt):
    try:
        return date_dt.strftime(SERVER_DATETIME_FORMAT)
    except:
        return date_dt


def _strp(date_str):
    try:
        return datetime.strptime(date_str, SERVER_DATE_FORMAT)
    except:
        try:
            return datetime.strptime(date_str, SERVER_DATETIME_FORMAT)
        except:
            return date_str


def sanitize_account_number(acc_number):
    if acc_number:
        return re.sub(r'\W+', '', acc_number).upper()
    return False
