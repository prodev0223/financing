# -*- coding: utf-8 -*-


from odoo import api, fields, models


class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    num_days = fields.Integer(string='Payment Term number of days', compute='_num_days')

    @api.one
    @api.depends('line_ids.days', 'line_ids.value')
    def _num_days(self):
        self.num_days = 0
        line = self.line_ids.filtered(lambda r: r.value == 'balance')
        if line:
            self.num_days = line.days

    @api.model
    def get_or_create_payment_term_by_days(self, num_days):
        term_line_obj = self.sudo().env['account.payment.term.line']
        term_obj = self.sudo().env['account.payment.term']
        line_id = term_line_obj.search([('value', '=', 'balance'), ('days', '=', num_days)], limit=1)
        if line_id:
            return line_id.payment_id.id
        else:
            term_id = term_obj.create({
                'name': str(num_days) + ' d.',
                'note': str(num_days) + ' d.',
                'line_ids': [(0, 0, {
                    'value': 'balance',
                    'days': num_days,
                })],
            })
            return term_id.id
