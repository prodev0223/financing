# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, exceptions, _, SUPERUSER_ID


TEMPLATE = 'e_document.dynamic_workplace_compensation_order_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def dynamic_workplace_compensation_order_workflow(self):
        """
        Creates Hr.Employee.Compensation records for the employee and confirms said records
        """
        self.ensure_one()

        date_from_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
        payslip_year = self.env['years'].search([('code', '=', date_from_dt.year)], limit=1)
        payslip_month = str(date_from_dt.month).zfill(2)

        compensation = self.env['hr.employee.compensation'].create({
            'employee_id': self.employee_id2.id,
            'date_from': self.date_1,
            'date_to': self.date_2,
            'payslip_year_id': payslip_year.id,
            'payslip_month': payslip_month,
            'amount': self.float_1,
            'compensation_type': 'dynamic_workplace',
            'related_document': self.id,
            'compensation_time_ids': [(0, 0, line.read()[0]) for line in self.e_document_time_line_ids]
        })
        compensation.action_confirm()
        self.write({
            'record_model': 'hr.employee.compensation',
            'record_ids': self.format_record_ids([compensation.id]),
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        original_document = self.sudo().cancel_id
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)

        if original_document and original_document.sudo().template_id == template:
            tests_enabled = tools.config.get('test_enable')
            new_cr = self.pool.cursor() if not tests_enabled else self._cr  # Use existing cursor if tests are running
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            set_failed_workflow = False
            try:
                compensations = env[original_document.record_model].browse(original_document.parse_record_ids())
                try:
                    compensations.action_draft()
                    compensations.unlink()
                except:
                    if not tests_enabled:
                        new_cr.rollback()
                    set_failed_workflow = True
                if not tests_enabled:
                    new_cr.commit()
            except:
                if not tests_enabled:
                    new_cr.rollback()
            finally:
                if not tests_enabled:
                    new_cr.close()
                if self.failed_workflow != set_failed_workflow:
                    self.write({'failed_workflow': set_failed_workflow})
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    @api.onchange('date_1')
    def _onchange_date_1(self):
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda r: r.template_id == template and r.date_1):
            date_1_dt = datetime.strptime(rec.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            first_of_month = (date_1_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.date_1 != first_of_month:
                rec.date_1 = first_of_month
            last_of_month = (date_1_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.date_2 != last_of_month:
                rec.date_2 = last_of_month
        try:
            return super(EDocument, self)._onchange_date_1()
        except:
            pass

    @api.multi
    @api.onchange('date_2')
    def _onchange_date_2(self):
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda r: r.template_id == template and r.date_2):
            date_2_dt = datetime.strptime(rec.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)
            last_of_month = (date_2_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.date_2 != last_of_month:
                rec.date_2 = last_of_month
            first_of_month = (date_2_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.date_1 != first_of_month:
                rec.date_1 = first_of_month
        try:
            return super(EDocument, self)._onchange_date_2()
        except:
            pass

    @api.multi
    def execute_confirm_workflow_update_values(self):
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for rec in self.filtered(lambda r: r.template_id == template):
            rec.date_3 = rec.date_1
        return super(EDocument, self).execute_confirm_workflow_update_values()

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE, False)
        for rec in self.filtered(lambda r: r.sudo().template_id == template and not r.sudo().skip_constraints_confirm):
            date_from = rec.date_1
            date_to = rec.date_2
            employee = rec.employee_id2
            appointments = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '>=', date_from),
                ('date_end', '=', False)
            ], order='date_start asc')
            if not appointments:
                raise exceptions.ValidationError(_('Mėnesį, su kuriuo išmokama kompensacija darbuotojas {} neturi '
                                                   'jokio darbo sutarties priedo').format(employee.name))
            appointment = appointments[0]
            wage = appointment.wage
            if appointment.struct_id.code == 'VAL':
                work_norm = self.env['hr.employee'].sudo().employee_work_norm(
                    calc_date_from=date_from,
                    calc_date_to=date_to,
                    contract=appointment.contract_id,
                    appointment=appointment
                ).get('hours', 0.0)
                wage = wage * work_norm
            if tools.float_compare(rec.float_1, wage / 2.0, precision_digits=2) > 0:  # P3:DivOK
                raise exceptions.ValidationError(_('Kompensacijos dydis negali būti didesnis, nei 50% darbuotojo '
                                                   'bazinio DU. Šis dydis viršijamas darbuotojui '
                                                   '{}').format(employee.name))

            if rec.e_document_time_line_ids and not \
                    all(date_from <= l.date <= date_to for l in rec.e_document_time_line_ids):
                raise exceptions.ValidationError(_('Not all set dates are in the set period from {} to {}').format(
                    date_from, date_to
                ))
            if not rec.e_document_time_line_ids:
                raise exceptions.ValidationError(_('Nenustatytos darbo dienos, už kurias skiriama ši kompensacija'))

    @api.onchange('employee_id2', 'float_2', 'e_document_time_line_ids')
    def _onchange_employee_id2_set_amount(self):
        template = self.env.ref(TEMPLATE, False)
        if template and self.template_id and self.template_id == template and self.employee_id2:
            time_lines = self.e_document_time_line_ids
            duration = [time_line.time_to - time_line.time_from for time_line in time_lines]
            if duration:
                duration = sum(duration)
                date_from = self.date_1
                date_to = self.date_2
                percentage = self.float_2
                appointment = self.env['hr.contract.appointment'].search([
                    ('employee_id', '=', self.employee_id2.id),
                    ('date_start', '<=', date_to),
                    '|',
                    ('date_end', '>=', date_from),
                    ('date_end', '=', False)
                ], order='date_start asc', limit=1)
                if not appointment:
                    return

                if appointment.struct_id.code == 'VAL':
                    hourly_wage = appointment.wage
                else:
                    ziniarastis_period_line = self.env['ziniarastis.period.line'].search([
                        ('date_from', '=', date_from),
                        ('contract_id', '=', appointment.contract_id.id),
                    ], limit=1)
                    if not ziniarastis_period_line:
                        return
                    period_regular_work_hours = ziniarastis_period_line.with_context(
                        appointment_id=appointment.id, maximum=True
                    ).num_regular_work_hours
                    if tools.float_is_zero(period_regular_work_hours, precision_digits=2):
                        return
                    hourly_wage = appointment.wage / period_regular_work_hours  # P3:DivOK
                if tools.float_is_zero(hourly_wage, precision_digits=2):
                    return
                if percentage < 0.0 or percentage > 50.0:
                    raise exceptions.ValidationError(_('Compensation amount must be between 0-50% of the employees '
                                                       'base pay amount'))
                self.float_1 = hourly_wage * duration * percentage / 100.0  # P3:DivOK

    @api.multi
    @api.onchange('employee_id2', 'date_1', 'date_2', 'template_id')
    def _onchange_employee_or_dates_update_dynamic_workplace_times(self):
        template = self.env.ref(TEMPLATE, False)
        for rec in self:
            if template and rec.template_id and rec.template_id == template and rec.employee_id2 and rec.date_1 and \
                    rec.date_2:
                appointments = self.env['hr.contract.appointment'].search([
                    ('employee_id', '=', rec.employee_id2.id),
                    ('date_start', '<=', rec.date_2),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', rec.date_1)
                ])

                date_from_dt = datetime.strptime(rec.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(rec.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_dt = date_from_dt

                overwrite_set_times = False
                new_time_line_vals = [(5, 0)]

                while date_dt <= date_to_dt:
                    date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    appointment = appointments.filtered(
                        lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date)
                    )
                    schedule_template = appointment.schedule_template_id
                    if not schedule_template:
                        date_dt += relativedelta(days=1)
                        continue
                    work_times = schedule_template.work_times_by_fixed_attendance_line_ids(date_dt)
                    
                    if not overwrite_set_times and work_times:
                        overwrite_set_times = True

                    if work_times:
                        for work_time in work_times:
                            new_time_line_vals.append((0, 0, {
                                'e_document_id': rec.id,
                                'employee_id': rec.employee_id2.id,
                                'date': date,
                                'time_from': work_time[0],
                                'time_to': work_time[1],
                                'duration': work_time[1] - work_time[0]
                            }))
                    date_dt += relativedelta(days=1)

                if overwrite_set_times:
                    rec.e_document_time_line_ids = new_time_line_vals

    @api.model
    def default_get(self, fields):
        res = super(EDocument, self).default_get(fields)
        template = self.env.ref(TEMPLATE, False)
        if res.get('template_id') == template.id:
            res['float_2'] = 50
        return res


EDocument()
