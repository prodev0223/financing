# -*- coding: utf-8 -*-
from __future__ import division

from odoo import models, api, exceptions, _

TEMPLATE = 'e_document.end_agreement_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def get_original_document(self):
        self.ensure_one()
        return self.cancel_id

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if not template:
            return res
        documents = self.filtered(lambda doc: doc.template_id == template and not doc.sudo().skip_constraints_confirm)
        for doc in documents:
            original_document = doc.get_original_document()
            if original_document.date_from > doc.date_from:
                raise exceptions.ValidationError(_('End date has to be after the original agreement starts'))
            if original_document.date_to and original_document.date_to < doc.date_from:
                raise exceptions.ValidationError(_('End date has to be before the original agreement ends'))
        return res

    @api.multi
    def end_agreement(self, date_from):
        return

    @api.multi
    def end_agreement_workflow(self):
        self.ensure_one()
        original_document = self.get_original_document()
        original_document.write({'rejected': True})
        original_document.end_agreement(self.date_from)
