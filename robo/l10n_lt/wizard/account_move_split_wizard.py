# -*- coding: utf-8 -*-
from __future__ import division
from collections import defaultdict
from odoo import _, api, exceptions, fields, models, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class AccountMoveSplitWizard(models.TransientModel):

    _name = 'account.move.split.wizard'

    def _default_date_from(self):
        active_id = self._context.get('active_id')
        if active_id:
            move = self.env['account.move'].browse(active_id).exists()
            if move:
                return move.date

    date_from = fields.Date(string='Data nuo', default=_default_date_from)
    number_of_months = fields.Integer(string='Mėnesių skaičius')
    move_id = fields.Many2one('account.move', string='Žurnalo įrašas')
    account_id = fields.Many2one('account.account', string='Debetuojama sąskaita')

    @api.multi
    def split_account_move(self):
        self.ensure_one()
        AccountMove = self.env['account.move']

        move = self.move_id
        if not move:
            active_id = self._context.get('active_id')
            if active_id:
                move = AccountMove.browse(active_id).exists()
                if not move:
                    raise exceptions.ValidationError(_('Nenustatytas žurnalo įrašas.'))

        if self.number_of_months <= 0:
            raise exceptions.ValidationError(_('Mėnesių skaičius turi būti teigiamas.'))

        currency = move.company_id.currency_id
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        n = self.number_of_months
        lines = defaultdict(list)

        # Create a dictionary of split move lines values
        for line in move.line_ids:
            amount_to_distribute = line.debit - line.credit
            is_positive = tools.float_compare(amount_to_distribute, 0.0, precision_rounding=currency.rounding) > 0

            base_split_line_values = {
                'ref': _('Išskaidyta periodui %s') % (line.ref or '/'),
                'partner_id': line.partner_id.id,
                'account_id': line.account_id.id if is_positive else self.account_id.id,
                'journal_id': line.journal_id.id,
                'analytic_account_id': line.analytic_account_id.id,
                'product_id': line.product_id.id,

            }
            for i in range(n):
                # P3:DivOK - amount to distribute is float
                amount = currency.round(amount_to_distribute / (n - i))
                amount_to_distribute -= amount
                split_line_values = base_split_line_values.copy()
                split_line_values.update({
                    'date': date_from + relativedelta(months=i),
                    'debit': 0.0 if is_positive else -amount,
                    'credit': amount if is_positive else 0.0,
                    'name': line.name + _(' (%s iš %s)') % (i + 1, n),
                })
                lines[i].append((0, 0, split_line_values))

        base_split_move_values = {
            'ref': _('Išskaidyta periodui %s') % (move.ref or '/'),
            'journal_id': move.journal_id.id,
        }

        split_move_ids = []
        # Create split moves
        for i in range(n):
            split_move_values = base_split_move_values.copy()
            split_move_values.update({
                'name': move.name + _(' (%s iš %s)') % (i + 1, n),
                'date': date_from + relativedelta(months=i),
                'line_ids': lines[i],
            })
            split_move = AccountMove.create(split_move_values)
            split_move.post()
            split_move_ids.append(split_move.id)

        if not split_move_ids:
            raise exceptions.UserError(_('Nebuvo sukurta naujų įrašų.'))

        return {
            'name': _('Žurnalo įrašai'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', split_move_ids)],
        }
