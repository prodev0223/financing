# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools


class NsoftReportMoveLine(models.Model):
    """
    Model that holds lines for one parent nsoft.report.move
    lines are split by nsoft category
    """
    _name = 'nsoft.report.move.line'
    _inherit = ['nsoft.sum.accounting.line.base', 'mail.thread']

    # Sums
    line_amount = fields.Float(string='Eilutės suma')
    line_quantity = fields.Float(string='Eilutės kiekis')

    # Other fields
    product_name = fields.Char(string='Produkto pavadinimas')
    category_name = fields.Char(string='Kategorijos pavadinimas')

    # Relational fields
    nsoft_report_move = fields.Many2one('nsoft.report.move', string='nSoft aktas')
    move_id = fields.Many2one('account.move', string='Žurnalo įrašas')

    # State
    state = fields.Selection([('imported', 'Įrašas importuotas'),
                              ('failed', 'Klaida kuriant aktą'),
                              ('created', 'Įrašas sukurtas'),
                              ('cancelled_dub', 'Dublikatas -- atšaukta')], string='Būsena',
                             default='imported')

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, '{} - Eilutė'.format(rec.nsoft_report_move.ext_doc_number)) for rec in self]


NsoftReportMoveLine()
