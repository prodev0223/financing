# -*- coding: utf-8 -*-

from odoo import models, fields


class IrModel(models.Model):
    _inherit = 'ir.model'

    robo_editable_mail_templates = fields.Boolean(string='Allow changing mail templates of this model in ROBO mail '
                                                         'template managment module')


IrModel()
