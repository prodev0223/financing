# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api
from odoo.addons.sepa import api_bank_integrations as abi


class EInvoiceExportLine(models.TransientModel):
    _name = 'e.invoice.export.line'

    name = fields.Char(string='Mokėjimo paskirtis')
    partner_id = fields.Many2one('res.partner', string='Partneris',
                                 ondelete='cascade', readonly=True, inverse='_set_res_partner_bank_id')
    invoice_id = fields.Many2one('account.invoice', string='Sąskaita faktūra', ondelete='cascade', readonly=True)
    res_partner_bank_id = fields.Many2one(
        'res.partner.bank', string='Partnerio banko sąskaita',
        domain="[('bank_id.bic','=', %s)]" % abi.E_INVOICE_ALLOWED_BANKS
    )
    bank_name = fields.Char('Bankas', compute='_compute_bank_name')
    amount = fields.Float(string='Neapmokėta suma', readonly=True)

    @api.multi
    @api.depends('res_partner_bank_id')
    def _compute_bank_name(self):
        for rec in self:
            rec.bank_name = rec.res_partner_bank_id.bank_id.name

    @api.multi
    def _set_res_partner_bank_id(self):
        cron_job = self._context.get('cron_push_e_invoices')
        for rec in self.filtered(lambda x: x.partner_id):
            # Default bank to assign is forced in partner card
            bank_to_assign = rec.partner_id.res_partner_bank_e_invoice_id
            # If it's not cron job, try to search for other banks
            if not cron_job:
                swed_bank = rec.partner_id.bank_ids.filtered(
                    lambda x: x.bank_id.bic == abi.SWED_BANK)
                if swed_bank:
                    bank_to_assign = swed_bank[0]
                else:
                    banks = rec.partner_id.bank_ids.filtered(
                        lambda x: x.bank_id.bic in abi.E_INVOICE_ALLOWED_BANKS)
                    bank_to_assign = banks[0] if banks else False
            rec.res_partner_bank_id = bank_to_assign


EInvoiceExportLine()
