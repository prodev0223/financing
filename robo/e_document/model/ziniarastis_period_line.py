# -*- coding: utf-8 -*-
from odoo import api, models


class ZiniarastisPeriodLine(models.Model):
    _inherit = 'ziniarastis.period.line'

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id')
    def _show_warning(self):
        recs = self.filtered(lambda r: r.date_from and r.date_to and r.employee_id)
        if not recs:
            for rec in self:
                rec.show_warning = False
            return
        date_from = min(recs.mapped('date_from'))
        date_to = max(recs.mapped('date_to'))
        bad_employee_ids = self.env['e.document'].search([
            '|',
                ('state', 'in', ('draft', 'confirm')),
                '&',
                    ('failed_workflow', '=', True),
                    ('state', '=', 'e_signed'),
            '|',
                '&',
                    ('date_from_display', '>=', date_from),
                    ('date_from_display', '<=', date_to),
                '&',
                    ('date_to_display', '>=', date_from),
                    ('date_to_display', '<=', date_to),
        ]).mapped('related_employee_ids').ids
        for rec in self:
            rec.show_warning = rec.employee_id.id in bad_employee_ids


ZiniarastisPeriodLine()
