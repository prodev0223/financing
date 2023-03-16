# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from six import iteritems
import json


class AdvancePaymentsWizard(models.TransientModel):
    _name = 'advance.payment.wizard'
    _description = 'Advance Payments wizard'

    def _date(self):
        date = datetime.now() - relativedelta(months=1, day=31)
        return date

    date = fields.Date(string='Data', required=True, default=_date)
    type = fields.Selection([('customer', 'Klientų'), ('supplier', 'Tiekėjų')], string='Tipas', required=True,
                            default='customer')
    account_ids = fields.Many2many('account.account', string='Sąskaitos', domain=[('reconcile', '=', True)])
    line_ids = fields.One2many('advance.payment.wizard.line', 'wizard_id', string='Eilutės')
    extended_mode = fields.Boolean(string='Išplėstinė ataskaita', default=False, inverse='form_lines')

    @api.onchange('type')
    def onch_set_account_ids(self):
        accounts = self.env['account.account']
        if self.type == 'customer':
            accounts = self.env['account.account'].search([('code', 'in', ['2410', '4230', '4231', '4420', '4421'])])
        elif self.type == 'supplier':
            accounts = self.env['account.account'].search([('code', 'in', ['4430', '4431', '2080'])])
        self.account_ids = [(6, 0, accounts.ids)]

    @api.multi
    def form_lines(self):
        aml_payments_domain = [('date', '<=', self.date),
                               ('account_id', 'in', self.account_ids.ids),
                               ('move_id.state', '=', 'posted'),
                               ('journal_id.type', '=', 'bank'),
                               ('matched_credit_ids', '=', False),
                               ('matched_debit_ids', '=', False),
                               ]
        if self.type == 'customer':
            customer_report = True
        else:
            customer_report = False
        if customer_report:
            aml_payments_domain += ['|',
                                        '&',
                                            ('currency_id', '=', False),
                                            ('amount_residual', '<', 0),
                                        '&',
                                            ('currency_id', '!=', False),
                                            ('amount_residual_currency', '<', 0)]
        else:
            aml_payments_domain += ['|',
                                        '&',
                                            ('currency_id', '=', False),
                                            ('amount_residual', '>', 0),
                                        '&',
                                            ('currency_id', '!=', False),
                                            ('amount_residual_currency', '>', 0)]
        payment_amls = self.env['account.move.line'].search(aml_payments_domain)
        partners = payment_amls.mapped('partner_id')

        aml_invoice_domain = [('account_id', 'in', self.account_ids.ids),
                              ('partner_id', 'in', partners.ids),
                              ('move_id.state', '=', 'posted')]

        if customer_report:
            aml_invoice_domain += ['|',
                                    '&',
                                    ('currency_id', '=', False),
                                    ('amount_residual', '>', 0),
                                    '&',
                                    ('currency_id', '!=', False),
                                    ('amount_residual_currency', '>', 0)]
        else:
            aml_invoice_domain += ['|',
                                    '&',
                                    ('currency_id', '=', False),
                                    ('amount_residual', '<', 0),
                                    '&',
                                    ('currency_id', '!=', False),
                                    ('amount_residual_currency', '<', 0)]
        invoices_partner_ids = set(self.env['account.move.line'].search(aml_invoice_domain).mapped('partner_id').ids)

        lines = [(5,)]
        min_amount_to_send = 1
        full_data = defaultdict(self.env['account.move.line'].browse)
        for aml in payment_amls:
            key = (aml.partner_id.id, aml.currency_id.id)
            full_data[key] |= aml

        for (partner_id, currency_id), amls in iteritems(full_data):
            if currency_id:
                amount = sum(amls.mapped('amount_currency'))
                amount_residual = sum(amls.mapped('amount_residual_currency'))
            else:
                amount = sum(amls.mapped('balance'))
                amount_residual = sum(amls.mapped('amount_residual'))
            if abs(amount_residual) < min_amount_to_send:
                continue
            if self.extended_mode:
                lines.extend((0,0,{'partner_id': partner_id,
                             'description': aml.name,
                             'dates': aml.date[:7],
                             'amount': aml.amount_currency if currency_id else aml.balance,
                             'amount_residual': aml.amount_residual_currency if currency_id else aml.amount_residual,
                             'currency_id': currency_id or self.env.user.company_id.currency_id.id,
                             'reconcile_possible': partner_id in invoices_partner_ids})
                             for aml in amls)
                continue

            line_vals = {'partner_id': partner_id,
                         'description': ', '.join(amls.mapped('name')),
                         'dates': ', '.join(sorted(set(aml.date[:7] for aml in amls))),
                         'amount': amount,
                         'amount_residual': amount_residual,
                         'currency_id': currency_id or self.env.user.company_id.currency_id.id,
                         'reconcile_possible': partner_id in invoices_partner_ids}
            lines.append((0, 0, line_vals))
        self.line_ids = lines

    @api.multi
    def get_report(self):
        self.ensure_one()
        # return self.env['report'].get_action(self, 'robo_reminders.unreconciled_payments_report_template')
        data = {
            'context': json.dumps(self._context),
            'doc_ids': self.ids,
            'doc_model': self._name,
                }
        return self.env['report'].get_action(self, 'robo_reminders.unreconciled_payments_report_template', data=data)

    @api.multi
    def name_get(self):
        return [(rec.id, _('Nesudengti mokėjimai')) for rec in self]


AdvancePaymentsWizard()


class AdvancePaymentsWizardLine(models.TransientModel):
    _name = 'advance.payment.wizard.line'

    _order = 'partner_id'

    wizard_id = fields.Many2one('advance.payment.wizard', string='Wizard', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Partneris', required=False, ondelete='cascade')
    description = fields.Char(string='Dokumentas')
    dates = fields.Text(string='Mokėjimo datos')
    amount = fields.Monetary(string='Balansas')
    amount_residual = fields.Monetary(string='Likutinė vertė')
    currency_id = fields.Many2one('res.currency', string='Valiuta')
    reconcile_possible = fields.Boolean(string='Galimi neatitikimai')


AdvancePaymentsWizardLine()
