# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class EtsyDataImportJob(models.Model):
    """
    Model used to hold threaded XLSX data import results for backend data import XLSX.
    """
    _name = 'etsy.data.import.job'

    execution_start_date = fields.Datetime(string='Start of execution')
    execution_end_date = fields.Datetime(string='End of execution')
    state = fields.Selection([('in_progress', 'In Progress'),
                              ('finished', 'Finished'),
                              ('failed', 'Failed')],
                             string='Status')
    fail_message = fields.Char(string='Fail message')
    created_ids = fields.Many2many('account.invoice')

    imported_file_name = fields.Char(string='Imported file name')
    show_open_button = fields.Boolean(compute='_compute_show_open_button')

    @api.multi
    @api.depends('created_ids', 'state')
    def _compute_show_open_button(self):
        for rec in self:
            rec.show_open_button = True if rec.state in ['finished'] and rec.created_ids else False

    @api.multi
    def action_open_invoices(self):
        """
        Open invoice tree with domain filtering the invoices that
        were created by this data import job
        :return: None
        """
        self.ensure_one()
        if self.created_ids:
            action = self.env.ref('account.action_invoice_tree1').read()[0]
            action['domain'] = [('id', 'in', self.created_ids.ids)]
            return action

    @api.multi
    def name_get(self):
        return [(rec.id, _('XLSX Import jobs')) for rec in self]


EtsyDataImportJob()
