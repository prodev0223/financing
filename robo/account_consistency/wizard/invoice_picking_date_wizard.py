# -*- coding: utf-8 -*-
from openerp import models, fields, api, _, exceptions, tools
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


class InvoicePickingDateConsistencyWizard(models.TransientModel):
    _name = 'invoice.picking.date.consistency.wizard'
    _description = 'Stock accounting dates'

    def _date_from(self):
        date = datetime.now() - relativedelta(months=3)
        year, month = date.year, date.month,
        month = ((month - 1) / 3) * 3 + 1
        return datetime(year, month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _date_to(self):
        date = datetime.now() - relativedelta(months=3)
        year, month = date.year, date.month,
        month = ((month - 1) / 3) * 3 + 3
        return (datetime(year, month, 1) + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    date_from = fields.Date(string='Date From', required=True, default=_date_from)
    date_to = fields.Date(string='Date to', required=True, default=_date_to)
    fix_record_ids = fields.Many2many('invoice.picking.date.consistency', 'invoice_pick_date_cons_rel', string='Invoices',
                                      domain="[('state', '!=', 'fixed')]")
    domain_selection = fields.Selection([('diff_quarter', 'Different Quarters'),
                                         ('diff_month', 'Different Months'),
                                         ('diff_dates', 'Different Dates')],
                                        string='Domain', default='diff_month', required=True)

    @api.onchange('domain_selection')
    def onchange_domain_selection(self):
        if self.domain_selection == 'diff_quarter':
            self.fix_record_ids = [
                (6, 0, self.env['invoice.picking.date.consistency'].search([('diff_quarter', '=', True)]).ids)]
        elif self.domain_selection == 'diff_month':
            self.fix_record_ids = [
                (6, 0, self.env['invoice.picking.date.consistency'].search([('diff_month', '=', True)]).ids)]
        elif self.domain_selection == 'diff_dates':
            self.fix_record_ids = [
                (6, 0, self.env['invoice.picking.date.consistency'].search([('state', '!=', 'fixed')]).ids)]
        else:
            self.fix_record_ids = [(6, 0, [])]

    @api.multi
    def fix_all(self):
        for line in self.fix_record_ids:
            line.fix()


InvoicePickingDateConsistencyWizard()
