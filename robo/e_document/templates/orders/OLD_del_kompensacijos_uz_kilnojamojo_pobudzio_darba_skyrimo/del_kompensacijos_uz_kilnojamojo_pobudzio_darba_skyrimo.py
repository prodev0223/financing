# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, exceptions, _, SUPERUSER_ID


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_workflow(self):
        """
        Creates Hr.Employee.Compensation records for each document line/employee and confirms said records
        """
        self.ensure_one()
        lines = self.e_document_line_ids
        HrEmployeeCompensation = self.env['hr.employee.compensation']
        compensations = HrEmployeeCompensation
        for line in lines:
            compensations |= HrEmployeeCompensation.create({
                'employee_id': line.employee_id2.id,
                'date_from': self.date_1,
                'date_to': self.date_2,
                'payslip_year_id': self.payslip_year_id.id,
                'payslip_month': self.payslip_month,
                'amount': line.float_1,
                'compensation_type': 'dynamic_workplace',
                'related_document': self.id
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
        template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
                                raise_if_not_found=False)

        if original_document and original_document.sudo().template_id == template:
            tests_enabled = tools.config.get('test_enable')
            lines = original_document.e_document_line_ids
            new_cr = self.pool.cursor() if not tests_enabled else self._cr  # Use existing cursor if tests are running
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})
            set_failed_workflow = False
            try:
                if original_document.record_model == 'hr.employee.bonus':
                    date_from_dt = datetime.strptime(original_document.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    HrEmployeeBonus = env['hr.employee.bonus']
                    bonuses = HrEmployeeBonus.search([
                        ('employee_id', 'in', lines.mapped('employee_id2').ids),
                        ('for_date_from', '=', original_document.date_1),
                        ('for_date_to', '=', original_document.date_2),
                        ('payment_date_from', '=', date_from),
                        ('payment_date_to', '=', date_to),
                        ('bonus_type', '=', '1men'),
                        ('amount_type', '=', 'bruto'),
                        ('taxation_type', '=', 'taxable_over_half_of_salary')
                    ])
                    bonuses_to_unlink = HrEmployeeBonus
                    for line in lines:
                        line_bonus = bonuses.filtered(lambda b: b.employee_id.id == line.employee_id2.id and
                                                                not tools.float_compare(b.amount, line.float_1,
                                                                                        precision_digits=2))
                        if not line_bonus:
                            set_failed_workflow = True
                        else:
                            try:
                                line_bonus.action_cancel()
                                bonuses_to_unlink |= line_bonus
                                if not tests_enabled:
                                    new_cr.commit()
                            except:
                                if not tests_enabled:
                                    new_cr.rollback()
                                set_failed_workflow = True
                    bonuses_to_unlink.unlink()
                else:
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
                    #TODO: maybe create a ticket for it when needed?
                    self.write({'failed_workflow': set_failed_workflow})
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.multi
    @api.depends('e_document_line_ids', 'bonus_input_type')
    def _compute_text_1(self):
        res = super(EDocument, self)._compute_text_1()
        template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
                                False)
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
        template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
                                raise_if_not_found=False)
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
        template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
                                raise_if_not_found=False)
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
        template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
                                raise_if_not_found=False)
        for rec in self.filtered(lambda r: r.template_id == template):
            date_3_dt = datetime(rec.payslip_year_id.code, int(rec.payslip_month), 1)
            rec.date_3 = date_3_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return super(EDocument, self).execute_confirm_workflow_update_values()

    # @api.multi
    # @api.onchange('date_3')
    # def _onchange_date_3(self):
    #     template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
    #                             raise_if_not_found=False)
    #     for rec in self.filtered(lambda r: r.template_id == template and r.date_3):
    #         date_3_dt = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
    #         first_of_month = (date_3_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    #         if rec.date_3 != first_of_month:
    #             rec.date_3 = first_of_month
    #     try:
    #         return super(EDocument, self)._onchange_date_3()
    #     except:
    #         pass

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.isakymas_del_kompensacijos_uz_kilnojamojo_pobudzio_darba_skyrimo_template',
                                False)
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


EDocument()
