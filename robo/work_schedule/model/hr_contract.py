# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import _, api, models, tools


class HrContract(models.Model):
    _inherit = 'hr.contract'

    @api.model
    def cron_warn_about_leaving_employees_schedule_submission(self):
        date_now = datetime.now()
        date_tomorrow = date_now + relativedelta(days=1)
        tomorrow = date_tomorrow.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        extended_schedule = self.env.user.company_id.with_context(date=tomorrow).extended_schedule
        if not extended_schedule:
            return
        ending_contracts = self.env['hr.contract'].search([('date_end', '=', tomorrow)])
        if not ending_contracts:
            return

        actually_ending_contracts = self.env['hr.contract']
        for contract in ending_contracts:
            contract_end = contract.date_end
            contract_end_date = datetime.strptime(contract_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            following_day = (contract_end_date + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            following_contract = contract.employee_id.contract_ids.filtered(lambda c: c.date_start == following_day)
            if not following_contract:
                actually_ending_contracts |= contract

        if not actually_ending_contracts:
            return

        employee_ids = actually_ending_contracts.mapped('employee_id').ids
        factual_schedule_id = self.env.ref('work_schedule.factual_company_schedule').id
        schedule_lines = self.env['work.schedule.line']
        date = datetime.strptime(actually_ending_contracts[0].date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
        for employee_id in employee_ids:
            schedule_lines |= self.env['work.schedule.line'].search([
                ('employee_id', '=', employee_id),
                ('state', 'not in', ['confirmed', 'done']),
                ('year', '=', date.year),
                ('month', '=', date.month),
                ('work_schedule_id', '=', factual_schedule_id),
            ])
        employees_not_submitted = schedule_lines.mapped('employee_id')

        departments_of_not_submitted_employees = employees_not_submitted.mapped('department_id').ids
        data_for_emails = {}
        for department in departments_of_not_submitted_employees:
            data_for_emails[department] = {}
            data_for_emails[department]['addressees'] = self.env['hr.employee'].search([
                ('confirm_department_ids', 'in', department),
            ]).mapped('work_email')
            data_for_emails[department]['employees_not_submitted'] = employees_not_submitted.filtered(
                lambda e: e.department_id.id == department
            ).mapped('name_related')

        subject = _('Išeinančio darbuotojo darbo grafiko pateikimas')
        body_base = _('''
        Reikia pateikti darbuotojų, su kuriais baigiasi darbo santykiai, darbo grafiką, 
        prieš darbo sutarties nutraukimą. Darbuotojai:<br>
                     ''')
        for department in data_for_emails:
            employees_of_department = '' + ';<br>'.join(data_for_emails[department]['employees_not_submitted'])
            body = body_base + employees_of_department
            self.env['script'].send_email(
                emails_to=data_for_emails[department]['addressees'],
                subject=subject,
                body=body,
            )
        body_base += ';<br>'.join(employees_not_submitted.mapped('name_related'))
        msg = {
            'body': body_base,
            'subject': subject,
            'message_type': 'comment',
            'subtype': 'mail.mt_comment',
        }
        mail_channel = self.env.ref('work_schedule.warn_about_leaving_employees_schedule_submission_mail_channel',
                                    raise_if_not_found=False)
        mail_channel.sudo().message_post(**msg)

    @api.one
    def end_contract(self, date_end, **kw):
        res = super(HrContract, self).end_contract(date_end, **kw)
        days = self.env['work.schedule.day'].search([
            ('date', '>', self.date_end),
            ('employee_id', '=', self.employee_id.id)
        ])
        contracts = self.search([
            ('employee_id', '=', self.employee_id.id),
            ('date_start', '>=', self.date_end)
        ])
        unlink_ids = []
        for day in days:
            contract_for_day = contracts.filtered(
                lambda c: c.date_start <= day.date and (not c.date_end or c.date_end >= day.date))
            if not contract_for_day:
                unlink_ids += day.mapped('line_ids.id')
        self.env['work.schedule.day.line'].browse(unlink_ids).with_context(allow_delete_special=True).unlink()
        return res

HrContract()
