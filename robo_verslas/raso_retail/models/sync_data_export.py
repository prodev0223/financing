# -*- coding: utf-8 -*-

from odoo import models, fields


class SyncDataExport(models.Model):
    _name = 'sync.data.export'

    data_type = fields.Selection([('0', 'Sales'),
                                  ('1', 'Invoices'),
                                  ('2', 'Tara'),
                                  ('3', 'Refunds')], required=True)
    data_provider = fields.Char(string='Tiekėjas')
    sync_data = fields.Text(string='Perduodami duomenys')
    shop_no = fields.Char(string='Parduotuvės numeris')
    status = fields.Integer(string='Būsena')
    sync_data_export_id = fields.Integer(string='Eksporto ID')
    creation_errors = fields.Integer(string='Klaidų skaičius')


SyncDataExport()