# -*- coding: utf-8 -*-

from odoo import models, fields


class DataImportRevisions(models.Model):

    _name = 'data.import.revisions'

    revision_number = fields.Integer(string='Įrašo versija')
    data_import_id = fields.Many2one('sync.data.import')
    res_id = fields.Integer(string='Įrašo identifikatorius')
    res_model = fields.Char(string='Įrašo modelis')


DataImportRevisions()
