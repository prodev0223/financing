# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class ResCompany(models.Model):
    _inherit = 'res.company'

    auto_split_invoice_tax = fields.Boolean(string='Automatiškai skaidyti sąskaitų mokesčius')
    enable_extended_invoice_tax_amounts = fields.Boolean(string='Įgalinti mokesčių detalizaciją sąskaitų sąrašuose')


ResCompany()


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    auto_split_invoice_tax = fields.Boolean(
        string='Automatiškai skaidyti sąskaitų mokesčius',
        help='Jei nustatyta, tiekėjų sąskaitų mokesčių eilutės bus automatiškai išskaidytos, '
             'jei sąskaitos patvirtinimo momentu sistemoje bus įvestas mišrus PVM'
    )
    enable_extended_invoice_tax_amounts = fields.Boolean(
        string='Įgalinti mokesčių detalizaciją sąskaitų sąrašuose',
        inverse='_set_enable_extended_invoice_tax_amounts'
    )

    @api.model
    def default_get(self, field_list):
        res = super(RoboCompanySettings, self).default_get(field_list)
        company = self.env.user.sudo().company_id
        res.update({
            'auto_split_invoice_tax': company.auto_split_invoice_tax,
            'enable_extended_invoice_tax_amounts': company.enable_extended_invoice_tax_amounts,
        })
        return res

    @api.model
    def _get_company_policy_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_policy_field_list()
        res.extend((
            'auto_split_invoice_tax',
            'enable_extended_invoice_tax_amounts',
        ))
        return res

    @api.multi
    def _set_enable_extended_invoice_tax_amounts(self):
        """
        Add extended tax amount group to accountant
        users on activation.
        :return: None
        """
        # Reference needed groups
        tax_amount_group = self.sudo().env.ref('mixed_vat_rate.extended_invoice_tax_amounts')
        accountant_group = self.sudo().env.ref('robo_basic.group_robo_premium_accountant')

        for rec in self:
            if rec.enable_extended_invoice_tax_amounts:
                accountant_group.write({'implied_ids': [(4, tax_amount_group.id)]})
            else:
                # On deactivation, remove the inheritance, and clear the users
                accountant_group.write({'implied_ids': [(3, tax_amount_group.id)]})
                tax_amount_group.write({'users': [(5,)]})


RoboCompanySettings()
