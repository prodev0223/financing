# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def akcininku_sprendimas_del_sprendimo_panaikinimo_workflow(self):
        self.ensure_one()
        cancel_doc = self
        num_previous_cancelling_decisions = 0
        while True:
            if not cancel_doc.cancel_id:
                break
            cancel_doc = cancel_doc.cancel_id
            if cancel_doc.is_shareholders_decision_cancelling_doc():
                num_previous_cancelling_decisions += 1

        if num_previous_cancelling_decisions == 0 or num_previous_cancelling_decisions % 2 == 0:
            # Cancel the initial document
            cancel_doc.with_context(confirming_cancelling_decision=True).cancel_shareholders_decision_workflow()
        else:
            # Confirm the initial document
            cancel_doc.with_context(confirming_cancelling_decision=True).workflow_execution()

    @api.multi
    def is_shareholders_decision_cancelling_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.akcininku_sprendimas_del_sprendimo_panikinimo_template', raise_if_not_found=False)
        is_doc = doc_to_check and self.sudo().template_id.id == doc_to_check.id
        if not is_doc:
            try:
                is_doc = doc_to_check and self.template_id.id == doc_to_check.id
            except:
                pass
        return is_doc

    @api.multi
    def cancel_shareholders_decision_workflow(self):
        res = super(EDocument, self).cancel_shareholders_decision_workflow()
        docs_to_cancel = [doc for doc in self if doc.is_shareholders_decision_cancelling_doc()]
        for doc in docs_to_cancel:
            cancel_doc = doc
            num_previous_cancelling_decisions = 0
            while True:
                if not cancel_doc.cancel_id:
                    break
                cancel_doc = cancel_doc.cancel_id
                if cancel_doc.is_shareholders_decision_cancelling_doc():
                    num_previous_cancelling_decisions += 1

            if num_previous_cancelling_decisions == 0 or num_previous_cancelling_decisions % 2 == 0:
                # Confirm the initial document
                cancel_doc.with_context(confirming_cancelling_decision=True).workflow_execution()
            else:
                # Cancel the initial document
                cancel_doc.with_context(confirming_cancelling_decision=True).cancel_shareholders_decision_workflow()

        return res


EDocument()
