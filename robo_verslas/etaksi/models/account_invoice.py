# -*- coding: utf-8 -*-
from odoo import fields, _, models, api, tools, exceptions
from datetime import datetime


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.one
    @api.depends('date_invoice')
    def _get_invoice_month_in_words(self):
        months = {
            1: _('sausio'),
            2: _('vasario'),
            3: _('kovo'),
            4: _('balandžio'),
            5: _('gegužės'),
            6: _('birželio'),
            7: _('liepos'),
            8: _('rugpjūčio'),
            9: _('rugsėjo'),
            10: _('spalio'),
            11: _('lapkričio'),
            12: _('gruodžio')
        }

        datetime_invoice = datetime.strptime(self.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
        self.date_invoice_month = months[datetime_invoice.month]

    @api.one
    @api.depends('date_invoice')
    def _get_invoice_year(self):
        datetime_invoice = datetime.strptime(self.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
        self.date_invoice_year = datetime_invoice.year

    date_invoice_month = fields.Text(compute=_get_invoice_month_in_words)
    date_invoice_year = fields.Integer(compute=_get_invoice_year)

    @api.multi
    def action_invoice_sent(self):
        self.ensure_one()
        ctx = dict(self.env.context)

        if self.sudo().journal_id.mail_server_id:
            smtp_user = self.sudo().journal_id.mail_server_id.smtp_user
            smtp_name = self.sudo().journal_id.mail_server_id.name
            if smtp_user:
                ctx['force_email_sender_mail'] = smtp_user
            if smtp_name:
                ctx['force_email_sender_name'] = smtp_name
        ctx['force_template'] = self.env.ref('etaksi.email_template_edi_invoice', False)
        res = super(AccountInvoice, self.with_context(ctx)).action_invoice_sent()

        if self.sudo().journal_id.mail_server_id and res and res.get('res_id'):
            vals = {
                'mail_server_id': self.sudo().journal_id.mail_server_id.id,
            }
            compose_id = self.sudo().env['mail.compose.message'].browse(res.get('res_id'))
            compose_id.write(vals)
        return res

    @api.model
    def create_action_mass_invoice_mailing(self):
        action = self.env.ref('etaksi.action_mass_invoice_mailing')
        if action:
            action.create_action()

    @api.multi
    def open_action_mass_invoice_mailing(self):
        """
        Create and open etaksi mass mailing wizard from account.invoice action
        :return: None
        """
        ctx = self._context.copy()
        invoices_to_send = self.filtered(
            lambda r: r.state in ['open', 'paid'] and r.type in ['out_invoice', 'out_refund'])
        if not invoices_to_send:
            raise exceptions.UserError(_("Nėra sąskaitų faktūrų, kurias būtų galima apmokėti."))
        wizard = self.env['etaksi.invoice.mass.mailing'].create({'invoice_ids': [(6, 0, invoices_to_send.ids)]})
        return {
            'name': _('Masinis sąskaitų siuntimas'),
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'etaksi.invoice.mass.mailing',
            'view_id': self.env.ref('etaksi.form_etaksi_invoice_mass_mailing').id,
            'res_id': wizard.id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


AccountInvoice()
