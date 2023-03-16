# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import models, api, exceptions, tools, _, fields


TEMPLATE = 'e_document.isakymas_del_mokymosi_atostogu_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    holiday_payment = fields.Selection(string='Holiday payment', readonly=True, states={'draft': [('readonly', False)]},
                                       default='paid_half_of_vdu', inverse='set_final_document',
                                       selection=[('paid_at_vdu', 'Paid at VDU'),
                                                  ('paid_half_of_vdu', 'Paid half of VDU'),
                                                  ('other_amount', 'Other amount'),
                                                  ('not_paid', 'Not paid')],
                                       )

    @api.multi
    def isakymas_del_mokymosi_atostogu_workflow(self):
        self.ensure_one()
        hol_id = self.env['hr.holidays'].create({
            'name': 'Mokymosi atostogos',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_MA').id,
            'date_from': self.calc_date_from(self.date_from),
            'date_to': self.calc_date_to(self.date_to),
            'type': 'remove',
            'numeris': self.document_number,
            'is_paid_for': True if self.holiday_payment != 'not_paid' else False,
            'holiday_payment': self.holiday_payment,
            'payment_amount': self.float_2,
        })
        hol_id.action_approve()
        self.inform_about_creation(hol_id)
        self.write({
            'record_model': 'hr.holidays',
            'record_id': hol_id.id,
        })

    @api.multi
    def execute_confirm_workflow_check_values(self):
        super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE)):
            if rec.sudo().skip_constraints_confirm:
                continue
            should_employee_be_compensated = 'true' if rec.employee_should_be_compensated() else 'false'
            if should_employee_be_compensated == 'true' and rec.holiday_payment == 'not_paid':
                raise exceptions.ValidationError(
                    _('The employee has had a continuous work relationship of 5 years or longer, '
                      'therefore he must be compensated for the educational holiday.'))
            if rec.holiday_payment == 'other_amount' and tools.float_compare(rec.float_2, 0.0, precision_digits=2) != 1:
                raise exceptions.ValidationError(_('The amount provided cannot be equal to zero or less than zero'))

    @api.onchange('employee_id2')
    def onchange_employee_id2(self):
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE)):
            rec.selection_bool_1 = 'true' if rec.employee_should_be_compensated() else 'false'

    @api.multi
    def employee_should_be_compensated(self):
        """
        Method to compute if employee is inclined to compensation for educational holiday - if the current work
        relationship is continuous and exactly equal or longer than 5 years;
        :return: Boolean, True if employee should be compensated, False if not;
        """
        def string_to_dt(date_string):
            """
            Convert from date string to datetime object;
            """
            return datetime.strptime(date_string, tools.DEFAULT_SERVER_DATE_FORMAT)
        self.ensure_one()
        if not self.template_id == self.env.ref(TEMPLATE) or not self.employee_id2:
            return False
        res = False
        employee_contracts = self.employee_id2.contract_ids.sorted(key='date_start', reverse=True)
        if not employee_contracts:
            return False
        consecutive_contracts = employee_contracts[0]
        if len(employee_contracts) > 1:
            for employee_contract in employee_contracts[1:]:
                contract_end = string_to_dt(employee_contract.date_end)
                last_consecutive_contract_start = string_to_dt(consecutive_contracts[-1].date_start)
                if not (contract_end + relativedelta(days=1) >= last_consecutive_contract_start):
                    break
                consecutive_contracts |= employee_contract

        if consecutive_contracts[0].date_end:
            continuous_work_relation_end_date = string_to_dt(consecutive_contracts[0].date_end)
        else:
            continuous_work_relation_end_date = datetime.utcnow()

        continuous_work_relation_start_date = string_to_dt(consecutive_contracts[-1].date_start)
        duration_years = relativedelta(continuous_work_relation_end_date, continuous_work_relation_start_date).years

        if duration_years >= 5:
            res = True
        return res


EDocument()
