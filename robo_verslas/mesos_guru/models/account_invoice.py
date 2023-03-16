# -*- coding: utf-8 -*-

from odoo import models, fields, tools, api
from datetime import datetime


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def default_datetime(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    def default_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _default_butchery_id(self):
        return self.env.ref('mesos_guru.mg_butchery_address_1', False)

    batch_number = fields.Char(string='Partijos numeris')
    expiration_date = fields.Date(string='Tinka vartoti iki', default=default_date)
    unloading_address = fields.Char(string='Iškrovimo vieta')
    unloading_address_id = fields.Many2one('mg.unloading.address', string='Iškrovimo vieta')
    unloading_address_type = fields.Selection(
        [('select', 'Pasirinkti iškrovimo vietą'),
         ('enter', 'Įrašyti iškrovimo vietą')], defaut='select', required=True, string='Įvesties būdas')
    butchery_id = fields.Many2one('mg.butchery.address', string='Skerdyklos vieta', default=_default_butchery_id)
    loading_time = fields.Datetime(string='Pakrovimo laikas', default=default_datetime)
    estimated_delivery_time = fields.Datetime(string='Numatomas pristatymo laikas', default=default_datetime)
    driver_id = fields.Many2one('hr.employee', string='Vairuotojas')  # TODO: remove
    vehicle_driver_id = fields.Many2one('res.partner', string='Vairuotojas',
                                        domain=[('is_company', '=', False), ('is_active_employee', '=', True)])
    vehicle_name = fields.Char(string='Automobilis', default='VW Transporter LTC919')
    courier_id = fields.Many2one('hr.employee', string='Krovinį išdavė')
    carrier_id = fields.Many2one('res.partner', string='Vežėjas', default=lambda self: self.env.user.company_id)

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        res = super(AccountInvoice, self)._onchange_partner_id()

        custom_partner_dict = {
            '305232183': {
                'vehicle_name': 'Mercedes Vito LJA 479',
                'driver_name': 'Mindaugas Stonys',
            },
            '48810130532': {
                'vehicle_name': 'VW Caddy HCG 142',
                'driver_name': 'Ignas Čerkauskas'
            },
            '8747611': {
                'vehicle_name': 'Toyota Hiace LGI 446',
                'driver_name': 'Ūkininkas Aidas Abromaitis'
            }
        }
        custom_partner = custom_partner_dict.get(self.partner_id.kodas)
        if custom_partner:
            self.carrier_id = self.partner_id.id
            self.vehicle_name = custom_partner.get('vehicle_name')
            vehicle_driver = self.env['res.partner'].search([
                ('name', '=', custom_partner.get('driver_name')),
            ])
            if vehicle_driver:
                self.vehicle_driver_id = vehicle_driver.id
        return res


AccountInvoice()
