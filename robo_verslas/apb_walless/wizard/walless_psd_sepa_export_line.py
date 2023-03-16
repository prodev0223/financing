# -*- coding: utf-8 -*-
from odoo import models, api, fields

STATIC_HR_JOB_NAME = 'Partneris'


class WallessPsdSepaExportLine(models.TransientModel):

    _name = 'walless.psd.sepa.export.line'

    name = fields.Char(string='Mokėjimo paskirtis')
    date = fields.Date(string='Data')
    amount = fields.Float(string='Suma')

    # Relational fields
    ultimate_debtor_id = fields.Many2one('res.partner', string='Pradinis mokėtojas', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Partneris', ondelete='cascade')
    currency_id = fields.Many2one('res.currency', string='Valiuta', ondelete='cascade')
    bank_account_id = fields.Many2one('res.partner.bank', string='Banko sąskaita', ondelete='cascade')
    wizard_id = fields.Many2one('walless.psd.sepa.export', string='Vedlys')
    allowed_bank_account_ids = fields.Many2many('res.partner.bank', compute='_compute_allowed_bank_account_ids')

    @api.depends('partner_id')
    def _compute_allowed_bank_account_ids(self):
        """ Compute the allowed bank accounts from the partner registered bank accounts """
        for rec in self:
            rec.allowed_bank_account_ids = [(6, False, rec.partner_id.bank_ids.ids)]

    @api.onchange('ultimate_debtor_id')
    def _onchange_ultimate_debtor_id(self):
        """
        On ultimate_debtor_id field change return the domain so the partners
        that can be selected on that field would only include shareholders/attorneys.
        :return: Field domain (dict)
        """
        res_partners = self.env['hr.employee'].search([]).mapped('address_home_id')
        return {'domain': {'ultimate_debtor_id': [('id', 'in', res_partners.ids)]}}

    @api.onchange('partner_id', 'allowed_bank_account_ids')
    def _onchange_partner_id(self):
        """ Reset the bank_account_id field to preferred bank account for the selected partner """
        if self.partner_id:
            self.bank_account_id = self.partner_id.get_preferred_bank(self.wizard_id.journal_id)


WallessPsdSepaExportLine()

