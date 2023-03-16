# -*- coding: utf-8 -*-
from odoo import models, api, tools, exceptions
from odoo.addons.queue_job.job import identity_exact
from odoo.addons.queue_job.job import job
from itertools import islice


class RKeeperSaleLine(models.Model):
    _inherit = 'r.keeper.sale.line'

    @api.multi
    def find_related_account_tax(self):
        """
        Completely override find_related_account_tax for rKeeper sale line.
        Custom VAT rate calculations are used.
        """
        self.ensure_one()
        account_tax = self.env['account.tax']
        force_taxes = mapped_taxes = False

        # Check whether tax mapper exists
        tax_mapper = self.env['r.keeper.product.tax.mapper'].search(
            [('product_id', '=', self.product_id.id)]
        )
        if tax_mapper:
            mapped_taxes = True
            account_tax = tax_mapper.tax_id

        if not account_tax:
            amount_total = self.amount_wo_vat + self.amount_vat
            if not tools.float_is_zero(amount_total, precision_digits=2):
                percentage = round(((amount_total / self.amount_wo_vat) - 1) * 100, 2)
                forbidden_taxe_codes = self.env['ir.config_parameter'].sudo().get_param('r_keeper_forbidden_tax_codes')
                base_tax_domain = [('type_tax_use', '=', 'sale'), ('price_include', '=', False)]
                if forbidden_taxe_codes:
                    base_tax_domain.append(('code', 'not in', [str(c) for c in forbidden_taxe_codes.split(',')]))
                account_tax = self.env['account.tax'].search([('amount', '=', percentage)] + base_tax_domain, limit=1)

                # If corresponding taxes were not found, try to round the percentage to the nearest one
                # accepted percentages are 21, 9 and 5. If percentage is not in these ranges, continue
                if not account_tax:
                    # TODO: improve this maybe with some sort of settings. Removing the option to have PVM3 for bk
                    # r_keeper seems to be passing weird amounts 0.20 + 0.01 tax when rate should be 9%
                    # lower amounts are also problematic.
                    amount_leaf_added = False
                    if 15 <= percentage <= 30:
                        base_tax_domain.append(('amount', '=', 21))
                        amount_leaf_added = True
                    elif 2 <= percentage < 15:
                        base_tax_domain.append(('amount', '=', 9))
                        amount_leaf_added = True

                    # Indicates that domain has amount leaf appended
                    if amount_leaf_added:
                        force_taxes = True
                        account_tax = self.env['account.tax'].search(base_tax_domain, limit=1)

        return account_tax, force_taxes, mapped_taxes

    @api.multi
    def prepare_data(self, sale_ids, date_from, tax_to_skip_ids, allowed_diff, limit=80, n_channels=8, date_to=None):
        """Temporal method to fix BK sales via script"""

        sales = self.browse(sale_ids).exists()
        if date_to:
            sales = sales.filtered(lambda c: date_from < c.doc_date < date_to)
        else:
            sales = sales.filtered(lambda c: c.doc_date > date_from)

        invoice_data = {}
        for sale in sales:
            invoice_data.setdefault(sale.invoice_id.id, self.env['r.keeper.sale.line'])
            invoice_data[sale.invoice_id.id] |= sale

        n_channels = n_channels or 8
        invoice_data = dict(islice(invoice_data.items(), limit))
        chunk_size = int(len(invoice_data) / n_channels)

        def chunks(d_data, size):
            it = iter(d_data)
            for i in range(0, len(d_data), size):
                yield {k: d_data[k] for k in islice(it, size)}

        for channel, data_chunk in enumerate(chunks(invoice_data, chunk_size)):
            for invoice_id, sales in data_chunk.items():
                self.with_delay(
                    channel='root.single_%s' % (channel % n_channels + 1),
                    identity_key=identity_exact, eta=30
                ).queue_job_fix_taxes(invoice_id, sales, tax_to_skip_ids, allowed_diff)

    @job
    @api.model
    def queue_job_fix_taxes(self, invoice_id, sales, tax_to_skip_ids, allowed_diff):
        """Temporal method to fix BK sales via script"""

        # Job json conversion does not work that well
        # explicitly convert to int
        invoice_id = int(invoice_id)
        invoice = self.env['account.invoice'].browse(invoice_id)
        all_sales = invoice.mapped('invoice_line_ids.r_keeper_sale_line_ids')
        sales_to_change = sales
        invoice_lines = invoice.invoice_line_ids

        total_lines_to_change = self.env['account.invoice.line']
        for sale_to_change in sales_to_change:
            total_lines_to_change |= invoice_lines.filtered(
                lambda r: sale_to_change in r.r_keeper_sale_line_ids
            )

        taxes_to_force = any(x.force_taxes for x in sales_to_change)
        no_mismatch = invoice.force_taxes == taxes_to_force
        if no_mismatch:
            total_taxes = total_lines_to_change.mapped('invoice_line_tax_ids.id')
            tax_ids = tax_to_skip_ids
            for tx in tax_ids:
                if tx in total_taxes:
                    return

        default_type = sales_to_change[0].line_type

        invoice_lines = invoice.invoice_line_ids
        force_taxes = invoice.force_taxes or taxes_to_force

        res = invoice.action_invoice_cancel_draft_and_remove_outstanding()
        invoice.write({'force_taxes': False})
        invoice.invoice_line_ids.write({'price_subtotal_make_force_step': False})
        invoice.recompute_taxes_if_neccesary()

        for sale_to_change in sales_to_change:
            line_to_change = invoice_lines.filtered(
                lambda r: sale_to_change in r.r_keeper_sale_line_ids)
            if not line_to_change:
                raise exceptions.ValidationError('No lines to change. Invoice %s' % invoice.id)
            if len(line_to_change.r_keeper_sale_line_ids) > 1:
                raise exceptions.ValidationError('Too much lines to change. Invoice %s' % invoice.id)
            line_to_change.write({
                'price_unit': sale_to_change.calculated_price_unit,
                'invoice_line_tax_ids': [(6, 0, sale_to_change.tax_id.ids)],
            })

        default_analytic = sales_to_change[0].point_of_sale_id.analytic_account_id
        forced_taxes_amounts = {}

        grouped_lines = {}
        for line in all_sales:
            # Loop through lines and build dict of dicts with following mapping
            # {PRODUCT: TAX: {PRICE_UNIT: SALE_LINES, PRICE_UNIT_2: SALE_LINES}}...
            product = line.product_id
            tax = line.tax_id
            p_unit = line.calculated_price_unit
            grouped_lines.setdefault(product, {})
            grouped_lines[product].setdefault(line.tax_id, {})
            grouped_lines[product][tax].setdefault(p_unit, self.env['r.keeper.sale.line'])
            grouped_lines[product][tax][p_unit] |= line

        total_invoice_amount = vat_invoice_amount = untaxed_artificial_amount = untaxed_invoice_amount = 0.0
        # Loop through grouped lines and add them to invoice_line list
        for product, by_product in grouped_lines.items():
            for tax, by_tax in by_product.items():
                for price_unit, lines in by_tax.items():
                    # Determine the account of the product
                    product_account = product.get_product_income_account(return_default=True)
                    # Taxes are always mapped per product
                    mapped_taxes = lines[0].mapped_taxes
                    # Get total quantity of batch lines
                    tot_quantity = 0
                    for x in lines.mapped('quantity'):
                        tot_quantity += x
                    # Accumulate artificial invoice amount
                    untaxed_artificial_amount += price_unit * tot_quantity
                    # If mapped taxes are applied, price_unit is always VAT included
                    if mapped_taxes:
                        untaxed_invoice_amount += price_unit * tot_quantity
                    else:
                        # Get amount vat of the batch
                        batch_amount_vat = 0.0
                        for x in lines.mapped('amount_vat'):
                            batch_amount_vat += x
                        if force_taxes:
                            # If at least one line had forced taxes
                            # save forced amounts grouped by key of tax/account/analytic-account
                            tax_account = tax.account_id or product_account
                            group_key = '{}/{}/{}'.format(tax.id, tax_account.id, default_analytic.id)
                            forced_taxes_amounts.setdefault(
                                group_key, {
                                    'amount': 0.0, 'tax_id': tax.id,
                                    'tax_account_id': tax_account.id,
                                    'line_account_id': product_account.id,
                                    'analytic_account_id': default_analytic.id,
                                })
                            forced_taxes_amounts[group_key]['amount'] += batch_amount_vat

                        # Accumulate total vat amount and untaxed amount
                        vat_invoice_amount += batch_amount_vat

                        temp_amt = 0.0
                        for x in lines.mapped('amount_wo_vat'):
                            temp_amt += x

                        untaxed_invoice_amount += temp_amt

        # Calculate total invoice amount
        total_invoice_amount += vat_invoice_amount + untaxed_artificial_amount

        # Check if there are any forced taxes amounts
        if forced_taxes_amounts:
            for data in forced_taxes_amounts.values():
                # Find corresponding invoice tax line
                invoice_tax_line = invoice.tax_line_ids.filtered(
                    lambda r: r.tax_id.id == data['tax_id'] and r.account_id.id == data['tax_account_id']
                    and (r.account_analytic_id.id == data['analytic_account_id'] or not r.account_analytic_id)
                )
                current_amount = invoice_tax_line.amount
                # Get the difference between tax amounts
                tax_difference = tools.float_round(data['amount'] - current_amount, precision_digits=2)
                if not tools.float_is_zero(tax_difference, precision_digits=2):
                    # Check if amount should be "moved" or just subtracted
                    untaxed_difference = tools.float_round(
                        invoice.amount_untaxed_signed - untaxed_artificial_amount, precision_digits=2)
                    # If there's a difference, write new amount
                    # to tax line and force the taxes
                    invoice_tax_line.write({'amount': data['amount']})
                    if not invoice.force_taxes:
                        invoice.write({'force_taxes': True})

                    if not tools.float_is_zero(untaxed_difference, precision_digits=2):
                        # Get the invoice line that contains this tax
                        invoice_line_to_modify = invoice.invoice_line_ids.filtered(
                            lambda r: data['tax_id'] in r.invoice_line_tax_ids.ids
                            and r.account_id.id == data['line_account_id']
                            and r.account_analytic_id.id == data['analytic_account_id']
                        )[0]
                        # Calculate new amount and subtract it from current amount
                        # depends so that new forced tax amount and this untaxed
                        # amount still make the same total e.g.
                        # Before this block of code -> vat5 + untaxed15 = total20,
                        # after this block of code -> vat6 + untaxed14 = total20
                        new_amount = tools.float_round(
                            invoice_line_to_modify.amount_depends - untaxed_difference, precision_digits=2
                        )
                        invoice_line_to_modify.write({
                            'amount_depends': new_amount,
                            'price_subtotal_make_force_step': True,
                            'price_subtotal_save_force_value': new_amount
                        })
                        invoice_line_to_modify.with_context(
                            direct_trigger_amount_depends=True).onchange_amount_depends()

        if default_type == 'out_refund':
            total_invoice_amount *= -1

        # Check whether amounts do match before opening an invoice
        compare_amounts = [
            (total_invoice_amount, invoice.amount_total_signed, 'Total Amount'),
            (vat_invoice_amount, invoice.amount_tax_signed, 'VAT Amount')
        ]
        # Get allowed invoice difference
        allowed_diff = allowed_diff or 1.0

        amount_errors = str()
        for calculated, factual, a_type in compare_amounts:
            if tools.float_compare(calculated, factual, precision_digits=2):
                diff = tools.float_round(abs(calculated - factual), precision_digits=2)
                # It's already rounded here, so it's fine to compare with '>'
                if diff > allowed_diff:
                    amount_errors += 'Sąskaitos suma nesutampa su paskaičiuota suma (%s != %s). %s' % (
                        calculated, factual, a_type
                    )
        # Check if invoice has any amount errors and rollback with error if it does
        if amount_errors:
            raise exceptions.ValidationError('Amount errors %s. Invoice %s' % (amount_errors, invoice.id))

        # Open the invoice and force the partner
        try:
            invoice.action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False)
        except Exception as e:
            raise exceptions.ValidationError('Confirmation errors %s. Invoice %s' % (str(e.args), invoice.id))

        self.env.cr.commit()
