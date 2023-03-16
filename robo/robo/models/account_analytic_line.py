# -*- coding: utf-8 -*-
from six import itervalues, iteritems

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools, exceptions, _


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'
    # ROBO: system default parameter 50->show; (>=100-hide) though we can specify model's default;
    _default_field_sequence = 50

    deferred_line = fields.Boolean(default=False, string='Išskaidyta eilutė')
    partner_id = fields.Many2one('res.partner', string='Projekto partneris', lt_string='Projekto partneris', store=True,
                                 readonly=True, compute='_partner_id')
    amount = fields.Monetary(
        groups="robo_basic.group_robo_premium_manager,"
               "robo_basic.group_robo_free_manager,"
               "robo_analytic.group_robo_analytic_see_amounts", copy=False)
    analytic_amount_currency = fields.Monetary(
        groups="robo_basic.group_robo_premium_manager,"
               "robo_basic.group_robo_free_manager,"
               "robo_analytic.group_robo_analytic_see_amounts")
    amount_currency = fields.Monetary(
        groups="robo_basic.group_robo_premium_manager,"
               "robo_basic.group_robo_free_manager,"
               "robo_analytic.group_robo_analytic_see_amounts")
    name = fields.Char(sequence=9)
    product_id = fields.Many2one(sequence=13)
    project_id = fields.Many2one(sequence=15)
    date = fields.Date(sequence=1)
    account_id = fields.Many2one(sequence=12, inverse='_set_account_id')
    move_partner_id = fields.Many2one('res.partner', string='Partneris',
                                      readonly=True, sequence=3, lt_string='Partneris')
    analytic_group_id = fields.Many2one('account.analytic.group', string='Analitinė grupė',
                                        compute='_compute_analytic_group_id', store=True)

    @api.one
    @api.depends('move_id.partner_id', 'account_id.partner_id')
    def _partner_id(self):
        if self.move_id.partner_id and not self.project_id:
            self.partner_id = self.move_id.partner_id.id
        else:
            self.partner_id = self.account_id.partner_id.id

    @api.multi
    @api.depends('account_id.analytic_group_id')
    def _compute_analytic_group_id(self):
        for rec in self:
            if rec.account_id:
                rec.analytic_group_id = rec.account_id.analytic_group_id

    @api.multi
    def _set_account_id(self):
        for rec in self:
            if rec.move_id and len(rec.move_id.analytic_line_ids) == 1:
                rec.move_id.write({
                    'analytic_account_id': rec.account_id.id
                })

    @api.multi
    def check_locked_analytic_batch_integrity(self, recs_to_keep, recs_to_change):
        """
        If current record batch has records in both locked and unlocked periods,
        and if specific context is passed - raise an error to ensure data integrity
        :param recs_to_keep: records that are in locked period
        :param recs_to_change: records that are in un-locked period
        :return: None
        """
        # If we have records in locked and unlocked period in the same batch
        # and specific context is passed - raise an error
        if self._context.get('ensure_analytic_batch_integrity') and recs_to_change and recs_to_keep:
            latest_date = self.sorted(lambda x: x.date, reverse=True)[0].date
            raise exceptions.ValidationError(
                _('Įrašas turi išskaidytas analitines eilutes, tačiau tik dalis jų patenka į užšaldytą analitinį '
                  'periodą. Tam kad būtų užtikrintas duomenų integralumas, veiksmas yra draužiamas. Pakoreguokite '
                  'užšaldyto analitinio periodo datas. Vėliausia analitinės eilutės data - {}').format(latest_date))

    @api.multi
    def unlink(self):
        self.check_access_rights('unlink')
        # Check whether analytic line to be unlinked is in locked period or not
        obj = self.env['analytic.lock.dates.wizard']
        mode_kw = 'return' if self.sudo().env.user.company_id.analytic_lock_type == 'freeze' else 'raise'

        recs = self.filtered(lambda x: not obj.check_locked_analytic(x.date, mode=mode_kw))
        # Gather records to keep
        recs_to_keep = self.filtered(lambda x: x.id not in recs.ids)
        self.check_locked_analytic_batch_integrity(recs_to_keep, recs)

        # Manually break the link, because records are cascaded otherwise
        data_to_preserve = {}
        for rec in recs_to_keep:
            # Preserve related values, because they are lost when link is cut
            data_to_preserve[rec] = {
                'general_account_id': rec.general_account_id.id,
                'partner_id': rec.partner_id.id,
                'currency_id': rec.currency_id.id,
            }
        # Cut the link, then execute separate write to preserve the values
        recs_to_keep.with_context(skip_locked_analytic_checks=True).write({'move_id': False})
        for rec, values in iteritems(data_to_preserve):
            rec.with_context(skip_locked_analytic_checks=True).write(values)

        return super(AccountAnalyticLine, recs).unlink()

    @api.multi
    def write(self, vals):
        self.check_access_rights('write')
        # Check whether analytic line to be written to is in locked period or not
        obj = self.env['analytic.lock.dates.wizard']
        if self._context.get('skip_locked_analytic_checks'):
            recs = self
        else:
            mode_kw = 'return' if self.sudo().env.user.company_id.analytic_lock_type == 'freeze' else 'raise'
            recs = self.filtered(lambda x: not obj.check_locked_analytic(x.date, mode=mode_kw))
            # Gather records to keep
            recs_to_keep = self.filtered(lambda x: x.id not in recs.ids)
            self.check_locked_analytic_batch_integrity(recs_to_keep, recs)

        new_vals = {}
        for fname, field in iteritems(self._fields):
            if fname not in vals:
                continue
            if field.groups and not self.user_has_groups(field.groups):
                continue
            new_vals[fname] = vals[fname]

        return super(AccountAnalyticLine, recs.sudo()).write(new_vals)

    @api.model
    def create(self, vals):
        self.check_access_rights('create')
        # Check whether analytic line to be created is in locked period or not
        obj = self.env['analytic.lock.dates.wizard']
        mode_kw = 'return' if self.sudo().env.user.company_id.analytic_lock_type == 'freeze' else 'raise'
        if 'date' in vals and obj.check_locked_analytic(vals.get('date'), mode=mode_kw):
            return self.env['account.analytic.line']
        return super(AccountAnalyticLine, self.sudo()).create(vals)

    @api.model
    def refresh_analytic_amounts(self, date_from, date_to):
        self.env['account.analytic.line'].search(
            [('date', '>=', date_from), ('date', '<=', date_to)]).with_context(ignore_state=True).write({})

    @api.model
    def cron_refresh_analytic_accounts(self, date=None):
        """
        Cron-job //
        Refreshes analytic accounts for the previous month of the passed date or datetime.now().
        If date_from is in locked period, do not execute the cron job.
        :param date: Base date (str/None)
        :return: None
        """
        date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) if date else datetime.now()
        date_from = (date + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if not self.env['analytic.lock.dates.wizard'].check_locked_analytic(date_from, mode='return'):
            self.refresh_analytic_amounts(date_from, date_to)

    @api.model
    def refresh_everything(self):
        self.env['account.analytic.line'].search([]).with_context(ignore_state=True).write({})

    def _check_state(self):
        if self._context.get('ignore_state'):
            return True
        return super(AccountAnalyticLine, self)._check_state()
