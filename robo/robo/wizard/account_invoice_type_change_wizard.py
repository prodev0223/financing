# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class AccountInvoiceTypeChangeWizard(models.TransientModel):
    _name = 'account.invoice.type.change.wizard'

    def _default_type(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice = self.env['account.invoice'].browse(active_id)
            return invoice.type

    def _default_sale_journal_id(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice = self.env['account.invoice'].browse(active_id)
            if invoice.type in ['out_invoice', 'out_refund']:
                return invoice.journal_id

    def _default_purchase_journal_id(self):
        active_id = self._context.get('active_id', False)
        if active_id:
            invoice = self.env['account.invoice'].browse(active_id)
            if invoice.type in ['in_invoice', 'in_refund']:
                return invoice.journal_id

    type = fields.Selection([
        ('out_invoice', 'Kliento sąskaita'),
        ('in_invoice', 'Tiekėjo sąskaita'),
        ('out_refund', 'Kliento grąžinimas'),
        ('in_refund', 'Tiekėjo grąžinimas')], string='Sąskaitos tipas', default=_default_type)

    sale_journal_id = fields.Many2one('account.journal', string='Žurnalas', domain=[('type', '=', 'sale')],
                                      default=_default_sale_journal_id)
    purchase_journal_id = fields.Many2one('account.journal', string='Žurnalas', domain=[('type', '=', 'purchase')],
                                          default=_default_purchase_journal_id)

    @api.multi
    def change_type(self):
        """
        Method used to change type of account_invoice in draft state.
        If invoice type is out_invoice or out_refund, type is only changed if invoice is created in document processing.
        The amounts and prices are recomputed in case of a change from invoice to refund. Also the accounts and
        journals are changed if invoice is changed from in to out and vice versa.
        :return: None
        """
        self.ensure_one()
        invoice_type = {
            'out_invoice': 'out',
            'in_invoice': 'in',
            'out_refund': 'out',
            'in_refund': 'in'
        }

        account_2410 = self.env.ref('l10n_lt.1_account_229')
        account_4430 = self.env.ref('l10n_lt.1_account_378')

        invoice_type_to_account_code = {
            'out_invoice': account_2410,
            'in_invoice': account_4430,
            'out_refund': account_2410,
            'in_refund': account_4430,
        }

        if not self.env.user.is_accountant():
            return False

        active_id = self._context.get('active_id', False)
        if not active_id:
            return False

        invoice = self.env['account.invoice'].browse(active_id)

        if invoice.state != 'draft':
            return False

        type_from = invoice.type
        type_to = self.type

        if type_from == type_to:
            raise exceptions.UserError(_('Sąskaitai jau yra nustatytas šis tipas.'))

        invoice_vals = {'type': type_to}
        if invoice_type[type_from] == 'out' and not invoice.imported_pic:
            raise exceptions.UserError(
                _('Pardavimo sąskaitos tipas gali būti pakeistas tik tuo atveju, jei sąskaita '
                  'buvo sukurta apdorojant dokumentus.'))

        if invoice_type[type_from] != invoice_type[type_to]:
            if invoice_type[type_to] == 'out' and not invoice.partner_id.customer:
                raise exceptions.UserError(_('Sąskaitoje nurodytas partneris nėra klientas.'))
            elif invoice_type[type_to] == 'in' and not invoice.partner_id.supplier:
                raise exceptions.UserError(_('Sąskaitoje nurodytas partneris nėra tiekėjas.'))

            for invoice_line in invoice.invoice_line_ids:
                if invoice_type[type_from] == 'in':
                    account = invoice_line.product_id.get_product_income_account(return_default=True)
                else:
                    account = invoice_line.product_id.get_product_expense_account(return_default=True)
                if account:
                    invoice_line.write({'account_id': account.id})
            account_to_id = invoice_type_to_account_code[type_to].id
            if account_to_id:
                invoice_vals['account_id'] = account_to_id

            if invoice_type[type_from] == 'in' and invoice.reference:
                invoice_vals['number'] = invoice.reference
        if invoice_type[type_to] == 'out' and self.sale_journal_id.id != invoice.journal_id.id:
            invoice_vals['journal_id'] = self.sale_journal_id.id
        elif invoice_type[type_to] == 'in' and self.purchase_journal_id.id != invoice.journal_id.id:
            invoice_vals['journal_id'] = self.purchase_journal_id.id

        if invoice_type[type_from] == 'in' and invoice_type[type_to] == 'out':
            invoice_vals['move_name'] = invoice.reference
        else:
            invoice_vals['move_name'] = False
        invoice.write(invoice_vals)
        invoice._compute_amount()

        mapper_tax_opposite_tax = {tax: False for tax in invoice.invoice_line_ids.mapped('invoice_line_tax_ids')}
        for tax in mapper_tax_opposite_tax.keys():
            opposite_tax = self.env['account.tax'].with_context(type=False).search([
                ('code', '=', tax.code),
                ('price_include', '=', tax.price_include),
                ('type_tax_use', '!=', tax.type_tax_use),
            ], limit=1)
            mapper_tax_opposite_tax[tax] = opposite_tax
        for invoice_line in invoice.invoice_line_ids:
            for tax in invoice_line.invoice_line_tax_ids:
                opposite_tax = mapper_tax_opposite_tax[tax]
                if opposite_tax:
                    invoice_line.invoice_line_tax_ids = [(3, tax.id), (4, opposite_tax.id)]
            invoice_line._compute_price()

        invoice_view_id = self.env.ref('account.invoice_form').id if invoice_type[type_to] == 'out' else self.env.ref(
            'account.invoice_supplier_form').id
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice',
            'res_id': invoice.id,
            'view_id': invoice_view_id,
            'target': 'current',
        }
