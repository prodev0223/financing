# -*- coding: utf-8 -*-

from odoo import models, api, fields


class ZiniarastisPeriodSelectedExport(models.TransientModel):
    _name = 'ziniarastis.period.selected.export'

    employee_ids = fields.Many2many('hr.employee', string='Darbuotojai',
                                    domain=['|', ('active', '=', False), ('active', '=', True)])
    ziniarastis_period_id = fields.Many2one('ziniarastis.period', required=True)

    @api.multi
    def export_selected_timetable(self):
        return self.ziniarastis_period_id.with_context(employee_ids=self.employee_ids).export_excel()


ZiniarastisPeriodSelectedExport()
