# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, exceptions, fields, models, tools
from odoo.tools.translate import _
from .darbuotojai import get_last_work_day, get_vdu
from ..report.suvestine import ALL_PAYROLL_CODES as ALLOWED_INPUT_LINE_CODES


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def npd_value_selection(self):
        npd_values = self.env['payroll.parameter.history'].sudo().search([
            ('field_name', '=', 'npd_max'),
            ('date_from', '<', '2022-01-01')
        ])
        npd_list = [('auto', 'Nustatyti automatiškai')]
        for npd_value in npd_values:
            date_from = npd_value.date_from
            name = _('Nuo {0} - įprastai {1}').format(date_from, npd_value.value)
            npd_list.append((str(npd_value.date_from), name))

        npd_values_depending_on_avg_wage = self.env['payroll.parameter.history'].sudo().search([
            ('field_name', 'in', ['under_avg_wage_npd_max', 'above_avg_wage_npd_max']),
            ('date_from', '>=', '2022-01-01')
        ]).sorted(key=lambda v: v.date_from)
        for date in set(npd_values_depending_on_avg_wage.mapped('date_from')):
            date_npd_vals = npd_values_depending_on_avg_wage.filtered(lambda v: v.date_from == date)
            name = _('From {}').format(date)
            under_avg_wage_npd_max = date_npd_vals.filtered(lambda v: v.field_name == 'under_avg_wage_npd_max')
            above_avg_wage_npd_max = date_npd_vals.filtered(lambda v: v.field_name == 'above_avg_wage_npd_max')
            if not above_avg_wage_npd_max:
                # Use last above avg npd max field.
                above_avg_wage_npd_max_fields = npd_values_depending_on_avg_wage.filtered(
                    lambda v: v.field_name == 'above_avg_wage_npd_max' and v.date_from <= date
                ).sorted(key=lambda v: v.date_from, reverse=True)
                above_avg_wage_npd_max = above_avg_wage_npd_max_fields and above_avg_wage_npd_max_fields[0]
            if under_avg_wage_npd_max or above_avg_wage_npd_max:
                name += ' - '
                if under_avg_wage_npd_max:
                    name += _('{} below').format(under_avg_wage_npd_max.value)
                    if above_avg_wage_npd_max:
                        name += _(' and ')
                if above_avg_wage_npd_max:
                    name += _('{} above').format(above_avg_wage_npd_max.value)
                name += _(' the average monthly wage')
            npd_list.append((str(date), name))
        return npd_list

    def _date(self):
        if self.date_to:
            return self.date_to

    vdu_record_table = fields.Html(compute='_compute_vdu_records_and_info', string='VDU Įrašai')
    vdu_calculation_table = fields.Html(compute='_compute_vdu_records_and_info', string='VDU Paskaičiavimai')
    payroll_id = fields.Many2one('hr.payroll', compute='_compute_payroll_id')
    employee_is_being_laid_off = fields.Boolean(compute='_compute_employee_is_being_laid_off', store=True)
    npd_used = fields.Selection(npd_value_selection, default='auto', string='Taikomas NPD', required=True, states={'done': [('readonly', True)]})
    warn_about_include_current_month = fields.Boolean(compute='_compute_warn_about_include_current_month')
    warn_about_possible_incorrect_calculations = fields.Boolean(compute='_compute_warn_about_possible_incorrect_calculations')
    warn_about_possible_parenthood_holidays_npd_issue = fields.Boolean(compute='_compute_warn_about_possible_parenthood_holidays_npd_issue')
    date = fields.Date(default=_date)
    show_not_all_benefits_in_kind_on_payslip_warning = fields.Boolean(
        compute='_compute_show_not_all_benefits_in_kind_on_payslip_warning'
    )
    show_benefit_in_kind_employer_pays_taxes_warning = fields.Boolean()
    employer_benefit_in_kind_tax_move = fields.Many2one('account.move', readonly=True)
    holiday_balance_by_accumulation_records = fields.Float(
        string='Nepanaudotų atostogų likutis pagal etatų skirtumus periodo pabaigai',
        compute='_compute_holiday_balance_by_accumulation_records',
        store=True
    )
    show_different_appointment_values_business_trip_warning = fields.Boolean(
        compute='_compute_show_different_appointment_values_business_trip_warning'
    )

    @api.multi
    @api.depends('date_to', 'employee_id')
    def _compute_holiday_balance_by_accumulation_records(self):
        for rec in self:
            if rec.holiday_accumulation_usage_policy and rec.employee_id and rec.date_to and not rec.imported:
                contract = rec.contract_id
                date_to = rec.date_to
                if contract.work_relation_end_date:
                    date_to = min(date_to, contract.work_relation_end_date)

                accumulation_records = self.env['hr.employee.holiday.accumulation'].sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('date_from', '>=', contract.work_relation_start_date),
                    ('date_from', '<=', date_to)
                ], order='date_from desc')

                balance = 0.0
                for accumulation_record in accumulation_records:
                    record_balance = accumulation_record.get_balance_before_date(date_to)
                    if accumulation_record.accumulation_type == 'calendar_days':
                        appointment = accumulation_record.appointment_id
                        num_week_work_days = appointment.schedule_template_id.num_week_work_days if appointment else 5.0
                        record_balance = record_balance * num_week_work_days / 7.0  # P3:DivOK
                    balance += record_balance

                # Add days the employee will accumulate after last accumulation
                # Find out the date the holiday balance has been calculated to
                today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                last_accumulation_record = accumulation_records and accumulation_records[0]
                if last_accumulation_record:
                    date_calculated_up_to = last_accumulation_record.date_to or today
                else:
                    date_calculated_up_to = None
                if date_calculated_up_to and date_calculated_up_to < date_to:
                    # Find all appointments the holiday balance should still be calculated for
                    date_calculated_up_to_dt = datetime.strptime(date_calculated_up_to,
                                                                 tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_to_calculate_from_dt = date_calculated_up_to_dt + relativedelta(days=1)
                    date_to_calculate_from = date_to_calculate_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    balance += contract.get_leaves_accumulated_at_a_later_date(date_to_calculate_from, date_to)

                rec.holiday_balance_by_accumulation_records = balance
            else:
                rec.holiday_balance_by_accumulation_records = 0.0

    @api.multi
    @api.depends('input_line_ids.code', 'input_line_ids.amount')
    def _compute_show_not_all_benefits_in_kind_on_payslip_warning(self):
        for rec in self:
            payslip_benefit_in_kind_lines = rec.input_line_ids.filtered(lambda l: l.code in ['NTR', 'NTRD'])
            payslip_benefit_in_kind_amount = sum(payslip_benefit_in_kind_lines.mapped('amount'))
            benefit_in_kind_records = self.env['hr.employee.natura'].sudo().search([
                ('state', '=', 'confirm'),
                ('employee_id', '=', rec.employee_id.id),
                ('date_from', '=', rec.date_from),
                ('date_to', '=', rec.date_to)
            ])
            benefit_in_kind_record_amount = sum(benefit_in_kind_records.mapped('amount'))
            payslip_amount_less_than_record_amount = tools.float_compare(
                payslip_benefit_in_kind_amount,
                benefit_in_kind_record_amount,
                precision_digits=2
            ) < 0
            rec.show_not_all_benefits_in_kind_on_payslip_warning = payslip_amount_less_than_record_amount

    @api.multi
    @api.depends('input_line_ids.code', 'input_line_ids.amount')
    def _compute_show_different_appointment_values_business_trip_warning(self):
        ContractAppointment = self.env['hr.contract.appointment'].sudo()
        for rec in self:
            different_appointment_values = False
            if any(x.code == 'NAKM' for x in rec.input_line_ids):
                appointments = ContractAppointment.search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('date_start', '<=', rec.date_to),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', rec.date_from)
                ])
                # If employee has appointments with different wage and salary structure information, show the warning
                if len(set([(a.struct_id.code, a.wage) for a in appointments])) > 1:
                    different_appointment_values = True
            rec.show_different_appointment_values_business_trip_warning = different_appointment_values

    @api.onchange('date_to', 'employee_id')
    def change_date(self):
        self.date = self.date_to

    @api.model
    def export_payslips_xls(self):
        ctx = self._context.copy()
        payslips_to_export = self
        if not payslips_to_export:
            raise exceptions.UserError(_("Nėra algalapių, kuriuos būtų galima eksportuoti."))
        ctx.update({'payslip_ids': payslips_to_export.mapped('id')})

        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.payslip.export',
            'view_id': self.env.ref('l10n_lt_payroll.hr_payslip_export_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.model
    def payslip_export_xls_action(self):
        action = self.env.ref('l10n_lt_payroll.server_action_payslip_xls_export')
        if action:
            action.create_action()

    @api.model
    def create_payslip_confirm_action(self):
        action = self.env.ref('l10n_lt_payroll.server_action_payslip_confirm')
        if action:
            action.create_action()

    @api.multi
    def _compute_payroll_id(self):
        date_ranges = [(rec.date_from, rec.date_to) for rec in self]
        date_ranges = list(set(date_ranges))

        from_dates = [date_range[0] for date_range in date_ranges]
        to_dates = [date_range[1] for date_range in date_ranges]
        min_from = min(from_dates)
        max_from = max(to_dates)

        all_payrolls = self.env['hr.payroll'].search([
            ('date_from', '<=', max_from),
            ('date_to', '>=', min_from)
        ])
        for date_range in date_ranges:
            range_from = date_range[0]
            range_to = date_range[1]
            date_range_slips = self.filtered(lambda s: s.date_from == range_from and s.date_to == range_to)
            date_range_payroll_id = all_payrolls.filtered(lambda p: p.date_from == range_from and p.date_to == range_to)
            if not date_range_payroll_id:
                date_range_payroll_id = self.env['hr.payroll'].create({'date_from': range_from, 'date_to': range_to})
            for slip in date_range_slips:
                slip.payroll_id = date_range_payroll_id

    @api.one
    @api.depends('contract_id.date_end')
    def _compute_warn_about_include_current_month(self):
        if self.contract_id.date_end:
            ends_on_current_month = datetime.strptime(self.contract_id.date_end,
                                                      tools.DEFAULT_SERVER_DATE_FORMAT).month == \
                                    datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT).month
            self.warn_about_include_current_month = self.contract_id.ends_on_the_last_work_day_of_month and \
                                                    self.contract_id.ends_the_work_relation and ends_on_current_month

    @api.multi
    @api.depends('worked_days_line_ids.appointment_id', 'worked_days_line_ids.number_of_hours',
                 'worked_days_line_ids.number_of_days', 'date_from', 'date_to', 'line_ids.amount')
    def _compute_warn_about_possible_incorrect_calculations(self):
        for rec in self:
            warn = False
            appointment_id = rec.worked_days_line_ids.mapped('appointment_id').sorted(key='date_start', reverse=True)
            if appointment_id:
                appointment_id = appointment_id[0]

                illness_amount = sum(rec.line_ids.filtered(lambda l: l.code in ['L']).mapped('amount'))
                bruto = sum(rec.line_ids.filtered(lambda l: l.code in ['BRUTON']).mapped('amount')) - illness_amount

                # Determine NPD date
                npd_values = rec.get_npd_values()
                npd_date = npd_values['npd_date']

                payroll_values = self.env['hr.payroll'].get_payroll_values(
                    date=rec.date_to,
                    bruto=bruto,
                    force_npd=None if appointment_id.use_npd else 0.0,
                    voluntary_pension=appointment_id.sodra_papildomai and appointment_id.sodra_papildomai_type,
                    disability=appointment_id.darbingumas.name if appointment_id.invalidumas else False,
                    illness_amount=illness_amount,
                    npd_date=npd_date,
                    is_foreign_resident=appointment_id.employee_id.is_non_resident,
                    is_fixed_term=appointment_id.contract_id.is_fixed_term,
                )
                total_neto = payroll_values.get('neto', 0.0)
                payslip_neto_adjusted = sum(rec.line_ids.filtered(lambda l: l.code in ['BENDM', 'ISSK', 'AVN']).mapped('amount'))
                warn = tools.float_compare(abs(total_neto - payslip_neto_adjusted), 0.01, precision_digits=3) > 0
            rec.warn_about_possible_incorrect_calculations = warn

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id')
    def _compute_warn_about_possible_parenthood_holidays_npd_issue(self):
        parenthood_holiday_status_code = self.env.ref('hr_holidays.holiday_status_TA')
        for rec in self:
            if not rec.date_from:
                rec.warn_about_possible_parenthood_holidays_npd_issue = False
                continue
            date_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            month_start = (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            month_end = (date_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            problematic_parenthood_holidays_exist = self.env['hr.holidays'].search_count([
                ('state', '=', 'validate'),
                ('type', '=', 'remove'),
                ('employee_id', '=', rec.employee_id.id),
                ('holiday_status_id', '=', parenthood_holiday_status_code.id),
                '|',
                '&',
                ('date_from_date_format', '<=', month_end),
                ('date_from_date_format', '>', month_start),
                '&',
                ('date_to_date_format', '<', month_end),
                ('date_to_date_format', '>=', month_start),
            ])
            rec.warn_about_possible_parenthood_holidays_npd_issue = problematic_parenthood_holidays_exist

    @api.one
    def include_this_month_in_vdu_calculations(self):
        include_last = False
        if self.ismoketi_kompensacija:
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            month_end = (date_to_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            month_last_work_day = get_last_work_day(self, month_end)
            last_app = next_app = appointments_past_to = False
            appointments_up_to = self.contract_id.appointment_ids.filtered(
                lambda r: r['date_end'] and r['date_end'] <= self.date_to). \
                sorted(lambda r: r['date_end'], reverse=True)
            if appointments_up_to:
                last_app = appointments_up_to[0]
                appointments_past_to = self.contract_id.appointment_ids.filtered(
                    lambda r: r['date_start'] >= last_app.date_end).sorted(lambda r: r['date_start'])
            if appointments_past_to:
                next_app = appointments_past_to[0]
                last_app_end_date = datetime.strptime(last_app.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                next_app_start_date = datetime.strptime(next_app.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            if last_app and month_last_work_day <= last_app.date_end <= month_end:
                if not next_app or (next_app_start_date != (
                        last_app_end_date + relativedelta(days=+1)) and next_app_start_date != last_app_end_date):
                    include_last = True
        return include_last

    @api.one
    def _compute_vdu_records_and_info(self):
        if not (self.date_from and self.date_to and self.employee_id):
            return

        related_contracts = self.contract_id.get_contracts_related_to_work_relation()
        employee_vdu_count = self.env['employee.vdu'].search_count([
            ('employee_id', '=', self.employee_id.id),
            ('date_from', '<', self.date_from),
            '|',
            ('contract_id', 'in', related_contracts.ids),
            ('contract_id', '=', False)
        ])
        include_last = self.ismoketi_kompensacija and self.warn_about_include_current_month and \
                       employee_vdu_count < 3

        daily_vdu_values = get_vdu(self.env, self.date_from, self.employee_id, contract_id=self.contract_id.id,
                                   include_last=include_last, vdu_type='d')
        hourly_vdu_values = get_vdu(self.env, self.date_from, self.employee_id, contract_id=self.contract_id.id,
                                    include_last=include_last, vdu_type='h')

        TABLE = '''
        <table width=100%>
            <tr>
                <th colspan="1"></th>
                <th colspan="1">{}</th>
                <th colspan="1">{}</th>
                <th colspan="1">{}</th>
            </tr>'''.format(
            _('Priskaitytas DU'),
            _('Dirbtų dienų sk.'),
            _('Dirbtų valandų sk.'),
        )

        TABLE_ROW = \
            '''<tr>
                   <th colspan="1">{}</th>
                   <td colspan="1">{}</td>
                   <td colspan="1">{}</td>
                   <td colspan="1">{}</td>
               </tr>'''

        vdu_values = daily_vdu_values.get('salary_info', {}) or hourly_vdu_values.get('salary_info', {})
        vdu_rec_values = vdu_values.get('vdu_record_data', {})

        total_amount = sum(rec[1].get('amount', 0.0) for rec in vdu_rec_values.items())
        long_term_bonus_amount = vdu_values.get('long_term_bonus_amount', 0.0)
        quarterly_bonus_amount = vdu_values.get('quarterly_bonus_amount', 0.0)
        total_amount += quarterly_bonus_amount
        total_amount += long_term_bonus_amount
        total_days = sum(rec[1].get('days', 0.0) for rec in vdu_rec_values.items())
        total_hours = sum(rec[1].get('hours', 0.0) for rec in vdu_rec_values.items())

        for date in sorted(vdu_rec_values.keys(), reverse=True):
            TABLE += TABLE_ROW.format(
                date,
                round(vdu_rec_values[date].get('amount', 0.0), 3),
                round(vdu_rec_values[date].get('days', 0.0), 2),
                round(vdu_rec_values[date].get('hours', 0.0), 2)
            )

        TABLE += TABLE_ROW.format(_('Ketvirtinės premijos'), round(quarterly_bonus_amount, 3), '-', '-')
        TABLE += TABLE_ROW.format(_('Ilgesnės premijos laikotarpiui'), round(long_term_bonus_amount, 3), '-', '-')
        TABLE += TABLE_ROW.format(_('Viso'), round(total_amount, 2), round(total_days, 2), round(total_hours, 2))
        TABLE += '</table>'

        self.vdu_record_table = TABLE

        TABLE = '''
                <table width=100%>
                    <tr>
                        <th colspan="1"></th>
                        <th colspan="1">Dieninis VDU</th>
                        <th colspan="1">Valandinis VDU</th>
                        <th colspan="1">VDU_D pritraukimas iki MMA</th>
                        <th colspan="1">VDU_H pritraukimas iki MMA</th>
                    </tr>'''

        TABLE_ROW = \
            '''<tr>
                   <th colspan="1">{}</th>
                   <td colspan="1">{}</td>
                   <td colspan="1">{}</td>
                   <td colspan="1">{}</td>
                   <td colspan="1">{}</td>
               </tr>'''

        daily_minimum_wage_adjustment = daily_vdu_values.get('minimum_wage_adjustment', {})
        hourly_minimum_wage_adjustment = hourly_vdu_values.get('minimum_wage_adjustment', {})

        daily_vdu_calculation_values = daily_vdu_values.get('calculation_info', {})
        hourly_vdu_calculation_values = hourly_vdu_values.get('calculation_info', {})

        TABLE += TABLE_ROW.format(
            _('Formulė'),
            daily_vdu_calculation_values.get('formula', '-'),
            hourly_vdu_calculation_values.get('formula', '-'),
            daily_minimum_wage_adjustment.get('formula', _('Nepritraukiama')),
            hourly_minimum_wage_adjustment.get('formula', _('Nepritraukiama'))
        )
        TABLE += TABLE_ROW.format(
            _('Priežastis'),
            daily_vdu_calculation_values.get('reason', '-'),
            hourly_vdu_calculation_values.get('reason', '-'),
            _('Mažiau už dienos MA') if daily_minimum_wage_adjustment else '-',
            _('Mažiau už valandos MA') if hourly_minimum_wage_adjustment else '-',
        )
        TABLE += TABLE_ROW.format(
            _('Paskaičiavimas'),
            daily_vdu_calculation_values.get('formula_with_real_values', '-'),
            hourly_vdu_calculation_values.get('formula_with_real_values', '-'),
            daily_minimum_wage_adjustment.get('formula_with_real_values', '-'),
            hourly_minimum_wage_adjustment.get('formula_with_real_values', '-'),
        )
        day_amnt = daily_vdu_values.get('calculation_info', {}).get('amount')
        day_amnt = tools.float_round(day_amnt, precision_digits=2) if day_amnt else '-'

        hour_amnt = hourly_vdu_values.get('calculation_info', {}).get('amount')
        hour_amnt = tools.float_round(hour_amnt, precision_digits=2) if hour_amnt else '-'

        day_mma = daily_vdu_values.get('vdu') if daily_minimum_wage_adjustment else False
        day_mma = tools.float_round(day_mma, precision_digits=2) if day_mma else '-'

        hour_mma = hourly_vdu_values.get('vdu') if hourly_minimum_wage_adjustment else False
        hour_mma = tools.float_round(hour_mma, precision_digits=2) if hour_mma else '-'
        TABLE += TABLE_ROW.format(_('Suma'), day_amnt, hour_amnt, day_mma, hour_mma)
        TABLE += '</table>'
        self.vdu_calculation_table = TABLE

    @api.one
    @api.depends('contract_id', 'contract_id.date_end', 'date_from', 'date_to')
    def _compute_employee_is_being_laid_off(self):
        is_last = False
        if self.contract_id and self.contract_id.date_end:
            contract_date_end = self.contract_id.date_end
            if self.date_from <= contract_date_end <= self.date_to:
                contract_date_end_dt = datetime.strptime(contract_date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                next_work_day_after = self.env['hr.payroll'].get_next_work_day(contract_date_end_dt)
                if not next_work_day_after:
                    next_work_day_after = (contract_date_end_dt+relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                next_contract = self.env['hr.contract'].search_count([
                    ('employee_id', '=', self.employee_id.id),
                    ('date_start', '<=', next_work_day_after),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', next_work_day_after)
                ])
                if not next_contract:
                    is_last = True
        self.employee_is_being_laid_off = is_last

    @api.multi
    @api.constrains('input_line_ids')
    def _check_input_line_ids_should_exist(self):
        if self.env.user.id != SUPERUSER_ID:
            input_codes = self.mapped('input_line_ids.code')
            bad_codes = [code for code in input_codes if code not in ALLOWED_INPUT_LINE_CODES]
            holiday_codes = ['A', 'AM']  # Should modify through holiday records
            other_forbidden_codes = holiday_codes
            bad_codes += [code for code in input_codes if code in other_forbidden_codes]
            if bad_codes:
                # Some codes are not used in reports & this check prevents wrong code inputs
                msg = _('Priskaitymų su {} kodais įvestis neleidžiama, koreguokite įvestį eilučių, '
                                             'iš kurių susisedada jūsų pageidaujamo kodo '
                                             'taisyklė.').format(', '.join(bad_codes))
                if any(holiday_code in bad_codes for holiday_code in holiday_codes):
                    msg += _(' Norėdami keisti atostoginių sumas - tai darykite neatvykimo įraše.')
                raise exceptions.UserError(msg)

    @api.multi
    def get_accumulated_holidays_data(self, date):
        """
        Get the data to create accounting entries for accumulated holiday reserves
        :param date: date at which to compute the entries
        :return: dictionary with keys 'date' and 'data'
        """
        res = self.mapped('employee_id').get_holidays_reserve_data(date)
        return res

    @api.multi
    def create_accumulated_holidays_reserve_entry(self, date):
        """
        Create accounting entry for accumulated holidays obligations
        :param date: date at which calculate the amounts, as str
        :return: created 'account.move' record
        """
        all_amounts_data = self.get_accumulated_holidays_data(date)
        move = self.env['hr.employee'].create_accumulated_holidays_reserve_entry(all_amounts_data)
        return move

    @api.multi
    def get_overtime_lines_compensated_by_holidays(self):
        return self.env['hr.employee.overtime.time.line'].search([
            ('overtime_id.employee_id', 'in', self.mapped('employee_id').ids),
            ('date', '<=', max(self.mapped('date_to'))),
            ('date', '>=', min(self.mapped('date_from'))),
            ('overtime_id.state', '=', 'confirmed'),
            ('overtime_id.overtime_compensation', '=', 'holidays')
        ])

    @api.multi
    def _create_holiday_compensation_records(self):
        overtime_lines_compensated_in_holidays = self.get_overtime_lines_compensated_by_holidays()
        for payslip in self:
            contract = payslip.contract_id
            if payslip.state != 'done' or not contract:
                continue

            payslip_overtime_lines_compensated_in_holidays = overtime_lines_compensated_in_holidays.filtered(
                lambda l: l.overtime_id.employee_id == payslip.employee_id and
                          payslip.date_from <= l.date <= payslip.date_to
            )
            if not payslip_overtime_lines_compensated_in_holidays:
                continue

            overtime_line_durations = [
                l.get_duration_by_time_of_day() for l in payslip_overtime_lines_compensated_in_holidays
            ]
            overtime_during_daytime = sum(duration.get('day', 0.0) for duration in overtime_line_durations)
            overtime_during_night_time = sum(duration.get('night', 0.0) for duration in overtime_line_durations)

            vd_coefficient = contract.company_id.vd_coefficient
            vdn_coefficient = contract.company_id.vdn_coefficient

            adjusted_daytime_compensation_duration = overtime_during_daytime * vd_coefficient
            adjusted_night_time_compensation_duration = overtime_during_night_time * vdn_coefficient

            total_overtime_holiday_compensation_duration = adjusted_daytime_compensation_duration + \
                                                           adjusted_night_time_compensation_duration

            if not tools.float_is_zero(total_overtime_holiday_compensation_duration, precision_digits=2):
                date = max(payslip_overtime_lines_compensated_in_holidays.mapped('date'))
                appointment = payslip.contract_id.with_context(date=date).appointment_id
                if not appointment:
                    continue
                schedule_template = appointment.schedule_template_id
                post = schedule_template.etatas
                work_norm = schedule_template.work_norm
                # P3:DivOK
                duration_in_days = total_overtime_holiday_compensation_duration / 8.0 * post * work_norm
                holiday_compensation = self.env['hr.employee.holiday.compensation'].create({
                    'employee_id': payslip.employee_id.id,
                    'date': payslip.date_to,
                    'record_id': payslip.id,
                    'record_model': 'hr.payslip',  # TODO hr.employee.overtime record would be better
                    'number_of_days': duration_in_days
                })
                holiday_compensation.action_confirm()

    @api.multi
    def _remove_holiday_compensation_records(self):
        holiday_compensation_records = self.env['hr.employee.holiday.compensation'].search([
            ('record_model', '=', 'hr.payslip'),
            ('record_id', 'in', self.ids),
            ('state', '=', 'confirmed')
        ])
        holiday_compensation_records.action_draft()
        holiday_compensation_records.unlink()

    @api.multi
    def atsaukti(self):
        res = super(HrPayslip, self).atsaukti()
        self._remove_holiday_compensation_records()
        return res

    @api.multi
    def calculate_and_add_deductions_with_limited_amount(self):
        self.ensure_one()
        deductions = self.env['hr.employee.isskaitos'].search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'confirm'),
            ('limit_deduction_amount', '=', True)
        ]).filtered(lambda rec: rec.can_be_limited)
        if not deductions:
            return False

        # Remove existing deduction move line reconciliation since it's created at the end of this method. Only applies
        # for deductions with limited deduction amounts
        deduction_move_lines = deductions.mapped('move_id.line_ids')
        deduction_move_lines.remove_move_reconcile()
        moves = deductions.mapped('move_id').exists()
        moves.button_cancel()
        moves.unlink()

        total_limited_deduction_amount = sum(deductions.mapped('amount'))

        # NET amount = amount from GROSS, stuff already deducted and and stuff paid in advance
        lines = self.line_ids
        already_deducted = sum(lines.filtered(lambda r: r.code in ['IŠSK']).mapped('total'))
        paid_in_advance = sum(lines.filtered(lambda r: r.code in ['AVN']).mapped('total'))
        current_payable = sum(lines.filtered(lambda r: r.code in ['BENDM']).mapped('total'))

        # If the advance is more than what should be left after deductions - then the advance should be lowered.
        total_amount_neto = current_payable + paid_in_advance + already_deducted

        # Should not deduct from specific compensations
        other_addition = sum(self.line_ids.filtered(lambda r: r.code in ['KKPD']).mapped('total'))
        # In this case KKPD is a dynamic workplace compensation that's in the M rule (used in BENDM rule). This
        # compensation is not taxed. Should not be deducted from.

        total_amount_neto -= other_addition
        total_amount_neto = max(total_amount_neto, 0.0)

        # Get MAX deduction percentages
        percentage_over = 50
        percentage_under = 20

        # Get NET amount from current GROSS minimum wage
        net_minimum_wage = self.get_neto_mma()

        # Calculate how much can be deducted from under the minimum wage
        under_mma_amount_to_calc_from = min(total_amount_neto, net_minimum_wage)
        under_mma_amount_deductible = under_mma_amount_to_calc_from * percentage_under / 100.0  # P3:DivOK

        # Calculate how much can be deducted from over the minimum wage
        over_mma_amount_deductible = 0.0
        if tools.float_compare(net_minimum_wage, total_amount_neto, precision_digits=2) < 0:
            over_mma_amount = total_amount_neto - net_minimum_wage
            over_mma_amount_deductible = over_mma_amount * percentage_over / 100.0  # P3:DivOK

        # Get the max deductible amount
        max_deductible_amount = under_mma_amount_deductible + over_mma_amount_deductible
        max_deductible_amount = tools.float_round(max_deductible_amount, precision_digits=2)

        # Compare with the required deductible amount and the maximum that is going to be paid for this payslip
        amount_to_deduct = min(total_limited_deduction_amount, max_deductible_amount, current_payable + paid_in_advance)

        # Get the deduction line to update
        deduction_lines = self.input_line_ids.filtered(lambda line: line.code == 'ISSK')
        deduction_line = deduction_lines and deduction_lines[0]
        if deduction_line:
            # Do not add duplicate amounts because when payslip sheet is recomputed, the ISSK line
            # that was previously created, remains
            if tools.float_compare(deduction_line.amount, amount_to_deduct, precision_digits=2):
                deduction_line.write({'amount': deduction_line.amount + amount_to_deduct})
        else:
            self.env['hr.payslip.input'].create({
                'name': _('Išskaitos'),
                'code': 'ISSK',
                'contract_id': self.contract_id.id,
                'amount': amount_to_deduct,
                'payslip_id': self.id
            })

        for deduction in deductions:
            # Create moves for each deduction based on proportion of deductible amount and the actual amount that's
            # going to be deducted
            try:
                proportion_of_total_amount = deduction.amount / total_limited_deduction_amount
            except ZeroDivisionError:
                proportion_of_total_amount = 0.0
            limited_amount_deducted_for_deduction = proportion_of_total_amount * amount_to_deduct
            if tools.float_compare(limited_amount_deducted_for_deduction, 0.0, precision_digits=2) > 0:
                deduction.create_move_entry(limited_amount_deducted_for_deduction)

        return True

    @api.multi
    def create_holiday_fix(self):
        self._create_holiday_compensation_records()
        return super(HrPayslip, self).create_holiday_fix()

    @api.multi
    def payslip_data_is_accessible(self):
        """
        Method intended to be overridden
        :return: Indicator if payslip data is accessible for user
        """
        self.ensure_one()
        is_accessible = self.env.user.is_hr_manager() \
                        or self.env.user.is_manager() or self.employee_id.user_id.id == self._uid
        return is_accessible


HrPayslip()
