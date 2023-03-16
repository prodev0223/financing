# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, exceptions, models, tools

TEMPLATE_EXT_REF = 'e_document.group_dynamic_workplace_compensation_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def group_dynamic_workplace_compensation_workflow(self):
        """
        Creates Hr.Employee.Compensation records for each document line/employee and confirms said records
        """
        self.ensure_one()
        lines = self.e_document_line_ids
        HrEmployeeCompensation = self.env['hr.employee.compensation']
        compensations = HrEmployeeCompensation
        for line in lines:
            compensation_times = self.e_document_time_line_ids
            compensation_time_vals = []
            for compensation_time in compensation_times:
                date = compensation_time.date
                appointment = line.employee_id2.with_context(date=date).contract_id.appointment_id
                time_values = compensation_time.read()[0]
                if appointment:
                    regular_hours = appointment.schedule_template_id.get_regular_hours(date)
                    time_from = 8.0
                    time_to = min(8.0 + regular_hours, 24.0)
                    time_values['time_from'] = time_from
                    time_values['time_to'] = time_to
                    time_values['duration'] = max(0.0, time_to - time_from)
                compensation_time_vals.append((0, 0, time_values))

            compensations |= HrEmployeeCompensation.create({
                'employee_id': line.employee_id2.id,
                'date_from': self.date_1,
                'date_to': self.date_2,
                'payslip_year_id': self.payslip_year_id.id,
                'payslip_month': self.payslip_month,
                'amount': line.float_1,
                'compensation_type': 'dynamic_workplace',
                'related_document': self.id,
                'compensation_time_ids': compensation_time_vals
            })
        compensations.action_confirm()
        self.write({
            'record_model': 'hr.employee.compensation',
            'record_ids': self.format_record_ids(compensations.ids),
        })

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        original_document = self.sudo().cancel_id
        template = self.env.ref(TEMPLATE_EXT_REF, False)
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
    @api.depends('e_document_line_ids', 'bonus_input_type')
    def _compute_text_1(self):
        res = super(EDocument, self)._compute_text_1()
        template = self.env.ref('e_document.group_dynamic_workplace_compensation_template', False)
        for rec in self.filtered(lambda t: t.sudo().template_id == template):
            if len(rec.sudo().e_document_line_ids) < 2:
                bonus_table = ''
            else:
                bonus_table = '''Kompensacija skiriamas šiems darbuotojams:
                <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                    <tr style="border:1px solid black;">
                        <td style="border:1px solid black;"><b>Vardas pavardė</b></td>
                        <td style="border:1px solid black;"><b>Kompensacijos dydis, EUR</b></td>
                    </tr>'''
                for line in rec.e_document_line_ids:
                    amount = '%.2f' % line.float_1
                    amount = amount.replace('.', ',')
                    bonus_table += '''<tr style="border:1px solid black;">
                        <td style="border:1px solid black;">%(name)s</td>
                        <td style="border:1px solid black;">%(amount)s</td>
                    </tr>''' % {
                        'name': line.employee_id2.name,
                        'amount': amount,
                    }
                bonus_table += """</table>"""
            rec.compute_text_1 = bonus_table
        return res

    @api.multi
    @api.onchange('date_1')
    def _onchange_date_1(self):
        template = self.env.ref(TEMPLATE_EXT_REF, raise_if_not_found=False)
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
        template = self.env.ref(TEMPLATE_EXT_REF, raise_if_not_found=False)
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
        template = self.env.ref(TEMPLATE_EXT_REF, raise_if_not_found=False)
        for rec in self.filtered(lambda r: r.template_id == template):
            date_3_dt = datetime(rec.payslip_year_id.code, int(rec.payslip_month), 1)
            rec.date_3 = date_3_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return super(EDocument, self).execute_confirm_workflow_update_values()

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE_EXT_REF, False)
        for rec in self.filtered(lambda r: r.sudo().template_id == template and not r.sudo().skip_constraints_confirm):
            date_from = rec.date_1
            date_to = rec.date_2
            appointments = self.env['hr.contract.appointment'].search([
                ('employee_id', 'in', rec.mapped('e_document_line_ids.employee_id2').ids),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '>=', date_from),
                ('date_end', '=', False)
            ], order='date_start asc')
            if not rec.e_document_line_ids:
                raise exceptions.UserError(_('Nepasirinkti darbuotojai, kuriems skiriama kompensacija'))
            # Check the times the compensation is for
            if not rec.e_document_time_line_ids:
                raise exceptions.ValidationError(_('Nenustatytos darbo dienos, už kurias skiriama ši kompensacija'))

            for worked_outside_day in rec.e_document_time_line_ids:
                wod_date = worked_outside_day.date
                if wod_date > date_to or wod_date < date_from:
                    raise exceptions.ValidationError(_('Nustatyta darbo diena {}, už kurią skiriama kompensacija, '
                                                       'nepatenka į laikotarpio, už kurį skiriama kompensacija, '
                                                       'diapazoną, nuo {} iki {}').format(
                        wod_date, date_from, date_to)
                    )

            for line in rec.e_document_line_ids:
                employee = line.employee_id2
                employee_appointments = appointments.filtered(lambda a: a.employee_id == employee)
                if not employee_appointments:
                    raise exceptions.ValidationError(_('Mėnesį, su kuriuo išmokama kompensacija darbuotojas {} neturi '
                                                       'jokio darbo sutarties priedo').format(employee.name))
                employee_appointment = employee_appointments[0]
                wage = employee_appointment.wage
                if employee_appointment.struct_id.code == 'VAL':
                    work_norm = self.env['hr.employee'].sudo().employee_work_norm(
                        calc_date_from=date_from,
                        calc_date_to=date_to,
                        contract=employee_appointment.contract_id,
                        appointment=employee_appointment
                    ).get('hours', 0.0)
                    wage = wage * work_norm
                if tools.float_compare(line.float_1, wage / 2.0, precision_digits=2) > 0:  # P3:DivOK
                    raise exceptions.ValidationError(_('Kompensacijos dydis negali būti didesnis, nei 50% darbuotojo '
                                                       'bazinio DU. Šis dydis viršijamas darbuotojui '
                                                       '{}').format(employee.name))

                for worked_outside_day in rec.e_document_time_line_ids:
                    wod_date = worked_outside_day.date
                    wod_employee_appointment = employee_appointments.filtered(
                        lambda appointment: appointment.date_start <= wod_date and
                                            (not appointment.date_end or appointment.date_end >= wod_date)
                    )
                    if not wod_employee_appointment:
                        raise exceptions.ValidationError(_('{} datai nustatytai darbo dienai, darbuotojas {} neturi '
                                                           'aktyvios darbo sutarties').format(wod_date, employee.name))
                    if not wod_employee_appointment.schedule_template_id.is_work_day(wod_date):
                        raise exceptions.ValidationError(_('{} nėra darbuotojo {} darbo diena.').format(
                            wod_date, employee.name
                        ))

EDocument()


class EDocumentTimeLine(models.Model):
    _inherit = 'e.document.time.line'

    @api.model
    def create(self, values):
        if 'e_document_id' in values:
            doc_id = values.get('e_document_id')
            if doc_id:
                doc = self.env['e.document'].browse(doc_id)
                template = self.env.ref(TEMPLATE_EXT_REF, False)
                if template and doc.template_id == template:
                    # Allow no times to be entered
                    if 'time_from' not in values:
                        values['time_from'] = 0.0
                    if 'time_to' not in values:
                        values['time_to'] = 0.0
        return super(EDocumentTimeLine, self).create(values)


EDocumentTimeLine()