# -*- coding: utf-8 -*-


from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class PayslipsReportWizard(models.TransientModel):
    _name = 'payslips.report.wizard'

    year = fields.Selection([(2013, '2013'), (2014, '2014'), (2015, '2015'), (2016, '2016'), (2017, '2017'),
                             (2018, '2018'), (2019, '2019'), (2020, '2020'), (2021, '2021'), (2022, '2022'),
                             (2023, '2023'), (2024, '2024')], string='Metai',
                            default=lambda r: datetime.utcnow().year,
                            required=True)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Mėnuo', required=True,
                             default=lambda r: datetime.utcnow().month)
    all_employees = fields.Boolean(string="Rodyti visus darbuotojus", default=True)
    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai')
    department_id = fields.Many2one('hr.department', string='Padalinys')
    report_template = fields.Selection([
        ('payslip_run', 'Atlyginimų suvestinė'),
        ('payslip_run_by_department', 'Atlyginimų suvestinė pagal skyrių'),
        ('payslip_run_by_department_and_employees', 'Atlyginimų suvestinė pagal skyrių ir darbuotojus'),
    ], default='payslip_run', string='Ataskaitos tipas')
    force_lang = fields.Selection([('lt_LT', 'Lietuvių kalba'),
                                   ('en_US', 'Anglų kalba')], string='Priverstinė ataskaitos kalba')

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        return super(PayslipsReportWizard, self.with_context(active_test=False)).read(fields=fields, load=load)

    @api.multi
    def open_report(self):
        date_from_dt = datetime(self.year, self.month, 1)
        date_to_dt = date_from_dt + relativedelta(day=31)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            payslip_run_obj = self.sudo().env['hr.payslip.run']
        else:
            payslip_run_obj = self.env['hr.payslip.run']
        paysliprun_id = payslip_run_obj.search(
            [('date_start', '=', date_from),
             ('date_end', '=', date_to)], limit=1)
        if paysliprun_id and paysliprun_id.state == 'close':
            ctx = {
                'active_id': paysliprun_id.id,
                'active_ids': paysliprun_id.ids,
                'active_model': 'hr.payslip.run',
                'lang': self.force_lang,
            }

            emp_data = {
                'payslip_run_id': paysliprun_id._ids,
                'force_lang': self.force_lang or self.env.user.company_id.partner_id.lang,
            }

            employees = self.with_context(active_test=False).employee_ids
            department = self.department_id
            payslip_ids = paysliprun_id.slip_ids
            if not self.all_employees:
                if department and not employees:
                    employees = self.env['hr.contract.appointment'].sudo().search([
                        '&',
                        '|',
                        ('department_id', '=', department.id),
                        '&',
                        ('employee_id.department_id', '=', department.id),
                        ('department_id', '=', False),
                        ('date_start', '<=', date_to),
                        '|',
                        ('date_end', '=', False),
                        ('date_end', '>=', date_from)
                    ]).mapped('employee_id')
                payslip_ids = payslip_ids.filtered(lambda r: r.employee_id in employees)
                emp_data.update({
                    'employee_ids': employees._ids
                })

            if not payslip_ids:
                raise exceptions.UserError(_('Atlyginimai nurodytam periodui dar nepaskaičiuoti.'))

            mapper = {
                'payslip_run': 'l10n_lt_payroll.report_suvestine_sl',
                'payslip_run_by_department': 'l10n_lt_payroll.report_hr_payslip_run_by_department',
                'payslip_run_by_department_and_employees': 'l10n_lt_payroll.report_hr_payslip_run_by_dep_and_empl',
            }
            report_name = mapper.get(self.report_template) or 'l10n_lt_payroll.report_suvestine_sl'
            res = self.env['report'].with_context(ctx).get_action(paysliprun_id, report_name, data=emp_data)
            if 'report_type' in res:
                if self._context.get('force_pdf'):
                    res['report_type'] = 'qweb-pdf'
                if self._context.get('force_html'):
                    res['report_type'] = 'qweb-html'
            return res
        else:
            raise exceptions.UserError(_('Atlyginimai nurodytam periodui dar nepaskaičiuoti.'))

    @api.multi
    def download_excel(self):
        date_from_dt = datetime(self.year, self.month, 1)
        date_to_dt = date_from_dt + relativedelta(day=31)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            payslip_run_obj = self.sudo().env['hr.payslip.run']
        else:
            payslip_run_obj = self.env['hr.payslip.run']
        paysliprun_id = payslip_run_obj.search(
            [('date_start', '=', date_from),
             ('date_end', '=', date_to)], limit=1)
        if paysliprun_id and paysliprun_id.state == 'close':
            payslips = paysliprun_id.slip_ids
            employees = self.with_context(active_test=False).employee_ids
            department = self.department_id
            if not self.all_employees:
                if department and not employees:
                    employees = self.env['hr.contract.appointment'].sudo().search([
                        '&',
                        '|',
                        ('department_id', '=', department.id),
                        '&',
                        ('employee_id.department_id', '=', department.id),
                        ('department_id', '=', False),
                        ('date_start', '<=', date_to),
                        '|',
                        ('date_end', '=', False),
                        ('date_end', '>=', date_from)
                    ]).mapped('employee_id')
                payslips = payslips.filtered(lambda r: r.employee_id in employees)
            if payslips:
                return payslips.with_context(lang=self.force_lang or self.env.user.lang).export_payslips()
        if not self._context.get('archive'):
            raise exceptions.Warning(_('Atlyginimai nurodytam periodui dar nepaskaičiuoti.'))

    @api.multi
    def name_get(self):
        return [(rec.id, _('Atlyginimų suvestinė')) for rec in self]
