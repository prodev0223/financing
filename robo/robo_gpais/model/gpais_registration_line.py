# -*- coding: utf-8 -*-
from odoo import api, fields, models
from .gpais_commons import PRODUCT_TYPES


class GpaisRegistrationLine(models.Model):
    _name = 'gpais.registration.line'

    gpais_product_type = fields.Selection(PRODUCT_TYPES + [('baterija', 'Baterija')],
                                          string='GPAIS produkto tipas')
    klasifikacija = fields.Many2one('gpais.klasifikacija', string='Klasifikacija',
                                    domain="[('product_type', '=', gpais_product_type)]")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.user.sudo().company_id, ondelete='cascade')
    activity_own_need = fields.Boolean(string='Sunaudojimas savo reikmėms')
    activity_b2c = fields.Boolean(string='Mažmeninė prekyba')
    activity_b2b = fields.Boolean(string='Didmeninė prekyba')
    activity_remote = fields.Boolean(string='Nuotolinė prekyba')
    activity_export = fields.Boolean(string='Išvežimas iš LR vidaus rinkos')
    activity_export_broker = fields.Boolean(string='Išvežimas iš LR vidaus rinkos per trečiuosius asmenis')
    buitine_iranga = fields.Boolean(string='Sunaudojimas savo reikmėms')
    rusis = fields.Selection([('BATERIJA', 'BATERIJA'), ('AKUMULIATORIUS', 'AKUMULIATORIUS')],
                             string='Rūšis')
    imontuota = fields.Boolean(string='Įmontuota')
    chemine_sudetis = fields.Many2one('gpais.klasifikacija', domain="[('code_class', '=', 'CL127')]")
    material_type = fields.Selection([('kita', 'Kita'),
                                      ('kombinuota_kita', 'Kombinuota (kita)'),
                                      ('kombinuota', 'Kombinuota'),
                                      ('medis', 'Medis'),
                                      ('metalas', 'Metalas'),
                                      ('pet', 'PET'),
                                      ('plastikas', 'Plastikas'),
                                      ('popierius', 'Popierius'),
                                      ('stiklas', 'Stiklas'),
                                      ('kombinuota_kita_vyr_stiklas', 'Kombinuota tuščia kita (vyraujanti stiklas)'),
                                      ], string='Medžiaga')
    use_type = fields.Selection([('vienkartine', 'Vienkartinė'), ('daukartine', 'Daugkartinė')],
                                string='Vienkartinė/Daugkartinė',)
    uzstatine = fields.Boolean(string='Užstatinė')

    @api.multi
    def generate_wizard_line_vals_battery(self):
        res = [{
            'klasifikacija': line.klasifikacija.id,
            'rusis': line.rusis,
            'imontuota': line.imontuota,
            'chemine_sudetis': line.chemine_sudetis.id,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export_broker': line.activity_export_broker,
        } for line in self.filtered(lambda l: l.gpais_product_type == 'baterija')]
        return res

    @api.multi
    def generate_wizard_line_vals_eei(self):
        res = [{
            'klasifikacija': line.klasifikacija.id,
            'buitine_iranga': line.buitine_iranga,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export_broker': line.activity_export_broker,
        } for line in self.filtered(lambda l: l.gpais_product_type == 'elektronineIranga')]
        return res

    @api.multi
    def generate_wizard_line_vals_package(self):
        res = [{
            # 'klasifikacija': line.klasifikacija.id,
            'material_type': line.material_type,
            'use_type': line.use_type,
            'uzstatine': line.uzstatine,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export': line.activity_export,
            'activity_export_broker': line.activity_export_broker,
        } for line in self.filtered(lambda l: l.gpais_product_type == 'prekinisVienetas')]
        return res

    @api.multi
    def generate_wizard_line_vals_oil(self):
        res = [{
            'klasifikacija': line.klasifikacija.id,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export': line.activity_export,
            'activity_export_broker': line.activity_export,
        } for line in self.filtered(lambda l: l.gpais_product_type == 'alyvosGaminys')]
        return res

    @api.multi
    def generate_wizard_line_vals_transport(self):
        res = [{
            'klasifikacija': line.klasifikacija.id,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export_broker': line.activity_export,
        } for line in self.filtered(lambda l: l.gpais_product_type == 'transportoPriemone')]
        return res

    @api.multi
    def generate_wizard_line_vals_goods(self):
        res = [{
            'klasifikacija': line.klasifikacija.id,
            'activity_own_need': line.activity_own_need,
            'activity_b2c': line.activity_b2c,
            'activity_b2b': line.activity_b2b,
            'activity_remote': line.activity_remote,
            'activity_export': line.activity_export,
            'activity_export_broker': line.activity_export,
        } for line in self.filtered(lambda l: l.gpais_product_type == 'apmokestinamasGaminys')]
        return res
