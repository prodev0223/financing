# -*- coding: utf-8 -*-


import uuid

from odoo.addons.robo_basic.models.utils import validate_email

from odoo import _, api, exceptions, fields, models


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    def random_unique_code(self):
        return uuid.uuid4()

    partner_ids = fields.Many2many(
        'res.partner', 'mail_compose_message_res_partner_rel',
        'wizard_id', 'partner_id', string='Papildomi gavėjai')
    unique_wizard_id = fields.Text(default=random_unique_code, store=False)
    user_attachment_ids = fields.Many2many('ir.attachment', compute='_compute_all_attachments', string='Prisegtukai',
                                           readonly=False)
    nbr_of_attachments = fields.Integer(compute='_compute_nbr_of_attachments')
    attachment_drop_lock = fields.Boolean(compute='_compute_attachment_drop_lock')
    additional_recipients = fields.Char(string='Additional recipients')

    @api.multi
    @api.depends('template_id')
    def _compute_all_attachments(self):
        for rec in self:
            ids = []
            if rec.id:
                ids = self.env['ir.attachment'].search([
                    ('res_model', '=', 'mail.compose.message'),
                    ('res_id', '=', rec.id),
                    '|',
                    ('res_field', '!=', False),
                    ('res_field', '=', False)
                ]).ids
            ids += rec.attachment_ids.ids
            rec.user_attachment_ids = [(5, 0,)] + [(4, doc_id) for doc_id in ids]

    @api.multi
    def _compute_nbr_of_attachments(self):
        for rec in self:
            rec.nbr_of_attachments = len(rec.user_attachment_ids.ids)

    @api.multi
    def _compute_attachment_drop_lock(self):
        for rec in self:
            rec.attachment_drop_lock = False

    @api.multi
    def send_mail_action(self):
        partners_check_emails = self.mapped('partner_ids')
        partners_with_bad_email = []
        for partner in partners_check_emails:
            if not partner.email:
                partners_with_bad_email.append(partner.name)
            else:
                for email in partner.email.split(';'):
                    if email and not validate_email(email.strip()):
                        partners_with_bad_email.append(partner.name)
                        break

        if len(partners_with_bad_email):
            raise exceptions.UserError(
                _('Pašalinkite šiuos gavėjus, nes jų el. pašto adresas sukonfigūruotas netinkamai: \n\n')
                + " \n".join(partners_with_bad_email))

        self.attachment_ids |= self.user_attachment_ids

        if self._context.get('force_send_message'):
            partners = self.mapped('partner_ids')
            notify_settings_by_partner = dict(partners.mapped(lambda r: (r.id, r.notify_email)))
            partners.sudo().write({'notify_email': 'always'})
            res = super(MailComposeMessage,
                        self.with_context(mail_notify_author=True, create_statistics=True)).send_mail_action()
            for partner in partners.sudo():
                partner.notify_email = notify_settings_by_partner[partner.id]
        else:
            res = super(MailComposeMessage,
                        self.with_context(mail_notify_author=True, create_statistics=True)).send_mail_action()
        return res

    @api.multi
    def get_mail_values(self, res_ids):
        self.ensure_one()
        res = super(MailComposeMessage, self).get_mail_values(res_ids)
        additional_recipients_emails = self.additional_recipients
        additional_recipients_email_list = set()
        additional_recipients_with_bad_email = []

        if not additional_recipients_emails:
            return res

        for email in additional_recipients_emails.replace(' ', '').split(';'):
            if not email or not validate_email(email.strip()):
                additional_recipients_with_bad_email.append(email)
            else:
                additional_recipients_email_list.add(str(email.lower()))

        if len(additional_recipients_with_bad_email):
            raise exceptions.UserError(
                _('Please remove these recipients because their email address is not configured correctly: \n')
                + " ".join(additional_recipients_with_bad_email))

        for res_id in res_ids:
            res[res_id].update({
                'additional_recipients': '; '.join(str(email) for email in additional_recipients_email_list)
            })

        return res

