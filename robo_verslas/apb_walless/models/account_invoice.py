# -*- coding: utf-8 -*-

from odoo import models, api, _, exceptions, tools, fields
from . import apb_walless_tools as awt

# 1.8% value is actually 2.7% value from 2022. Kept 1.8 so that data doesn't have to be updated.
SODRA_ROYALTY_PERCENTAGE_MAPPER = {
                '0': 0.1252,
                '1.8': 0.15221,
                '3': 0.1552,
            }


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    employee_invoice = fields.Boolean(compute='_employee_invoice')

    # Computes / On-changes ------------------------------------------------------------------------------------

    @api.multi
    @api.depends('type', 'partner_id.employee_ids')
    def _employee_invoice(self):
        """
        Compute //
        Calculate whether current account.invoice object is and invoice by an employee
        :return: None
        """
        for rec in self:
            if rec.type in ['in_invoice', 'in_refund'] and rec.partner_id.employee_ids:
                rec.employee_invoice = True

    @api.multi
    def action_invoice_open(self):
        for rec in self:
            if rec.type in ['in_invoice', 'in_refund'] and rec.partner_id.employee_ids:
                rec.write({'b_klase_kodas_id': self.env.ref('l10n_lt_payroll.b_klases_kodas_29').id})
                super(AccountInvoice, rec.with_context(skip_attachments=True)).action_invoice_open()
            else:
                super(AccountInvoice, rec).action_invoice_open()

    @api.onchange('payment_mode', 'ap_employee_id')
    def onchange_payment_mode(self):
        pass  # overridden from robo module, don't use any partner_id domains in walless_partners

    # Main methods --------------------------------------------------------------------------------------------

    @api.model
    def prep_vals(self, iml, inv):
        """
        Method used to override account.move.line data that are being created
        from account.invoice object.
        :param iml: move.lines to-be-created from account invoice object
        :param inv: account.invoice object
        :return: call to super()
        """
        if inv.employee_invoice:
            try:
                tax_line = next(item for item in iml if 'type' in item and item.get('type') == 'tax')
            except StopIteration:
                tax_line = {}
            try:
                split_line = next(item for item in iml if 'type' in item and item.get('type') == 'dest')
            except StopIteration:
                raise exceptions.ValidationError(_('Nekorektiškos sąskaitos eilutės'))

            template = {
                'type': 'dest',
                'date_maturity': split_line.get('date_maturity'),
                'invoice_id': split_line.get('invoice_id'),
                'name': split_line.get('name')
            }

            accounts = self.env['account.account'].search([('code', 'in', awt.ACCOUNT_CODE_LIST)])

            codes_not_found = set(awt.ACCOUNT_CODE_LIST) - set(accounts.mapped('code'))
            if codes_not_found:
                raise exceptions.UserError(_('Nerastos šios buhalterinės sąskaitos naudojamos '
                                             'Honorarų skaičiavimui: {0}').format(', '.join(codes_not_found)))

            tax_account = accounts.filtered(lambda a: a.code == awt.TAX_ACCOUNT_CODE).id
            vsd_account = accounts.filtered(lambda a: a.code == awt.VSD_ACCOUNT_CODE).id
            psd_account = accounts.filtered(lambda a: a.code == awt.PSD_ACCOUNT_CODE).id
            gpm_account = accounts.filtered(lambda a: a.code == awt.GPM_ACCOUNT_CODE).id

            aml_list = []
            if tax_line:
                tax_amt = tax_line.get('price', 0) * -1
                vals = {
                    'account_id': tax_account,
                    'price': tax_amt,
                }
                vals.update(template)
                aml_list.append(vals)
            else:
                tax_amt = 0
            split_amount = split_line.get('price', 0)
            split_amount -= tax_amt
            # Calculate amounts
            static_num = SODRA_ROYALTY_PERCENTAGE_MAPPER.get(inv.partner_id.sodra_royalty_percentage or '0')

            if not inv.partner_id.vsd_with_royalty:
                vsd_amount = tools.float_round(
                    ((split_amount - split_amount * 0.3) * 0.9) * static_num, precision_digits=2)
                vsd_account = vsd_account
                vals = {
                    'account_id': vsd_account,
                    'price': vsd_amount,
                }
                vals.update(template)
                aml_list.append(vals)
            else:
                vsd_amount = 0.0

            # Static WallessAPB formula that differs from other accounting calculations
            # Hardcoded numbers are meant to stay until Walless changes their formula
            psd_amount = tools.float_round(((split_amount - split_amount * 0.3) * 0.9) * 0.0698, precision_digits=2)
            gpm_amount = tools.float_round((split_amount - split_amount * 0.3) * 0.15, precision_digits=2)

            old_amt = split_line.get('price', 0)
            total_amount = vsd_amount + psd_amount + gpm_amount + tax_amt
            amt = tools.float_round(old_amt - total_amount, precision_digits=2)
            if tools.float_compare(amt + total_amount, old_amt, precision_digits=2) != 0:
                leftovers = amt + total_amount - old_amt
                amt -= leftovers

            # Apply amount
            next(item for item in iml if 'type' in item and item.get('type') == 'dest')['price'] = amt

            vals = {
                'account_id': psd_account,
                'price': psd_amount,
            }
            vals.update(template)
            aml_list.append(vals)
            vals = {
                'account_id': gpm_account,
                'price': gpm_amount,
            }
            vals.update(template)
            aml_list.append(vals)
            iml += aml_list
        return super(AccountInvoice, self).prep_vals(iml, inv)


AccountInvoice()
