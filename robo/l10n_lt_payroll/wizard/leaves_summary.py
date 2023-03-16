# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, api, fields, tools, exceptions
from odoo.tools.translate import _
from collections import OrderedDict
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo.tools.misc import formatLang


class HrLeavesReportWizard(models.TransientModel):
    _name = 'hr.leaves.report.wizard'

    def default_date_to(self):
        return datetime.now() + relativedelta(months=-1, day=31)

    date_from = fields.Date(string='Data nuo')
    date_to = fields.Date(string='Likučio data', required=True, default=default_date_to)
    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai')
    holiday_status_ids = fields.Many2many('hr.holidays.status', string='Atostogų tipai')

    @api.multi
    def get_all_leaves(self, date_from, date_to, employee_ids, holiday_status_ids):
        employee_ids = self.env['hr.employee'].browse(employee_ids).sorted(lambda r: r.tabelio_numeris)
        res = OrderedDict()
        for employee_id in employee_ids:
            leaves_accumulation_type = employee_id.sudo().with_context(date=date_to).leaves_accumulation_type
            if date_from:
                data_dict = employee_id.with_context(leaves_summary_status_ids=holiday_status_ids,
                                                     leaves_summary_from_force=date_from,
                                                     leaves_summary_spec=True)._get_remaining_days(
                    date=date_to, accumulation_type=leaves_accumulation_type)
            else:
                data_dict = employee_id.with_context(leaves_summary_status_ids=holiday_status_ids,
                                                     leaves_summary_spec=True)._get_remaining_days(
                    date=date_to, accumulation_type=leaves_accumulation_type)

            holidays = data_dict.get('holidays')
            end_hols = data_dict.get('intersecting_end')
            start_hols = data_dict.get('intersecting_start')
            holidays += end_hols + start_hols
            res[employee_id.id] = {
                'holidays': holidays,
                'used_work_days': data_dict.get('used_work_days'),
                'used_calendar_days': data_dict.get('used_calendar_days'),
            }
        return res

    @api.multi
    def get_data_for_report(self, date_from, date_to, employee_ids, holiday_status_ids):
        def _strf(date):
            try:
                return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                return date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        def _strp(date):
            try:
                return datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            except:
                return datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)

        def likutis_at_date(employee, date, date_from=False):
            empl_accumulation_type = employee.with_context(date=date).leaves_accumulation_type
            likutis = employee._get_remaining_days(date=date,
                                                       accumulation_type=empl_accumulation_type,
                                                       from_date=date_from)
            return round(likutis, 3)

        contract_ids = self.env['hr.contract']
        if not employee_ids:
            contract_domain = [('date_start', '<=', date_to)]
            if date_from:
                contract_domain.extend(['|', ('date_end', '=', False), ('date_end', '>=', date_from)])
            contract_ids = self.env['hr.contract'].with_context(active_test=False).search(contract_domain)
            employee_ids = contract_ids.mapped('employee_id')
        else:
            employee_ids = self.env['hr.employee'].browse(employee_ids)
        if not holiday_status_ids:
            leave_type_codes = ['A', 'NA', 'KR']  # todo ar tik tokie?
            holiday_status_ids = self.env['hr.holidays.status'].with_context(active_test=False).search([('kodas', 'in', leave_type_codes)]).ids

        if employee_ids and not contract_ids:
            contract_ids = self.env['hr.contract'].search([('employee_id', 'in', employee_ids.mapped('id'))])

        res = []

        date_to_dt = _strf(_strp(date_to) + relativedelta(days=1))
        date_from_forced = date_from
        if not date_from:
            if contract_ids:
                date_from = min(contract_ids.mapped('date_start'))
            else:
                return res
        date_from_dt = _strf(_strp(date_from))

        all_holidays = self.env['hr.holidays'].search([
            ('date_from', '<', date_to_dt),
            ('date_to', '>=', date_from_dt),
            ('employee_id', 'in', employee_ids.mapped('id')),
            ('holiday_status_id', 'in', holiday_status_ids),
            ('state', '=', 'validate'),
        ])

        for employee_id in employee_ids:
            employee_contracts = contract_ids.filtered(lambda c: c.employee_id.id == employee_id.id)
            empl_date_start = date_from_forced
            if not empl_date_start:
                if date_from_forced:
                    contract_for_date = employee_contracts.filtered(lambda c: c.date_start <= date_from_forced and (not c.date_end or c.date_end >= date_from_forced))
                    if contract_for_date:
                        empl_date_start = date_from_forced
                if not empl_date_start:
                    periods = [(c.date_start, c.date_end if c.date_end else date_to) for c in employee_contracts]
                    periods.sort(key=lambda p: p[0], reverse=True)
                    periods_len = len(periods)

                    for i in range(0, periods_len):
                        curr_period = periods[i]
                        try:
                            next_period = periods[i+1]
                        except:
                            next_period = False

                        prev_date = _strf(_strp(curr_period[0]) - relativedelta(days=1))
                        if next_period and next_period[1] == prev_date:
                            continue
                        else:
                            empl_date_start = curr_period[0]
                            break
                    if not empl_date_start:
                        empl_date_start = date_from_forced  # I don't think this will ever happen, but need to check

            employee_holidays = all_holidays.filtered(lambda h: h.employee_id.id == employee_id.id and h.date_from_date_format <= date_to and (h.date_to_date_format >= empl_date_start or not h.date_to_date_format))

            holiday_events = []

            for holiday in employee_holidays:
                holiday_start = holiday.date_from_date_format
                holiday_end = holiday.date_to_date_format

                used_work_days = abs(holiday.darbo_dienos) if holiday.leaves_accumulation_type == 'work_days' else 0.0
                used_calendar_days = abs(holiday.number_of_days)

                if not (holiday_start >= empl_date_start and holiday_end <= date_to):
                    used_work_days, used_calendar_days = 0.0, 0.0
                    adjusted_start = max(holiday_start, empl_date_start)
                    adjusted_end = min(holiday_end, date_to)

                    national_holidays = self.env['sistema.iseigines'].search([
                        ('date', '<=', adjusted_end),
                        ('date', '>=', adjusted_start)
                    ])

                    num_national_holiday_days = 0.0
                    # Calendar days
                    for national_holiday in national_holidays:
                        appointment = holiday.contract_id.with_context(date=national_holiday.date).appointment_id
                        is_work_day = appointment.schedule_template_id.with_context(calculating_holidays=True).is_work_day(national_holiday.date)
                        if not is_work_day:
                            num_national_holiday_days += 1
                    used_calendar_days = ((_strp(adjusted_end)+relativedelta(days=1)) - _strp(adjusted_start)).days - \
                                         num_national_holiday_days

                    # Work days
                    if holiday.leaves_accumulation_type == 'work_days':
                        c_date = _strp(adjusted_start)
                        while c_date <= _strp(adjusted_end):
                            c_date_strf = _strf(c_date)
                            appointment = holiday.contract_id.with_context(date=c_date_strf).appointment_id
                            is_work_day = appointment.schedule_template_id.is_work_day(c_date_strf)
                            if is_work_day:
                                used_work_days += 1
                            c_date += relativedelta(days=1)

                    holiday_start = adjusted_start
                    holiday_end = adjusted_end

                holiday_events.append({
                    'start': holiday_start,
                    'end': holiday_end,
                    'work_days_used': used_work_days,
                    'calendar_days_used': used_calendar_days,
                    'holiday_status_id': holiday.holiday_status_id.id
                })

            try:
                empl_tabelio_numeris = int(employee_id.tabelio_numeris)
            except:
                empl_tabelio_numeris = employee_id.tabelio_numeris

            start_balance = likutis_at_date(employee_id, empl_date_start)
            # Show the balance at the start of the day rather than at the end of it
            appointment = employee_id.with_context(date=empl_date_start).appointment_id
            if appointment:
                accumulation_per_day = appointment._leaves_accumulated_per_day()

                is_accumulating_holidays = appointment.contract_id.is_accumulating_holidays(empl_date_start)
                if not is_accumulating_holidays or (
                        appointment.leaves_accumulation_type == 'work_days' and
                        not appointment.schedule_template_id.is_work_day(empl_date_start)
                ):
                    # So that no days are deducted. Balance is going to be at the end of the day before.
                    accumulation_per_day = 0.0
                start_balance -= accumulation_per_day
                # Deducting the same amount of days as the start balance yields negative 0 (0.795... - 0.795... = -0.0)
                if tools.float_is_zero(start_balance, precision_digits=3):
                    start_balance = abs(start_balance)
                start_balance = tools.float_round(start_balance, precision_digits=3)

            res.append({
                'employee_id': employee_id.id,
                'tabelio_numeris': empl_tabelio_numeris,
                'start_balance': start_balance,
                'calc_from': empl_date_start,
                'end_balance': likutis_at_date(employee_id, date_to),
                'holiday_events': holiday_events
            })

        return res

    @api.multi
    def export(self):
        self.ensure_one()
        data = {'wizard_id': self.id}
        return self.env['report'].get_action(self, 'l10n_lt_payroll.report_leaves_summary', data=data)


