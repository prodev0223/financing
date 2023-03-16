# -*- coding: utf-8 -*-
import exceptions

from odoo import fields, models, api, _


class HrEmployeeForcedWorkTime(models.Model):
    _name = 'hr.employee.forced.work.time'
    _inherit = ['robo.time.line']

    employee_id = fields.Many2one('hr.employee', 'Employee', required=True, ondelete='cascade')
    marking_id = fields.Many2one('tabelio.zymejimas', 'Marking', required=True, ondelete='cascade',
                                 default=lambda self: self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD').id)

    @api.multi
    @api.constrains('employee_id', 'date', 'time_from', 'time_to')
    def _check_times_do_not_overlap(self):
        for rec in self:
            other_times_for_date = self.search([
                ('employee_id', '=', rec.employee_id.id),
                ('date', '=', rec.date),
                ('id', '!=', rec.id)
            ])
            if not other_times_for_date:
                continue

            if any(t.time_from < rec.time_to and t.time_to > rec.time_from for t in other_times_for_date):
                raise exceptions.UserWarning(_('Forced work time already set for employee {0} for date {1}').format(
                    rec.employee_id.name, rec.date)
                )


HrEmployeeForcedWorkTime()
