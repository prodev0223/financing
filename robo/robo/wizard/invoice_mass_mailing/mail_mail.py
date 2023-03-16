# -*- coding: utf-8 -*-
from odoo import models, api


class MailMail(models.Model):
    _name = 'mail.mail'
    _inherit = 'mail.mail'

    @api.multi
    def _postprocess_sent_message(self, mail_sent=True):
        """
        Extend _postprocess_sent_message. If mail came from invoice mass mailing
        check whether it failed or not, if it did, gather failed recipient names and
        write them to mass mailing wizard
        :param mail_sent: indicates whether email was sent
        :return: super of _postprocess_sent_message
        """
        if self._context.get('mass_invoice_mailing'):
            wizard_id = self._context.get('mass_mailing_wizard_id')
            if wizard_id and not mail_sent:
                invoice_mailing_wizard = self.env['invoice.mass.mailing.wizard'].browse(wizard_id)
                failed_partners = str()
                for mail in self.filtered(lambda x: x.model == 'account.invoice'):
                    failed_partners += '{}\n'.format('/'.join(mail.recipient_ids.mapped('name')))
                if invoice_mailing_wizard.failed_partners:
                    invoice_mailing_wizard.failed_partners += failed_partners
                else:
                    invoice_mailing_wizard.failed_partners = failed_partners
        return super(MailMail, self)._postprocess_sent_message(mail_sent=mail_sent)


MailMail()
