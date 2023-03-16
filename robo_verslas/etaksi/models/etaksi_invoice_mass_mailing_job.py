# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class EtaksiDataImportJob(models.Model):
    """
    Model used to hold etaksi mass invoice mailing jobs
    """
    _name = 'etaksi.invoice.mass.mailing.job'

    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')
    state = fields.Selection([('in_progress', 'Vykdomas'),
                              ('finished', 'Sėkmingai įvykdytas'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')
    fail_message = fields.Char(string='Klaidos pranešimas')
    mailed_ids = fields.Many2many('account.invoice')

    @api.multi
    def name_get(self):
        return [(rec.id, _('Sąskaitų siuntimo darbai')) for rec in self]


EtaksiDataImportJob()
