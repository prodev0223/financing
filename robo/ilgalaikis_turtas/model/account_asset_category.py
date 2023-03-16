# -*- coding: utf-8 -*-
from odoo import fields, models, api


class AccountAssetCategory(models.Model):
    _inherit = 'account.asset.category'

    prorata = fields.Boolean(default=False)

    enable_accounts_filter = fields.Boolean(string='Define revaluation and cost accounts')

    # account_asset_id  (depreciation asset) 1211

    account_prime_cost_id = fields.Many2one('account.account', string='Accumulated depr. Account',
                                            domain=[('is_view', '=', False), ('deprecated', '=', False)],
                                            help='Pastatų ir statinių įsigijimo savikainos nusidėvėjimas. Pvz. 1217')

    account_asset_revaluation_depreciation_id = fields.Many2one('account.account', string='Revaluation depr. Account',
                                                                domain=[('is_view', '=', False),
                                                                        ('deprecated', '=', False)],
                                                                help='Pastatų ir statinių perkainotos vertės dalies nusidėvėjimas. Pvz. 1218')

    account_revaluation_id = fields.Many2one('account.account', string='Revaluation Account',
                                             domain=[('is_view', '=', False), ('deprecated', '=', False)])  # 1219

    account_revaluation_reserve_id = fields.Many2one('account.account', string='Revaluation reserve Account',
                                                     domain=[('is_view', '=', False), ('deprecated', '=', False)],
                                                     help='Ilgalaikio materialiojo turto perkainojimo rezervas (rezultatai). Pvz. 321')
    account_revaluation_profit_id = fields.Many2one('account.account', string='Revaluation profit Account',
                                                    domain=[('is_view', '=', False), ('deprecated', '=', False)],
                                                    help='Pelno (nuostolių) ataskaitoje nepripažintas ataskaitinių metų pelnas. Pvz. 3412')
    account_depreciation_id = fields.Many2one('account.account',
                                              domain=[('is_view', '=', False), ('deprecated', '=', False)])

    account_revaluation_expense_id = fields.Many2one('account.account', string='Revaluation expense Account',
                                                     domain=[('is_view', '=', False), ('deprecated', '=', False)],
                                                     help='Ilgalaikio materialiojo turto vertės sumažėjimo sąnaudos. Pvz. 6133')
    account_depreciation_expense_id = fields.Many2one(required=False)  # todo o gal naudoti?

    account_analytic_id = fields.Many2one(string='Priverstinė analitinė sąskaita',
                                          help='Šios kategorijos turtas pagal nutylėjimą naudos šiame '
                                               'laukelyje nustatytą analitinę sąskaitą, neatsižvelgiant '
                                               'į turtą kuriančios sąskaitos faktūros nustatymus.')
    is_non_material = fields.Boolean(string='Nėra materialus', compute='_compute_is_non_material')

    @api.depends('name')
    def _compute_is_non_material(self):
        for rec in self:
            rec.is_non_material = rec.name.startswith('11') if rec.name else False


AccountAssetCategory()
