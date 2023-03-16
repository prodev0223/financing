# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import _, exceptions, fields, models, tools
import xlwt
import StringIO

HEADER = ['Eil. Nr.', 'Darbuotojo vardas, pavardė', 'Darbuotojo asmens kodas',
          'Darbuotojo darbo užmokestis, nurodytas darbo sutartyje',
          'Darbuotojo darbo sutartyje nurodyti priedai prie darbo užmokesčio',
          'Darbuotojui paskelbtos prastovos pradžios data',
          'Darbuotojui priskaičiuotas darbo užmokestis, Eur',
          'Iš jų: priskaičiuotas darbo užmokestis už prastovos laiką, Eur',
          'Darbuotojui nustatytas darbo valandų skaičius per mėnesį',
          'Iš jų: darbuotojo prastovos laikas (valandomis) per mėnesį']


class DowntimeReport(models.TransientModel):
    _name = 'downtime.report'

    year = fields.Selection([(2021, '2021'), (2022, '2022'), (2023, '2023'), (2024, '2024')], string='Metai',
                            default=lambda r: datetime.utcnow().year, required=True)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Mėnuo',
                             default=lambda r: datetime.utcnow().month, required=True)

    def generate_report(self):
        state_declared_emergency = self.env.ref('l10n_lt_payroll.quarantine_november_2020', raise_if_not_found=True)
        appointment_date_dt = (datetime.strptime(state_declared_emergency.date_start,
                                                 tools.DEFAULT_SERVER_DATETIME_FORMAT) - relativedelta(days=1))
        fiscalyear_date_from = self.env.user.company_id.compute_fiscalyear_dates(date=appointment_date_dt)['date_from']\
            .strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        appointment_date = appointment_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt = datetime(self.year, self.month, 1)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = date_from_dt + relativedelta(day=31)
        date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        payslip_run = self.env['hr.payslip.run'].search(
            [('date_start', '=', date_from),
             ('date_end', '=', date_to)], limit=1)

        if not payslip_run or payslip_run.state != 'close':
            raise exceptions.UserError(_('Atlyginimai nurodytam periodui dar nepaskaičiuoti.'))

        user = self.env.user
        user_has_access = user.is_manager() or user.is_hr_manager()
        if not user_has_access:
            raise exceptions.AccessError(_('Trūksta teisių pasiekti šią ataskaitą.'))

        downtime_codes = ['PN']
        regular_amount_codes = ['BRUTON']
        data = []
        number = 0
        for slip in payslip_run.slip_ids:
            employee = slip.employee_id
            downtime = self.env['hr.employee.downtime'].search([
                ('date_from_date_format', '<=', date_to),
                ('date_to_date_format', '>=', date_from),
                ('employee_id', '=', employee.id),
                ('holiday_id.state', '=', 'validate')
            ], limit=1)

            if not downtime:
                continue

            downtime_lines = slip.sudo().mapped('worked_days_line_ids').filtered(lambda l: l.code in downtime_codes)
            downtime_hours = sum(downtime_lines.mapped('number_of_hours'))
            downtime_amount = sum(slip.line_ids.filtered(lambda l: l.code in downtime_codes).mapped('total'))

            if not downtime_hours and not downtime_amount:
                continue

            full_hours = slip.ziniarastis_period_line_id.num_regular_work_hours \
                if slip.ziniarastis_period_line_id else 0
            full_amount = sum(slip.line_ids.filtered(lambda l: l.code in regular_amount_codes).mapped('total'))

            number += 1
            appointment = employee.contract_id.with_context(date=appointment_date).appointment_id
            # Not a very specific way to check if bonuses are defined in contract - no other way for now
            if appointment:
                bonus_date_from = appointment.contract_id.date_start \
                    if appointment.contract_id.date_start > fiscalyear_date_from else fiscalyear_date_from
                bonus_date_to = appointment_date
            else:
                appointment = employee.contract_id.with_context(date=date_from).appointment_id
                bonus_date_from = appointment.contract_id.date_start
                bonus_date_to = date_to

            bonus_records = self.env['hr.employee.bonus'].search_count([
                ('employee_id', '=', employee.id),
                ('for_date_to', '<=', bonus_date_to),
                ('for_date_from', '>=', bonus_date_from)
            ])

            bonus_specified = 'Taip' if bonus_records else 'Ne'

            data.append([number, employee.name.upper(), employee.identification_id, appointment.wage, bonus_specified,
                         downtime.date_from_date_format, full_amount, downtime_amount, full_hours, downtime_hours])

        workbook = xlwt.Workbook(encoding='utf-8')
        worksheet = workbook.add_sheet(_('Prastovų suvestinė'))

        header_bold_brd = xlwt.easyxf("font: bold on; borders: left thin, right thin, bottom thin ")
        col = 0
        for val in HEADER:
            worksheet.write(0, col, val, header_bold_brd)
            worksheet.col(col).width = 256 * 20
            col += 1
        for row, line in enumerate(data, 1):
            for col, val in enumerate(line):
                worksheet.write(row, col, val)

        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(1)
        f = StringIO.StringIO()
        workbook.save(f)
        base64_file = f.getvalue().encode('base64')
        file_name = _('Prastovų_suvestinė_' + str(self.year) + '_' + str(self.month) + '.xls')
        attachment = self.env['ir.attachment'].create({
            'res_model': 'downtime.report',
            'res_id': self[0].id,
            'type': 'binary',
            'name': file_name,
            'datas_fname': file_name,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=downtime.report&res_id=%s&attach_id=%s' % (
                self[0].id, attachment.id),
            'target': 'self',
        }
