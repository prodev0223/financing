# -*- coding: utf-8 -*-
from odoo import api, models, exceptions


class suvestine(models.AbstractModel):

    _name = 'report.eksploatacijos_aktas.report_eksploatacijos_aktas_sl'

    @api.multi
    def render_html(self, doc_ids, data=None):

        report_obj = self.env['report']
        report = report_obj._get_report_from_name('eksploatacijos_aktas.report_eksploatacijos_aktas_sl')
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': self.env[report.model].browse(doc_ids),
        }

        # if not all(self.env[report.model].browse(self._ids).mapped('turtas_viz_date')):
        #     raise exceptions.Warning('Negalime atspausdinti nevizuotų dokumentų!')

        return report_obj.render('eksploatacijos_aktas.report_eksploatacijos_aktas_sl', docargs)
