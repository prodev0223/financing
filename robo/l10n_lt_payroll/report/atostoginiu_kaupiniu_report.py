# -*- coding: utf-8 -*-

from odoo import api, models


class AtostoginiuKaupiniuReport(models.AbstractModel):
    _name = 'report.l10n_lt_payroll.atostoginiu_kaupiniu_report_template'

    @api.multi
    def render_html(self, doc_ids=None, data=None):
        if data is None:
            data = {}
        data.update({'company': self.env.user.company_id})
        return self.env['report'].render('l10n_lt_payroll.atostoginiu_kaupiniu_report_template', data)
