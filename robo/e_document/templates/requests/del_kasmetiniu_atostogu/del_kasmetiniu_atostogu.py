# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, api, tools, _, exceptions


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_kasmetiniu_atostogu_workflow(self):
        self.ensure_one()
        generated_id = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template').id,
            'document_type': 'isakymas',
            'employee_id2': self.employee_id1.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'date_2': self.date_document,
            'user_id': self.user_id.id,
            'atostoginiu_ismokejimas': self.atostoginiu_ismokejimas,
        })
        self.write({'record_model': 'e.document', 'record_id': generated_id.id})

    @api.multi
    def check_workflow_constraints(self):
        res = super(EDocument, self).check_workflow_constraints()
        for rec in self:
            res += rec.check_holiday_payout_constraint()
        return res

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda rec: not rec.sudo().skip_constraints_confirm):
            issues = rec.check_holiday_payout_constraint()
            if issues:
                raise exceptions.Warning(issues)
        return res

    @api.multi
    def check_holiday_payout_constraint(self):
        self.ensure_one()
        if self.template_id.id == self.env.ref('e_document.prasymas_del_kasmetiniu_atostogu_template').id:
            if self.atostoginiu_ismokejimas == 'pries':
                date_from_year = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT).year
                date_to_year = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT).year
                if date_from_year != date_to_year:
                    return _('Negalite rinktis atostoginių išmokėjimo prieš atostogas, kai pildomas prašymas metų '
                             'sandūroje')
        return str()


EDocument()
