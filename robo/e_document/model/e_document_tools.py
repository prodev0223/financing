# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import tools


def assert_correct_lithuanian_identification_id(identification_id):
    """
    Check whether passed identification id matches the lithuanian identification id format
    :param identification_id: identification_id (str)
    :return: True/False
    """
    if len(identification_id) != 11:
        return False
    if not identification_id.isdigit():
        return False
    try:
        year = (1800 + ((int(identification_id[0])-1) // 2) * 100) + int(identification_id[1:3])  # P3:DivOK
        datetime(year, int(identification_id[3:5]), int(identification_id[5:7]))
    except ValueError:
        return False
    last_digit = int(identification_id[-1])
    coefficients_1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]
    remainder_1 = sum(int(a) * b for a, b in zip(identification_id, coefficients_1)) % 11
    if remainder_1 == last_digit:
        return True
    elif remainder_1 != 10:
        return False
    else:
        coefficients_2 = [3, 4, 5, 6, 7, 8, 9, 1, 2, 3]
        remainder_2 = sum(int(a) * b for a, b in zip(identification_id, coefficients_2)) % 11
        if remainder_2 == 10:
            remainder_2 = 0
        return last_digit == remainder_2


def remove_letters(data):
    """
    Remove letters from the passed string
    :param data: passed string
    :return: string with removed letters
    """
    mas = []
    if data is not None and isinstance(data, (str, unicode)):
        for letter in data:
            if letter.isdigit():
                mas.append(letter)
    return ''.join(mas)


def assert_correct_identification_id(identification_id):
    """
    Check whether passed identification id matches the format
    :param identification_id: identification_id (str)
    :return: True/False
    """
    if not identification_id:
        return False
    sid = remove_letters(identification_id)
    if not assert_correct_lithuanian_identification_id(sid):
        return False
    if len(sid) != 11:
        return False
    else:
        if sid[:1] not in ['3', '5', '4', '6']:
            return False
        data_str = get_birthdate_from_identification(sid)
        try:
            datetime.strptime(data_str, '%Y-%m-%d')
        except ValueError:
            return False
        return True


def get_birthdate_from_identification(identification_id):
    """
    Retrieve birthdate from provided identification id
    :param identification_id: identification_id (str)
    :return: birthdate (str)
    """
    if not assert_correct_lithuanian_identification_id(identification_id):
        return False
    date_part = identification_id[:-4]
    year = str((1800 + ((int(date_part[0])-1) // 2) * 100) + int(date_part[1:3]))  # P3:DivOK
    month = date_part[3:5]
    day = date_part[-2:]
    return year + '-' + month + '-' + day


def get_age_from_identification(identification_id):
    """
    Retrieve age from provided identification id
    :param identification_id: identification_id (str)
    :return: age (int)
    """
    identification_id = remove_letters(identification_id)
    if not assert_correct_identification_id(identification_id):
        return False
    today = datetime.utcnow() + relativedelta(hour=0, minute=0, second=0, microsecond=0)
    birthdate = datetime.strptime(get_birthdate_from_identification(identification_id),
                                  tools.DEFAULT_SERVER_DATE_FORMAT)
    return relativedelta(today, birthdate).years
