# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, tools, _


TEMPLATE = 'e_document.prasymas_del_darbo_grafiko_pakeitimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_darbo_grafiko_pakeitimo_workflow(self):
        self.ensure_one()

        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_darbo_grafiko_pakeitimo_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'time_1': self.time_1,
            'time_2': self.time_2,
            'date_2': self.date_document,
            'date_4': self.date_3,
            'user_id': self.user_id.id,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self.filtered(lambda d: d.template_id == self.env.ref(TEMPLATE)):
            appointment = rec.employee_id1.contract_id.with_context(date=rec.date_3).appointment_id
            if not appointment:
                raise exceptions.ValidationError(
                    _('Current appointment of employee {} could not be found').format(rec.employee_id1.name_related))
            schedule_template_type = appointment.sudo().schedule_template_id.template_type
            if not schedule_template_type or schedule_template_type not in ['fixed', 'suskaidytos']:
                raise exceptions.ValidationError(
                    _('Request for {} can not be {} because work time depends on post and work time norm. In order to '
                      'change them, please contact your HR manager').format(rec.employee_id1.name_related, _('signed')))
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE)):
            appointment = rec.employee_id1.contract_id.with_context(date=rec.date_3).appointment_id
            if not appointment:
                raise exceptions.ValidationError(
                    _('Current appointment of employee {} could not be found').format(rec.employee_id1.name_related))
            schedule_template_type = appointment.sudo().schedule_template_id.template_type
            if not schedule_template_type or schedule_template_type not in ['fixed', 'suskaidytos']:
                raise exceptions.ValidationError(
                    _('Request for {} can not be {} because work time depends on post and work time norm. In order to '
                      'change them, please contact your HR manager').format(self.employee_id1.name_related,
                                                                            _('formed')))


EDocument()
