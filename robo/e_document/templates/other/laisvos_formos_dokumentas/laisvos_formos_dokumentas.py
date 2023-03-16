# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def laisvos_formos_dokumentas_workflow(self):
        self.ensure_one()
        pass

    @api.multi
    def cancel_document(self):
        self.ensure_one()
        if self.document_type == 'other' and self.state == 'e_signed':
            user_employees = self.env.user.employee_ids
            employee = self.employee_id1
            document_employee_is_user = employee.id in user_employees.ids if user_employees and employee else False
            if not document_employee_is_user and not self.env.user.is_manager():
                raise exceptions.UserError(_('Negalite atšaukti dokumento'))
            self.sudo().write({
                'state': 'cancel',
                'cancel_uid': self.env.uid
            })


EDocument()
