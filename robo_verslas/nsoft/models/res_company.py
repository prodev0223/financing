# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):

    _inherit = 'res.company'

    nsoft_accounting_threshold_date = fields.Datetime(string='Apskaitos pradžios data')
    last_nsoft_db_sync = fields.Datetime(groups='base.group_system')
    nsoft_accounting_type = fields.Selection([
        ('sum', 'Suminė'), ('detail', 'Detali')],
        string='nSoft Apskaitos tipas', default='detail', inverse='_nsoft_accounting_type'
    )
    # Field is set via script
    enable_nsoft_cash_operations = fields.Boolean(
        compute='_compute_enable_nsoft_cash_operations',
        inverse='_set_enable_nsoft_cash_operations',
    )

    @api.multi
    def _compute_enable_nsoft_cash_operations(self):
        """Check if nsoft cash operation functionality is enabled"""
        self.ensure_one()
        enable_nsoft_cash_operations = self.env['ir.config_parameter'].sudo().get_param(
            'enable_nsoft_cash_operations') == 'True'
        self.enable_nsoft_cash_operations = enable_nsoft_cash_operations

    @api.multi
    def _set_enable_nsoft_cash_operations(self):
        """Update config parameter based on company settings value"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'enable_nsoft_cash_operations', str(self.enable_nsoft_cash_operations),
        )
        # Add or remove the cash operation group from accountant user
        nsoft_cash_operation_group = self.env.ref('nsoft.group_nsoft_cash_operations')
        accountant_group = self.env.ref('robo_basic.group_robo_premium_accountant')
        if self.enable_nsoft_cash_operations:
            accountant_group.sudo().write({'implied_ids': [(4, nsoft_cash_operation_group.id)]})
        else:
            accountant_group.sudo().write({'implied_ids': [(3, nsoft_cash_operation_group.id)]})
            nsoft_cash_operation_group.write({'users': [(5,)]})

    @api.one
    def _nsoft_accounting_type(self):
        group_group_nsoft_sum_accounting = self.env.ref('nsoft.group_nsoft_sum_accounting')
        group_id = self.env.ref('robo_basic.group_robo_premium_accountant')

        if self.nsoft_accounting_type and self.nsoft_accounting_type == 'sum':
            group_id.sudo().write({
                'implied_ids': [(4, group_group_nsoft_sum_accounting.id)]
            })
        else:
            group_id.sudo().write({
                'implied_ids': [(3, group_group_nsoft_sum_accounting.id)]
            })
            group_group_nsoft_sum_accounting.write({'users': [(5,)]})
