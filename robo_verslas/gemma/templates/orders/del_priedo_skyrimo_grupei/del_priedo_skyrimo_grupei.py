# -*- coding: utf-8 -*-
from odoo import models, api, tools, fields, _, exceptions


class EDocument(models.Model):
    _inherit = 'e.document'

    show_exclude_data_from_du_aspi = fields.Boolean(compute='_compute_show_exclude_data_from_du_aspi')

    @api.multi
    @api.depends('template_id')
    def _compute_show_exclude_data_from_du_aspi(self):
        company_setting_enabled = self.env.user.company_id.allow_exclude_data_from_du_aspi_report
        for rec in self.filtered(
                lambda t: t.template_id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')):
            rec.show_exclude_data_from_du_aspi = company_setting_enabled

    @api.multi
    def isakymas_del_priedo_skyrimo_grupei_workflow(self):
        lines = self.get_document_lines()
        date_from, date_to = self._get_bonus_payment_dates()
        bonuses = self.env['hr.employee.bonus']
        employees_ids = lines.mapped('employee_id2').ids
        for line in lines:
            bonus_rec = self.env['hr.employee.bonus'].create({
                'employee_id': line.employee_id2.id,
                'for_date_from': self.date_1,
                'for_date_to': self.date_2,
                'payment_date_from': date_from,
                'payment_date_to': date_to,
                'bonus_type': self.bonus_type_selection,
                'amount': line.float_1,
                'amount_type': self.bonus_input_type,
                'related_document': self.id,
                'exclude_bonus_from_du_aspi': self.bool_1,
            })
            bonus_rec.confirm()
            bonuses += bonus_rec
        self.write({
            'record_model': 'hr.employee.bonus',
            'record_ids': self.format_record_ids(bonuses.ids),
        })

        self.inform_about_payslips_that_need_to_be_recomputed(employees_ids, date_from, date_to)