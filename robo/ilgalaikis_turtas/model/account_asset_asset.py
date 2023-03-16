# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, exceptions, _, tools
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, float_compare


def last_day_of_month(date_dt):
    return date_dt == date_dt + relativedelta(day=31)


def not_positive(amount, precision_digits=2):
    return tools.float_compare(amount, 0.0, precision_digits=precision_digits) <= 0


class AccountAssetAsset(models.Model):
    _name = 'account.asset.asset'
    _inherit = ['account.asset.asset', 'mail.thread']

    def _default_pirkimo_data(self):
        if self.invoice_id and self.invoice_id.operacijos_data:
            return self.invoice_id.operacijos_data
        else:
            return False

    date = fields.Date(string='Entry date', required=True, lt_string='Įvedimo data')
    date_first_depreciation = fields.Date(string='Pirmojo nusidėvėjimo data', lt_string='Pirmojo nusidėvėjimo data',
                                          required=True, inverse='force_recompute_depreciation_board')
    method_period = fields.Integer(default=1)
    pirkimo_data = fields.Date(string='Purchase date', lt_string='Pirkimo data')
    method_progress_factor = fields.Float(string='Degressive Factor', readonly=True, default=0.3,
                                          states={'draft': [('readonly', False)]})
    prorata = fields.Boolean(default=False)
    responsible_employee_id = fields.Many2one('hr.employee', string='Materially responsible person',
                                              compute='_compute_responsible', store=True)
    responsible_date = fields.Date(string='Responsible from', compute='_compute_responsible', store=True)
    responsible_history = fields.One2many('account.asset.responsible', 'asset_id', string='Responsibility history',
                                          readonly=True, copy=False)
    revaluation_history_ids = fields.One2many('account.asset.revaluation.history', 'asset_id',
                                              string='Revaluation history', readonly=True)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita',
                                          inverse='force_recompute_depreciation_board')

    account_depreciation_id = fields.Many2one('account.account',
                                              string='Nusidėvėjimo įrašai: Ilgalaikio turto sąskaita',
                                              domain=[('internal_type', '=', 'other'), ('deprecated', '=', False)],
                                              readonly=True, states={'draft': [('readonly', False)]})

    current_value = fields.Float(string='Current Value', compute='_compute_current_value', store=True)

    value_adjusted = fields.Float(string='Gross Value Adjusted', compute='_compute_value_adjusted', store=True)
    total_value_residual = fields.Float(compute='_compute_amount_total_residual', store=True, digits=0,
                                        string='Residual Value Adjusted')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency', store=True)
    sale_invoice_id = fields.Many2one('account.invoice', readonly=True, string='Sale invoice',
                                      copy=False)  # OBSOLETE, Now there can be multiple sales.
    written_off_or_sold = fields.Boolean(string='Written off or sold', readonly=True, copy=False)
    date_close = fields.Date(
        string='Naudojimo pabaigos data')  # FIXME: it seems that value is not set correctly when the good is liquidated
    original_value = fields.Float(string='Original Value', track_visibility='onchange')
    change_line_ids = fields.One2many('account.asset.change.line', 'asset_id', string='Pagerinimai',
                                      readonly=True)
    value_gross_total = fields.Float(string='Vertė', compute='_compute_value_gross_total', store=True)
    value_residual_effective = fields.Float(string='Likutinė nudėvėtina vertė',
                                            compute='_compute_value_residual_effective')
    value_at_date = fields.Float(string='Value at the given moment', compute='_compute_value_at_date')
    change_between_dates = fields.Float(string='Value changes and revaluations in the interval',
                                        compute='_compute_change_between_dates')
    sell_move_id = fields.Many2one('account.move', readonly=True)
    sell_move_ids = fields.Many2many('account.move', readonly=True)
    revaluation_move_ids = fields.One2many('account.move', 'asset_id', readonly=True)
    writeoff_move_id = fields.Many2one('account.move', string='Nurašymų žurnalo įrašas', readonly=True)
    writeoff_date = fields.Date(string='Nurašymo data', related='writeoff_move_id.date', readonly=True)
    salvage_value = fields.Float(default=1.0)
    write_off_between_dates = fields.Float(string='Value changes and revaluations in the interval',
                                           compute='_compute_write_off_between_dates')
    historical_change_amount = fields.Float(string='Historical value increases')
    code = fields.Char(copy=False)

    sale_line_ids = fields.One2many('account.invoice.line', 'asset_id', string='Pardavimai')
    split_asset_ids = fields.One2many('account.asset.asset', 'previous_asset_id',
                                      string='Išskaidyti ilgalaikio turto įrašai', readonly=True)
    previous_asset_id = fields.Many2one('account.asset.asset', string='Pradinis ilgalaikio turto įrašas', readonly=True,
                                        ondelete='restrict')

    quantity = fields.Float(string='Pradinis kiekis', required=True, default=1.0)
    original_quantity = fields.Float(string='Originalus kiekis', required=True, default=1.0)
    residual_quantity = fields.Float(string='Likutinis kiekis', compute='_compute_residual_quantity')
    account_asset_id = fields.Many2one('account.account', string='Ilgalaikio turto sąskaita',
                                       domain=[('internal_type', '=', 'other'), ('deprecated', '=', False)],
                                       readonly=True, states={'draft': [('readonly', False)]})
    method_number = fields.Integer(inverse='force_recompute_depreciation_board')
    method_number_not_by_norm = fields.Integer(inverse='force_recompute_depreciation_board')
    is_depreciated_not_by_norm = fields.Boolean(string='Asset depreciated not according to norm')
    next_forced_depreciation_date = fields.Date(string='Next forced depreciation date')

    price_unit = fields.Float(
        string='Vieneto vertė',
        compute='_compute_price_unit',
        help='(Vertė / Kiekis)'
    )

    original_price_unit = fields.Float(
        string='Originali vieneto vertė',
        compute='_compute_original_price_unit',
        help='(Pradinė vertė / pradinis kiekis)'
    )

    residual_price_unit = fields.Float(
        string='Likutinė nudėvėtina vieneto vertė',
        compute='_compute_residual_price_unit',
        help='(Likutinė vertė / likutinis kiekis)'
    )

    quantity_sold = fields.Float(string='Parduotas kiekis', compute='_compute_quantity_sold')

    method = fields.Selection(selection_add=[('cant_be_depreciated', 'Neskaičiuojama')])

    asset_department_id = fields.Many2one('account.asset.department', string='Ilgalaikio turto skyrius', required=False)

    salvage_value_check_performed = fields.Boolean(readonly=True)

    #####################
    #  COMPUTE METHODS  #
    #####################

    @api.depends('responsible_history.employee_id', 'responsible_history.date')
    def _compute_responsible(self):
        for rec in self.filtered('responsible_history'):
            last = rec.responsible_history.sorted(key=lambda r: r.date, reverse=True)[0]
            rec.responsible_date = last.date
            rec.responsible_employee_id = last.employee_id.id

    @api.multi
    @api.depends('value', 'salvage_value', 'depreciation_line_ids.move_check', 'depreciation_line_ids.amount',
                 'change_line_ids', 'revaluation_history_ids', 'sale_line_ids')
    def _compute_current_value(self):
        for rec in self:
            rec.current_value = rec.total_value_residual + rec.salvage_value

    @api.multi
    @api.depends('value', 'revaluation_history_ids.value_difference')
    def _compute_value_adjusted(self):
        for rec in self:
            revaluation_value_difference = sum(rec.revaluation_history_ids.mapped('value_difference'))
            rec.value_adjusted = rec.value + revaluation_value_difference

    @api.multi
    def current_depreciation_values(self, date=False):
        self.ensure_one()
        if not date:
            date = self._context.get('date') or datetime.utcnow().strftime(DF)
        posted_depreciation_line_ids = self.depreciation_line_ids.filtered(
            lambda l: l.move_check and l.depreciation_date <= date)

        changes = self.change_line_ids.filtered(lambda l: l.date <= date)
        revaluations = self.revaluation_history_ids.filtered(lambda h: h.date <= date)
        sales = self.sale_line_ids.filtered(lambda s: s.date_invoice <= date and s.used_in_calculations)

        change_amounts = sum(changes.mapped('change_amount'))
        revaluation_amounts = sum(revaluations.mapped('value_difference'))
        sale_revaluation_changes = sum(sales.mapped('revaluation_change'))
        sale_depreciation_changes = sum(sales.mapped('depreciation_change'))
        initial_depreciation_amount = self.value - self.salvage_value

        # [How the value has changed] + [Initial depreciation value] + [How the sales impacted the initial values]
        depreciation_left = change_amounts + initial_depreciation_amount + sale_depreciation_changes
        revaluation_depreciation_left = revaluation_amounts + sale_revaluation_changes
        revaluation_total_depreciated = depreciation_total_depreciated = 0.0
        if posted_depreciation_line_ids:
            # We need to get revaluation depreciation changes, otherwise we'll compute later
            # Just grab the data from the latest line posted
            latest_posted_depreciation_line = posted_depreciation_line_ids.sorted(lambda l: l.depreciation_date,
                                                                              reverse=True)[0]
            revaluation_total_depreciated = latest_posted_depreciation_line.revaluation_total_depreciated_amount
            depreciation_total_depreciated = latest_posted_depreciation_line.depreciated_value
            depreciation_left -= latest_posted_depreciation_line.depreciated_value
            revaluation_depreciation_left -= latest_posted_depreciation_line.revaluation_total_depreciated_amount
        depreciation_left = max(depreciation_left, 0.0)
        return {
            'depreciation_left': depreciation_left,
            'revaluation_left': revaluation_depreciation_left,
            'depreciation_depreciated': depreciation_total_depreciated,
            'revaluation_depreciated': revaluation_total_depreciated
        }

    @api.one
    @api.depends('value', 'salvage_value', 'depreciation_line_ids.move_check', 'depreciation_line_ids.amount',
                 'change_line_ids', 'revaluation_history_ids', 'sale_line_ids')
    def _compute_amount_total_residual(self):
        current_depreciation_values = self.current_depreciation_values()
        value_to_be_depreciated = current_depreciation_values.get('depreciation_left', 0.0) + \
                                  current_depreciation_values.get('revaluation_left', 0.0)
        self.total_value_residual = value_to_be_depreciated

    @api.multi
    def _compute_currency(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id.id

    @api.depends('value', 'change_line_ids.change_amount')
    def _compute_value_gross_total(self):
        for rec in self:
            rec.value_gross_total = rec.value + sum(rec.change_line_ids.mapped('change_amount'))

    @api.one
    @api.depends('value_residual', 'change_line_ids.change_amount')
    def _compute_value_residual_effective(self):
        self._compute_amount_total_residual()
        self.value_residual_effective = self.total_value_residual

    @api.multi
    def _compute_value_at_date(self):
        date = self._context.get('date', datetime.utcnow().strftime(DF))

        for asset in self:
            # Get asset lines and revaluation history
            depreciation_lines = asset.depreciation_line_ids.filtered(
                lambda l: l.depreciation_date <= date and l.move_check
            )
            change_lines = asset.change_line_ids.filtered(lambda l: l.date <= date)
            revaluation_history_ids = asset.revaluation_history_ids.filtered(lambda h: h.date <= date)

            # Calculate depreciation amount
            depreciation_amount = sum(depreciation_lines.mapped('amount'))

            # Determine if depreciation should be adjusted when depreciation value exceeds max possible depreciation
            # amount
            # TODO This conditional statement should not be needed. Asset accounting entries should be fixed instead.
            #  This is caused by rounding errors when computing the depreciation board fixed by 4d522eaa
            if depreciation_lines:
                last_depreciation_line = asset.depreciation_line_ids.sorted(
                    key=lambda l: l.depreciation_date, reverse=True
                )[0]
                adjust_depreciated_value = date >= last_depreciation_line.depreciation_date and \
                                           last_depreciation_line.move_check
                if adjust_depreciated_value:
                    total_value_to_depreciate = asset.with_context(date=asset.date).value_at_date - asset.salvage_value
                    # Don't include the depreciated amount for assets that start depreciating at their initiation date
                    total_value_to_depreciate += sum(asset.depreciation_line_ids.filtered(
                        lambda l: l.depreciation_date <= asset.date and l.move_check
                    ).mapped('amount'))

                    # Check the difference between what was actually depreciated and how much should have been
                    # depreciated
                    depreciation_difference = depreciation_amount - total_value_to_depreciate
                    if tools.float_compare(abs(depreciation_difference), 0.01, precision_digits=2) <= 0:
                        # If the depreciated amount exceeds the total value that should have been depreciated by a tiny
                        # margin - return the total value that should have been depreciated.
                        depreciation_amount = total_value_to_depreciate

            # Calculate changes and revaluations
            change_amount = sum(change_lines.mapped('change_amount'))
            revaluation_value = sum(revaluation_history_ids.mapped('value_difference'))

            value = asset.value - depreciation_amount + change_amount + revaluation_value

            if asset.state == 'close' and asset.date < date and asset.written_off_or_sold:
                write_off_date = asset.date_close
                if not write_off_date:
                    depreciation_dates = asset.depreciation_line_ids. \
                        filtered(lambda l: l.move_check).mapped('depreciation_date')
                    depr_dates = depreciation_dates
                    if depr_dates:
                        write_off_date = max(depr_dates)
                if not write_off_date or write_off_date <= date:
                    value = 0.0
            asset.value_at_date = tools.float_round(value, precision_digits=2)

    @api.one
    def _compute_change_between_dates(self):
        today = datetime.utcnow().strftime(DF)
        date_from = self._context.get('date_from', today) or today
        date_to = self._context.get('date_to', today) or today

        change_lines = self.change_line_ids.filtered(lambda l: date_from <= l.date <= date_to)
        revaluation_history_ids = self.revaluation_history_ids.filtered(lambda h: date_from <= h.date <= date_to)

        change_amount = sum(change_lines.mapped('change_amount'))
        revaluation_value_difference = sum(revaluation_history_ids.mapped('value_difference'))

        diff = change_amount + revaluation_value_difference
        if self.date and (date_from < self.date):
            diff += self.historical_change_amount
        self.change_between_dates = tools.float_round(diff, precision_digits=2)

    @api.one
    def _compute_write_off_between_dates(self):
        today = datetime.utcnow().strftime(DF)
        date_to = self._context.get('date_to', today) or today
        diff = 0
        if self.written_off_or_sold:
            dates_depreciations = self.depreciation_line_ids.filtered(lambda r: r.move_check).mapped(
                'depreciation_date')
            date_written_off = self.date_close or max(dates_depreciations) if dates_depreciations else self.date
            if date_written_off <= date_to:
                date_to_prev = (datetime.strptime(date_written_off, DF) - timedelta(
                    days=1)).strftime(DF)
                diff -= self.with_context(date=date_to_prev).value_at_date
        self.write_off_between_dates = diff

    @api.one
    @api.depends('quantity', 'sale_line_ids')
    def _compute_residual_quantity(self):
        self.residual_quantity = self.quantity - self.quantity_sold

    @api.multi
    @api.depends('depreciation_line_ids.move_id', 'sell_move_id', 'sell_move_ids', 'revaluation_move_ids',
                 'writeoff_move_id')
    def _entry_count(self):
        for asset in self:
            depreciation_lines = self.env['account.asset.depreciation.line'].search([
                ('asset_id', '=', asset.id),
                '|',
                ('move_id', '!=', False),
                ('move_ids', '!=', False)])
            res = 0
            for line in depreciation_lines:
                res += len(line.mapped('move_ids')) or len(line.mapped('move_id'))
            res += len(asset.mapped('sell_move_id.id'))
            res += len(asset.mapped('sell_move_ids.id'))
            res += len(asset.mapped('sale_line_ids.invoice_id.move_id.id'))
            res += len(asset.mapped('revaluation_move_ids.id'))
            res += len(asset.mapped('writeoff_move_id.id'))
            asset.entry_count = res or 0

    @api.one
    @api.depends('original_value', 'original_quantity')
    def _compute_original_price_unit(self):
        if not tools.float_is_zero(self.original_quantity, precision_digits=2):
            original_price_unit = self.original_value / self.original_quantity
        else:
            original_price_unit = 0.0
        self.original_price_unit = original_price_unit

    @api.one
    @api.depends('quantity', 'value_residual', 'change_line_ids.change_amount', 'sale_line_ids')
    def _compute_residual_price_unit(self):
        if not tools.float_is_zero(self.residual_quantity, precision_digits=2):
            residual_price_unit = self.value_residual_effective / self.residual_quantity
        else:
            residual_price_unit = 0.0
        self.residual_price_unit = residual_price_unit

    @api.one
    @api.depends('value', 'quantity')
    def _compute_price_unit(self):
        if not tools.float_is_zero(self.quantity, precision_digits=2):
            price_unit = self.value / self.quantity
        else:
            price_unit = 0.0
        self.price_unit = price_unit

    @api.one
    @api.depends('sale_line_ids')
    def _compute_quantity_sold(self):
        date = self._context.get('date')
        if not date:
            date = datetime.utcnow().strftime(DF)
        sale_line_ids = self.sale_line_ids.filtered(lambda l: l.date_invoice <= date and l.used_in_calculations)
        self.quantity_sold = sum(sale_line_ids.mapped('quantity'))

    #####################################
    #  CONSTRAINS AND ONCHANGE METHODS  #
    #####################################

    @api.multi
    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if rec.code and self.search_count([('code', '=', rec.code)]) > 1:
                raise exceptions.ValidationError(_('Ilgalaikio turto numeris negali kartotis.'))

    @api.multi
    @api.constrains('value', 'salvage_value')
    def _check_residual_value(self):
        for rec in self:
            if float_compare(rec.value - rec.salvage_value, 0, precision_digits=2) < 0:
                raise exceptions.ValidationError(_('Turto vertė negali tapti neigiama'))

    @api.multi
    @api.constrains('value', 'quantity')
    def _check_original_price_unit(self):
        is_being_imported = self._context.get('is_being_imported')
        for rec in self:
            # Checks that the long term asset original price unit is more than what is defined in company settings
            if rec.category_id.is_non_material:
                min_value = rec.company_id.longterm_non_material_assets_min_val
            else:
                min_value = rec.company_id.longterm_assets_min_val
            is_financial_property = rec.category_id.name.startswith('16')
            if not is_being_imported and tools.float_compare(
                    rec.original_price_unit, min_value, precision_digits=2) < 0 and not is_financial_property:
                raise exceptions.ValidationError(
                    _('Šio turto vieneto kaina yra per maža priskirti šį turtą, kaip ilgalaikį turtą. Nustatyta, kad įmonė '
                      'ilagalaikiu turtu pripažįsta turtą nuo {0}, o šio turto vieneto vertė yra {1}.'
                      ).format(min_value, round(rec.original_price_unit, 2)))

    @api.multi
    @api.constrains('quantity', 'sale_line_ids')
    def _check_residual_quantity_positive(self):
        for rec in self:
            if tools.float_compare(rec.residual_quantity, 0.0, precision_digits=2) < 0:
                raise exceptions.ValidationError(
                    _('Ilgalaikio turto {0} likutinis kiekis negali būti neigiamas').format(rec.name))

    @api.multi
    @api.constrains('next_forced_depreciation_date')
    def _check_next_forced_depreciation_date(self):
        for rec in self:
            if not rec.next_forced_depreciation_date:
                continue
            if rec.next_forced_depreciation_date < rec.date or rec.next_forced_depreciation_date < rec.date_first_depreciation:
                raise exceptions.ValidationError(
                    _('Next forced depreciation date: {}.\n'
                      'Can not be before than date of introduction: {}.\n'
                      'Or earlier than date of first depreciation: {}.').format(rec.next_forced_depreciation_date,
                                                                                rec.date,
                                                                                rec.date_first_depreciation,
                                                                                ))

    @api.onchange('category_id')
    def _onchange_category_id(self):
        category_account_analytic_id = self.category_id.account_analytic_id
        if category_account_analytic_id:
            self.account_analytic_id = category_account_analytic_id

    @api.onchange('account_analytic_id')
    def _onchange_account_analytic_id(self):
        depreciation_lines_without_move_check = self.depreciation_line_ids.filtered(lambda l: not l.move_check)
        for line_id in depreciation_lines_without_move_check:
            line_id.account_analytic_id = self.account_analytic_id

    @api.onchange('value')
    def _onchange_value(self):
        self.original_value = self.value

    @api.onchange('next_forced_depreciation_date')
    def _onchange_next_forced_depreciation_date(self):
        if not self.next_forced_depreciation_date:
            return
        elif self.next_forced_depreciation_date < self.date:
            return {'warning': {'title': _('Warning'),
                                'message': _('Next forced depreciation date: {}.\n'
                                             'Can not be before than date of introduction: {}.').format(
                                                                                self.next_forced_depreciation_date,
                                                                                self.date,
                                                                                )}}
        elif not self.date_first_depreciation or not self.date:
            return
        elif self.next_forced_depreciation_date < self.date_first_depreciation:
            return {'warning': {'title': _('Warning'),
                                'message': _('Next forced depreciation date: {}.\n'
                                             'Cannot be before than date of first depreciation: {}.').format(
                                                                                self.next_forced_depreciation_date,
                                                                                self.date_first_depreciation,
                                                                                )}}

    ##################
    #  CRUD METHODS  #
    ##################

    @api.model
    def create(self, vals):
        res = super(AccountAssetAsset, self).create(vals=vals)
        if res and self.env.user.company_id.company_activity_form == 'iv':
            res.inform_about_creation()
        return res

    @api.multi
    def write(self, vals):
        dont_recompute = 'depreciation_line_ids' not in vals and 'state' not in vals
        return super(AccountAssetAsset, self.with_context(dont_compute_depreciation_board=dont_recompute)).write(vals)

    #############
    #  ACTIONS  #
    #############

    @api.multi
    def action_self_production(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'asset.production.wizard',
            'context': {'asset_id': self.id},
            'target': 'new',
        }

    @api.multi
    def action_add_responsible(self):
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'asset.assign.responsible',
            'context': {'active_ids': self._ids},
            'target': 'new',
        }

    @api.multi
    def action_set_to_close(self):
        if any(asset.written_off_or_sold for asset in self):
            raise exceptions.UserError(_('You cannot write off asset that has been written off or sold'))
        ctx = {'account_asset_ids': self.mapped('id')}
        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.asset.write.off.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def action_change_value(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset.change.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': {'asset_id': self.id},
        }

    @api.multi
    def action_sell(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset.sell.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': {'active_ids': self._ids},
        }

    @api.multi
    def action_merge(self):
        self = self.filtered(lambda x: x.active)
        if len(self) < 2:
            raise exceptions.UserError(_('You have to select multiple active assets'))
        if any(rec.state != 'draft' for rec in self):
            raise exceptions.UserError(_('Only draft assets may be merged'))
        if len(self.mapped('category_id')) > 1:
            raise exceptions.UserError(_('Only assets of the same category may be merged'))
        related_move_ids = self._get_related_move_ids()
        if related_move_ids:
            raise exceptions.UserError(_('Only assets with no posted journal entries may be merged'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset.merge.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'context': {
                'account_asset_ids': self._ids
            },
        }

    @api.multi
    def ensure_lines_not_posted(self, date, after=True):
        """

        :param date: check entries after or before this date
        :param after: to check before this date or after
        """
        for rec in self:
            depreciation_lines = rec.mapped('depreciation_line_ids').filtered(lambda l: l.move_check)
            if after:
                depreciation_lines = depreciation_lines.filtered(lambda l: l.depreciation_date >= date)
            else:
                depreciation_lines = depreciation_lines.filtered(lambda l: l.depreciation_date <= date)

            if depreciation_lines:
                err_msg = _('Šis veiksmas negali būti atliktas, nes egzistuoja užregistruoti nusidėvėjimo įrašai '
                            'ilgalaikio turto ({0}) įraše, kurie yra {1} už {2}')
                err_msg = err_msg.format(rec.name, 'vėlesni' if after else 'ankstesni', date)
                raise exceptions.UserError(err_msg)

    ############################
    #  OTHER BUSINESS METHODS  #
    ############################

    @api.multi
    def _get_last_depreciation_date(self):
        """
        @return: Returns a dictionary of the effective dates of the last depreciation entry made for given asset ids.
                 If there isn't any, return the purchase date of this asset
        """
        self.env.cr.execute("""
                SELECT a.id as id, COALESCE(MAX(m.date),a.date_first_depreciation) AS date
                FROM account_asset_asset a
                LEFT JOIN account_asset_depreciation_line rel ON (rel.asset_id = a.id)
                LEFT JOIN account_move m ON (rel.move_id = m.id)
                WHERE a.id IN %s
                GROUP BY a.id, m.date order by date""", (tuple(self.ids),))
        result = dict(self.env.cr.fetchall())
        return result

    @api.multi
    def _get_change_data(self):
        self.ensure_one()
        res = {}
        currency = self.currency_id
        for change_line in self.change_line_ids:
            change_amount = change_line.change_amount
            change_depreciation_amount = change_line.method_number
            change_line_date = change_line.date

            date_res = res.get(change_line_date, {})
            date_res['change_amount'] = date_res.get('change_amount', 0.0) + currency.round(change_amount)
            date_res['extra_dotations'] = date_res.get('extra_dotations', 0) + change_depreciation_amount
            res[change_line_date] = date_res

        return res

    @api.multi
    def _get_revaluation_data(self):
        self.ensure_one()
        res = {}
        currency = self.currency_id
        for revaluation in self.revaluation_history_ids:
            revaluation_amount = revaluation.value_difference
            revaluation_date = revaluation.date

            date_res = res.get(revaluation_date, {})
            date_res['change_amount'] = date_res.get('change_amount', 0.0) + currency.round(revaluation_amount)
            res[revaluation_date] = date_res

        return res

    @api.multi
    def _get_sale_data(self):
        self.ensure_one()
        res = {}
        for sale_line in self.sale_line_ids.filtered(lambda s: s.used_in_calculations):
            sale_quantity = sale_line.quantity
            sale_date = sale_line.date_invoice
            sale_depreciation_change = sale_line.depreciation_change
            sale_revaluation_change = sale_line.revaluation_change

            date_res = res.get(sale_date, {})
            date_res['quantity_change'] = date_res.get('quantity_change', 0.0) - sale_quantity
            date_res['depreciation_change'] = date_res.get('depreciation_change', 0.0) + sale_depreciation_change
            date_res['revaluation_change'] = date_res.get('revaluation_change', 0.0) + sale_revaluation_change
            res[sale_date] = date_res

        return res

    @api.multi
    def get_base_move_line_values(self):
        self.ensure_one()
        return {
            'name': self.name,
            'credit': 0.0,
            'debit': 0.0,
            'journal_id': self.category_id.journal_id.id,
            'currency_id': False,
            'amount_currency': 0.0,
        }

    @api.multi
    def inform_about_creation(self):
        self.ensure_one()
        prem_acc_group_id = self.env.ref('robo_basic.group_robo_premium_accountant').id
        admin_group_id = self.env.ref('base.group_system').id
        users = self.env['res.users'].search([('groups_id', 'in', prem_acc_group_id),
                                              ('groups_id', 'not in', admin_group_id)])
        partner_ids = users.mapped('partner_id.id')

        msg = {
            'body': _('Informuojame, kad atsirado naujas ilgalaikio turto įrašas, data: %s, pavadinimas %s') % (
                self.date, self.name),
            'subject': _('Naujas ilgalaikis turtas'),
            'priority': 'medium',
            'front_message': True,
            'rec_model': 'account.asset.asset',
            'rec_id': self.id,
            'partner_ids': partner_ids,
        }

        self.robo_message_post(**msg)

    @api.multi
    def force_close(self):
        self.ensure_one()
        if self.state != 'open':
            raise exceptions.UserError(_('Cannot close not running asset'))
        self.write({'state': 'close'})
        self.message_post(body=_('Closing asset'))

    @api.multi
    def validate(self):
        for asset in self:
            if not asset.code:
                code = self.env['ir.sequence'].next_by_code('ASSETS')
                while self.search_count([('code', '=', code)]):
                    code = self.env['ir.sequence'].next_by_code('ASSETS')
                asset.write({'code': code})
        return super(AccountAssetAsset, self).validate()

    @api.multi
    def _update_aml_vals_with_analytic_id(self, vals):
        self.ensure_one()
        account_id = vals.get('account_id')
        if account_id:
            account = self.env['account.account'].browse(account_id).filtered(lambda a: a.code in ['5', '6'])
            if account:
                vals['analytic_account_id'] = self.account_analytic_id.id

    @api.multi
    def open_entries(self):
        move_ids = self._get_related_move_ids()
        return {
            'name': _('Journal Entries'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', move_ids)],
        }

    @api.multi
    def _get_related_move_ids(self):
        move_ids_list = [
            self.mapped('depreciation_line_ids.move_id.id'),
            self.mapped('depreciation_line_ids.move_ids.id'),
            self.mapped('sell_move_ids.id'),
            self.mapped('sell_move_id.id'),
            self.mapped('sale_line_ids.invoice_id.move_id.id'),
            self.mapped('revaluation_move_ids.id'),
            self.mapped('writeoff_move_id.id'),
        ]
        related_move_ids = [x for sublist in move_ids_list for x in sublist]
        return related_move_ids

    @api.multi
    def get_last_depreciation_date(self):
        """
        Get the latest posted depreciation line and return its date. If not lines are posted - return False (bool)
        :rtype: date
        :return: Last posted depreciation line date
        """
        self.ensure_one()
        last_depreciation_date = False
        posted_depreciation_lines = self.depreciation_line_ids.filtered(lambda r: r.move_check)
        if posted_depreciation_lines:
            latest_depreciation_line = posted_depreciation_lines.sorted(lambda l: l.depreciation_date, reverse=True)[0]
            last_depreciation_date = latest_depreciation_line.depreciation_date
        return last_depreciation_date

    @api.multi
    def write_off(self, closing_expense_account_id, closing_date=None):
        self.ensure_one()

        if self.written_off_or_sold:
            raise exceptions.UserError(_('Ilgalaikis turtas %s jau buvo parduotas arba nurašytas') % self.name)
        use_sudo = self.env.user.has_group('ilgalaikis_turtas.group_asset_manager')
        if use_sudo and not self.env.user.has_group('base.group_system'):
            self.message_post('Writing off asset')
            self = self.sudo()

        category = self.category_id
        category_name = category.name
        credit_account = category.account_asset_id.id
        accumulated_depr_account = category.account_prime_cost_id.id

        if not accumulated_depr_account:
            raise exceptions.UserError(_('Accumulated depreciation account not set for category %s' % category_name))

        # Unlink depreciation lines that were not posted yet
        self.depreciation_line_ids.filtered(lambda r: not r.move_check).unlink()

        # Get the latest depreciation values
        ctx_date = self.get_last_depreciation_date()
        depreciation_values = self.with_context(date=ctx_date).current_depreciation_values()
        depreciation_left = depreciation_values.get('depreciation_left', 0.0)
        revaluation_left = depreciation_values.get('revaluation_left', 0.0)
        depreciation_depreciated = depreciation_values.get('depreciation_depreciated', 0.0)
        revaluation_depreciated = depreciation_values.get('revaluation_depreciated', 0.0)
        revaluation_total = revaluation_left + revaluation_depreciated

        if not closing_date:
            closing_date = datetime.utcnow().strftime(DF)

        journal_id = category.journal_id.id
        account_move_lines = []

        base_move_line_vals = {
            'name': self.name,
            'credit': 0.0,
            'debit': 0.0,
            'journal_id': journal_id,
            'partner_id': self.partner_id.id,
            'currency_id': False,
            'amount_currency': 0.0,
            'date': closing_date,
        }

        # Create revaluation reserve moves
        if not tools.float_is_zero(revaluation_total, precision_digits=2):
            account_revaluation_reserve_id = category.account_revaluation_reserve_id.id
            account_revaluation_profit_id = category.account_revaluation_profit_id.id
            if not account_revaluation_reserve_id:
                raise exceptions.UserError(_('Nenustatyta ilgalaikio turto perkainavimo rezervo sąskaita'))
            if not account_revaluation_profit_id:
                raise exceptions.UserError(_('Nenustatyta ilgalaikio turto perkainavimo pelno sąskaita'))

            move_line = base_move_line_vals.copy()
            move_line.update({
                'account_id': account_revaluation_reserve_id,
                'debit': abs(revaluation_left),
            })
            account_move_lines += [(0, 0, move_line)]
            move_line = base_move_line_vals.copy()
            move_line.update({
                'account_id': account_revaluation_profit_id,
                'credit': abs(revaluation_left),
            })
            account_move_lines += [(0, 0, move_line)]

        # Create the main move lines
        # D/Closing account/Depreciation left + Salvage value
        move_line = base_move_line_vals.copy()
        move_line.update({
            'account_id': closing_expense_account_id,
            'debit': abs(depreciation_left + self.salvage_value),
        })
        account_move_lines += [(0, 0, move_line)]

        # D/Accumulated Depreciation account (XXX7)/Total depreciated amount
        depreciated_before_takeover = self.original_price_unit - self.price_unit
        depreciated_before_takeover = max(depreciated_before_takeover, 0.0)
        # Multiply by the quantity that's being written off since depreciation before take over is based on price unit.
        depreciated_before_takeover *= self.residual_quantity
        move_line = base_move_line_vals.copy()
        move_line.update({
            'account_id': accumulated_depr_account,
            'debit': depreciation_depreciated + depreciated_before_takeover,
        })
        account_move_lines += [(0, 0, move_line)]

        # K/Asset account (XXX0)/The whole value of the asset
        change_lines = self.change_line_ids.filtered(lambda c: c.date <= (ctx_date or closing_date))
        pagerinimai_amount = sum(change_lines.mapped('change_amount'))
        move_line = base_move_line_vals.copy()
        move_line.update({
            'account_id': credit_account,
            'credit': abs(self.original_value + pagerinimai_amount),
        })
        account_move_lines += [(0, 0, move_line)]

        # Update with analytics
        for aml in account_move_lines:
            if len(aml) == 3:
                self._update_aml_vals_with_analytic_id(aml[2])

        # Create the move and post
        write_off_move = self.env['account.move'].create({
            'ref': self.code,
            'date': closing_date or False,
            'journal_id': journal_id,
            'line_ids': account_move_lines,
        })
        write_off_move.post()

        # Finalise the operation
        self.write({'state': 'close',
                    'date_close': closing_date,
                    'written_off_or_sold': True,
                    'writeoff_move_id': write_off_move.id})

    @api.multi
    def perform_asset_sale(self, sale_invoice_id, move_lines):
        self.ensure_one()

        if self.written_off_or_sold:
            raise exceptions.UserError(_('Ilgalaikis turtas %s nurašytas arba parduotas') % self.name)

        if not sale_invoice_id:
            raise exceptions.UserError(_('Nenurodyta sąskaita kurioje parduodamas ilgalaikis turtas'))

        category = self.category_id

        account_prime_cost = category.account_prime_cost_id.id
        account_asset_revaluation_depr = category.account_asset_revaluation_depreciation_id.id
        account_asset_id = category.account_asset_id.id

        if not (account_prime_cost and account_asset_revaluation_depr and account_asset_id):
            raise exceptions.UserError(_('Asset category %s does not have all the accounts configured') % category.name)

        account_revaluation_reserve_id = category.account_revaluation_reserve_id.id
        account_revaluation_profit_id = category.account_revaluation_profit_id.id

        asset_name = self.name
        journal_id = sale_invoice_id.journal_id.id
        partner_id = sale_invoice_id.partner_id.id or self.partner_id.id

        sale_date = sale_invoice_id.date_invoice
        residual_price_unit = self.with_context(date=sale_date).residual_price_unit
        residual_quantity = self.with_context(date=sale_date).residual_quantity

        base_move_line_vals = {
            'name': asset_name,
            'debit': 0.0,
            'credit': 0.0,
            'journal_id': journal_id,
            'partner_id': partner_id,
            'currency_id': False,
            'amount_currency': 0.0,
            'date': sale_date,
            'tax_ids': [(6, 0, sale_invoice_id.mapped('invoice_line_ids.invoice_line_tax_ids.id'))],
            'invoice_id': sale_invoice_id.id,
            # todo not the nicest way
        }

        # Get global revaluation and depreciation amounts
        depreciation_values = self.with_context(date=sale_date).current_depreciation_values()

        # Set up global revaluation and depreciation amounts
        depreciation_left = depreciation_values.get('depreciation_left', 0.0)
        revaluation_left = depreciation_values.get('revaluation_left', 0.0)
        depreciation_depreciated = depreciation_values.get('depreciation_depreciated', 0.0)
        revaluation_depreciated = depreciation_values.get('revaluation_depreciated', 0.0)

        # Set up individual revaluation and depreciation amounts
        depreciation_left_per_unit = depreciation_left / residual_quantity
        revaluation_left_per_unit = revaluation_left / residual_quantity
        depreciation_depreciated_per_unit = depreciation_depreciated / residual_quantity
        revaluation_depreciated_per_unit = revaluation_depreciated / residual_quantity

        account_asset_transfer_loss = self.env.user.company_id.account_asset_transfer_loss.id
        account_asset_transfer_profit = self.env.user.company_id.account_asset_transfer_profit.id

        asset_sale_lines = sale_invoice_id.mapped('invoice_line_ids').filtered(lambda l: l.asset_id.id == self.id)
        for asset_sale_line in asset_sale_lines:
            quantity_being_sold = asset_sale_line.quantity

            asset_sale_line_vals = {
                'base_price': quantity_being_sold * residual_price_unit,
                'actual_price': abs(asset_sale_line.price_subtotal_signed),
                'depreciation_left': depreciation_left_per_unit * quantity_being_sold,
                'revaluation_left': revaluation_left_per_unit * quantity_being_sold,
                'depreciation_depreciated': depreciation_depreciated_per_unit * quantity_being_sold,
                'revaluation_depreciated': revaluation_depreciated_per_unit * quantity_being_sold,
            }
            asset_sale_line_vals['total_depreciated'] = asset_sale_line_vals.get('revaluation_left') + \
                                                        asset_sale_line_vals.get('revaluation_depreciated')
            asset_sale_line_vals['total_revaluated'] = asset_sale_line_vals.get('depreciation_left') + \
                                                         asset_sale_line_vals.get('depreciation_depreciated')

            revaluation_total = asset_sale_line_vals.get('revaluation_depreciated', 0.0) + asset_sale_line_vals.get('revaluation_left', 0.0)

            depreciated_before_takeover = self.original_price_unit - self.price_unit
            depreciated_before_takeover = max(depreciated_before_takeover, 0.0)

            purchase_price_quant = self.original_price_unit * quantity_being_sold
            salvage_price_quant = self.salvage_value * quantity_being_sold / self.quantity

            move_line = base_move_line_vals.copy()
            debit_amount = tools.float_round(asset_sale_line_vals.get(
                'depreciation_depreciated', 0.0) + depreciated_before_takeover, precision_digits=2)
            move_line.update({
                'account_id': account_prime_cost,
                'debit': debit_amount
            })
            new_move_lines = [(0, 0, move_line)]

            pagerinimai_amount = 0.0
            for change in self.change_line_ids.filtered(lambda c: c.date <= sale_date):
                change_quant = self.with_context(date=change.date).quantity
                change_singular_amount = change.change_amount / change_quant
                change_for_quant_of_sale = change_singular_amount * quantity_being_sold
                pagerinimai_amount += change_for_quant_of_sale

            move_line = base_move_line_vals.copy()
            move_line.update({
                'account_id': account_asset_id,
                'credit': tools.float_round(purchase_price_quant + pagerinimai_amount, 2)
            })
            new_move_lines += [(0, 0, move_line)]

            value_difference = asset_sale_line_vals.get('actual_price') - asset_sale_line_vals.get('base_price') - salvage_price_quant
            sale_price_comparison = tools.float_compare(value_difference, 0.0, precision_digits=2)

            if sale_price_comparison != 0:
                if not account_asset_transfer_loss:
                    raise exceptions.UserError(
                        _('Kompanijos nustatymuose nenustatyta ilgalaikio turto perleidimo nuostolių sąskaita'))
                if not account_asset_transfer_profit:
                    raise exceptions.UserError(
                        _('Kompanijos nustatymuose nenustatyta ilgalaikio turto perleidimo pelno sąskaita'))

                if sale_price_comparison > 0:  # Pelnas
                    move_line = base_move_line_vals.copy()
                    move_line.update({
                        'account_id': account_asset_transfer_profit,
                        'credit': tools.float_round(abs(value_difference), 2)
                    })
                    new_move_lines += [(0, 0, move_line)]
                else:  # Nuostolis
                    move_line = base_move_line_vals.copy()
                    move_line.update({
                        'account_id': account_asset_transfer_loss,
                        'debit': tools.float_round(abs(value_difference), 2)
                    })
                    new_move_lines += [(0, 0, move_line)]

            # Create reserve move lines
            if not tools.float_is_zero(revaluation_total, precision_digits=2):
                if not account_revaluation_reserve_id:
                    raise exceptions.UserError(_('Nenustatyta ilgalaikio turto perkainavimo rezervo sąskaita'))
                if not account_revaluation_profit_id:
                    raise exceptions.UserError(_('Nenustatyta ilgalaikio turto perkainavimo pelno sąskaita'))

                move_line_1 = base_move_line_vals.copy()
                move_line_1.update({  # 321
                    'account_id': account_revaluation_reserve_id,
                    'debit': tools.float_round(abs(value_difference), 2),
                })
                new_move_lines += [(0, 0, move_line_1)]

                move_line_2 = base_move_line_vals.copy()
                move_line_2.update({  # 3412
                    'account_id': account_revaluation_profit_id,
                    'credit': tools.float_round(abs(value_difference), 2),
                })
                new_move_lines += [(0, 0, move_line_2)]

            for aml in new_move_lines:
                if len(aml) == 3:
                    self._update_aml_vals_with_analytic_id(aml[2])

            residual_quantity -= quantity_being_sold

            # total_credit = sum(line['credit'] for line in [new_move_line[2] for new_move_line in new_move_lines])
            # total_debit = sum(line['debit'] for line in [new_move_line[2] for new_move_line in new_move_lines])
            # total_debit += asset_sale_line_vals['actual_price']

            move_lines += new_move_lines

        # Sometimes due to python rounding issues we get unbalanced entries. This tries to balance it out here,
        total_credit = sum([line[2]['credit'] for line in move_lines])
        total_debit = sum([line[2]['debit'] for line in move_lines])
        difference = abs(total_credit - total_debit)
        balances_out = tools.float_is_zero(difference, precision_digits=3)
        if not balances_out and tools.float_compare(difference, 0.02, precision_digits=3) < 0:
            subtract_from = 'credit' if tools.float_compare(total_credit, total_debit, precision_digits=3) > 0 else 'debit'
            while not tools.float_is_zero(difference, precision_digits=3):
                for line in [l for l in move_lines if not tools.float_is_zero(l[2][subtract_from], precision_digits=3)]:
                    line[2][subtract_from] -= 0.01
                    difference -= 0.01
                    if tools.float_is_zero(difference, precision_digits=3):
                        break
                total_credit = sum([line[2]['credit'] for line in move_lines])
                total_debit = sum([line[2]['debit'] for line in move_lines])
                difference = abs(total_credit - total_debit)

        residual_quantity_comparison = tools.float_compare(residual_quantity, 0.0, precision_digits=2)
        if residual_quantity_comparison < 0:
            raise exceptions.UserError(_('Negalima patvirtinti sąskaitos, nes ilgalaikio turto likutis taptų neigiamas'))

        if tools.float_is_zero(residual_quantity, precision_digits=2):
            self.write({'date_close': sale_date,
                        'state': 'close',
                        'written_off_or_sold': True})

        return move_lines

    @api.model
    def perform_salvage_value_checks(self):
        days_to_check_in_the_future = 7

        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_cutoff_dt = datetime.utcnow() + relativedelta(days=days_to_check_in_the_future)
        date_cutoff = date_cutoff_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        categories_to_check = self.env['account.asset.category'].search([
            '|',
            ('name', 'ilike', '120'),
            '|',
            ('name', 'ilike', '121'),
            ('name', 'ilike', '123'),
        ])
        assets_to_inform_about = self.search([
            ('category_id', 'in', categories_to_check.ids),
            ('salvage_value_check_performed', '=', False),
            ('state', '=', 'open'),
            ('date_first_depreciation', '>=', now),
            ('date_first_depreciation', '<=', date_cutoff)
        ])
        if assets_to_inform_about:
            asset_table = _('''
                <table style="border-collapse: collapse;">
                    <tr>
                        <th style="padding: 3px; border: 1px solid black;">Pavadinimas</th>
                        <th style="padding: 3px; border: 1px solid black;">Kategorija</th>
                        <th style="padding: 3px; border: 1px solid black;">Pirmojo nusidėvėjimo data</th>
                        <th style="padding: 3px; border: 1px solid black;">Likvidacinė vertė</th>
                        <th style="padding: 3px; border: 1px solid black;">Nuoroda sistemoje</th>
                    </tr>
            ''')
            asset_table_row = _('''
                    <tr>
                        <td style="padding: 3px; border: 1px solid black;">{}</td>
                        <td style="padding: 3px; border: 1px solid black;">{}</td>
                        <td style="padding: 3px; border: 1px solid black;">{}</td>
                        <td style="padding: 3px; border: 1px solid black;">{}</td>
                        <td style="padding: 3px; border: 1px solid black;"><a href="{}">Atidaryti</a></td>
                    </tr>
            ''')
            base_url = '''https://{}.robolabs.lt/web?'''.format(self.env.cr.dbname)
            base_url += '''id={}&view_type=form&model=account.asset.asset'''

            for asset in assets_to_inform_about:
                asset_table += asset_table_row.format(
                    asset.name,
                    asset.category_id.name,
                    asset.date_first_depreciation,
                    asset.salvage_value,
                    base_url.format(asset.id)
                )
            asset_table += '</table>'

            category_names = categories_to_check.mapped('name')
            category_names.sort()

            body = _('''Sveiki,
            tai priminimas patikrinti IT likvidacinę vertę. Per ateinančią savaitę numatoma pirmą kartą 
            nudėvėti šį IT: <br/><br/>
            {}
            <br/>
            Šis priminimas siunčiamas tik IT esančiam šiose kategorijose:<br/>
            {}
            ''').format(asset_table, '<br/>'.join(category_names))

            subject = _('Priminimas patikrinti IT likvidacinę vertę [{}] ({})').format(self.env.cr.dbname, now)

            assets_to_inform_about.write({'salvage_value_check_performed': True})

            try:
                ticket_obj = self.env['mail.thread']._get_ticket_rpc_object()
                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'ticket_record_id': False,
                    'name': subject,
                    'ticket_user_login': self.env.user.login,
                    'ticket_user_name': self.env.user.name,
                    'description': body,
                    'ticket_type': 'accounting',
                    'user_posted': self.env.user.name
                }
                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError(_('The distant method did not create the ticket.'))
            except Exception as exc:
                message = 'Failed to create ticket about checking account asset salvage value. Exception: %s' % str(exc.args)
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    ###############################################
    #  NOT REALLY COMPUTES, ONLY CALLED THAT WAY  #
    ###############################################
    @api.multi
    def force_recompute_depreciation_board(self):
        if self.env.context.get('skip_force_recompute_depreciation_board'):
            # We skip the inverse call on asset creation, as there is an explicit call to the method right after
            return
        for rec in self:
            rec.with_context(dont_compute_depreciation_board=False).compute_depreciation_board()

    @api.multi
    def compute_depreciation_board(self):
        self.ensure_one()
        if self.is_depreciated_not_by_norm and self.method_number_not_by_norm >= self.method_number:
            raise exceptions.ValidationError(_('Method number not by norm must be less than method number by norm'))
        do_not_compute_this_board = self._context.get('dont_compute_depreciation_board', False)
        not_draft = self.state != 'draft'
        cant_be_depreciated = self.method == 'cant_be_depreciated'
        unposted_depreciation_line_ids = self.depreciation_line_ids.filtered(lambda l: not l.move_check)
        if do_not_compute_this_board and not_draft:
            return

        if cant_be_depreciated:
            if self.state == 'draft':
                unposted_depreciation_line_ids.unlink()
                return

        no_value_residual_effective = tools.float_is_zero(self.value_residual_effective, precision_digits=2)
        posted_depreciation_line_ids = self.depreciation_line_ids.filtered(lambda l: l.move_check)

        if unposted_depreciation_line_ids:
            unposted_depreciation_line_ids.unlink()

        if no_value_residual_effective:
            return

        if not self.date_first_depreciation:
            self.date_first_depreciation = self.date

        # Assets value could of been increased or the asset could of been reevaluated thus we need the changes.
        # This returns the amount increase in value and extra dotation number by dates
        changes_by_date = self._get_change_data()
        revaluations_by_date = self._get_revaluation_data()
        sales_by_date = self._get_sale_data()

        undone_dotation_number_by_norm = 0
        if self.is_depreciated_not_by_norm and self.method_number_not_by_norm:
            undone_dotation_number = self.undone_dotation_number_base(method_number=self.method_number_not_by_norm)
            undone_dotation_number_by_norm = self.undone_dotation_number_base(method_number=self.method_number)
        else:
            undone_dotation_number = self.undone_dotation_number_base(method_number=self.method_number)

        # Get the next depreciation date
        # If the asset has not been depreciated yet - will return first depreciation date which if not set is asset.date
        last_depreciation_date = datetime.strptime(self._get_last_depreciation_date()[self.id], DF)
        if self.next_forced_depreciation_date:
            next_forced_depreciation_date = datetime.strptime(self.next_forced_depreciation_date, DF)
            if next_forced_depreciation_date > last_depreciation_date:
                next_depreciation_date = next_forced_depreciation_date
        else:
            next_depreciation_date = last_depreciation_date
        dates_posted = posted_depreciation_line_ids.mapped('depreciation_date')
        if dates_posted and max(dates_posted) >= datetime.strftime(next_depreciation_date, DF):
            next_depreciation_date = next_depreciation_date + relativedelta(months=self.method_period)

        # Find out how much of the asset is left
        previous_sale_lines = self.sale_line_ids.filtered(lambda s: s.date_invoice <= last_depreciation_date.strftime(DF))
        sale_quantity = sum(previous_sale_lines.mapped('quantity'))
        asset_quantity = self.quantity - sale_quantity

        date = next_depreciation_date.strftime(DF)
        # Maybe there were changes/reevaluations before the first depreciation that we must take into account.
        changes = [changes_by_date[dk] for dk in changes_by_date.keys() if dk < date]
        revaluations = [revaluations_by_date[dk] for dk in revaluations_by_date.keys() if dk < date]
        sales = self.sale_line_ids.filtered(lambda s: s.date_invoice <= date and s.used_in_calculations)
        previous_sale_revaluation_changes = sum(sale.revaluation_change for sale in sales)
        previous_revaluation_amounts = sum(revaluation.get('change_amount', 0.0) for revaluation in revaluations)
        previous_dotation_increases = sum(change.get('extra_dotations', 0) for change in changes)
        previous_dotation_increases += sum(revaluation.get('extra_dotations', 0) for revaluation in revaluations)
        undone_dotation_number += previous_dotation_increases
        remaining_revaluation_value = previous_revaluation_amounts - previous_sale_revaluation_changes
        amount_to_be_depreciated = self.with_context(date=date).value_residual

        remaining_revaluation_value = max(remaining_revaluation_value, 0.0)
        total_depreciated_amount = revaluation_total_depreciated_amount = 0.0

        # Find out how much is there left to depreciate and how much has been already depreciated
        if posted_depreciation_line_ids:
            # Just grab the data from the latest line posted
            latest_posted_depreciation_line = posted_depreciation_line_ids.sorted(lambda l: l.depreciation_date,
                                                                                  reverse=True)[0]
            total_depreciated_amount = sum(posted_depreciation_line_ids.mapped('amount'))
            remaining_revaluation_value = latest_posted_depreciation_line.remaining_revaluation_value
            revaluation_total_depreciated_amount = latest_posted_depreciation_line.revaluation_total_depreciated_amount
            amount_to_be_depreciated = self.with_context(date=date).value_at_date - self.salvage_value

        amount_to_be_depreciated = amount_to_be_depreciated_by_norm = max(amount_to_be_depreciated, 0.0)

        sequence = len(posted_depreciation_line_ids)
        depreciation_date = next_depreciation_date
        depreciation_at_end_of_month = last_day_of_month(depreciation_date)
        commands = []

        first_sequence = bool(posted_depreciation_line_ids)

        while True:
            sequence += 1
            dp_date = depreciation_date.strftime(DF)

            # Compute change period in months
            period_end_dt = depreciation_date
            period_start_dt = period_end_dt - relativedelta(months=self.method_period)
            if depreciation_at_end_of_month:
                period_start_dt += relativedelta(day=31)
            period_start = period_start_dt.strftime(DF)
            period_end = period_end_dt.strftime(DF)

            # When to stop the loop
            quantity_not_positive = not_positive(asset_quantity)
            nothing_to_depreciate = not_positive(amount_to_be_depreciated) and not_positive(remaining_revaluation_value)
            later_changes = {dk: changes_by_date[dk] for dk in changes_by_date.keys() if dk > period_start}
            later_revaluations = {dk: revaluations_by_date[dk] for dk in revaluations_by_date.keys() if
                                  dk > period_start}
            later_events = (later_changes or later_revaluations)
            if quantity_not_positive or (nothing_to_depreciate and not later_events) or (undone_dotation_number == 0.0 and not later_events):
                break

            # Changes, revaluations and sales from the last period (stuff that has to be accounted for)
            changes = list()
            # Do not include changes for the first dotation if posted depreciation lines exist since the changes are
            # included when retrieving value for date
            if not first_sequence:
                changes = [
                    changes_by_date[dk] for dk in changes_by_date.keys()
                    if max(period_start, self.pirkimo_data) < dk <= period_end
                ]
            first_sequence = False
            revaluations = [revaluations_by_date[dk] for dk in revaluations_by_date.keys() if
                            period_start < dk <= period_end]
            sales = [sales_by_date[dk] for dk in sales_by_date.keys() if period_start < dk <= period_end]

            # Change and revaluation values that get added to the global amounts
            undone_dotation_number += sum(change.get('extra_dotations', 0) for change in changes)
            undone_dotation_number += sum(revaluation.get('extra_dotations', 0) for revaluation in revaluations)
            undone_dotation_number = max(undone_dotation_number, 0)
            change_amount = sum(change.get('change_amount', 0.0) for change in changes)
            revaluation_amount = sum(revaluation.get('change_amount', 0.0) for revaluation in revaluations)
            amount_to_be_depreciated += change_amount
            remaining_revaluation_value += revaluation_amount

            # Calculate how much should be depreciated
            depreciation_amount_by_norm = 0.0
            if undone_dotation_number != 0:
                depreciation_amount = self.currency_id.round(self.calculate_depreciation_amount(
                    sequence, amount_to_be_depreciated, undone_dotation_number))
                revaluation_depreciation_amount = self.currency_id.round(self.calculate_depreciation_amount(
                    sequence, remaining_revaluation_value, undone_dotation_number))
                if undone_dotation_number_by_norm:
                    depreciation_amount_by_norm = self.currency_id.round(self.calculate_depreciation_amount(
                        sequence, amount_to_be_depreciated_by_norm, undone_dotation_number_by_norm))
            else:
                depreciation_amount = revaluation_depreciation_amount = 0.0

            amount_to_be_depreciated -= depreciation_amount
            if undone_dotation_number_by_norm:
                amount_to_be_depreciated_by_norm -= depreciation_amount_by_norm
            remaining_revaluation_value -= revaluation_depreciation_amount
            total_depreciated_amount += depreciation_amount
            revaluation_total_depreciated_amount += revaluation_depreciation_amount

            # This is how much a single unit has depreciation right before the sale.
            residual_depreciation_value = amount_to_be_depreciated / float(asset_quantity)
            # This is how much a single unit has revaluation right before the sale.
            residual_revaluation_value = remaining_revaluation_value / float(asset_quantity)
            # Sale amounts
            if sales:
                total_sales_quantity = abs(sum([sale.get('quantity_change') for sale in sales]))
                asset_quantity -= total_sales_quantity
                asset_quantity = max(asset_quantity, 0.0)
                actual_sale_depreciation_value = residual_depreciation_value * total_sales_quantity
                actual_sale_revaluation_value = residual_revaluation_value * total_sales_quantity
                amount_to_be_depreciated -= actual_sale_depreciation_value
                remaining_revaluation_value -= actual_sale_revaluation_value
                amount_to_be_depreciated = max(amount_to_be_depreciated, 0.0)
                remaining_revaluation_value = max(remaining_revaluation_value, 0.0)

            if not tools.float_is_zero(depreciation_amount, precision_digits=2):
                vals = {
                    'amount': self.currency_id.round(depreciation_amount),
                    'amount_not_by_norm': self.currency_id.round(depreciation_amount_by_norm),
                    'revaluation_depreciation': self.currency_id.round(revaluation_depreciation_amount),
                    'remaining_revaluation_value': self.currency_id.round(remaining_revaluation_value),
                    'revaluation_total_depreciated_amount': revaluation_total_depreciated_amount,
                    'asset_id': self.id,
                    'sequence': sequence,
                    'name': (self.code or '') + '/' + str(sequence),
                    'remaining_value': self.currency_id.round(amount_to_be_depreciated+self.salvage_value),
                    'depreciated_value': self.currency_id.round(total_depreciated_amount),
                    'depreciation_date': dp_date,
                    'account_analytic_id': self.account_analytic_id.id,
                }
                commands.append((0, False, vals))

            depreciation_date += relativedelta(months=self.method_period)
            if depreciation_at_end_of_month:
                depreciation_date += relativedelta(day=31)

            undone_dotation_number -= 1
            undone_dotation_number = max(undone_dotation_number, 0)
            if undone_dotation_number_by_norm:
                undone_dotation_number_by_norm -= 1
                undone_dotation_number_by_norm = max(undone_dotation_number_by_norm, 0)

        self.write({'depreciation_line_ids': commands})
        for line in self.depreciation_line_ids:
            if self.currency_id.round(line.amount) < 0 or self.currency_id.round(line.remaining_value) < 0:
                raise exceptions.UserError(
                    _('Turtas per nurodytą laikotarpį pasiektų vertę, mažesnę už nurodytą likutį.'))
        return True

    def calculate_depreciation_amount(self, sequence, amount_to_be_depreciated, depreciations_to_be_made):
        # TODO Prorata not taken into account and degressive is not set
        first_sequence = sequence == 1

        depreciation_amount = 0.0

        if self.method == 'degressive':
            if first_sequence:
                depreciation_amount = self.value_gross_total * self.method_progress_factor
        elif self.method == 'linear':
            depreciation_amount = amount_to_be_depreciated / float(depreciations_to_be_made)

        return depreciation_amount

    # def _compute_board_amount(self, sequence, residual_amount, amount_to_depr, undone_dotation_number,
    #                           posted_depreciation_line_ids, total_days, depreciation_date):
    #     is_degressive = self.method == 'degressive'
    #     first_sequence = sequence == 1
    #
    #     if self.prorata and not (is_degressive and first_sequence):
    #         amount = super(AccountAssetAsset, self)._compute_board_amount(sequence, residual_amount, amount_to_depr,
    #                                                                       undone_dotation_number,
    #                                                                       posted_depreciation_line_ids, total_days,
    #                                                                       depreciation_date)
    #     else:
    #         if is_degressive and first_sequence:
    #             amount = self.value_gross_total * self.method_progress_factor
    #             if self.prorata:
    #                 days = total_days - float(depreciation_date.strftime('%j'))
    #                 amount = amount / total_days * days
    #         elif self.method == 'linear':
    #             amount = amount_to_depr / float(undone_dotation_number)
    #     return amount

    @api.multi
    def undone_dotation_number_base(self, method_number):
        """
        Based on the depreciation settings computes how many depreciations are still left for the asset to reach its
        liquidation value. Does not take into account the changes, computes based on the initial settings

        :return: number of dotations still to be performed for the asset
        :rtype: integer
        """
        self.ensure_one()
        if not self.date_first_depreciation:
            self.date_first_depreciation = self.date  # If not set, last depreciation date does fallback to this.

        last_depreciation_date = datetime.strptime(self._get_last_depreciation_date()[self.id], DF)
        check_date = last_depreciation_date

        if self.method_time == 'end':
            undone_dotation_number = 0
            scheduled_date_end = datetime.strptime(self.method_end, DF)
            date_to_stop_depreciating = scheduled_date_end
            while check_date <= date_to_stop_depreciating:
                check_date += relativedelta(months=self.method_period)
                undone_dotation_number += 1
        else:
            posted_depreciation_line_ids = self.depreciation_line_ids.filtered(lambda l: l.move_check)
            undone_dotation_number = method_number - len(posted_depreciation_line_ids)

        return undone_dotation_number

    @api.multi
    def check_asset_category_all_relevant_accounts(self):
        for rec in self:
            asset_categ = rec.category_id

            base_msg = _('Asset category is missing these related accounts:\n{0}')
            err_msg = ''
            if not asset_categ.account_prime_cost_id:
                err_msg += 'Accumulated depr. account\n'
            if not asset_categ.account_revaluation_reserve_id:
                err_msg += 'Revaluation reserve account\n'
            if not (rec.account_depreciation_id or asset_categ.account_depreciation_id):
                err_msg += 'Depreciation Expense\n'
            if not asset_categ.account_asset_revaluation_depreciation_id:
                err_msg += 'Revaluation depr. account\n'
            if not asset_categ.account_revaluation_profit_id:
                err_msg += 'Revaluation profit account\n'
            if not asset_categ.account_revaluation_expense_id:
                err_msg += 'Revaluation expense account\n'
            if not asset_categ.account_asset_id:
                err_msg += 'Depreciation Asset account\n'
            if not asset_categ.account_revaluation_id:
                err_msg += 'Value Decrease account\n'
            if err_msg:
                raise exceptions.UserError(base_msg.format(err_msg))

    @api.multi
    def create_starting_accounting_values(self):
        total_debit = 0.0
        total_credit = 0.0
        off_books_account_id = self.env['account.account'].search([('code', '=', '999999')])
        if not off_books_account_id:
            raise exceptions.UserError(_('Nepavyko surasti atitinkamos apskaitos informacijos.'))
        journal_id = self.env['account.journal'].search([('code', '=', 'START')], limit=1)
        if not journal_id:
            journal_id = self.env['account.journal'].create({
                'name': 'Pradiniai likučiai',
                'code': 'START',
                'type': 'general',
                'update_posted': True,
            })
        lines = []
        move = {
            'ref': u'Pradinė ilgalaikio turto vertė',
            'date': (self.env.user.company_id.compute_fiscalyear_dates()['date_from']).
                strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'journal_id': journal_id.id,
            'line_ids': lines,
        }
        for asset in self:
            if tools.float_is_zero(asset.original_value, precision_digits=2):
                return
            if asset.value < asset.original_value:
                total_credit += asset.original_value - asset.value
                lines.append((0, 0, {
                    'name': u'Sukauptas nusidėvėjimas: ' + asset.name,
                    'account_id': asset.category_id.account_prime_cost_id.id,
                    'debit': 0.0,
                    'credit': asset.original_value - asset.value,
                    'journal_id': journal_id.id,
                }))
            lines.append((0, 0, {
                'name': u'Originali vertė: ' + asset.name,
                'account_id': asset.category_id.account_asset_id.id,
                'credit': 0.0,
                'debit': asset.original_value,
                'journal_id': journal_id.id,
            }))
            total_debit += asset.original_value
        if tools.float_compare(total_credit, total_debit, precision_digits=2) != 0:
            if total_debit > total_credit:
                last_credit = total_debit - total_credit
                last_debit = 0.0
            else:
                last_debit = total_credit - total_debit
                last_credit = 0.0
            lines.append((0, 0, {
                'name': u'Balansuojantis įrašas',
                'account_id': off_books_account_id.id,
                'debit': last_debit,
                'credit': last_credit,
                'journal_id': journal_id.id,
            }))
        self.env['account.move'].create(move)
        for asset in self:
            for line in asset.depreciation_line_ids.filtered(
                    lambda r: datetime.strptime(r.depreciation_date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    <= datetime.utcnow()).sorted(key=lambda r: r.depreciation_date):
                line.create_move()


AccountAssetAsset()
