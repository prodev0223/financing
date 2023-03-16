# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, exceptions, tools


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def action_invoice_sent(self):
        self.ensure_one()
        ctx = dict(self.env.context)
        if self.sudo().journal_id.mail_server_id:
            smtp_user = self.sudo().journal_id.mail_server_id.smtp_user
            if smtp_user:
                ctx['force_email_sender_mail'] = smtp_user
        ctx['force_email_sender_name'] = self.sudo().journal_id.name

        main_account_invoice_template = self.env.ref('cherrymusic.cherry_music_main_account_invoice_mail_template',
                                                     raise_if_not_found=False)
        if main_account_invoice_template:
            ctx['force_template'] = main_account_invoice_template

        res = super(AccountInvoice, self.with_context(ctx)).action_invoice_sent()
        if self.sudo().journal_id.mail_server_id and res and res.get('res_id'):
            vals = {
                'mail_server_id': self.sudo().journal_id.mail_server_id.id,
            }
            compose_id = self.sudo().env['mail.compose.message'].browse(res.get('res_id'))
            compose_id.write(vals)
        return res


AccountInvoice()
