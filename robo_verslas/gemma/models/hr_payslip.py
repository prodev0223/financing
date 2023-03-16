# coding=utf-8
from odoo import models, api


class HrPayslip(models.Model):

    _inherit = 'hr.payslip'

    @api.model
    def get_salary_work_time_codes(self):
        # REMOVE KV (Use VDU for Gemma)
        return {
            'normal': {'FD', 'DN', 'VD', 'VDN', 'KS', 'DP', 'VSS', 'SNV', 'BĮ', 'BN', 'MD'},
            'extra': {'DN', 'VD', 'VDN', 'DP', 'VSS', 'SNV'},
        }


HrPayslip()