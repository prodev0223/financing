# -*- coding: utf-8 -*-
from odoo import tools
from datetime import datetime
from dateutil.relativedelta import relativedelta
allowed_calc_error = 0.01
date_from_initial = '2019-01-01 00:00:00'


def assert_creation_weekday():
    return True if datetime.utcnow().weekday() in [3] else False


def delay_date():
    # Disable delay date for now. If mistakes from Polis will still occur,
    # re-enable delay date.
    return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)


universal_vat_mapper = {
    '0': 'PVM1',
    '1': 'PVM3',
    '2': 'PVM12',
    '3': 'PVM5',
    '4': 'PVM25',
    '5': 'PVM9',
}

universal_product_tax_mapping = {
    'DOV1': 'Ne PVM',
    'KORT1': 'Ne PVM',
    'LAP': 'PVM1'
}

rehabilitation_products = [
    'F01',
    'F01-1',
    'F02',
    'F02-1',
    'F03',
    'F03-1',
    'F04',
    'F04-1',
    'F05',
    'F05-1',
    'F07',
    'F07-1',
    'F08',
    'F08-1',
    'F09',
    'F09-01',
    'F10',
    'F10-1',
    'F11',
    'F11-1',
    'F12',
    'M09',
    'M09-1',
    'D01',
    'D02',
    'D03',
    'D04',
    'REZ',
    'AR02',
    'AR02-02',
    'AR02-1',
    'AR03',
    'AR03-01',
    'AR03-03',
    'AR06',
    'AR06-01',
    'AR07',
    'AR07-01',
    'GR21',
    'AR1',
    'GR01',
    'GR05',
    'GR06',
    'GR09',
    'GR10',
    'GR11',
    'GR12',
    'GR16',
    'GR17',
    'GR18',
    'GR19',
    'KT03',
    'KT04',
    'KVK01',
    'KVK02',
    'KVK03',
    'KVK04',
    'ER01',
    'ER01-02',
    'ER01-1',
    'ER03',
    'ER03-01',
    'KT01',
    'KT01-1',
    'KT02',
    'KT02-1',
    'KT05',
    'KT10',
    'KT11',
    'KT12',
    'KT13',
    'KT6',
    'KT8',
    'M01',
    'M01-1',
    'ST12',
    'STC10',
    'STC11',
    'STC12',
    'STC13',
    'TP1',
    'TP2',
    'G01',
    'G02',
    'G03',
    'G07',
    'G08',
    'G09',
    'G12',
    'G13',
    'K001',
    'MK-1',
    'MK-2',
    'M0002',
    'M001',
    'M02',
    'M02-1',
    'M03',
    'M04',
    'M04-1',
    'M05',
    'M05-1',
    'M06',
    'M06-1',
    'M07',
    'M07-1',
    'M12',
    'M15',
    'M15-1',
    'V01',
    'V01-1',
    'V02'
]

# Data used for account.bank.statement.line export to POLIS
BANK_STATEMENT_FIELD_MAPPING = {
    'date': 'OperacijosData',
    'amount_company_currency': 'Suma',
    'partner_code': 'PacientoAK',
    'name': 'MokejimoPaskirtis',
    'line_id': 'RLMokejimoID'
}

STATIC_SUCCESS_RESPONSE_MESSAGE = 'OK'

FAIL_MESSAGE_TEMPLATE = 'Nepavyko eksportuoti banko išrašų eilučių į POLIS, klaidos pranešimas: '

STATEMENT_LINE_THRESHOLD_DATE = '2020-04-01'
