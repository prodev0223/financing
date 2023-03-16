# -*- coding: utf-8 -*-

from odoo import models, api, _, exceptions, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.remote_work_request_template', raise_if_not_found=False)
        for rec in self.filtered(lambda d: d.template_id == template):
            if rec.date_to and rec.date_to < rec.date_from:
                raise exceptions.UserError(_('Date to has to be a later or the same date as date from'))
            if rec.additional_remote_work_compensation == 'specific_amount' and \
                tools.float_compare(rec.float_1, 0.0, precision_digits=2) <= 0:
                raise exceptions.UserError(_('Incorrect compensation amount'))

    @api.multi
    def remote_work_request_workflow(self):
        self.ensure_one()
        template = self.sudo().get_remote_work_agreement_template()
        generated_id = self.sudo().create({
            'template_id': template.id,
            'document_type': 'agreement',
            'employee_id2': self.employee_id1.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'additional_remote_work_compensation': self.additional_remote_work_compensation,
            'float_1': self.float_1,
            'extra_text': self.extra_text,
            'text_4': self.text_3,
        })
        user = self.employee_id1.user_id or self.env.user
        generated_id.sudo().with_context(users_ids_not_to_inform=[user.id]).confirm()
        generated_id.sudo(user).sign()
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref('e_document.remote_work_request_template', raise_if_not_found=False)
        if self.cancel_id and self.cancel_id.template_id == template:
            raise exceptions.UserError(_('You can not cancel remote work requests, please leave a comment at the '
                                         'bottom of the document'))
        else:
            super(EDocument, self).execute_cancel_workflow()


EDocument()
