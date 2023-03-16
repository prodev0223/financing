# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import _, api, exceptions, models, tools


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_kasmetiniu_atostogu_workflow(self):
        self.ensure_one()

        existing_holiday = self.env['hr.holidays'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_cl').id),
            ('date_from_date_format', '=', self.date_from),
            ('date_to_date_format', '=', self.date_to),
            ('type', '=', 'remove'),
            ('state', '=', 'validate'),
        ])

        if not existing_holiday:
            hol_id = self.env['hr.holidays'].create({
                'name': 'Kasmetinės atostogos',
                'data': self.date_document,
                'employee_id': self.employee_id2.id,
                'holiday_status_id': self.env.ref('hr_holidays.holiday_status_cl').id,
                'date_from': self.calc_date_from(self.date_from),
                'date_to': self.calc_date_to(self.date_to),
                'type': 'remove',
                'numeris': self.document_number,
                'ismokejimas': 'before_hand' if self.politika_atostoginiai == 'rinktis' and self.atostoginiu_ismokejimas == 'pries' else 'du',
                'department_id': self.employee_id2.department_id.id,
            })
            hol_id.action_approve()
            self.inform_about_creation(hol_id)
            self.write({
                'record_model': 'hr.holidays',
                'record_id': hol_id.id,
            })
        else:
            existing_doc = self.search([
                ('date_from', '=', self.date_from),
                ('date_to', '=', self.date_to),
                ('employee_id2', '=', self.employee_id2.id),
                ('template_id', '=', self.template_id.id),
                ('state', '=', 'e_signed'),
                ('rejected', '=', False),
            ])

            if existing_doc:
                raise exceptions.UserError(_('Negalima pasirašyti šio dokumento, nes jau egzistuoja atostogos šiai datai pagal kitą įsakymą.'))
            else:
                existing_holiday.write({
                    'numeris': self.document_number,
                    'ismokejimas': 'before_hand' if self.politika_atostoginiai == 'rinktis' and
                                                    self.atostoginiu_ismokejimas == 'pries' else 'du',
                    'department_id': self.employee_id2.department_id.id,
                })
                self.write({
                    'record_model': 'hr.holidays',
                    'record_id': existing_holiday.id,
                })

        date_now_str = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.atostoginiu_ismokejimas == 'pries' and self.date_from <= date_now_str:
            try:
                subject = _('[{}] Įsakymas dėl kasmetinių atostogų buvo pasirašytas atgaline data').format(self._cr.dbname)
                body = _("""Įsakymas dėl kasmetinių atostogų buvo pasirašytas atgaline data, bei 
                atostoginių apmokėjimas buvo pasirinktas prieš atostogas.""")
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                message = _("""
                [{}] Failed to create a ticket for informing accountant about holidays order for a past date: {}
                \nKlaida: {}
                """).format(self._cr.dbname, self.id, str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template', False)
        for rec in self.filtered(lambda r: r.sudo().template_id == template and not r.sudo().skip_constraints_confirm):
            if rec.date_from > rec.date_to:
                raise exceptions.ValidationError(_('Date to has to be a later or the same date as date from'))

    @api.one
    @api.depends('date_from', 'date_to', 'employee_id2')
    def _warn_about_sumine_holidays_abuse(self):
        self.warn_about_sumine_holidays_abuse = False
        if self.template_id.id == self.env.ref(
                'e_document.isakymas_del_kasmetiniu_atostogu_template').id and self.date_from and self.date_to and self.employee_id2:
            appointment = self.employee_id2.with_context(date=self.date_from).contract_id.appointment_id
            if not appointment:
                appointment = self.employee_id2.contract_id.appointment_id
            if appointment and appointment.sudo().schedule_template_id.template_type == 'sumine' and \
                    appointment.sudo().struct_id.code == 'MEN':
                holiday_length = (datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) - datetime.strptime(
                    self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)).days
                if holiday_length < 7.0:
                    self.warn_about_sumine_holidays_abuse = True

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        return super(EDocument, self).execute_cancel_workflow()  #TODO: this check is too strong
        template = self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template', raise_if_not_found=False)
        if self.cancel_id and self.cancel_id.template_id.id == template.id:
            if self.cancel_id.record_model == 'hr.holidays' and self.cancel_id.record_id:
                holiday = self.env['hr.holidays'].browse(self.cancel_id.record_id).exists()
                if holiday and holiday.payment_id.state == 'done':
                    raise exceptions.ValidationError(
                        _('''
                        Atostogų išmoka jau atlikta. Jei tikrai norite atšaukti atostogas - 
                        palikite žinutę buhalteriui šio dokumento apačioje.
                        '''))
        return super(EDocument, self).execute_cancel_workflow()


EDocument()
