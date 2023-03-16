# -*- coding: utf-8 -*-

from odoo import models, api, exceptions, _


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def akcininku_sprendimas_del_vadovo_pakeitimo_workflow(self):
        self.ensure_one()
        self.env['res.company.ceo'].create({
            'company_id': self.env.user.company_id.id,
            'employee_id': self.employee_id2.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })

    @api.multi
    def is_ceo_change_shareholders_decision_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.akcininku_sprendimas_del_vadovo_pakeitimo_template', raise_if_not_found=False)
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
        docs_to_cancel = [doc for doc in self if doc.is_ceo_change_shareholders_decision_doc()]
        for doc in docs_to_cancel:
            company_ceo_rec = self.env['res.company.ceo'].sudo().search([
                ('company_id', '=', self.env.user.company_id.id),
                ('employee_id', '=', doc.employee_id2.id),
                ('date_from', '=', doc.date_from),
                ('date_to', '=', doc.date_to),
            ])
            company_ceo_rec.sudo().unlink()
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        docs = self.filtered(lambda d: d.is_ceo_change_shareholders_decision_doc())
        for doc in docs:
            if doc.date_to and doc.date_from > doc.date_to:
                raise exceptions.UserError(_('Data nuo negali būti daugiau, nei data iki'))
        return res

EDocument()
