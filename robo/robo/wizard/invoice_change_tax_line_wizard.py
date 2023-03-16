# -*- coding: utf-8 -*-


from odoo import _, api, exceptions, fields, models, tools


class InvoiceChangeTaxLineWizard(models.TransientModel):
    _name = 'invoice.change.tax.line.wizard'

    def get_default_amount(self):
        return self._context.get('default_amount', 0.0)

    tax_line_id = fields.Many2one('account.invoice.tax')
    name = fields.Char(related='tax_line_id.name', readonly=True)
    account_id = fields.Many2one('account.account', related='tax_line_id.account_id', readonly=True)
    currency_id = fields.Many2one('res.currency', related='tax_line_id.currency_id', readonly=True)
    amount = fields.Monetary(string='Suma', currency_field='currency_id', default=get_default_amount)
    has_picking = fields.Boolean(compute='_compute_has_picking')

    @api.multi
    @api.depends('tax_line_id.invoice_id')
    def _compute_has_picking(self):
        """Checks whether related invoice has pickings"""
        for rec in self:
            if not rec.tax_line_id.invoice_id:
                raise exceptions.ValidationError(_('Invoice was not found. Please contact the system administrators'))
            pickings = rec.tax_line_id.invoice_id.get_related_pickings()
            if pickings:
                rec.has_picking = True

    @api.multi
    def change_vals(self):
        """
        Changes invoice tax line amount.
        Base constraints are checked before execution.
        :return: None
        """
        self.ensure_one()

        # Ref the two groups
        acc_group = self.user_has_groups('robo_basic.group_robo_premium_accountant')
        tax_group = self.user_has_groups('robo.robo_front_tax_change')

        if not (acc_group or tax_group):
            raise exceptions.ValidationError(_('Tik buhalteriai gali keisti patvirtintos sąskaitos mokesčių eilutes'))

        # Invoice can be edited in all states except for cancel
        invoice = self.tax_line_id.invoice_id
        if invoice.state == 'cancel':
            raise exceptions.ValidationError(_('Negalima keisti mokesčių eilutės šioje būsenoje'))

        # Accountant group can bypass accountant validated check
        if not acc_group and invoice.accountant_validated:
            raise exceptions.ValidationError(_('Negalima keisti sąskaitos kuri patvirtinta buhalterio!'))

        # If only tax group is present for current user
        # sudo the execution, otherwise preserve the user
        if not acc_group and tax_group:
            self = self.sudo()

        # Write tax changes to the line
        if invoice.state in ['paid', 'open']:
            res = invoice.action_invoice_cancel_draft_and_remove_outstanding()
            self.write_vals()
            invoice.with_context(skip_attachments=True).action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False)
        else:
            self.write_vals()

        return {'type': 'ir.actions.act_close_wizard_and_reload_view'}

    @api.multi
    def write_vals(self):
        """
        Writes new amount to related invoice tax line,
        if amount differs, it also forces the taxes.
        :return: None
        """
        diff_amounts = tools.float_compare(self.tax_line_id.amount, self.amount, precision_digits=2)
        self.tax_line_id.write({
            'amount': self.amount,
        })
        if diff_amounts:
            self.tax_line_id.invoice_id.write({
                'force_taxes': True,
            })
