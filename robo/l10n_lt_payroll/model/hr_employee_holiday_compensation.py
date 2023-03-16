# -*- coding: utf-8 -*-

from odoo import _, api, exceptions, fields, models


class HrEmployeeHolidayCompensation(models.Model):
    _name = 'hr.employee.holiday.compensation'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade', readonly=False,
                                  states={'confirmed': [('readonly', True)]})
    date = fields.Date('Date', required=True, readonly=False, states={'confirmed': [('readonly', True)]})
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed')], 'State', required=True, default='draft')
    number_of_days = fields.Float('Number of days', required=True, readonly=False,
                                  states={'confirmed': [('readonly', True)]}, digits=(16, 5))
    record_id = fields.Integer('Record ID')
    record_model = fields.Char('Record Model')
    has_related_records = fields.Boolean(compute='_compute_has_related_records')

    @api.multi
    def name_get(self):
        return [
            (
                rec.id,
                _('{} holiday accumulation for {} - {} days').format(
                    rec.employee_id.name,
                    rec.date,
                    round(rec.number_of_days, 3)
                )
            ) for rec in self
        ]

    @api.multi
    @api.depends('record_id', 'record_model')
    def _compute_has_related_records(self):
        for rec in self:
            rec.has_related_records = rec.record_id and rec.record_model

    @api.multi
    def action_draft(self):
        self.write({'state': 'draft'})

    @api.multi
    def action_confirm(self):
        self.write({'state': 'confirmed'})

    @api.multi
    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise exceptions.UserError(_('You can not delete confirmed holiday compensation records. Please reset '
                                         'records to draft state'))
        return super(HrEmployeeHolidayCompensation, self).unlink()

    @api.multi
    def action_open_related_records(self):
        self.ensure_one()
        if not self.has_related_records:
            return
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': self.record_model,
            'name': _('Related records'),
            'view_id': False,
            'domain': "[('id', '=', {})]".format(self.record_id),
        }


HrEmployeeHolidayCompensation()
