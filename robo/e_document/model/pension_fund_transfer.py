# coding: utf-8

from odoo import models, fields


class PensionFundTransfer(models.Model):
    _inherit = 'pension.fund.transfer'

    e_document_id = fields.Many2one('e.document', string='Related e-document')

    
