# -*- coding: utf-8 -*-

from odoo import api, models, fields


class ResCompany(models.Model):

    _inherit = 'res.company'
    gemma_db_sync = fields.Datetime(groups='base.group_system')
    polis_bank_statement_sync = fields.Boolean(groups='base.group_system')

    health_institiution_type_name = fields.Char(string='Sveikatos įstaigos steigėjo aprašymas',
                                                default='Privati asmens sveikatos priežiūros įstaiga')
    health_institiution_id_code = fields.Char(string='Sveikatos įstaigos ID kodas', default='17110')
    allow_exclude_data_from_du_aspi_report = fields.Boolean(
        string='Allow excluding bonus data from DU ASPI reports',
        help='When this box is checked an additional box will appear on bonus EDoc where you can select if you want '
             'the bonuses created by the document to be included in DU ASPI report',
        compute='_compute_allow_exclude_data_from_du_aspi_report',
        inverse='_set_allow_exclude_data_from_du_aspi_report',
    )

    @api.multi
    def _compute_allow_exclude_data_from_du_aspi_report(self):
        self.ensure_one()
        allow_exclude_data_from_du_aspi_report = self.env['ir.config_parameter'].sudo().get_param(
            'allow_exclude_data_from_du_aspi_report') == 'True'
        self.allow_exclude_data_from_du_aspi_report = allow_exclude_data_from_du_aspi_report or False

    @api.multi
    def _set_allow_exclude_data_from_du_aspi_report(self):
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param('allow_exclude_data_from_du_aspi_report',
                                                         str(self.allow_exclude_data_from_du_aspi_report))


ResCompany()
