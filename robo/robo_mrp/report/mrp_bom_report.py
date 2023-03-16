# -*- coding: utf-8 -*-

import time
from odoo import api, models, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ReportMrpBom(models.AbstractModel):
    _name = 'report.robo_mrp.mrp_bom_report'

    @api.multi
    def render_html(self, doc_ids, data=None):
        docargs = {
            'doc_ids': doc_ids,
            'company': self.sudo().env.user.company_id,
            'data': data,
        }
        return self.env['report'].render('robo_mrp.mrp_bom_report', docargs)
