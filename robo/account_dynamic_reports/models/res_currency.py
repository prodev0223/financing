# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    excel_format = fields.Char(string='Excel format', default='_ * #,##0.00_) ;_ * - #,##0.00_) ;_ * "0"??_) ;_ @_ ',
                               required=True)
