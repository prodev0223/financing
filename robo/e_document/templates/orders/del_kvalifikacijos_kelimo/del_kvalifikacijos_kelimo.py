# -*- coding: utf-8 -*-
from odoo import models, api, exceptions, _, tools
from datetime import datetime


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_kvalifikacijos_kelimo_workflow(self):
        self.ensure_one()
        hol_id = self.env['hr.holidays'].create({
            'name': 'Kvalifikacijos Kėlimas',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_KV').id,
            'date_from': self.calc_date_from(self.date_3),
            'date_to': self.calc_date_to(self.date_3),
            'type': 'remove',
            'numeris': self.document_number,
            'is_paid_for': True
        })
        hol_id.action_approve()
        self.inform_about_creation(hol_id)
        self.write({
            'record_model': 'hr.holidays',
            'record_id': hol_id.id,
        })

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.isakymas_del_kvalifikacijos_kelimo_template', False)
        for rec in self:
            if rec.sudo().skip_constraints_confirm:
                continue
            if rec.sudo().template_id == template:
                contract = self.env['hr.contract'].search([
                    ('employee_id', '=', rec.employee_id2.id),
                    ('date_start', '<=', rec.date_3),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', rec.date_3)
                ], limit=1)
                if not contract:
                    raise exceptions.UserError(_('Darbuotojas %s neturi aktyvios darbo sutarties.') % rec.date_3)

    @api.multi
    def check_workflow_constraints(self):
        """
        Checks constraints before allowing workflow to continue
        :return: error message as str
        """
        body = super(EDocument, self).check_workflow_constraints()
        template_id = self.sudo().template_id

        if template_id == self.env.ref('e_document.isakymas_del_kvalifikacijos_kelimo_template', False):
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id2.id),
                ('date_start', '<=', self.date_3),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_3)
            ], limit=1)
            if not contract:
                body += _('Darbuotojas %s neturi aktyvios darbo sutarties.') % self.date_3

        return body

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref('e_document.isakymas_del_kvalifikacijos_kelimo_template', False)
        document = self.cancel_id
        if document and document.sudo().template_id == template:
            record_model = document.record_model
            record_id = document.record_id
            if record_model == 'hr.holidays' and record_id:
                holiday = self.env['hr.holidays'].browse(record_id)
                if holiday.state == 'validate' and holiday.date_from:
                    period_line_ids = self.env['ziniarastis.period.line'].search([
                        ('employee_id', '=', holiday.employee_id.id),
                        ('date_from', '<=', holiday.date_from),
                        ('date_to', '>=', holiday.date_from)], limit=1)
                    if period_line_ids and period_line_ids[0].period_state == 'done':
                            raise exceptions.Warning(_('Įsakymo patvirtinti negalima, nes darbo užmokesčio '
                                                       'žiniaraštis jau buvo patvirtintas.'))
                    holiday.action_refuse()
                    holiday.action_draft()
                    holiday.unlink()
                elif holiday.state != 'validate':
                    holiday.action_draft()
                    holiday.unlink()
            else:
                raise exceptions.Warning(_('Nerastas susijęs neatvykimas'))
        else:
            super(EDocument, self).execute_cancel_workflow()


EDocument()
