# -*- coding: utf-8 -*-
from odoo import models, fields, _


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    crm_sharing_privacy_visibility = fields.Selection([
        ('followers', 'Komandos nariams'),
        ('employees', 'Matoma visiems darbuotojams'),
    ],
        string='Sąskaitų faktūrų privatumas', lt_string='Sąskaitų faktūrų privatumas', required=False,
        default='followers', groups='robo_basic.group_robo_premium_manager')
    use_invoices = fields.Boolean(default=True)
