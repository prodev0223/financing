# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AmazonImportWizardJob(models.Model):
    """
    Model that holds information about failed/imported amazon tasks
    """
    _name = 'amazon.import.wizard.job'

    file_name = fields.Char(string='Failo pavadinimas')
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')
    operation_type = fields.Selection(
        [('xml_import', 'XML Importas'), ('init_api', 'API startavimas')],
        string='Operacijos tipas', default='xml_import')
    xml_type = fields.Selection(
        [('orders', 'Užsakymai'), ('products', 'Produktai')], string='XML tipas')
    state = fields.Selection([('in_progress', 'Vykdomas'),
                              ('finished', 'Sėkmingai įvykdytas'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')
    fail_message = fields.Char(string='Klaidos pranešimas')

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(x.id, _('Amazon darbai - %s') % x.id) for x in self]


AmazonImportWizardJob()
