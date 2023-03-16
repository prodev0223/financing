# -*- coding: utf-8 -*-
from odoo import models


class SaskaitaFaktura(models.AbstractModel):
    _inherit = 'report.saskaitos.report_invoice'


    def get_discount_type(self):
        """
        Gets the discount type for display in invoice printing
        :return: 'perc' or 'currency'
        """
        return self.env.user.company_id.sudo().invoice_print_discount_type or 'perc'


SaskaitaFaktura()
