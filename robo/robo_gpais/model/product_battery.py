# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from .gpais_commons import veiklosBudas_mapping


class ProductBattery(models.Model):
    _inherit = 'product.battery'

    code = fields.Char(string='Kodas', required=True)
    rusis = fields.Selection([('BATERIJA', 'BATERIJA'), ('AKUMULIATORIUS', 'AKUMULIATORIUS')],
                             compute='_parameters', string='Rūšis', store=True)
    imontuota = fields.Boolean(string='Įmontuota', compute='_parameters', store=True)
    chemine_sudetis = fields.Many2one('gpais.klasifikacija', domain="[('code_class', '=', 'CL127')]", required=True)
    klasifikacija = fields.Many2one('gpais.klasifikacija', domain="[('code_class', '=', 'CL126')]", required=True)
    date_to_market_from = fields.Date(string='Pradėta tiekti rinkai nuo',
                                      default=fields.Date.today,
                                      help="Data turi būti vėlesnė nei registracijos data GPAIS sistemoje",
                                      required=True)
    date_to_market_until = fields.Date(string='Nustota tiekti rinkai nuo', default=False,
                                       help="Data turi būti vėlesnė nei registracijos data GPAIS sistemoje")

    _sql_constraints = [
        ('product_battery_code_unique', 'UNIQUE (code)', _('Kodas turi būti unikalus')),
    ]

    @api.one
    @api.depends('category')
    def _parameters(self):
        self.rusis = 'BATERIJA' if self.category in ['17', '18'] else 'AKUMULIATORIUS'
        self.imontuota = self.category in ['18', '20', '22', '24']

    @api.onchange('category')
    def onchange_category_set_klasifikacija(self):
        if not self.rusis:
            return
        if self.rusis in ['19', '20']:
            self.klasifikacija = self.env.ref('robo_gpais.gpais_klasifikatorius_48').id
        elif self.rusis in ['23', '24']:
            self.klasifikacija = self.env.ref('robo_gpais.gpais_klasifikatorius_49').id
        elif self.rusis in ['21', '22']:
            self.klasifikacija = self.env.ref('robo_gpais.gpais_klasifikatorius_50').id

    @api.multi
    def check_veiklos_budas(self, veiklo_budas, skip_activity=False):
        self.ensure_one()

        search_domain = [('company_id', '=', self.env.user.company_id.id),
                         ('imontuota', '=', self.imontuota),
                         ('rusis', '=', self.rusis),
                         ('chemine_sudetis', '=', self.chemine_sudetis.id),
                         ('gpais_product_type', '=', 'baterijia')]

        if veiklosBudas_mapping.get(veiklo_budas) and not skip_activity:
            attr = 'activity_' + veiklosBudas_mapping.get(veiklo_budas)
            search_domain.append((attr, '=', True))


        if self.env['gpais.registration.line'].search_count(search_domain):
            return True
        return False
