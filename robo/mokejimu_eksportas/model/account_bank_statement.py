# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools


class AccountBankStatement(models.Model):
    _name = 'account.bank.statement'
    _inherit = ['account.bank.statement', 'bank.export.base']

    charge_bearer = [
        ('CRED', 'moka gavejas'),
        ('DEBT', 'moka moketojas'),
        ('SHAR', 'mokėtojo banko mokesčius moka mokėtojas, gavėjo banko – gavėjas'),
    ]
    is_international = fields.Boolean(
        compute='_compute_is_international',
        string='Ar tarptautinis',
    )
    kas_sumoka = fields.Selection(
        charge_bearer, string='Banko mokesčių mokėtojas'
    )

    # TODO: Remove next week (for non updated views)
    ar_tarptautinis = fields.Boolean(store=False)
    show_non_structured_warning = fields.Boolean(compute='_compute_show_non_structured_warning')

    @api.multi
    @api.depends('line_ids.info_type', 'line_ids.partner_id')
    def _compute_show_non_structured_warning(self):
        """Check whether warning about non structured references should be displayed"""
        partners = self.env['res.partner'].search([
            ('kodas', 'in', self.get_structured_reference_partner_codes())
        ])
        for rec in self:
            if any(x.partner_id in partners and x.info_type != 'structured' for x in rec.line_ids):
                rec.show_non_structured_warning = True

    @api.multi
    @api.depends('line_ids.bank_account_id.acc_number', 'line_ids.amount')
    def _compute_is_international(self):
        """Checks whether statement is international"""
        for statement in self:
            statement.is_international = any(x.is_international for x in statement.line_ids)

    @api.multi
    def button_cancel(self):
        """On cancel delete account moves created by the bank statement"""
        super(AccountBankStatement, self).button_cancel()
        for statement in self:
            moves = statement.mapped('move_line_ids.move_id')
            moves.write({'state': 'draft'})
            moves.unlink()

    # -----------------------------------------------------------------------------------------------------------------
    # Bank export methods // ------------------------------------------------------------------------------------------

    @api.multi
    def download(self):
        """Method that is used to download SEPA XML file"""
        self.ensure_one()
        self.line_ids.mark_related_objects_as_exported()
        return self.export_sepa_attachment_download(
            self.get_bank_export_data(self.line_ids)
        )

    @api.multi
    def send_to_bank(self):
        """
        Method that is used to send bank statement data to bank.
        Validates the data-to-be send, determines what integration is used
        (SEPA or API, only those two at the moment), groups data
        accordingly, calls the method that is the initiator of
        bank statement export for specific journal.
        :return: result of export method for specific journal
        """
        self.ensure_one()
        self.env['account.bank.statement'].check_global_readonly_access()
        return self.send_to_bank_base(
            self.get_bank_export_data(self.line_ids)
        )
