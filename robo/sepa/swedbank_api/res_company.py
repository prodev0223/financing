# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    activate_e_invoices = fields.Boolean(groups='base.group_system', inverse='_activate_e_invoices')
    e_invoice_agreement_date = fields.Date(groups='base.group_system')
    global_e_invoice_agreement_id = fields.Char(groups='base.group_system')

    @api.one
    def _activate_e_invoices(self):
        group_e_invoices = self.env.ref('robo.group_robo_e_invoice')
        group_id = self.env.ref('robo_basic.group_robo_premium_manager')

        if self.activate_e_invoices:
            group_id.sudo().write({
                'implied_ids': [(4, group_e_invoices.id)]
            })
        else:
            group_id.sudo().write({
                'implied_ids': [(3, group_e_invoices.id)]
            })
            group_e_invoices.write({'users': [(5,)]})


ResCompany()
