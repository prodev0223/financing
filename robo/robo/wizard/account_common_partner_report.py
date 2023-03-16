# -*- coding: utf-8 -*-


from odoo import fields, models


class AccountCommonPartnerReport(models.TransientModel):
    _inherit = 'account.common.partner.report'

    result_selection = fields.Selection([('customer', 'Gautinos sumos'),
                                         ('supplier', 'Mokėtinos sumos'),
                                         ('customer_supplier', 'Gautinos ir mokėtinos sumos'),
                                         ('all', 'Visos sumos'),
                                         ], string="Atvaizduojama", lt_string='Atvaizduojama',
                                        required=True, default='customer')
