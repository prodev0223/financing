# -*- coding: utf-8 -*-


from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools


class TimesheetsReportWizard(models.TransientModel):
    _name = 'timesheets.report.wizard'

    year = fields.Selection([(2013, '2013'), (2014, '2014'), (2015, '2015'), (2016, '2016'), (2017, '2017'),
                             (2018, '2018'), (2019, '2019'), (2020, '2020'), (2021, '2021'), (2022, '2022'),
                             (2023, '2023'), (2024, '2024')], string='Metai',
                            default=lambda r: datetime.utcnow().year,
                            required=True)
    month = fields.Selection([(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5'), (6, '6'), (7, '7'),
                              (8, '8'), (9, '9'), (10, '10'), (11, '11'), (12, '12')], string='Mėnuo', required=True,
                             default=lambda r: datetime.utcnow().month)
    department_id = fields.Many2one('hr.department', string='Padalinys', required=False)
    download_for_all_employees = fields.Boolean(string='Atsisiųsti visiems darbuotojams', default=True)
    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai')
    employee_domain = fields.Many2many('hr.employee', 'employee_timesheet_wizard_domain_rel',
                                       compute='_employee_domain')

    @api.one
    @api.depends('department_id')
    def _employee_domain(self):
        if self.department_id:
            employee_ids = self.env['hr.employee'].search([('department_id', '=', self.department_id.id)])
        else:
            employee_ids = self.env['hr.employee'].search([])
        self.employee_domain = [(6, 0, employee_ids._ids)]

    @api.onchange('department_id')
    def check_change(self):
        employee_ids = self.employee_ids.filtered(lambda r: r in self.employee_domain)
        self.employee_ids = [(6, 0, employee_ids.ids)]

    @api.multi
    def download(self):
        self.ensure_one()
        date_from = datetime(self.year, self.month, 1)
        date_to = date_from + relativedelta(day=31)
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            ziniarastis_period_obj = self.sudo().env['ziniarastis.period']
        else:
            ziniarastis_period_obj = self.env['ziniarastis.period']
        ziniarastis_id = ziniarastis_period_obj.search(
            [('date_from', '=', date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
             ('date_to', '=', date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
             ('company_id', '=', self.env.user.company_id.id)], limit=1)
        if ziniarastis_id and ((
                                       ziniarastis_id.state == 'done' and self.download_for_all_employees) or not self.download_for_all_employees):
            if not self.download_for_all_employees:
                if not self.employee_ids:
                    raise exceptions.Warning(_('Nepasirinkote darbuotojų.'))
                else:
                    employees_not_confirmed = []
                    for employee in self.employee_ids:
                        related_lines = ziniarastis_id.related_ziniarasciai_lines.filtered(
                            lambda r: r['employee_id']['id'] == employee.id)
                        if not related_lines or any(line.state != 'done' for line in related_lines):
                            employees_not_confirmed.append(employee.id)
                    if len(employees_not_confirmed) != 0:
                        employees = self.sudo().env['hr.employee'].browse(employees_not_confirmed)
                        names = ", ".join(employees.mapped('name'))
                        raise exceptions.Warning(
                            _('Nurodytam periodui darbuotojų %s atlyginimai dar nėra paskaičiuoti') % (names))
                    else:
                        return ziniarastis_id.with_context(employee_ids=self.employee_ids).export_excel(
                            department_id=self.department_id.id)
            else:
                return ziniarastis_id.export_excel(department_id=self.department_id.id)
        else:
            raise exceptions.Warning(_('Atlyginimai nurodytam periodui dar nepaskaičiuoti.'))

    @api.multi
    def name_get(self):
        return [(rec.id, _('Laiko žiniaraštis')) for rec in self]
