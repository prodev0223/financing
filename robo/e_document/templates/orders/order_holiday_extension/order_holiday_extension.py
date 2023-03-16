# -*- coding: utf-8 -*-
from odoo import _, models, api, fields, tools, exceptions
from datetime import datetime


TEMPLATE = 'e_document.order_holiday_extension_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def order_holiday_extension_workflow(self):
        self.ensure_one()
        contract = self.employee_id2.contract_id.with_context(date=self.date_from)
        new_record = contract.update_terms(self.date_from, additional_leaves_per_year=self.int_1)
        if new_record:
            self.inform_about_creation(new_record)
            self.set_link_to_record(new_record)

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
                exception += _('Additional days on holiday extension document must be set to more than zero.\n')
            contract = self.employee_id2.contract_id.with_context(date=self.date_from)
            if not contract:
                exception += _('Selected employee does not have an active contract for current period')
            return exception
