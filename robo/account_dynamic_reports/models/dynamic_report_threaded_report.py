# -*- coding: utf-8 -*-

from odoo import models, api, _, exceptions


class DynamicThreadedReport(models.AbstractModel):
    _name = 'dynamic.report.threaded.report'
    _inherit = 'robo.threaded.report'

    @api.multi
    def _check_if_threaded_reports_are_enabled(self):
        self.ensure_one()
        if self.activated_threaded_reports:
            raise exceptions.ValueError(_('Can not open the report since threaded reports are enabled'))
