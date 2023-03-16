# -*- coding: utf-8 -*-
from odoo import api, fields, models


class GpaisRegistrationLinePackage(models.TransientModel):
    _name = 'gpais.registration.line.package'

    material_type = fields.Selection([('kita', 'Kita'),
                                      ('kombinuota_kita', 'Kombinuota (kita)'),
                                      ('kombinuota', 'Kombinuota'),
                                      ('medis', 'Medis'),
                                      ('metalas', 'Metalas'),
                                      ('pet', 'PET'),
                                      ('plastikas', 'Plastikas'),
                                      ('popierius', 'Popierius'),
                                      ('stiklas', 'Stiklas'),],
                                     required=True, string='Medžiaga')
    use_type = fields.Selection([('vienkartine', 'Vienkartinė'), ('daukartine', 'Daugkartinė')],
                                string='Vienkartinė / Daugkartinė', required=True)
    uzstatine = fields.Boolean(string="Užstatinė")
    activity_own_need = fields.Boolean(string='Sunaudojimas savo reikmėms')
    activity_b2c = fields.Boolean(string='Mažmeninė prekyba')
    activity_b2b = fields.Boolean(string='Didmeninė prekyba')
    activity_remote = fields.Boolean(string='Nuotolinė prekyba')
    activity_export = fields.Boolean(string='Išvežimas iš LR vidaus rinkos')
    activity_export_broker = fields.Boolean(string='Išvežimas iš LR vidaus rinkos per trečiuosius asmenis')

    @api.multi
    def get_line_values(self):
        res = [{
            'gpais_product_type': 'prekinisVienetas',
            'material_type': line.material_type,
            'use_type': line.use_type,
            'uzstatine': line.uzstatine,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export_broker': line.activity_export_broker,
            'activity_export': line.activity_export,
        } for line in self]
        return res
