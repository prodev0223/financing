# coding=utf-8
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import tools, models, fields, api, _
from .payroll_codes import PAYROLL_CODES

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    any_appointment_schedule_type_sumine_apskaita = fields.Boolean(
        compute='_compute_any_appointment_schedule_type_sumine_apskaita')
    sumine_apskaita_period_table = fields.Html(string='Suminės apskaitos priskaičiavimai', compute='_compute_sumine_periods_table')

    @api.one
    @api.depends('contract_id', 'date_from', 'date_to')
    def _compute_any_appointment_schedule_type_sumine_apskaita(self):
        is_sumine_apskaita = False
        if self.contract_id and self.date_from and self.date_to:
            sumine_appointments = self.env['hr.contract.appointment'].search([
                ('contract_id', '=', self.contract_id.id),
                ('schedule_template_id.template_type', '=', 'sumine'),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from),
            ])
            if sumine_appointments:
                is_sumine_apskaita = True
        self.any_appointment_schedule_type_sumine_apskaita = is_sumine_apskaita

    @api.multi
    def get_payslip_sumine_appointment_data(self, extra_worked_day_data=None):
        self.ensure_one()
        data = {
            'payslip_id': self.id,
            'appointment_data': [],
        }
        worked_time_codes = PAYROLL_CODES['WATCH_HOME'] + PAYROLL_CODES['WATCH_WORK'] + PAYROLL_CODES['EXTRA'] + PAYROLL_CODES['OVERTIME'] + PAYROLL_CODES['REGULAR'] + PAYROLL_CODES['OUT_OF_OFFICE'] + PAYROLL_CODES['UNPAID_OUT_OF_OFFICE']
        sumine_appointments = self.contract_id.mapped('appointment_ids').filtered(lambda a: a.schedule_template_id.template_type == 'sumine' and a.date_start <= self.date_to and (not a.date_end or a.date_end >= self.date_from))
        worked_time = work_norm = vdl_hours_accounted_for = ndl_hours_accounted_for = 0.0
        for appointment in sumine_appointments.sorted(key='date_start'):
            appointment_work_norm = self.env['hr.employee'].employee_work_norm(calc_date_from=self.date_from, calc_date_to=self.date_to, appointment=appointment, skip_leaves=True)['hours']
            appointment_work_lines = self.worked_days_line_ids.filtered(lambda l: l.appointment_id.id == appointment.id)
            if not appointment_work_lines and extra_worked_day_data:
                appointment_work_lines = [ext_data for ext_data in extra_worked_day_data if ext_data.get('appointment_id') == appointment.id]
            appointment_worked_time = sum(l['number_of_hours'] for l in appointment_work_lines if l['code'] in worked_time_codes)
            shorter_before_holidays = 0.0
            for l in appointment_work_lines:
                if 'compensated_time_before_holidays' not in l or not l['compensated_time_before_holidays']:
                    continue
                shorter_before_holidays += l['number_of_hours']
            appointment_worked_time -= shorter_before_holidays
            appointment_vdl_time = sum(l['number_of_hours'] for l in appointment_work_lines if l['code'] == 'VDL')
            appointment_ndl_time = sum(l['number_of_hours'] for l in appointment_work_lines if l['code'] == 'NDL')
            work_norm += appointment_work_norm
            worked_time += appointment_worked_time
            vdl_hours_accounted_for += appointment_vdl_time
            ndl_hours_accounted_for += appointment_ndl_time
            data['appointment_data'].append({
                'appointment_id': appointment.id,
                'appointment_structure': appointment.struct_id.name,
                'work_norm': round(appointment_work_norm, 3),
                'worked_time': round(appointment_worked_time, 3)
            })

        vdl_hours_to_account_for = max(0.0, worked_time - work_norm)
        ndl_hours_to_account_for = max(0.0, work_norm - worked_time)

        data.update({
            'worked_time': round(worked_time, 3),
            'work_norm': round(work_norm, 3),
            'vdl_hours_accounted_for': round(vdl_hours_accounted_for, 3),
            'ndl_hours_accounted_for': round(ndl_hours_accounted_for, 3),
            'vdl_hours_to_account_for': round(vdl_hours_to_account_for, 3),
            'ndl_hours_to_account_for': round(ndl_hours_to_account_for, 3),
        })
        return data

    @api.model
    def payslips_to_calculate_sumine_for(self, date_from, date_to, contract_id):
        CONTRACT_OBJ = self.env['hr.contract']
        contract = CONTRACT_OBJ.browse(contract_id)
        payslips = self.env['hr.payslip']
        should_payout = False
        company = self.env.user.company_id
        sumine_apskaita_period_start = company.sumine_apskaita_period_start
        if sumine_apskaita_period_start > date_from:
            return {
                'payslips': payslips,
                'should_payout': should_payout
            }
        sumine_apskaita_period_amount = company.sumine_apskaita_period_amount
        calc_from = datetime.strptime(sumine_apskaita_period_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        payslip_date_from_strp = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        months_between = relativedelta(payslip_date_from_strp, calc_from).months
        months_before = months_between % sumine_apskaita_period_amount
        calc_from_dt = payslip_date_from_strp - relativedelta(months=months_before)
        calc_to_dt_adjusted = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)+relativedelta(days=1)
        next_contract = False
        contracts_ids_to_include = []
        all_employee_earlier_contracts = CONTRACT_OBJ.search([('employee_id', '=', contract.employee_id.id), ('date_start', '<=', date_to)])
        contract_start_dates = all_employee_earlier_contracts.mapped('date_start')
        contract_start_dates.sort(reverse=True)
        for contract_start_date in contract_start_dates:
            contract_with_start_date = all_employee_earlier_contracts.filtered(lambda c: c.date_start == contract_start_date)
            contracts_ids_to_include.append(contract_with_start_date.id)
            prev_date = (datetime.strptime(contract_start_date, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            contract_end_for_prev_date = all_employee_earlier_contracts.filtered(lambda c: c.date_end == prev_date)
            if not contract_end_for_prev_date:
                break

        if contract.date_end:
            next_contract_date_start = (datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            next_contract = self.env['hr.contract'].search([
                ('employee_id', '=', contract.employee_id.id),
                ('date_start', '=', next_contract_date_start)
            ])
        contract_ends_this_period = contract.date_end and date_to >= contract.date_end >= date_from
        is_payout_month = relativedelta(calc_to_dt_adjusted, calc_from_dt).months == sumine_apskaita_period_amount
        should_payout = is_payout_month or (contract_ends_this_period and not next_contract)
        calc_from = calc_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        calc_to = date_to
        payslips = self.env['hr.payslip'].search([
            ('date_from', '<=', calc_to),
            ('date_to', '>=', calc_from),
            ('contract_id', 'in', contracts_ids_to_include)
        ])
        return {
            'payslips': payslips,
            'should_payout': should_payout
        }

    @api.one
    @api.depends('date_from', 'date_to', 'contract_id')
    def _compute_sumine_periods_table(self):
        TABLE_BODY = '''<table class='sumine_table'>%s</table>'''
        TABLE_HEADER = _('''
        <tr>
            <th>Algalapis</th>
            <th>Priedas</th>
            <th>Darbo norma (val.)</th>
            <th>Priskaičiuota (val.)</th>
            <th>Išmokėta NDL (val.)</th>
            <th>Išmokėta VDL (val.)</th>
            <th>Priskaičiuota NDL (val.)</th>
            <th>Priskaičiuota VDL (val.)</th>
        <tr>''')
        PAYSLIP_LINE = '''
        <tr class='period-header'>
            <td>%s</td>
            <td></td>
            <td>%s</td>
            <td>%s</td>
            <td>%s</td>
            <td>%s</td>
            <td>%s</td>
            <td>%s</td>
        </tr>'''
        PAYSLIP_APPOINTMENT_LINE = '''
        <tr class='payslip-header'>
            <td></td>
            <td><a href="%s" target="_blank">%s</a></td>
            <td>%s</td>
            <td>%s</td>
            <td></td>
            <td></td>
            <td></td>
            <td></td>
        </tr>'''
        TABLE_MAIN = ''
        month_mapping = {
            1: _('Sausis'),
            2: _('Vasaris'),
            3: _('Kovas'),
            4: _('Balandis'),
            5: _('Gegužė'),
            6: _('Birželis'),
            7: _('Liepa'),
            8: _('Rugpjūtis'),
            9: _('Rugsėjis'),
            10: _('Spalis'),
            11: _('Lapkritis'),
            12: _('Gruodis')
        }
        payslips_for_period = self.payslips_to_calculate_sumine_for(self.date_from, self.date_to, self.contract_id.id)['payslips']
        total_work_norm = total_worked_time = total_ndl_hours_accounted_for = total_vdl_hours_accounted_for = 0.0
        for payslip in payslips_for_period.sorted(key='date_from', reverse=True):
            payslip_date_from = datetime.strptime(payslip.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            payslip_name = month_mapping[payslip_date_from.month] + ' ' + str(payslip_date_from.year)
            payslip_sumine_data = payslip.get_payslip_sumine_appointment_data()
            payslip_work_norm = payslip_sumine_data['work_norm']
            payslip_worked_time = payslip_sumine_data['worked_time']
            payslip_ndl_hours_accounted_for = payslip_sumine_data['ndl_hours_accounted_for']
            payslip_vdl_hours_accounted_for = payslip_sumine_data['vdl_hours_accounted_for']
            payslip_ndl_hours_to_account_for = payslip_sumine_data['ndl_hours_to_account_for']
            payslip_vdl_hours_to_account_for = payslip_sumine_data['vdl_hours_to_account_for']
            total_work_norm += payslip_work_norm
            total_worked_time += payslip_worked_time
            total_ndl_hours_accounted_for += payslip_ndl_hours_accounted_for
            total_vdl_hours_accounted_for += payslip_vdl_hours_accounted_for
            payslip_table_data = PAYSLIP_LINE % (
                payslip_name,
                payslip_work_norm,
                payslip_worked_time,
                payslip_ndl_hours_accounted_for,
                payslip_vdl_hours_accounted_for,
                payslip_ndl_hours_to_account_for,
                payslip_vdl_hours_to_account_for,
            )
            payslip_sumine_appointment_data = payslip_sumine_data.get('appointment_data', [])
            for sumine_appointment in payslip_sumine_appointment_data:
                payslip_table_data += PAYSLIP_APPOINTMENT_LINE % (
                    'web#id=%s&model=hr.contract.appointment' % sumine_appointment['appointment_id'],
                    self.env['hr.contract.appointment'].browse(sumine_appointment['appointment_id']).display_name,
                    sumine_appointment.get('work_norm', 0.0),
                    sumine_appointment.get('worked_time', 0.0),
                )
            TABLE_MAIN += payslip_table_data
        total_vdl_hours_to_account_for = max(0.0, total_worked_time - total_work_norm)
        total_ndl_hours_to_account_for = max(0.0, total_work_norm - total_worked_time)
        totals_table_row = PAYSLIP_LINE % (
            'VISO',
            total_work_norm,
            total_worked_time,
            total_ndl_hours_accounted_for,
            total_vdl_hours_accounted_for,
            total_ndl_hours_to_account_for,
            total_vdl_hours_to_account_for,
        )
        self.sumine_apskaita_period_table = str(TABLE_BODY % (TABLE_HEADER+totals_table_row+TABLE_MAIN))

    @api.multi
    def onchange_employee_id(self, date_from, date_to, employee_id=False, contract_id=False):
        res = super(HrPayslip, self).onchange_employee_id(date_from, date_to, employee_id=employee_id, contract_id=contract_id)
        if not contract_id:
            if employee_id:
                extra_domain = [('employee_id', '=', employee_id)]
            else:
                extra_domain = []
            domain = extra_domain + [
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', date_from)
            ]
            contract_ids = self.env['hr.contract'].search(domain).mapped('id')
        else:
            contract_ids = [contract_id]

        ndl_zymejimas = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_NDL')
        vdl_zymejimas = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VDL')
        for contract in contract_ids:
            data = self.payslips_to_calculate_sumine_for(date_from, date_to, contract)
            if not data['should_payout']:
                continue
            latest_appointment = self.env['hr.contract.appointment'].search([
                ('contract_id', '=', contract),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', date_from)
            ]).sorted(key='date_start', reverse=True)
            if latest_appointment:
                latest_appointment = latest_appointment[0]
            else:
                latest_appointment = self.env['hr.contract'].browse(contract).with_context(date=date_from).appointment_id
            total_work_norm = 0.0
            total_worked_time = 0.0
            total_ndl_hours_accounted_for = 0.0
            total_vdl_hours_accounted_for = 0.0
            for payslip in data['payslips']:
                extra_worked_day_data = []
                if payslip.date_from == date_from and payslip.date_to == date_to:
                    extra_worked_day_data = res.get('value', {}).get('worked_days_line_ids', [])
                payslip_sumine_data = payslip.get_payslip_sumine_appointment_data(extra_worked_day_data)
                total_work_norm += payslip_sumine_data['work_norm']
                total_worked_time += payslip_sumine_data['worked_time']
                total_ndl_hours_accounted_for += payslip_sumine_data['ndl_hours_accounted_for'] if (payslip.date_from != date_from and payslip.date_to != date_to) else 0.0
                total_vdl_hours_accounted_for += payslip_sumine_data['vdl_hours_accounted_for'] if (payslip.date_from != date_from and payslip.date_to != date_to) else 0.0
            total_vdl_hours_to_account_for = max(0.0, total_worked_time - total_work_norm - total_vdl_hours_accounted_for)
            total_ndl_hours_to_account_for = max(0.0, total_work_norm - total_worked_time - total_ndl_hours_accounted_for)
            initial_vals = {
                'contract_id': contract,
                'number_of_days': 0.0,
                'sequence': 10,
                'appointment_id': latest_appointment.id,
            }
            if not tools.float_is_zero(total_ndl_hours_to_account_for, precision_digits=2):
                ndl_vals = initial_vals.copy()
                ndl_vals.update({
                    'code': ndl_zymejimas.code,
                    'name': ndl_zymejimas.name,
                    'number_of_hours': total_ndl_hours_to_account_for,
                })
                res['value']['worked_days_line_ids'].append(ndl_vals)
            if not tools.float_is_zero(total_vdl_hours_to_account_for, precision_digits=2):
                vdl_vals = initial_vals.copy()
                vdl_vals.update({
                    'code': vdl_zymejimas.code,
                    'name': vdl_zymejimas.name,
                    'number_of_hours': total_vdl_hours_to_account_for,
                })
                res['value']['worked_days_line_ids'].append(vdl_vals)
        return res

HrPayslip()
