# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from six import iteritems
from odoo.addons.queue_job.job import job


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    force_taxes = fields.Boolean(inverse='_set_force_taxes')

    split_tax = fields.Boolean(
        string='Išskaidyti mokesčiai',
        track_visibility='onchange', copy=False
    )

    # Calculated from invoice tax table
    non_deductible_tax_amount = fields.Float(
        string='Neatskaitomų mokesčių suma',
        compute='_compute_extended_tax_amounts',
        groups='mixed_vat_rate.extended_invoice_tax_amounts',
    )
    deductible_tax_amount = fields.Float(
        string='Atskaitomų mokesčių suma',
        compute='_compute_extended_tax_amounts',
        groups='mixed_vat_rate.extended_invoice_tax_amounts',
    )
    apparent_tax_amount = fields.Float(
        string='Menamų mokesčių suma',
        compute='_compute_extended_tax_amounts',
        groups='mixed_vat_rate.extended_invoice_tax_amounts',
    )

    @api.multi
    def _compute_extended_tax_amounts(self):
        """
        Calculate deductible, non-deductible and apparent tax amounts
        based on invoice tax table. Amounts are used for display
        purposes on invoice tree view - with a spec. group
        :return:
        """
        for rec in self:
            amount_deductible = amount_non_deductible = apparent_amount = 0.0
            # Calculations differ depending on whether amount tax is zero or not
            zero_tax = tools.float_is_zero(rec.amount_tax, precision_digits=2)
            for tax_line in rec.tax_line_ids:
                if tax_line.tax_id.nondeductible:
                    amount_non_deductible += tax_line.amount
                else:
                    if zero_tax and tax_line.tax_id.account_id and \
                            tax_line.tax_id.account_id.code.startswith('4492'):
                        apparent_amount += abs(tax_line.amount)
                    else:
                        amount_deductible += tax_line.amount
            # Get the sign based on the invoice
            sign = -1 if rec.type in ['in_refund', 'out_refund'] else 1
            # Assign the amounts
            rec.non_deductible_tax_amount = amount_non_deductible * sign
            rec.deductible_tax_amount = amount_deductible * sign
            rec.apparent_tax_amount = apparent_amount * sign

    @api.multi
    def _set_force_taxes(self):
        recs_to_update = self.filtered(lambda i: not i.force_taxes)
        recs_to_update.recalculate_taxes()
        recs_to_update.write({'split_tax': False})

    @api.multi
    def recalculate_taxes(self):
        self.mapped('invoice_line_ids').write({'split_tax': False})
        return super(AccountInvoice, self).recalculate_taxes()

    @api.multi
    def _get_invoice_to_split_dict(self):
        return self.get_invoice_to_split_dict()

    @api.multi
    def get_invoice_to_split_dict(self):
        """
        From a set of invoice records, returns those whose date matches a mixed VAT rate record.

        :returns: a dictionary with mixed VAT rate ids as keys, and a RecordSet of invoices as values
        :rtype: dict
        """
        res = {}
        for inv in self.filtered(lambda l: 'in_' in l.type and not l.split_tax):
            rate = self.env['res.company.mixed.vat'].search([('date_from', '<=', inv.date_invoice),
                                                             ('date_to', '>=', inv.date_invoice)])
            if rate:
                res.setdefault(rate.id, self.env['account.invoice'])
                res[rate.id] |= inv
        if self and not res and not self.env.context.get('do_not_raise_if_no_rate_found'):
            raise exceptions.UserError(
                _('Pasirinktų sąskaitų faktūrų pateikimo dienomis nerastas mišrus PVM procentas. Patikrinkite įmonės profilį.'))
        return res

    @api.multi
    def _split_tax_lines(self, rate=None):
        """
        Splits tax lines on invoice for mixed VAT rate, using the given rate.
        Ignores taxes that are already non deductible, or when amount is 0, or whose code starts with 'A'

        :param rate: percentage of tax that remains deductible
        :return: None
        """
        if not rate:
            raise exceptions.UserError(_('Nenurodytas mišraus PVM procentas'))
        for inv in self:
            currency = inv.currency_id or self.env.user.company_id.currency_id
            rounding = currency.decimal_places
            new_tax_line_vals = []
            for line in inv.tax_line_ids:
                tax = line.tax_id
                if tax.code.startswith('A'):
                    continue
                if tax.nondeductible:
                    continue
                if tools.float_is_zero(tax.amount, precision_digits=2):
                    continue
                account_analytic_id = self.env['account.analytic.account']
                ail = inv.invoice_line_ids.filtered(lambda x: tax.id in x.invoice_line_tax_ids.ids)
                if len(ail) == 1 or len(ail.mapped('account_analytic_id')) == 1:
                    account_analytic_id = ail.mapped('account_analytic_id')
                amount = line.amount
                new_amount = tools.float_round(amount * rate / 100.0, precision_digits=rounding)
                line.amount = new_amount

                nondeduc_tax = tax.find_matching_nondeductible()
                account = nondeduc_tax.get_account(refund='refund' in inv.type)
                if not account:
                    raise exceptions.UserError(_('Nenustatyti mokesčio DK sąskaita %s - %s (sąskaita %s)')
                                               % (nondeduc_tax.code, nondeduc_tax.name, inv.number))
                existing_line = inv.tax_line_ids.filtered(lambda l: l.tax_id == nondeduc_tax and l.account_id == account)
                if existing_line:
                    existing_line[0].amount += amount - new_amount
                    continue
                new_tax_line_vals.append({
                    'tax_id': nondeduc_tax.id,
                    'name': nondeduc_tax.name,
                    'amount': amount - new_amount,
                    'account_id': account.id,
                    'account_analytic_id': account_analytic_id.id
                })
            if new_tax_line_vals:
                inv.sudo().write({
                    'split_tax': True,
                    'force_taxes': True,
                    'tax_line_ids': [(0, 0, vals) for vals in new_tax_line_vals]
                })

    @api.model
    def _restore_saved_payments(self, saved_payment_lines):
        """
        Tries to restore saved assigned payment to invoices. Ignore failures

        :param saved_payment_lines: a dictionary with invoice ids as keys and list of account.move.line ids as values
        :returns: nothing
        :rtype: None
        """
        for inv_id, lines in iteritems(saved_payment_lines):
            inv = self.env['account.invoice'].browse(inv_id)
            for line in lines:
                try:
                    inv.assign_outstanding_credit(line.id)
                except:
                    pass

    @job
    @api.multi
    def action_split_tax(self):
        """ For invoices in the set that can and need to be split, save payments, cancel invoice, split taxes, then restore confirmed status and payments """
        #todo: remove the filter and make sure method can split correctly invoice that are not confirmed yet
        splitting_needs = self.filtered(lambda inv: inv.state in ('open', 'paid')).get_invoice_to_split_dict()
        for rate_id, inv_to_split in iteritems(splitting_needs):
            rate = self.env['res.company.mixed.vat'].browse(rate_id).rate
            saved_payment_lines = {inv.id: inv.payment_move_line_ids for inv in inv_to_split}
            for inv in inv_to_split:
                inv.mapped('move_id.line_ids').filtered(lambda l: l.account_id == inv.account_id).remove_move_reconcile()
            inv_to_split.action_invoice_cancel()
            inv_to_split.action_invoice_draft()
            inv_to_split._split_tax_lines(rate=rate)
            for inv in inv_to_split: #FIXME: action_invoice_open is not really multi
                inv.action_invoice_open()
            inv_to_split._restore_saved_payments(saved_payment_lines)

    @api.multi
    def make_taxes_nondeductible(self):
        """ Change tax lines to non-deductible taxes, and updates invoice lines."""
        self.write({'force_taxes': True})
        # clean_A_code_tax_needed = self.env['account.invoice']
        for line in self.mapped('tax_line_ids'):
            if tools.float_is_zero(line.tax_id.amount, precision_digits=2):
                continue
            if line.tax_id.code.startswith('A'):
                continue
            if line.tax_id.nondeductible:
                continue
            account_analytic_id = False
            ail = line.invoice_id.invoice_line_ids.filtered(lambda x: line.tax_id.id in x.invoice_line_tax_ids.ids)
            if ail.mapped('account_analytic_id'):
                analytic_amounts = {}
                for l in ail:
                    if not l.account_analytic_id:
                        continue
                    analytic_amounts.setdefault(l.account_analytic_id.id, 0)
                    analytic_amounts[l.account_analytic_id.id] += l.price_subtotal
                account_analytic_id = max(analytic_amounts, key=analytic_amounts.get)
            new_tax = line.tax_id.find_matching_nondeductible()
            line.write({
                'tax_id': new_tax.id,
                'name': new_tax.name,
                'account_id': new_tax.account_id.id if line.invoice_id.type == 'in_invoice' else new_tax.refund_account_id.id,
                'account_analytic_id': account_analytic_id,
            })
        # clean_A_code_tax_needed.mapped('invoice_line_ids')._remove_A_code_taxes()
        self.mapped('invoice_line_ids')._switch_to_nondeductible_taxes()

    @api.multi
    def action_invoice_open(self):
        """ Split invoice tax before opening if set in company_settings """
        auto_split = self.env.user.company_id.sudo().auto_split_invoice_tax
        if auto_split:
            splitting_needs = self.filtered(
                lambda inv: inv.type in ('in_invoice', 'in_refund') and not inv.force_taxes
            ).with_context(do_not_raise_if_no_rate_found=True).get_invoice_to_split_dict()
            for rate_id, inv_to_split in iteritems(splitting_needs):
                rate = self.env['res.company.mixed.vat'].browse(rate_id).rate
                #This will fail if not matching tax found. Behavior was agreed on by accountant
                inv_to_split._split_tax_lines(rate=rate)
        return super(AccountInvoice, self).action_invoice_open()

    @job
    @api.multi
    def action_make_taxes_nondeductible(self):
        """ Reset invoices to draft status to make all taxes non-deductible then restore invoice status """
        #todo: make sure the method can act correctly on invoices that are not confirmed yet
        for inv in self.filtered(lambda r: r.type in ['in_invoice', 'in_refund'] and r.state in ['open', 'paid']):
            saved_payment_lines = {inv.id: inv.payment_move_line_ids}
            inv.mapped('move_id.line_ids').filtered(lambda l: l.account_id == inv.account_id).remove_move_reconcile()
            inv.action_invoice_cancel()
            inv.action_invoice_draft()
            inv.make_taxes_nondeductible()
            inv.action_invoice_open()
            inv._restore_saved_payments(saved_payment_lines)

    @api.model
    def create_invoice_action_split_vat(self):
        action = self.env.ref('mixed_vat_rate.invoice_split_tax_action')
        if action:
            action.create_action()

    @api.model
    def create_invoice_action_tax_nondeductible(self):
        action = self.env.ref('mixed_vat_rate.invoice_make_taxes_nondeductible_action')
        if action:
            action.create_action()
