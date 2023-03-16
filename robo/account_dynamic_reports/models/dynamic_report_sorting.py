# -*- coding: utf-8 -*-

import json

from odoo import api, fields, models


class DynamicReportSorting(models.AbstractModel):
    _name = 'dynamic.report.sorting'

    sort_report_by = fields.Char(string='Sort report by')

    @api.multi
    def set_report_sorting(self, sorting_data):
        self.ensure_one()
        try:
            self.write({'sort_report_by': json.dumps(sorting_data)})
        except:
            pass

    @api.multi
    def get_report_sorting(self):
        self.ensure_one()
        res = []
        if self.sort_report_by:
            try:
                res = json.loads(self.sort_report_by)
            except:
                pass
        return res
