# -*- coding: utf-8 -*-
from odoo import models, fields


class RoboUxSettings(models.Model):
    _name = 'robo.ux.settings'

    company_id = fields.Many2one('res.company', string='Company', required=True)
    enabled = fields.Boolean('Enabled')

    invoice_mail_template_lt_id = fields.Many2one('mail.template')
    invoice_mail_template_en_id = fields.Many2one('mail.template')


RoboUxSettings()
