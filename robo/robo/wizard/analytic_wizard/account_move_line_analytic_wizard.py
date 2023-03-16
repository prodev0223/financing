# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, tools


class AccountMoveLineAnalyticWizard(models.TransientModel):
    """
    Wizard used to change account analytic id of specific account move line
    recreates analytic entries afterwards
    """
    _name = 'account.move.line.analytic.wizard'

    analytic_id = fields.Many2one('account.analytic.account', string='Analitinė sąskaita', readonly=False)
    tax_line_warning = fields.Boolean(compute='_tax_line_warning')

    locked_analytic_period = fields.Boolean(compute='_compute_locked_analytic_period')
    locked_analytic_period_message = fields.Text(compute='_compute_locked_analytic_period')

    @api.one
    def _compute_locked_analytic_period(self):
        """
        Compute //
        Check whether message about frozen/blocked analytics should be shown to the user
        :return: None
        """
        lock_type = 'freeze' if self.sudo().env.user.company_id.analytic_lock_type in ['freeze'] else 'block'
        recs = self.env['account.move.line'].browse(self._context.get('active_ids'))
        check_report = str()
        check_obj = self.env['analytic.lock.dates.wizard']
        for line in recs:
            if check_obj.check_locked_analytic(line.date, mode='return'):
                check_report += '{} \n'.format(line.name)
        if check_report:
            self.locked_analytic_period = True
            if lock_type in ['freeze']:
                self.locked_analytic_period_message = _('Apačioje pateiktos sąskaitos faktūros yra periode  kurio '
                                                        'analitika yra užšaldyta. Analitinės '
                                                        'sąskaitos keitimas yra leidžiamas, tačiau '
                                                        'pakeitimai nepateks į verslo analitiką \n\n') + check_report
            else:
                self.locked_analytic_period_message = _('Apačioje pateiktos sąskaitos faktūros yra periode kurio '
                                                        'analitika yra užrakinta. Analitinės '
                                                        'sąskaitos keitimas nėra leidžiamas \n\n') + check_report

    @api.one
    def _tax_line_warning(self):
        """
        Compute //
        Compute whether to show tax line warning
        :return: None
        """
        recs = self.env['account.move.line'].browse(self._context.get('active_ids'))
        invoices = recs.mapped('invoice_id')
        for invoice in invoices:
            corresponding = recs.filtered(lambda x: x.invoice_id.id == invoice.id)
            for line in corresponding.filtered(lambda x: x.tax_line_id):
                ail = invoice.invoice_line_ids.filtered(lambda x: line.tax_line_id.id in x.invoice_line_tax_ids.ids)
                if len(ail) > 1:
                    all_line_set = []
                    for rec in ail:
                        all_line_set.append(bool(corresponding.filtered(
                            lambda r: r.account_id.id == rec.account_id.id
                            and r.product_id.id == rec.product_id.id
                            and r.quantity == rec.quantity
                            and (not tools.float_compare(
                                r.credit, abs(rec.price_subtotal_signed), precision_digits=2)
                                or not tools.float_compare(
                                        r.debit, abs(rec.price_subtotal_signed), precision_digits=2)))))
                    if False in all_line_set:
                        self.tax_line_warning = True

    @api.multi
    def change_analytics(self):
        """
        Change analytics for specific account_move_line
        :return: None
        """
        self.ensure_one()
        # Every action that is executed from this method must keep the batch integrity
        self = self.with_context(ensure_analytic_batch_integrity=True)
        if not self.env.user.has_group('analytic.group_analytic_accounting'):
            return

        context = self._context
        active_ids = context.get('active_id') if context.get('change_line') else context.get('active_ids')

        recs = self.env['account.move.line'].browse(active_ids)
        for rec in recs.mapped('move_id'):
            self.env['analytic.lock.dates.wizard'].check_locked_analytic(analytic_date=rec.date)
        recs.mapped('analytic_line_ids').unlink()
        recs.write({'analytic_account_id': self.analytic_id.id})
        recs.create_analytic_lines()
        for aml in recs:
            if not aml.invoice_id or context.get('line_only'):
                continue
            ail = aml.invoice_id.invoice_line_ids
            line_to_change = ail.filtered(
                lambda r: r.account_id.id == aml.account_id.id
                and r.product_id.id == aml.product_id.id
                and r.quantity == aml.quantity
                and (not tools.float_compare(aml.credit, abs(r.price_subtotal_signed), precision_digits=2)
                     or not tools.float_compare(aml.debit, abs(r.price_subtotal_signed), precision_digits=2)))
            if line_to_change and len(line_to_change) == 1:
                line_to_change.sudo().write({
                    'account_analytic_id': self.analytic_id.id if self.analytic_id else False
                })
            else:
                atl = aml.invoice_id.tax_line_ids
                line_to_change = atl.filtered(
                    lambda r: r.account_id.id == aml.account_id.id
                    and r.tax_id.id == aml.tax_line_id.id)
                if line_to_change and len(line_to_change) == 1:
                    line_to_change.sudo().write({
                        'account_analytic_id': self.analytic_id.id if self.analytic_id else False
                    })


AccountMoveLineAnalyticWizard()
