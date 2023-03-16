# -*- coding: utf-8 -*-


from odoo import api, fields, models


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    active = fields.Boolean(string='Aktyvus', default=True)  # Ar email template yra aktyvus

    @api.multi
    def generate_email(self, res_ids, fields=None):
        fields = ['subject', 'body_html', 'email_from', 'email_to', 'partner_to', 'reply_to',
                  'scheduled_date']
        return super(MailTemplate, self).generate_email(res_ids, fields=fields)
