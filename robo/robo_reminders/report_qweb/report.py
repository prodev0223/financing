# -*- coding: utf-8 -*-
from odoo import api, models, tools

import logging
_logger = logging.getLogger(__name__)


class UnreconciledPaymentsReport(models.AbstractModel):

    _name = 'report.robo_reminders.unreconciled_payments_report_template'

    @api.multi
    def render_html(self, doc_ids, data=None):
        if data and 'doc_ids' in data and 'doc_model' in data:
            data['docs'] = self.env[data['doc_model']].browse(data['doc_ids'])
        return self.env['report'].render('robo_reminders.unreconciled_payments_report_template', values=data)


UnreconciledPaymentsReport()
