# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _, exceptions
from datetime import datetime
from odoo.tools import float_compare
from dateutil.relativedelta import relativedelta


class AccountVatWizard(models.TransientModel):
    _name = 'account.vat.wizard'

    def default_date_from(self):
        date_now = datetime.utcnow()
        year, month = date_now.year, date_now.month
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        date_from = datetime(year, month, 1)
        return date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_date_to(self):
        date_now = datetime.utcnow()
        year, month = date_now.year, date_now.month
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        date_from = datetime(year, month, 1)
        date_to = date_from + relativedelta(day=31)
        return date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_journal_id(self):
        return self.env.user.company_id.vat_journal_id

    def default_company_id(self):
        return self.env.user.company_id

    def default_bank_journal_id(self):
        return False

    date_from = fields.Date(string='Data nuo', default=default_date_from, required=True)
    date_to = fields.Date(string='Data iki', default=default_date_to, required=True)
    journal_id = fields.Many2one('account.journal', string='PVM žurnalas', default=default_journal_id, required=True)
    company_id = fields.Many2one('res.company', string='Kompanija', default=default_company_id, required=True)
    action = fields.Selection([('nothing', 'Jokio veiksmo'),
                               ('create', 'Sukurti bankinį išrašą'),
                               ('inform', 'Sukurti bankinį išrašą ir rodyti vadovui')],
                              string='Automatinis veiksmas', default='nothing', required=True)
    bank_journal_id = fields.Many2one('account.journal', string='Bankas', domain=[('type', '=', 'bank')],
                                      default=default_bank_journal_id)

    @api.onchange('company_id')
    def onchange_company(self):
        self.journal_id = self.company_id.vat_journal_id.id
        self.bank_journal_id = self.company_id.payroll_bank_journal_id

    @api.multi
    def create_pvm_entries(self):
        account_move_ids = self.env['account.account'].create_pvm_record(self.date_from, self.date_to,
                                                                         self.company_id.id, self.journal_id.id)

        if self.action in ('create', 'inform'):
            if not self.bank_journal_id:
                raise exceptions.UserError(_('Nurodykite žurnalą'))
            lines = self.env['account.move'].browse(account_move_ids).mapped('line_ids').filtered(
                lambda l: l.account_id.code.startswith('4') and l.account_id.reconcile
                and (not l.currency_id and float_compare(l.amount_residual, 0.0, precision_rounding=0.01) < 0 or
                     l.currency_id and float_compare(l.amount_residual_currency, 0.0, precision_rounding=0.01) < 0)
            )
            if not lines:
                raise exceptions.Warning(_('Banko išrašas nebuvo sukurtas, šiam mėnesiui nėra mokėtino PVM. '
                                           'Pakartokite operaciją be automatinio veiksmo opcijos.'))
            ctx = {'aml_ids': lines.ids, 'default_journal_id': self.bank_journal_id.id}
            wizard = self.env['account.invoice.export.wizard'].with_context(ctx).create({})
            wizard._onchange_journal_set_preferred_bank_account()
            bank_statement_view = wizard.with_context(pvm_bank_statement=True).create_bank_statement()
            if self.action == 'inform':
                bank_statement_id = bank_statement_view.get('res_id')
                self.env['account.bank.statement'].browse(bank_statement_id).show_front()
            # return bank_statement_view

        action = self.env.ref('account.action_move_journal_line')
        if len(account_move_ids) == 1:
            return {
                'name': action.name,
                'id': action.id,
                'view_mode': 'form',
                'view_id': False,
                'view_type': 'form',
                'res_model': 'account.move',
                'type': 'ir.actions.act_window',
                'target': 'current',
                'res_id': account_move_ids[0],
                'context': {},
            }
        else:
            return {
                'name': action.name,
                'id': action.id,
                'view_mode': 'tree',
                'view_id': False,
                'view_type': 'form',
                'res_model': 'account.move',
                'type': 'ir.actions.act_window',
                'target': 'current',
                'domain': [('id', 'in', account_move_ids)],
                'context': {},
            }
