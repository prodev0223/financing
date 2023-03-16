# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    default_royalty_amount = fields.Float(string='Bazinė honoraro suma',
                                          groups='robo_basic.group_robo_premium_manager')
    yearly_psd_amount = fields.Float(string='Metinė PSD įmokų suma')
    yearly_psd_amount_paid = fields.Float(string='Apmokėta PSD įmokų suma', compute='_compute_yearly_psd_amount_paid')
    is_accountant = fields.Boolean(compute='_compute_is_accountant')
    start_of_work = fields.Date(string='Darbo pradžia')

    @api.depends('address_home_id')
    def _compute_yearly_psd_amount_paid(self):
        psd_account_code = '44313'
        account_journal_code = 'KL'

        account_id = self.env['account.account'].sudo().search([('code', '=', psd_account_code)], limit=1).id
        account_journal_id = self.env['account.journal'].sudo().search([('code', '=', account_journal_code)], limit=1).id

        current_year = datetime.now().year
        date_from = datetime.strptime(('%s-01-01' % current_year), '%Y-%m-%d')
        date_to = datetime.strptime(('%s-12-31' % current_year), '%Y-%m-%d')

        account_move_lines = self.env['account.move.line'].sudo().search([('journal_id', '=', account_journal_id), ('account_id', '=', account_id),
                                                                   ('partner_id', '=', self.sudo().address_home_id.id),
                                                                   ('date', '>=', date_from), ('date', '<=', date_to)])

        self.yearly_psd_amount_paid = abs(sum(line.balance for line in account_move_lines))

    @api.multi
    def _compute_is_accountant(self):
        is_accountant = self.env.user.is_accountant()
        for rec in self:
            rec.is_accountant = is_accountant


HrEmployee()
