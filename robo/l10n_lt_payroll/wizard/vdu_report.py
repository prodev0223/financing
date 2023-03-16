# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools
from datetime import datetime
from ..report.vdu_excel import VduExcel


class VDUReportWizard(models.TransientModel):
    _name = 'vdu.report.wizard'

    def _today(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _get_default_employee_ids(self):
        return self._context.get('employee_ids') or False

    date = fields.Date('Report date', required=True, default=_today)
    all_employees = fields.Boolean('Export for all employees')
    employee_ids = fields.Many2many('hr.employee', string='Employees', default=_get_default_employee_ids)
    is_manager = fields.Boolean('Is the user a manager', compute='_compute_is_manager')

    @api.multi
    @api.depends('date', 'employee_ids', 'all_employees')
    def _compute_is_manager(self):
        is_manager = self.env.user.is_manager() or self.env.user.is_hr_manager()
        for rec in self:
            rec.is_manager = is_manager

    @api.multi
    def open_xls_report(self):
        if not self.is_manager:
            self.employee_ids = self.employee_ids.filtered(lambda e: e.id in self.env.user.partner_id.employee_ids.ids)
        elif self.all_employees:
            self.employee_ids = self.env['hr.employee'].search([])
        if not self.employee_ids:
            return False
        data = {
            'doc_ids': self.employee_ids.ids,
            'date': self.date
        }

        vdu_excel = VduExcel()

        vdu_data = self.env['report.l10n_lt_payroll.report_vdu'].get_data(self.employee_ids.ids, data=data)

        for record in vdu_data:
            vdu_excel.write_line(record)

        base64_file = vdu_excel.export()
        date_dt = datetime.strptime(self.date, '%Y-%m-%d')

        year, month = date_dt.year, date_dt.month
        filename = 'VDU_%s-%s.xlsx' % (str(year), str(month))
        attach_id = self.env['ir.attachment'].sudo().create({
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file,
            'res_model': self._name,
            'res_id': self.id,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model={}&res_id={}&attach_id={}'.format(
                self._name,
                self.id,
                attach_id.id
            ),
            'target': 'self',
        }

    @api.multi
    def open_report(self):
        if not self.is_manager:
            self.employee_ids = self.employee_ids.filtered(lambda e: e.id in self.env.user.partner_id.employee_ids.ids)
        elif self.all_employees:
            self.employee_ids = self.env['hr.employee'].search([])
        if not self.employee_ids:
            return False

        return self.env['report'].get_action(
            self.employee_ids,
            'l10n_lt_payroll.report_vdu',
            data={
                'doc_ids': self.employee_ids.ids,
                'date': self.date
            }
        )


VDUReportWizard()
