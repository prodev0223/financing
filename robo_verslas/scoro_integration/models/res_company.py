# -*- coding: utf-8 -*-

from odoo import models, fields


class ResCompany(models.Model):

    _inherit = 'res.company'
    scoro_db_sync = fields.Datetime(groups='base.group_system')
    scoro_stock_accounting = fields.Boolean(default=False)


ResCompany()
