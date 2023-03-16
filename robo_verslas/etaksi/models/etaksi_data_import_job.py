# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class EtaksiDataImportJob(models.Model):
    """
    Model used to hold threaded XLS data import results for custom Etaksi XLS.
    """
    _name = 'etaksi.data.import.job'

    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')
    state = fields.Selection([('in_progress', 'Vykdomas'),
                              ('finished', 'Sėkmingai įvykdytas'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')
    fail_message = fields.Char(string='Klaidos pranešimas')
    created_ids = fields.Many2many('account.invoice')
    mass_mailed = fields.Boolean(string='Sąskaitos išsiųstos')
    imported_file_name = fields.Char(string='Importuoto failo pavadinimas')
    imported_file = fields.Binary(string='Importuotas failas', attachment=True, readonly=True)
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
        return [(rec.id, _('XLS Importavimo darbai')) for rec in self]


EtaksiDataImportJob()
