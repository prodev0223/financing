# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta
from werkzeug import url_encode

from odoo import api, exceptions, models, tools
from odoo.tools.translate import _


class HrHolidays(models.Model):
    _inherit = 'hr.holidays'

    @api.multi
    def sepa_download(self):
        self.ensure_one()
        if self.payment_id:
            aml = self.payment_id.account_move_ids.mapped('line_ids')
            if self.ismokejimas == 'before_hand' and self.env.user.company_id.form_gpm_line_with_holiday_payout and \
                    not self.gpm_paid:
                aml = aml.with_context(form_gpm_payments_for_holidays=self.mapped('id'))
            if self._context.get('sepa', False):
                return aml.call_multiple_invoice_export_wizard()
            else:
                return aml.with_context(allow_download=False).call_multiple_invoice_export_wizard()
        else:
            raise exceptions.Warning(_('Pageidaujama operacija negali būti įvykdyta, nerastas išmokėjimo išrašas!'))

    @api.multi
    def update_ziniarastis(self, date_from=None, date_to=None):
        self.ensure_one()
        if not date_from:
            date_from = self.date_from[:10]
        if not date_to:
            date_to = self.date_to[:10]
        res = super(HrHolidays, self).update_ziniarastis(date_from, date_to)
        domain = [('employee_id', '=', self.employee_id.id)]
        if self.contract_id:
            domain.append(('contract_id', '=', self.contract_id.id))
        domain += [('date', '>=', date_from), ('date', '<=', date_to), ('state', '=', 'done')]
        done_days = self.env['ziniarastis.day'].search(domain)
        if done_days and self.state == 'validate':
            # Filter to only those days that do not have the holiday code so that the warning is only sent if any
            # of the days differ
            done_days = done_days.filtered(
                lambda d: len(d.ziniarastis_day_lines) != 1 or
                          d.ziniarastis_day_lines.code != self.holiday_status_id.tabelio_zymejimas_id.code
            )
        if done_days:
            body = (_("Patvirtinant/atšaukiant darbuotojo %s <a href='/mail/view?%s'>neatvykimą</a> nebuvo atnaujintas "
                      "jau patvirtintas žiniaraštis.") % (
                        self.employee_id.name, url_encode({'model': 'hr.holidays', 'res_id': self.id})))
            self.message_follower_ids.unlink()
            self.sudo().robo_message_post(subtype='mt_comment', body=body,
                                          partner_ids=self.company_id.findir.partner_id.ids, priority='high')
        return res

    @api.model
    def get_employee_default_holiday_amount(self, job_id=False, schedule_template=False, employee_dob=False,
                                            invalidumas=False):
        """
        :param job_id: Employee job id
        :param schedule_template: Employee schedule template
        :param employee_dob: Employee date of birth
        :param invalidumas: Is Employee disabled
        :return: Number of paid holiday work day leaves should be given
        """
        if job_id and isinstance(job_id, int):
            job_id = self.env['hr.job'].browse(job_id)
        if schedule_template and isinstance(schedule_template, int):
            schedule_template = self.env['schedule.template'].browse(schedule_template)
        # Num leaves based on schedule cases:
        # [5_day_week(work days), 6_day_week(work_days), flexible_schedule(calendar days)]
        # Source: https://www.e-tar.lt/portal/lt/legalAct/76731a705b4711e79198ffdb108a3753/ShJVPYkmQi
        type_holiday_mapping = {
            'underage': [25, 30, 5 * 7],
            'disabled': [25, 30, 5 * 7],
            'regular': [20, 24, 4 * 7],
            'teachers_and_psychologists': [40, 48, 8 * 7],
            'lecturers_and_study_related': [40, 48, 8 * 7],
            'art_ppl': [30, 36, 6 * 7],
            'nurses': [26, 31, 5 * 7 + 1],
            'medical_emergency_service_workers': [27, 32, 5 * 7 + 2],
            'surgeons': [28, 33, 5 * 7 + 3],
            'forced_medical_help_workers': [28, 33, 5 * 7 + 3],
            'psychologists_in_special_cases': [30, 36, 6 * 7],
            'pharmacy_workers': [25, 30, 5 * 7],
            'social_workers': [25, 30, 5 * 7],
            'airplane_pilot_and_navigation_instructors': [41, 50, 8 * 7],
            'pilots_and_navigators': [41, 50, 8 * 7],
            'pilots_testers': [41, 50, 8 * 7],
            'lithuanian_air_space_regular_employees': [35, 41, 7 * 7],
            'lithuanian_air_space_senior_employees': [35, 41, 7 * 7],
            'seamen': [25, 30, 5 * 7],
            'fishermen': [25, 30, 5 * 7],
            'biohazard_scientists': [25, 30, 5 * 7],
            'environment_scientists': [25, 30, 5 * 7],
        }

        if not schedule_template:
            case = 0
        elif not schedule_template.fixed_attendance_ids or schedule_template.template_type not in ['fixed',
                                                                                                   'suskaidytos']:
            case = 2
        else:
            num_work_days_week = len(set(schedule_template.fixed_attendance_ids.mapped('dayofweek')))
            if num_work_days_week == 5:
                case = 0
            elif num_work_days_week == 6:
                case = 1
            else:
                case = 2

        is_disabled = invalidumas
        is_underage = False
        if employee_dob:
            employee_age = relativedelta(datetime.utcnow(),
                                         datetime.strptime(employee_dob, tools.DEFAULT_SERVER_DATE_FORMAT)).years
            is_underage = employee_age < 18

        possible_holiday_amounts = []
        if is_disabled:
            possible_holiday_amounts.append(type_holiday_mapping['disabled'][case])
        if is_underage:
            possible_holiday_amounts.append(type_holiday_mapping['underage'][case])

        job_type = job_id.special_job_type if job_id and job_id.special_job_type else 'regular'
        amounts_based_on_job = type_holiday_mapping.get(job_type, type_holiday_mapping['regular'])
        possible_holiday_amounts.append(amounts_based_on_job[case])

        max_possible_amount_work_days = max(possible_holiday_amounts)
        if case == 2:
            # P3:DivOK
            max_possible_amount_work_days = max_possible_amount_work_days * 5.0 / 7.0

        # Company might decide to have more holiday days than required (e.g. 25 instead of the min - 20)
        additional_base_holiday_count = float(
            self.env['ir.config_parameter'].get_param('additional_base_holiday_count', 0)
        )
        max_possible_amount_work_days += additional_base_holiday_count

        return max_possible_amount_work_days
