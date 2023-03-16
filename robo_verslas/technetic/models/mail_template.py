# -*- coding: utf-8 -*-

from odoo import models, api


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    @api.one
    def _set_report_name(self):
        if self.model_id.model == 'account.invoice' and self.robo_custom:
            self.report_name = '''${((object.number or object.move_name or ('Išankstinė-' + str(object.proforma_number) if object.proforma_number else 'Sąskaita-' + str(object.id))) + '_' + object.partner_id.slugified_name + '.pdf').replace('/','_')}'''
