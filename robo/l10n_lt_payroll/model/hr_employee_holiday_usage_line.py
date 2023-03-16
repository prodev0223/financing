# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.addons.l10n_lt_payroll.model.darbuotojai import get_vdu


class HrEmployeeHolidayUsageLine(models.Model):
    _name = 'hr.employee.holiday.usage.line'

    usage_id = fields.Many2one('hr.employee.holiday.usage', string='Holiday Usage', required=True, readonly=True,
                               ondelete='cascade')
    holiday_id = fields.Many2one('hr.holidays', related='usage_id.holiday_id', readonly=True)
    confirmed = fields.Boolean('Confirmed', related='usage_id.confirmed', store=True)
    holiday_payment_line_id = fields.Many2one('hr.holidays.payment.line', readonly=True, required=True,
                                              ondelete='cascade')

    used_accumulation_id = fields.Many2one('hr.employee.holiday.accumulation', string='Used accumulation')
    date_from = fields.Date(string='Date from', compute='_compute_dates')
    date_to = fields.Date(string='Date to', compute='_compute_dates')
    accumulation_date_from = fields.Date(string='Accumulation date from', related='used_accumulation_id.date_from')
    accumulation_date_to = fields.Date(string='Accumulation date to', related='used_accumulation_id.date_to')
    post = fields.Float(string='Post', related='used_accumulation_id.post', readonly=True)

    used_days = fields.Float(string='Used days', readonly=True, digits=(16, 3))

    has_confirmed_payslip = fields.Boolean(compute='_compute_has_confirmed_payslip', compute_sudo=True, store=True)

    amount = fields.Float(string='Payment amount', compute='_compute_amounts', digits=(16, 3))
    vdu = fields.Float(string='Payment VDU', compute='_compute_vdu', digits=(16, 3))
    holiday_coefficient = fields.Float(string='Payment Holiday Coefficient',
                                       related='holiday_payment_line_id.holiday_coefficient')

    @api.multi
    @api.depends('holiday_payment_line_id.vdu', 'used_accumulation_id.post', 'used_accumulation_id.appointment_id',
                 'holiday_payment_line_id.period_date_from', 'holiday_payment_line_id.period_date_to',
                 'holiday_id.date_from', 'holiday_id.date_to')
    def _compute_vdu(self):
        for rec in self:
            accumulation = rec.used_accumulation_id
            schedule_template = accumulation.appointment_id.schedule_template_id
            work_norm = schedule_template.work_norm if schedule_template else 1.0
            holiday = rec.holiday_id
            use_daily_vdu = holiday.should_use_daily_vdu_for_holiday_accumulation_calculations()
            if use_daily_vdu:
                vdu = get_vdu(self.env, holiday.date_from_date_format or rec.date_from, holiday.employee_id,
                              contract_id=holiday.contract_id.id, vdu_type='d').get('vdu', 0.0)
            else:
                vdu = get_vdu(self.env, holiday.date_from_date_format or rec.date_from, holiday.employee_id,
                              contract_id=holiday.contract_id.id, vdu_type='h').get('vdu', 0.0)
                vdu = vdu * 8.0 * work_norm * rec.post
            if holiday:
                minimum_wage = holiday.get_min_day_wage() * work_norm * rec.post
                vdu = max(vdu, minimum_wage)
            rec.vdu = vdu

    @api.multi
    @api.depends('holiday_id.leaves_accumulation_type', 'holiday_payment_line_id.vdu',
                 'holiday_payment_line_id.holiday_coefficient', 'used_days', 'used_accumulation_id.post')
    def _compute_amounts(self):
        for rec in self:
            rec.amount = rec.used_days * rec.vdu

    @api.multi
    def name_get(self):
        return [(
            usage_line.id,
            _('{} holiday ({} - {}) usage line for {} out of {} days').format(
                usage_line.holiday_id.employee_id.name,
                usage_line.holiday_id.date_from_date_format,
                usage_line.holiday_id.date_to_date_format,
                usage_line.used_days,
                usage_line.usage_id.used_days,
            )
        ) for usage_line in self]

    @api.multi
    def _recompute_holiday_usage(self):
        self.mapped('usage_id')._recompute_holiday_usage()

    @api.multi
    @api.depends('holiday_payment_line_id.period_date_from', 'holiday_payment_line_id.period_date_to',
                 'holiday_id.date_from', 'holiday_id.date_to')
    def _compute_dates(self):
        for rec in self.filtered(lambda r: r.holiday_payment_line_id):
            payment_line = rec.holiday_payment_line_id
            holiday = rec.holiday_id
            rec.date_from = max(payment_line.period_date_from, holiday.date_from_date_format)
            rec.date_to = min(payment_line.period_date_to, holiday.date_to_date_format)

    @api.multi
    @api.depends('holiday_payment_line_id', 'holiday_payment_line_id.period_date_from',
                 'holiday_payment_line_id.period_date_to', 'holiday_id.state')
    def _compute_has_confirmed_payslip(self):
        for rec in self:
            rec.has_confirmed_payslip = self.env['hr.payslip'].search_count([
                ('date_from', '<=', rec.date_to),
                ('date_to', '>=', rec.date_from),
                ('state', '=', 'done'),
                ('employee_id', '=', rec.holiday_id.employee_id.id)
            ])