# -*- coding: utf-8 -*-


from odoo import _, api, models


class InvoiceRegistryWizard(models.TransientModel):
    _name = 'invoice.registry.wizard'
    _inherit = ['invoice.registry.wizard', 'robo.threaded.report']

    @api.multi
    def name_get(self):
        return [(rec.id, _('Sąskaitų faktūrų registras')) for rec in self]

    @api.multi
    def button_generate_report(self):
        """
        Generate invoice registry report, based on value stored in res.company determine
        whether to use threaded calculation or not
        :return: Result of specified method
        """
        # Define method and report names
        method_name = 'print_report'
        report_name = _('Sąskaitų faktūrų registras')

        # Some actions lose their context when re-browsed in threaded report mode,
        # thus if xls_report button is clicked, we ensure that we force the export type
        forced_xls = self._context.get('xls_report')

        if method_name and hasattr(self, method_name):
            return self.env['robo.report.job'].generate_report(self, method_name, report_name, forced_xls=forced_xls)
