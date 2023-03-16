# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _, tools
from datetime import datetime

TEMPLATE = 'e_document.request_holiday_extension_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def request_holiday_extension_workflow(self):
        self.ensure_one()
        order_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.order_holiday_extension_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_from': self.date_from,
            'int_1': self.int_1,
            'text_3': self.text_3,
        })
        self.write({'record_model': 'e.document', 'record_id': order_id.id})

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE, False)):
            exception = rec.check_request_holiday_extension_constraints()
            if exception:
                raise exceptions.UserError(exception)

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self.filtered(lambda d: d.template_id == self.env.ref(TEMPLATE, False)):
            res += rec.check_request_holiday_extension_constraints()
        return res

    @api.multi
    def check_request_holiday_extension_constraints(self):
        exception = str()
        for rec in self:
            if rec.int_1 < 1:
                exception += _('You can not request less than 1 day of additional holidays.\n')
            return exception
