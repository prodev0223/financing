# -*- coding: utf-8 -*-
from __future__ import division
from odoo import fields, models, api, _, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta


class InvoiceAnalyticWizardAll(models.TransientModel):
    _name = 'invoice.analytic.wizard.all'

    invoice_id = fields.Many2one('account.invoice')
    invoice_ids = fields.Many2many('account.invoice')
    analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita', readonly=False)

    show_action_button = fields.Boolean(compute='_show_action_button')
    default_action = fields.Selection([('split_analytic_lines', 'Skaidyti analitines eilutes'),
                                       ('force_dates', 'Keisti datas'),
                                       ('change_accounts', 'Keisti analitines sąskaitas')],
                                      string='Veiksmas', default='change_accounts')
    date_to_force = fields.Date(string='Data')
    deferred_period = fields.Selection([('1', '1 mėnuo'),
                                        ('2', '2 mėnesiai'),
                                        ('3', '3 mėnesiai'),
                                        ('4', '4 mėnesiai'),
                                        ('5', '5 mėnesiai'),
                                        ('6', '6 mėnesiai'),
                                        ('7', '7 mėnesiai'),
                                        ('8', '8 mėnesiai'),
                                        ('9', '9 mėnesiai'),
                                        ('10', '10 mėnesių'),
                                        ('11', '11 mėnesių'),
                                        ('12', '12 mėnesių'),
                                        ('13', '13 mėnesių'),
                                        ('14', '14 mėnesių'),
                                        ('15', '15 mėnesių'),
                                        ('16', '16 mėnesių'),
                                        ('17', '17 mėnesių'),
                                        ('18', '18 mėnesių'),
                                        ('19', '19 mėnesių'),
                                        ('20', '20 mėnesių'),
                                        ('21', '21 mėnuo'),
                                        ('22', '22 mėnesiai'),
                                        ('23', '23 mėnesiai'),
                                        ('24', '24 mėnesiai'),
                                        ], string='Išskaidymo periodas')

    locked_analytic_period = fields.Boolean(compute='_compute_locked_analytic_period')
    locked_analytic_period_message = fields.Text(compute='_compute_locked_analytic_period')

    @api.multi
    def _compute_locked_analytic_period(self):
        """
        Compute //
        Check whether message about frozen/blocked analytics should be shown to the user
        :return: None
        """
        lock_type = 'freeze' if self.sudo().env.user.company_id.analytic_lock_type in ['freeze'] else 'block'
        check_obj = self.env['analytic.lock.dates.wizard']
        for rec in self:
            if rec.invoice_id:
                if check_obj.check_locked_analytic(rec.invoice_id.date_invoice, mode='return'):
                    rec.locked_analytic_period = True
                    if lock_type in ['freeze']:
                        rec.locked_analytic_period_message = _('Sąskaita faktūra yra periode kurio analitika '
                                                               'yra užšaldyta. Analitinės sąskaitos keitimas '
                                                               'yra leidžiamas, tačiau pakeitimai '
                                                               'nepateks į verslo analitiką')
                    else:
                        rec.locked_analytic_period_message = _('Sąskaita faktūra yra periode kurio analitika yra užrakinta. '
                                                               'Analitinės sąskaitos keitimas nėra leidžiamas')
            if rec.invoice_ids:
                check_report = str()
                for invoice in rec.invoice_ids:
                    if check_obj.check_locked_analytic(invoice.date_invoice, mode='return'):
                        check_report += '{} \n'.format(invoice.number)
                if check_report:
                    rec.locked_analytic_period = True
                    if lock_type in ['freeze']:
                        rec.locked_analytic_period_message = _('Apačioje pateiktos sąskaitos faktūros yra periode '
                                                               'kurio analitika yra užšaldyta. Analitinės sąskaitos '
                                                               'keitimas yra leidžiamas, tačiau pakeitimai nepateks į '
                                                               'verslo analitiką \n\n') + check_report
                    else:
                        rec.locked_analytic_period_message = _('Apačioje pateiktos sąskaitos faktūros yra periode '
                                                               'kurio analitika yra užrakinta. Analitinės sąskaitos '
                                                               'keitimas nėra leidžiamas \n\n') + check_report

    @api.one
    def _show_action_button(self):
        """
        Compute //
        Computes whether additional analytic actions button should be shown
        :return: None
        """
        if self.env.user.company_id.additional_analytic_actions:
            self.show_action_button = True

    @api.multi
    def force_dates(self):
        """
        Force specified dates to corresponding analytic line objects
        :return: None
        """
        self.ensure_one()
        if self.locked_analytic_period:
            raise exceptions.UserError(
                _('Negalite skaidyti analitinės eilutės, sąskaita faktūra yra periode kurio analitika yra užšaldyta.')
            )
        for inv_line in self.invoice_id.invoice_line_ids:
            analytic_lines = inv_line.get_corresponding_aml().mapped('analytic_line_ids')
            analytic_lines.write({'date': self.date_to_force})

    @api.multi
    def split_analytic_lines(self):
        """
        Method that splits one account.analytic.line object into multiple based on specified period
        :return: None
        """
        self.ensure_one()
        if self.locked_analytic_period:
            raise exceptions.UserError(
                _('Negalite skaidyti analitinės eilutės, sąskaita faktūra yra periode kurio analitika yra užšaldyta.')
            )
        for inv_line in self.invoice_id.invoice_line_ids:
            analytic_lines = inv_line.get_corresponding_aml().mapped('analytic_line_ids')
            deferred_lines = analytic_lines.filtered(lambda c: c.deferred_line)
            orig_lines = analytic_lines.filtered(lambda c: not c.deferred_line)
            deferred_lines.unlink()
            for line in orig_lines:
                amount = (line.move_id.credit or 0.0) - (line.move_id.debit or 0.0)
                period = int(self.deferred_period)
                # P3:DivOK
                deferred_amount = tools.float_round(amount / period, precision_digits=2)
                relative_amount = period * deferred_amount
                leftovers = 0.0
                if tools.float_compare(relative_amount, amount, precision_digits=2) != 0:
                    leftovers = amount - relative_amount
                line.amount = deferred_amount
                deferred_line = self.env['account.analytic.line']
                for x in range(1, period):
                    date = (datetime.strptime(line.date, tools.DEFAULT_SERVER_DATE_FORMAT) +
                            relativedelta(months=x)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    deferred_line = line.copy(default={'date': date, 'amount': deferred_amount, 'deferred_line': True})
                if deferred_line:
                    deferred_line.amount = deferred_amount + leftovers

    @api.multi
    def change_analytics(self):
        """
        Change analytics of invoice.lines and recalculate/re-create corresponding analytic lines
        :return: None
        """
        self.ensure_one()
        # Every action that is executed from this method must keep the batch integrity
        self = self.with_context(ensure_analytic_batch_integrity=True)
        recs_to_use = self.invoice_id if self.invoice_id else self.invoice_ids
        for rec in recs_to_use:
            if not self.env.user.has_group('analytic.group_analytic_accounting'):
                return
            if rec.check_access_rights('write'):
                rec.check_access_rule('write')
                account_move_lines = rec.sudo().move_id.line_ids
                if rec.expense_split:
                    account_move_lines += rec.sudo().mapped('gpm_move.line_ids')
            else:
                return
            account_move_lines.mapped('analytic_line_ids').unlink()
            invoice_lines = rec.mapped('invoice_line_ids')
            invoice_lines.write({
                'account_analytic_id': self.analytic_id.id if self.analytic_id else False
            })
            non_deductible = rec.tax_line_ids.filtered(lambda x: x.tax_id.nondeductible)
            non_deductible.write({'account_analytic_id': self.analytic_id.id if self.analytic_id else False})
            for tax_id in non_deductible:
                aml = rec.move_id.line_ids.filtered(lambda x: x.tax_line_id.id == tax_id.tax_id.id)
                if len(aml) == 1:
                    aml.write({'analytic_account_id': self.analytic_id.id})
                    aml.create_analytic_lines()
            for inv_line in invoice_lines:
                if inv_line.sudo().deferred_line_id:
                    aml = inv_line.sudo().deferred_line_id.related_moves.mapped('line_ids')
                    aml.write({'analytic_account_id': self.analytic_id.id})
                    aml.create_analytic_lines()

            if rec.fuel_expense_move_id:
                aml = rec.sudo().fuel_expense_move_id.line_ids.filtered(
                    lambda l: l.account_id.code and l.account_id.code[0] in ['5', '6'])
                aml.write({'analytic_account_id': self.analytic_id.id})
                aml.create_analytic_lines()

            if rec.state in ['open', 'paid']:
                account_ids = rec.mapped('invoice_line_ids.account_id')
                lines_to_change = account_move_lines.filtered(
                    lambda r: r.account_id.id in account_ids.ids)
                if lines_to_change:
                    lines_to_change.write({'analytic_account_id': self.analytic_id.id})
                    lines_to_change.create_analytic_lines()

                    # Force analytics to related pickings move lines
                    invoices = self.invoice_id if self.invoice_id else self.invoice_ids
                    invoices.mapped('invoice_line_ids').force_picking_aml_analytics_prep(check_constraint=True)
                elif not lines_to_change:
                    raise exceptions.ValidationError(
                        _('Nepavyko pakeisti analitikos. Kreipkitės į Jus aptarnaujantį buhalterį.'))