HrLeavesReportWizard()


class HrLeavesReportWizardSipmlified(models.TransientModel):
    _name = 'hr.leaves.report.wizard.employee'

    def default_employee_id(self):
        if self._context.get('active_id'):
            return self._context['active_id']
        if self.env.user.employee_ids:
            return self.env.user.employee_ids[0]

    def default_date_to(self):
        return datetime.now() + relativedelta(months=-1, day=31)

    employee_id = fields.Many2one('hr.employee', required=True, default=default_employee_id)
    date_from = fields.Date(string='Data nuo')
    date_to = fields.Date(string='Likučio data', required=True, default=default_date_to)
    type = fields.Selection([('main', 'Kasmetinės atostogos'), ('all', 'Visos atostogos')],
                            string='Eksportuojamos atostogos', required=True, default='main')
    all_employees = fields.Boolean(string='Eksportuoti visus darbuotojus')
    only_active_employees = fields.Boolean(string='Tik aktyvūs darbuotojai')

    @api.multi
    def export(self):
        wizard_vals = {'date_from': self.date_from,
                       'date_to': self.date_to}
        if not self.all_employees:
            wizard_vals['employee_ids'] = [(4, self.employee_id.id)]
        else:
            contract_ids = self.env['hr.contract'].search([('date_start', '<=', self.date_to), '|',
                                                           ('date_end', '=', False), ('date_end', '>=', self.date_to)])
            employee_ids = contract_ids.mapped('employee_id').filtered(lambda e: e.user_id.active) if self.only_active_employees \
                else contract_ids.mapped('employee_id')

            if not employee_ids:
                raise exceptions.UserError(_("Nėra darbuotojų, kuriuos būtų galima įtraukti į suvestinę"))

            wizard_vals['employee_ids'] = [(4, e.id) for e in employee_ids]
        if self.type == 'main':
            main_leaves_type = self.env.ref('hr_holidays.holiday_status_cl')
            wizard_vals['holiday_status_ids'] = [(4, main_leaves_type.id)]
        wizard = self.env['hr.leaves.report.wizard'].with_context(active_test=False).create(wizard_vals)
        return wizard.export()


