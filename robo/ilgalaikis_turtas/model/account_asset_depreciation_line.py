# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, _, tools


class AccountAssetDepreciationLine(models.Model):
    _inherit = 'account.asset.depreciation.line'

    move_ids = fields.One2many('account.move', 'depreciation_line_id')

    move_check = fields.Boolean(compute='_compute_move_check', string='Posted', track_visibility='always', store=True)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita',
                                          default=lambda self: self.asset_id.account_analytic_id)

    revaluation_depreciation = fields.Float(string='Perkainavimo nusidėvėjimas', default=0.0, readonly=True)
    revaluation_total_depreciated_amount = fields.Float(string='Nudėvėtas perkainavimas', default=0.0, readonly=True)
    remaining_revaluation_value = fields.Float(string='Perkainavimo nusidėvėjimo likutis', default=0.0, readonly=True)
    total_amount_to_be_depreciated = fields.Float(string='Visas likutinis nusidėvėjimas',
                                                  compute='_compute_total_amount_to_be_depreciated')

    amount_not_by_norm = fields.Float(string='Depreciation amount by norm', digits=0, default=0.0, required=True)
    is_amount_not_by_norm = fields.Boolean(related='asset_id.is_depreciated_not_by_norm')

    @api.one
    @api.depends('remaining_value', 'remaining_revaluation_value')
    def _compute_total_amount_to_be_depreciated(self):
        self.total_amount_to_be_depreciated = self.remaining_value + self.remaining_revaluation_value - self.asset_id.salvage_value

    @api.one
    @api.depends('move_ids')
    def _compute_move_check(self):
        self.move_check = bool(self.move_ids)

    @api.multi
    def update_aml_vals_with_analytic_id(self, vals):
        self.ensure_one()
        account_id = vals.get('account_id')
        if account_id:
            account = self.env['account.account'].browse(account_id)
            if account and account.code[0] in ('5', '6'):
                vals['analytic_account_id'] = self.account_analytic_id.id or self.asset_id.account_analytic_id.id

    @api.multi
    def get_account_move_default_values(self):
        self.ensure_one()
        asset = self.asset_id
        method_number = asset.method_number if not asset.is_depreciated_not_by_norm else asset.method_number_not_by_norm
        asset_name = asset.name + ' (%s/%s)' % (self.sequence, method_number)
        partner_id = asset.partner_id.id
        company_currency = asset.company_id.currency_id
        current_currency = asset.currency_id
        reference = asset.code
        date = self.env.context.get('depreciation_date') or self.depreciation_date or fields.Date.context_today(self)
        journal_id = asset.category_id.journal_id.id
        move_vals = {
            'ref': reference,
            'date': date,
            'journal_id': journal_id,
            'depreciation_line_id': self.id
        }
        move_line_vals = {
            'name': asset_name,
            'debit': 0.0,
            'credit': 0.0,
            'journal_id': journal_id,
            'partner_id': partner_id,
            'currency_id': company_currency != current_currency and current_currency.id or False,
            'date': date,
            'amount_currency': 0.0
        }
        return {'account_move_values': move_vals, 'account_move_line_values': move_line_vals}

    @api.multi
    def remove_move(self):
        for line in self.filtered(lambda l: l.move_check).sorted(lambda l: l.depreciation_date, reverse=True):
            depreciation_lines = line.asset_id.depreciation_line_ids
            later_posted_lines = depreciation_lines.filtered(lambda r: r.move_check and
                                                                       r.depreciation_date > line.depreciation_date)
            if later_posted_lines:
                raise exceptions.UserError(_('Cannot unpost if there are later unposted lines'))
            line_moves = self.env['account.move']
            line_moves |= line.move_id
            line_moves |= line.move_ids
            line_moves.write({'state': 'draft'})
            line_moves.unlink()

    @api.multi
    def create_move(self, post_move=True):
        created_moves = self.env['account.move']

        if not self:
            return created_moves
        move_checks = list(set(self.mapped('move_check')))
        if len(move_checks) != 1:
            raise exceptions.UserError(_('Negalima sukurti šio nudėvėjimo, nes pasirinktų eilučių būsenos skiriasi'))
        if move_checks[0]:
            # Cancel the posted move
            self.remove_move()
            return created_moves

        # Actually create the move
        for line in self.sorted(lambda l: (l.asset_id.id, l.depreciation_date)):
            unposted_lines = line.asset_id.depreciation_line_ids.filtered(lambda r: not r.move_check and
                                                                          r.depreciation_date < line.depreciation_date)
            if unposted_lines:
                raise exceptions.UserError(_('Cannot post if there are earlier unposted lines'))

            company_currency = line.asset_id.company_id.currency_id
            current_currency = line.asset_id.currency_id

            category = line.asset_id.category_id

            depreciation_acc = line.asset_id.account_depreciation_id.id or category.account_depreciation_id.id  # 6115
            if category.enable_accounts_filter and category.account_prime_cost_id:
                depreciation_accumulation_acc = category.account_prime_cost_id.id
            else:
                depreciation_accumulation_acc = category.account_asset_id.id

            if line.asset_id.account_asset_id:
                depreciation_accumulation_acc = line.asset_id.account_asset_id.id

            if not depreciation_acc:
                raise exceptions.UserError(_('Depreciation account not configured for asset category %s') % category.name)
            if not depreciation_accumulation_acc:
                raise exceptions.UserError(
                    _('Accumulated depreciation account not configured for asset category %s') % category.name)

            base_values = line.get_account_move_default_values()
            move_vals = base_values.get('account_move_values', {})
            move_vals['depreciation_line_id'] = line.id
            base_move_line_vals = base_values.get('account_move_line_values', {})

            amount_original_depreciation = current_currency.compute(line.amount, company_currency)
            amount_revaluation_depreciation = current_currency.compute(line.revaluation_depreciation, company_currency)
            amount_not_by_norm_depreciation = current_currency.compute(line.amount_not_by_norm, company_currency) or 0.0
            total_depreciation_amount = amount_original_depreciation + amount_revaluation_depreciation

            main_move_lines = []

            # TODO do we care about this amount currency because it is the same for all move lines
            amount_currency = company_currency != current_currency and abs(line.amount) or 0.0
            amount_currency_not_by_norm = company_currency != current_currency and abs(line.amount_not_by_norm) or 0.0

            # Full depreciation amount move line to account depreciation
            depreciation_debit_move_line = base_move_line_vals.copy()
            depreciation_debit_move_line.update({
                'account_id': depreciation_acc,  # 6115
                'debit': total_depreciation_amount,
                'amount_currency': amount_currency,
            })
            line.update_aml_vals_with_analytic_id(depreciation_debit_move_line)
            main_move_lines.append((0, 0, depreciation_debit_move_line))

            # Only the original depreciation amount to depreciation accumulation account (revaluation depreciation
            # goes to another account)
            depreciation_credit_move_line = base_move_line_vals.copy()
            depreciation_credit_move_line.update({
                'account_id': depreciation_accumulation_acc,  # 1217
                'credit': amount_original_depreciation,
                'amount_currency': -amount_currency,
            })
            line.update_aml_vals_with_analytic_id(depreciation_credit_move_line)
            main_move_lines.append((0, 0, depreciation_credit_move_line))

            reserve_move = False

            # Positive Revaluation exists
            if tools.float_compare(amount_revaluation_depreciation, 0.0, precision_digits=2) > 0:
                revaluation_depreciation_acc = category.account_asset_revaluation_depreciation_id  # 1218
                if not revaluation_depreciation_acc:
                    raise exceptions.UserError(
                        _('Revaluation depreciation account not configured for asset category %s') % category.name)
                revaluation_reserve_acc = category.account_revaluation_reserve_id  # 321
                if not revaluation_reserve_acc:
                    raise exceptions.UserError(
                        _('Revaluation reserve Account not configured for asset category %s') % category.name)
                revaluation_profit_acc = category.account_revaluation_profit_id  # 3412
                if not revaluation_profit_acc:
                    raise exceptions.UserError(
                        _('Revaluation profit account not configured for asset category %s') % category.name)

                amount_revaluation_depreciation_is_positive = tools.float_compare(amount_revaluation_depreciation, 0.0, precision_digits=2) > 0

                # The revaluation depreciation goes to this account
                revaluation_credit_move_line = base_move_line_vals.copy()
                revaluation_credit_move_line.update({
                    'account_id': revaluation_depreciation_acc.id,  # 1218
                    'debit': 0.0 if amount_revaluation_depreciation_is_positive else -amount_revaluation_depreciation,
                    'credit': amount_revaluation_depreciation if amount_revaluation_depreciation_is_positive else 0.0,
                    'amount_currency': -amount_currency,
                })
                line.update_aml_vals_with_analytic_id(revaluation_credit_move_line)
                main_move_lines.append((0, 0, revaluation_credit_move_line))

                # Create_reserve_moves_after_increase
                reserve_debit_line = base_move_line_vals.copy()
                reserve_debit_line.update({
                    'account_id': revaluation_reserve_acc.id,  # 321
                    'debit': amount_revaluation_depreciation,
                    'amount_currency': amount_currency,
                })

                reserve_credit_line = base_move_line_vals.copy()
                reserve_credit_line.update({
                    'account_id': revaluation_profit_acc.id,  # 3412
                    'credit': amount_revaluation_depreciation,
                    'amount_currency': amount_currency,
                })
                line.update_aml_vals_with_analytic_id(reserve_debit_line)
                line.update_aml_vals_with_analytic_id(reserve_credit_line)

                reserve_move = move_vals.copy()
                reserve_move.update({
                    'line_ids': [(0, 0, reserve_debit_line), (0, 0, reserve_credit_line)],
                })

            main_move = move_vals.copy()
            main_move.update({
                'line_ids': main_move_lines,
            })
            main_move = self.env['account.move'].create(main_move)
            line.write({'move_id': main_move.id})
            created_moves |= main_move
            if reserve_move:
                created_moves |= self.env['account.move'].create(reserve_move)

            if line.asset_id.is_depreciated_not_by_norm and line.asset_id.method_number_not_by_norm:
                nondeductible_debit_account_code = '655'  # 655
                nondeductible_debit_account_id = self.env['account.account'].search([
                    ('code', '=', nondeductible_debit_account_code)]).id
                if not nondeductible_debit_account_id:
                    raise exceptions.ValidationError(
                        _('Debit account #{} was not found. Please contact support.').format(
                            nondeductible_debit_account_code))
                amount_difference = abs(amount_original_depreciation - amount_not_by_norm_depreciation)

                nondeductible_debit_move_line = base_move_line_vals.copy()
                nondeductible_debit_move_line.update({
                    'account_id': nondeductible_debit_account_id,
                    'debit': amount_difference,
                    'amount_currency': amount_currency_not_by_norm,
                })

                nondeductible_credit_move_line = base_move_line_vals.copy()
                nondeductible_credit_move_line.update({
                    'account_id': depreciation_accumulation_acc,
                    'credit': amount_difference,
                    'amount_currency': -amount_currency_not_by_norm,
                })

                nondeductible_move = move_vals.copy()
                nondeductible_move.update({
                    'line_ids': [(0, 0, nondeductible_debit_move_line), (0, 0, nondeductible_credit_move_line)],
                })
                created_moves |= self.sudo().env['account.move'].create(nondeductible_move)

        if post_move and created_moves:
            created_moves.post()
        return created_moves

    @api.multi
    def post_lines_and_close_asset(self):
        # We don't want to close the asset automatically, unless sold or writtenoff (and the related methods already
        # take care of that), so we overload this method from addons/account_asset to remove the closing
        self.log_message_when_posted()


AccountAssetDepreciationLine()
