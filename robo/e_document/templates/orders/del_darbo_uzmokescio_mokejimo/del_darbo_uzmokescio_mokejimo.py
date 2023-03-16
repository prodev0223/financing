# -*- coding: utf-8 -*-

from odoo import api, models


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_darbo_uzmokescio_mokejimo_workflow(self):
        self.ensure_one()
        avansu_politika = 'fixed_sum' if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else False
        avansu_politika_suma = self.advance_amount if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else 0.00
        new_record = self.contract_id_1.update_terms(date_from=self.date_5, wage=self.float_1,
                                                     avansu_politika=avansu_politika, avansu_politika_suma=avansu_politika_suma)
        if new_record:
            self.inform_about_creation(new_record)
            self.set_link_to_record(new_record)

    @api.multi
    def is_darbo_uzmokescio_mokejimo_template(self):
        self.ensure_one()
        return self.template_id == self.env.ref('e_document.isakymas_del_darbo_uzmokescio_mokejimo_template')

    @api.onchange('contract_id_1')  # todo check for not admin
    def _onchange_contract_id_1_set_date_3(self):
        if self.is_darbo_uzmokescio_mokejimo_template() and self.contract_id_1:
            self.date_3 = self.contract_id_1.date_start


EDocument()