HrLeavesReportWizardSipmlified()


class Atostogusuvestine(models.AbstractModel):

    _name = 'report.l10n_lt_payroll.report_leaves_summary'

    @api.multi
    def render_html(self, doc_ids, data=None):
        if data is not None:
            wizard_id = self.env['hr.leaves.report.wizard'].browse(data['wizard_id'])
            main_leaves_type = self.env.ref('hr_holidays.holiday_status_cl')
            date = wizard_id.date_to
            if self.env.user.is_manager():
                wizard_id = wizard_id.sudo()
            elif self.env.user.is_hr_manager():
                wizard_id = wizard_id.sudo()
            elif len(wizard_id.employee_ids) == 1 and wizard_id.employee_ids.user_id == self.env.user:
                wizard_id = wizard_id.sudo()
            if not wizard_id.holiday_status_ids or main_leaves_type.id in wizard_id.holiday_status_ids.ids:
                show_leaves_left = True
            else:
                show_leaves_left = False
            leaves_data = wizard_id.get_data_for_report(wizard_id.date_from, wizard_id.date_to, wizard_id.employee_ids.ids,
                                                        wizard_id.holiday_status_ids.ids)
            leaves_data.sort(key=lambda d: d['tabelio_numeris'])
            rows = []
            for employee_data in leaves_data:
                employee_id = employee_data.get('employee_id', False)
                if not employee_id:
                    continue

                employee = self.env['hr.employee'].browse(employee_id)
                appointment = employee.contract_id.with_context(date=date).appointment_id
                avg_hours_per_day = appointment.sudo().schedule_template_id.avg_hours_per_day if appointment else 8.0
                extra_hol_days_trips = 0

                business_trip_employee_line_ids = self.env['e.document.business.trip.employee.line'].sudo().search([('journey_compensation', '=', 'holidays'),
                                                                                                             ('employee_id', '=', employee_id),
                                                                                                             ('e_document_id.state', '=', 'e_signed'),
                                                                                                             ('e_document_id.date_to', '<=', date)])
                for employee_line in business_trip_employee_line_ids:
                    if not employee_line.journey_has_to_be_compensated:
                        continue
                    time_to_compensate = employee_line.journey_amount_to_be_compensated
                    extra_hol_days_trips += time_to_compensate / float(avg_hours_per_day)  # P3:DivOK

                min_leave_days, extra_hol_days_experience = employee.sudo().get_employee_leaves_num(date=date)

                leaves_accumulation_type = employee.with_context(date=date).leaves_accumulation_type
                date_start = employee_data.get('calc_from', False)
                leaves_accumulation_type_start = employee.with_context(date=date_start).leaves_accumulation_type if date_start else leaves_accumulation_type
                hol_lines = []
                holidays = employee_data['holiday_events']
                hol_work_days_used, hol_calendar_days_used = 0, 0
                for holiday in sorted(holidays, key=lambda r: r['start']):
                    num_work_days = abs(holiday['work_days_used'])
                    num_calendar_days = abs(holiday['calendar_days_used'])
                    hol_row = {'date_from': holiday['start'],
                               'date_to': holiday['end'],
                               'num_work_days': num_work_days,
                               'num_calendar_days': num_calendar_days}
                    hol_lines.append(hol_row)
                    if holiday['holiday_status_id'] == main_leaves_type.id:
                        hol_work_days_used += num_work_days
                        hol_calendar_days_used += num_calendar_days
                hol_days_left = employee_data.get('end_balance', 0.0)
                hol_days_left_start = employee_data.get('start_balance', 0.0)
                row_data = {'tabelio_numeris': employee.tabelio_numeris,
                            'employee_name': employee.name,
                            'date_from': date_start,
                            'hol_lines': hol_lines,
                            'hol_work_days_used': hol_work_days_used,
                            'hol_calendar_days_used': hol_calendar_days_used,
                            'hol_days_left': hol_days_left,
                            'hol_days_left_start': hol_days_left_start,
                            'leaves_accumulation_type_start': leaves_accumulation_type_start,
                            'leaves_accumulation_type': leaves_accumulation_type,
                            'extra_hol_days_experience': extra_hol_days_experience,
                            'extra_hol_days_trips': extra_hol_days_trips, }
                rows.append(row_data)
            docargs = {
                'date': date,
                'rows': rows,
                'show_leaves_left': show_leaves_left,
                'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            }

            return self.env['report'].render('l10n_lt_payroll.template_leaves_summary_document', docargs)


Atostogusuvestine()
