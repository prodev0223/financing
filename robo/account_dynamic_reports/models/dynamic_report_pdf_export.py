# -*- coding: utf-8 -*-

from odoo import api, models


class DynamicReportPDFExportSettings(models.AbstractModel):
    _name = 'dynamic.report.pdf.export.settings'

    @api.multi
    def get_pdf_header(self):
        return ''

    @api.multi
    def get_pdf_footer(self):
        return ''
