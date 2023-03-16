# -*- encoding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    operation_act_creation = fields.Selection([('manual', 'Rankinis'),
                                               ('auto', 'Automatinis')], default='manual',
                                              string='Eksploatacijos aktų sudarymas')


ResCompany()
