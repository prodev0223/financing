# -*- coding: utf-8 -*-

UPDATE_IMPORT_STATES = ['out_dated', 'not_tried', 'rejected']

VALIDATION_FAIL_MESSAGE_MAPPER = {
    'tax': 'Eilutė neturi nustatytų mokesčių',
    'tax_man': 'Eilutė neturi nustatytų rankinių nuolaidų mokesčių',
    'product': 'Eilutės produktas nerastas sistemoje',
    'shop': 'Parduotuvė kuriai priklauso ši pardavimo eilutė nėra sukonfigūruota',
    'pos': 'Kasos aparatas kuriam priklauso ši pardavimo eilutė nėra sukonfigūruotas',
    'validated': None,
}
