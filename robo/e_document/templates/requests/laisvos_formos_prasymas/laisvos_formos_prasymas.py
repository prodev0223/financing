# -*- coding: utf-8 -*-
from odoo import _, models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def laisvos_formos_prasymas_workflow(self):
        self.ensure_one()
        # Post a message about a free form request signed to mail channel
        subject = _('Free form request was signed')
        body = _('A free form request was submitted for employee {}.').format(self.employee_id1.name_related)
        msg_vals = {
            'subject': subject,
            'body': body,
            'channel': 'e_document.free_form_request_mail_channel',
            'rec_model': self._name,
            'rec_id': self.id,
        }
        self.message_post_to_mail_channel(**msg_vals)


EDocument()
