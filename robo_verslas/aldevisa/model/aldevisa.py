# -*- coding: utf-8 -*-
from odoo import models, fields, _


class AccountInvoice(models.Model):
    _inherit = 'ir.mail_server'

    allow_change = fields.Boolean(string='Leisti keisti', default=False, groups='base.group_no_one')
    sequence = fields.Integer(groups='base.group_no_one')


AccountInvoice()
