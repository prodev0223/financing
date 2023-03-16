# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, _
from odoo.tools import float_compare, float_is_zero


class AssetModify(models.TransientModel):
    _inherit = 'asset.modify'

    old_value = fields.Float(string='Current Value', readonly=True)
    new_value = fields.Float(string='New Value')
    date = fields.Date(string='Date', required=True)

    @api.onchange('date')
    def _onchange_date(self):
        asset_id = self.env.context.get('active_id', False)
        asset = self.env['account.asset.asset'].browse(asset_id)
        if asset:
            residual = asset.with_context(date=self.date).current_value
            self.new_value = residual
            self.old_value = residual

    @api.model
    def default_get(self, fields):
        res = super(AssetModify, self).default_get(fields)
        asset_id = self.env.context.get('active_id')
        asset = self.env['account.asset.asset'].browse(asset_id)
        if 'name' in fields:
            res.update({'name': asset.name})
        if 'old_value' in fields:
            res.update({'old_value': asset.current_value, 'new_value': asset.current_value})
        if 'method_number' in fields and asset.method_time == 'number':
            res.update({'method_number': asset.method_number})
        if 'method_period' in fields:
            res.update({'method_period': asset.method_period})
        if 'method_end' in fields and asset.method_time == 'end':
            res.update({'method_end': asset.method_end})
        if self.env.context.get('active_id'):
            res['asset_method_time'] = self._get_asset_method_time()
        return res

    @api.multi
    def modify(self):
        date = self.date
        asset_id = self.env.context.get('active_id', False)
        asset = self.env['account.asset.asset'].browse(asset_id)
        use_sudo = self.env.user.has_group('ilgalaikis_turtas.group_asset_manager')
        if use_sudo and not self.env.user.has_group('base.group_system'):
            asset.message_post('Revaluating asset')
            self = self.sudo()
        asset.check_asset_category_all_relevant_accounts()
        if asset.state != 'open':
            raise exceptions.UserError(_('Cannot modify depreciation of not running asset'))
        if asset.method != 'linear':
            raise exceptions.UserError(_('Cannot modify depreciation if computation method is not linear.'))
        asset.ensure_lines_not_posted(date)
        future_revaluations = asset.revaluation_history_ids.filtered(lambda h: h.date >= self.date)
        if future_revaluations:
            raise exceptions.UserError(_('Negalima atlikti perkainavimo šiai datai, nes ateityje egzistuoja suplanuoti '
                                         'perkainavimai'))
        self.create_revaluation_move()
        vals = {
            'asset_id': asset_id,
            'date': date,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'method_period': self.method_period,
            'method_number': self.method_number,
            'name': self.name,
        }

        self.env['account.asset.revaluation.history'].create(vals)
        asset.compute_depreciation_board()
        res = {'type': 'ir.actions.act_window_close'}
        return res

    @api.multi
    def create_revaluation_move(self):
        self.ensure_one()
        asset_id = self.env.context.get('active_id')
        asset = self.env['account.asset.asset'].browse(asset_id)
        depreciation_date = self.date
        company_currency = asset.company_id.currency_id
        current_currency = asset.currency_id
        amount_diff = self.new_value - self.old_value
        prec = self.env['decimal.precision'].precision_get('Account')
        if float_is_zero(amount_diff, precision_digits=prec):
            raise exceptions.UserError(_(''))

        asset_name = asset.name + ' (%s/)' % asset.method_number
        reference = asset.code
        journal_id = asset.category_id.journal_id.id
        partner_id = asset.partner_id.id
        category = asset.category_id

        base_move_line_vals = {
            'name': asset_name,
            'debit': 0.0,
            'credit': 0.0,
            'journal_id': journal_id,
            'partner_id': partner_id,
            'analytic_account_id': False,
            'date': depreciation_date,
            'currency_id': company_currency != current_currency and current_currency.id or False,
        }

        move_lines = []

        if float_compare(amount_diff, 0.0, precision_digits=prec) != 0:
            if amount_diff > 0:
                credit_account = category.account_revaluation_reserve_id.id
                debit_account = category.account_asset_id.id
            else:
                credit_account = category.account_asset_id.id
                debit_account = category.account_revaluation_reserve_id.id

            if not credit_account:
                raise exceptions.UserError(_('Ilgalaikio turto kategorijoje nenustatyta perkainavimo rezervo sąskaita'))
            if not debit_account:
                raise exceptions.UserError(_('Ilgalaikio turto kategorijoje nenustatyta ilgalaikio turto sąskaita'))

            move_line = base_move_line_vals.copy()
            move_line.update({
                'account_id': credit_account,
                'credit': abs(amount_diff),
                'amount_currency': company_currency != current_currency and -abs(amount_diff) or 0.0,
            })
            move_lines.append((0, 0, move_line))
            move_line = base_move_line_vals.copy()
            move_line.update({
                'account_id': debit_account,
                'debit': abs(amount_diff),
                'amount_currency': company_currency != current_currency and abs(amount_diff) or 0.0,
            })
            move_lines.append((0, 0, move_line))

        if not move_lines:
            return False

        move_vals = {
            'ref': reference,
            'date': depreciation_date or False,
            'journal_id': journal_id,
            'line_ids': move_lines,
            'asset_id': asset.id
        }
        move = self.env['account.move'].create(move_vals)
        move.post()
        return move


AssetModify()
