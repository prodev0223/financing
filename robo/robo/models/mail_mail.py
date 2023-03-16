# -*- coding: utf-8 -*-


from odoo import api, exceptions, fields, models, _


class MailMail(models.Model):
    _name = 'mail.mail'
    _inherit = 'mail.mail'

    @api.model
    def create(self, values):
        company = self.env.user.company_id
        if self._context.get('active_model') == 'account.invoice' and company.invoice_cc_emails:
            values['email_cc'] = values.get('email_cc') + ';' + company.invoice_cc_emails if \
                values.get('email_cc') else company.invoice_cc_emails
        overpay_request = self.env.ref('robo.email_template_overpay_transfer_request', False)
        if overpay_request and (self._context.get('default_template_id') == overpay_request.id or values.get('template_id') == overpay_request.id):
            if not self.env.user.is_accountant() and not self.env.user.has_group('robo.group_overpay_transfer_requests'):
                raise exceptions.UserError(_('You do not have the necessary rights to send overpay transfer requests.'))
        mail = super(MailMail, self).create(values)
        if self._context.get('create_statistics'):
            mail_sudo = mail.sudo()
            if mail_sudo.statistics_ids:
                mail_sudo.statistics_ids.write({'message_id': mail_sudo.message_id, 'state': 'outgoing'})
            else:
                self.env['mail.mail.statistics'].sudo().create({
                    'mail_mail_id': mail_sudo.id,
                    'mail_mail_id_int': mail_sudo.id,
                    'message_id': mail_sudo.message_id,
                    'state': 'outgoing',
                })
        return mail

    @api.multi
    def unlink(self):
        # Prevent deletion of mail.mail records
        return

    @api.multi
    def _postprocess_sent_message(self, mail_sent=True):
        for mail in self:
            if mail.model == 'robo.mail.mass.mailing.partners':
                wizard_line_id = self.env['robo.mail.mass.mailing.partners'].browse(mail.res_id)
                if mail_sent:
                    if self._context.get('active_model') == 'account.aged.trial.balance':
                        partner = wizard_line_id.partner_id

                        # last attachment
                        attachment_id = mail.mail_message_id.attachment_ids and mail.mail_message_id.attachment_ids[-1]
                        if attachment_id:
                            attachment_id.write({
                                'res_model': 'res.partner',
                                'res_id': partner.id,
                            })

                        if partner.balance_reconciliation_attachment_id.id != attachment_id:
                            partner.sudo().balance_reconciliation_attachment_id.unlink()

                        date_now = fields.Datetime.now()
                        partner.write({
                            'balance_reconciliation_send_date': date_now,
                            # last attachment?
                            'balance_reconciliation_attachment_id': attachment_id.id,
                        })
                        if self._context.get('post_date', False):
                            partner.message_post(body='Skolų suderinimo aktas buvo išsiųstas %s' % date_now[:10])

                else:
                    new_failed_value = (
                                                   wizard_line_id.mail_compose_message_id.failed_emails or '') + wizard_line_id.email + '\n'
                    wizard_line_id.mail_compose_message_id.failed_emails = new_failed_value

        return super(MailMail, self)._postprocess_sent_message(mail_sent=mail_sent)
