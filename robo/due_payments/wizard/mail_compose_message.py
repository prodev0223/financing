# -*- coding: utf-8 -*-
from odoo import models, api


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.multi
    def render_message(self, res_ids):
        self.ensure_one()
        if self._context.get('force_message_vals', False):
            multi_mode = True
            if isinstance(res_ids, (int, long)):
                multi_mode = False
                res_ids = [res_ids]
            forced_template_values = self._context.get('force_message_vals', {})
            subjects = self.render_template(self.subject, self.model, res_ids)
            bodies = self.render_template(self.body, self.model, res_ids, post_process=True)
            emails_from = self.render_template(self.email_from, self.model, res_ids)
            replies_to = self.render_template(self.reply_to, self.model, res_ids)
            results = {res_id: {'subject': forced_template_values.get('subject', subjects[res_id]),
                                'body': forced_template_values.get('body', bodies[res_id]),
                                'email_from': forced_template_values.get('email_from', emails_from[res_id]),
                                'reply_to': forced_template_values.get('reply_to', replies_to[res_id]),
                                'email_to': forced_template_values.get('email_to', False),
                                'email_cc': forced_template_values.get('email_cc', False)}
                       for res_id in res_ids}

            return multi_mode and results
        else:
            return super(MailComposeMessage, self).render_message(res_ids=res_ids)


MailComposeMessage()
