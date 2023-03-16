# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta
import odoo.addons.decimal_precision as dp


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    suma_eur_bepvm = fields.Float(string='Suma be PVM (EUR)', compute='_suma', store=True)
    operacijos_data = fields.Date(string='Išrašymo data', required=True, default=fields.Date.today, readonly=True,
                                  states={'draft': [('readonly', False)]}, copy=False, index=True)
    registration_date = fields.Date(string='Dokumento gavimo data', required=True, default=fields.Date.today,
                                    readonly=True,
                                    states={'draft': [('readonly', False)]}, copy=False, index=True)
    imt_tax_rate = fields.Integer(string='Mokesčių tarifas', compute='_get_imt_tax_rate', store=False)
    imt_tax_amount = fields.Float(string='Mokesčiai', compute='_get_imt_tax', store=False)
    print_detailed_taxes = fields.Boolean(string='Spausdinti detalius mokesčius', default=False, sequence=100)
    gp = fields.Float(string='Bendrasis pelnas', compute='_gp', store=True, compute_sudo=True)
    cost = fields.Float(string='Savikaina', compute='_gp', store=True, compute_sudo=True)
    date_invoice = fields.Date(inverse='_inverse_date_invoice')  # inverse method is also called elsewhere
    force_dates = fields.Boolean(string='Priverstinė data', readonly=True, states={'draft': [('readonly', False)]},
                                 copy=False, sequence=100, track_visibility='onchange'
                                 )

    proforma_vat_visibility = fields.Selection([('default', 'Numatytasis'),
                                      ('show_with', 'Rodyti su PVM'),
                                      ('show_without', 'Rodyti be PVM'),
                                      ('dont_show', 'Nerodyti PVM')], string='PVM rodymo nustatymai', default='default',
                                               copy=False, sequence=100,
                                               )

    validated_after_isaf = fields.Boolean(string='Validated after iSAF report', default=False, copy=False, sequence=100)
    create_isaf_ticket = fields.Boolean(string='Create iSAF ticket', default=False,
                                        groups='base.group_system', copy=False,
                                        help='Used for browsing invoices and creating accounting ticket when invoice needs to be handled by accountant',
                                        sequence=100,
                                        )
    margin_scheme_used = fields.Boolean(compute=lambda self: False)
    commercial_partner_id = fields.Many2one('res.partner', related=False, store=True, readonly=True, compute='_commercial_partner_id')

    @api.multi
    @api.depends('partner_id.commercial_partner_id')
    def _commercial_partner_id(self):
        for rec in self:
            rec.commercial_partner_id = rec.partner_id.commercial_partner_id

    @api.multi
    def _inverse_date_invoice(self):
        for rec in self:
            if rec.type in ['out_invoice', 'out_refund'] and rec.date_invoice:
                rec.write({
                    'registration_date': rec.date_invoice,
                    'operacijos_data': rec.date_invoice,
                })

    @api.depends('invoice_line_ids.gp', 'invoice_line_ids.cost')
    def _gp(self):
        for rec in self:
            rec.gp = sum(rec.sudo().invoice_line_ids.mapped('gp'))
            rec.cost = sum(rec.sudo().invoice_line_ids.mapped('cost'))

    @api.depends('amount_untaxed')
    def _suma(self):
        for rec in self:
            context = rec._context.copy()
            date = rec.operacijos_data or rec.date_invoice or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            context.update({'date': date})
            suma = rec.currency_id.with_context(context).compute(rec.amount_untaxed, rec.company_id.currency_id)
            rec.suma_eur_bepvm = suma

    @api.one
    @api.depends('tax_line_ids')
    def _get_imt_tax_rate(self):
        for l in self.tax_line_ids:
            for tag in l.tax_id.tag_ids:
                if tag.code == '15':
                    self.imt_tax_rate = int(l.tax_id.amount) if l.tax_id.amount else 0
                    return
        self.imt_tax_rate = 0

    @api.one
    @api.depends('tax_line_ids')
    def _get_imt_tax(self):
        for l in self.tax_line_ids:
            for tag in l.tax_id.tag_ids:
                if tag.code == '15':
                    self.imt_tax_amount = l.amount
                    return
        self.imt_tax_amount = 0.0

    @api.multi
    def invoice_print(self):
        self.ensure_one()
        self.sudo().sent = True
        return self.env['report'].get_action(self, 'saskaitos.report_invoice')

    @api.model
    def delete_invoice_report(self):
        try:
            self.env.ref('invoice.report_acc_invoice').unlink()
        except:
            pass
        try:
            self.env['ir.actions.report.xml'].search([('report_name', '=', 'account.report_invoice')]).unlink()
        except:
            pass
        try:
            self.env.ref('account.email_template_edi_invoice').unlink()
        except:
            pass

    @api.model
    def remove_invoice_registry_button(self):
        action = self.env.ref('saskaitos.account_invoice_registry_report', raise_if_not_found=False)
        if action:
            action.unlink_action()

    @api.model
    def get_isaf_report_date(self, date_invoice):
        isaf_day = self.env.user.sudo().company_id.isaf_default_day
        date_invoice_dt = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
        earliest_isaf_day, isaf_deadline_day = self.env.user.company_id.get_isaf_submission_earliest_and_deadline_days()
        isaf_date_from = (date_invoice_dt - relativedelta(day=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        isaf_date_to = (date_invoice_dt - relativedelta(day=31)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        isaf_export = self.sudo().env['vmi.document.export'].search([('doc_name', '=', 'iSAF'),
                                                                     '|',
                                                                         ('state', '=', 'confirmed'),
                                                                         ('state', '=', 'sent'),
                                                                     ('file_type', '=', 'xml'),
                                                                     ('document_date', '>=', isaf_date_from),
                                                                     ('document_date', '<=', isaf_date_to)], limit=1)
        if isaf_export:
            isaf_date = isaf_export.upload_date
            if isaf_date:
                isaf_date = datetime.strptime(isaf_date.split(' ')[0], tools.DEFAULT_SERVER_DATE_FORMAT)
                if earliest_isaf_day <= isaf_date.day <= isaf_deadline_day:
                    isaf_day = isaf_date.day - 1
        return isaf_day

    @api.model
    def check_isaf_report_submitted(self, date_invoice):
        date_invoice_dt = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
        isaf_date_from = (date_invoice_dt - relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        isaf_date_to = (date_invoice_dt - relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        isaf_export = self.sudo().env['vmi.document.export'].search([('doc_name', '=', 'iSAF'),
                                                                     '|',
                                                                         ('state', '=', 'confirmed'),
                                                                         ('state', '=', 'sent'),
                                                                     ('file_type', '=', 'xml'),
                                                                     ('document_date', '>=', isaf_date_from),
                                                                     ('document_date', '<=', isaf_date_to)], limit=1)
        return bool(isaf_export)

    @api.multi
    def compute_invoice_totals(self, company_currency, invoice_move_lines):
        # Method fully orverridden to replace try and use operacijos_data instead of date_invoice.
        total = 0
        total_currency = 0
        for line in invoice_move_lines:
            if self.currency_id != company_currency:
                date = self.operacijos_data or self.date_invoice or fields.Date.context_today(self)
                currency = self.currency_id.with_context(date=date)
                line['currency_id'] = currency.id
                line['amount_currency'] = currency.round(line['price'])
                line['price'] = currency.compute(line['price'], company_currency)
            else:
                line['currency_id'] = False
                line['amount_currency'] = False
                line['price'] = self.currency_id.round(line['price'])
            if self.type in ('out_invoice', 'in_refund'):
                total += line['price']
                total_currency += line['amount_currency'] or line['price']
                line['price'] = - line['price']
            else:
                total -= line['price']
                total_currency -= line['amount_currency'] or line['price']
        return total, total_currency, invoice_move_lines

    @api.multi
    def action_invoice_open(self):
        self.sudo().write({'validated_after_isaf': False,
                           'create_isaf_ticket': False})
        for rec in self:
            if 'out_' in rec.type and not rec.sudo().skip_isaf and \
                    any(code.startswith('PVM') for code in rec.mapped('tax_line_ids.tax_id.code')) \
                    and not self._context.get('skip_isaf_redeclaration'):
                isaf_submitted = rec.check_isaf_report_submitted(rec.date_invoice)
                if isaf_submitted:
                    rec.sudo().write({'validated_after_isaf': True,
                               'create_isaf_ticket': True})
            if rec.type in ['in_invoice', 'in_refund'] and not rec.force_dates and not rec.move_name:  # not self._context.get('skip_dates', False):
                date_invoice = operacijos_data = rec.date_invoice if rec.date_invoice else rec.operacijos_data
                date_invoice_dt = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
                passed_deadline = False
                isaf_day = self.get_isaf_report_date(date_invoice)
                fiscal_dates = self.env.user.company_id.compute_fiscalyear_dates(datetime.utcnow() - relativedelta(years=1))
                last_year1 = fiscal_dates['date_from'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                last_year2 = fiscal_dates['date_to'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                move_line_obj = self.sudo().env['account.move.line']
                closed_year = move_line_obj.search([('date', '>=', last_year1),
                                                    ('date', '<=', last_year2),
                                                    '|',
                                                    ('account_id.code', '=like', '5%'),
                                                    ('account_id.code', '=like', '6%'),
                                                    ('journal_id', '=', self.sudo().env.user.company_id.period_close_journal_id.id),
                                                    ('move_id.state', '=', 'posted')], count=True)
                last_year_records = move_line_obj.search([('date', '>=', last_year1),
                                                          ('date', '<=', last_year2),
                                                          ('move_id.state', '=', 'posted')], limit=1, count=True)
                invoice_type = rec.type
                if ((date_invoice <= last_year2 and not closed_year and last_year_records) or date_invoice > last_year2) and (
                         invoice_type in ['out_invoice', 'out_refund']):
                    registration_date = date_invoice
                else:
                    registration_date_dt = datetime.utcnow()
                    if date_invoice_dt < datetime(datetime.utcnow().year, 1, 1):

                        date_deadline = datetime(datetime.utcnow().year, 1, isaf_day)
                        if registration_date_dt > date_deadline and not closed_year and last_year_records:
                            passed_deadline = True

                        if date_invoice_dt < datetime(datetime.utcnow().year - 1, 12, 1):
                            passed_deadline = True

                    if passed_deadline:
                        operacijos_data = datetime(registration_date_dt.year - 1, 12, 31).strftime(
                            tools.DEFAULT_SERVER_DATE_FORMAT)
                        registration_date = operacijos_data
                    else:
                        date_invoice_d = datetime(date_invoice_dt.year, date_invoice_dt.month, date_invoice_dt.day)
                        registration_date = registration_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        registration_date_d = datetime(registration_date_dt.year, registration_date_dt.month,
                                                       registration_date_dt.day)
                        date_invoice_d_1 = date_invoice_d + relativedelta(day=1)
                        registration_date_d_1 = registration_date_d + relativedelta(day=1)
                        if date_invoice_d_1 == registration_date_d_1:
                            operacijos_data = date_invoice
                        elif (date_invoice_d_1 + relativedelta(
                                months=1)) == registration_date_d_1 and registration_date_d.day <= isaf_day:
                            operacijos_data = date_invoice
                        elif (date_invoice_d_1 + relativedelta(
                                months=1)) == registration_date_d_1 and registration_date_d.day > isaf_day:
                            operacijos_data = registration_date_d_1.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        elif (registration_date_d_1 - relativedelta(
                                months=1)) > date_invoice_d_1 and registration_date_d.day <= self.get_isaf_report_date((registration_date_d_1 - relativedelta(months=1)).strftime(
                                tools.DEFAULT_SERVER_DATE_FORMAT)):
                            operacijos_data = (registration_date_d_1 - relativedelta(months=1)).strftime(
                                tools.DEFAULT_SERVER_DATE_FORMAT)
                        elif (registration_date_d_1 - relativedelta(
                                months=1)) > date_invoice_d_1 and registration_date_d.day > self.get_isaf_report_date((registration_date_d_1 - relativedelta(months=1)).strftime(
                                tools.DEFAULT_SERVER_DATE_FORMAT)):
                            operacijos_data = registration_date_d_1.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                invoice_data = {
                    'date_invoice': operacijos_data,
                    'registration_date': registration_date,
                }
                rec.write(invoice_data)
            if (rec.date_invoice and datetime.strptime(rec.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT) <
                datetime.strptime(rec.operacijos_data, tools.DEFAULT_SERVER_DATE_FORMAT) and not rec.force_dates) \
                    or rec.state in ['proforma', 'proforma2']:
                rec.operacijos_data = rec.date_invoice

            # Registration date can never be lower than invoice date
            if rec.registration_date and rec.date_invoice and rec.type in ['in_invoice', 'in_refund']:
                reg_date_dt = datetime.strptime(rec.registration_date, tools.DEFAULT_SERVER_DATE_FORMAT)
                inv_date_dt = datetime.strptime(rec.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)

                # Always force registration date to date invoice if it's lower,
                # Ignoring the 'force_dates' boolean and other conditions
                if reg_date_dt < inv_date_dt:
                    rec.registration_date = rec.date_invoice

        return super(AccountInvoice, self).action_invoice_open()

    @api.multi
    def action_invoice_cancel(self):
        res = super(AccountInvoice, self).action_invoice_cancel()
        self.sudo().write({'validated_after_isaf': False,
                           'create_isaf_ticket': False})
        return res

    @api.multi
    def get_vat_payer_date(self):
        """Returns invoice date to check vat payer status against"""
        self.ensure_one()
        return self.operacijos_data or self.date_invoice


AccountInvoice()


class AccConfigSettings(models.TransientModel):
    _inherit = 'account.config.settings'

    group_proforma_invoices = fields.Boolean(default=True)


AccConfigSettings()


class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    gp = fields.Float(string='Gross Profit', compute='_gp', store=True, compute_sudo=True)
    cost = fields.Float(string='Cost', compute='_gp', store=True, compute_sudo=True)

    gp_invoice_date = fields.Float(string='Gross Profit (Month of invoice)', compute='_gp', store=True, compute_sudo=True)
    cost_invoice_date = fields.Float(string='Cost (Month of invoice)', compute='_gp', store=True, compute_sudo=True)

    no_stock_moves = fields.Boolean(string='Nėra susijusių sandėlio judėjimų', compute='_gp', store=True,
                                    lt_string='Nėra susijusių sandėlio judėjimų', compute_sudo=True)

    price_unit_tax_included_discount = fields.Float(compute='_compute_discount',
                                                    digits=dp.get_precision('Product Price'))
    price_unit_tax_included_discount_company = fields.Float(compute='_compute_discount',
                                                            digits=dp.get_precision('Product Price'))

    @api.one
    @api.depends('price_unit_tax_included', 'discount')
    def _compute_discount(self):
        self.price_unit_tax_included_discount = self.price_unit_tax_included / (1 - self.discount / 100.0)
        self.price_unit_tax_included_discount_company = self.price_unit_tax_included_company / (1 - self.discount / 100.0)

    @api.multi
    @api.depends('price_subtotal_signed', 'purchase_line_id.move_ids.state', 'invoice_id.state',
                 'sale_line_ids.procurement_ids.move_ids.state', 'product_id.type',
                 'sale_line_ids.procurement_ids.move_ids.non_error_quant_ids.cost',
                 'purchase_line_id.move_ids.non_error_quant_ids.cost',
                 'invoice_id.picking_id.move_lines.non_error_quant_ids.cost')
    def _gp(self):
        for line in self:
            if line.invoice_id.state in ['open', 'paid']:
                # Check whether invoice is of out type
                out_inv = line.invoice_id.type in ['out_invoice', 'out_refund']

                line_sudo = line.sudo()
                line.no_stock_moves = False
                # Revenue is only calculated on 'out' type invoices
                revenue = line.price_subtotal_signed if out_inv else 0.0
                if line.product_id.type == 'service':
                    line.gp = revenue
                    continue
                purchase_move_ids = line_sudo.mapped('purchase_line_id.move_ids').filtered(lambda r: r.state == 'done')
                sale_move_ids = line_sudo.mapped('sale_line_ids.procurement_ids.move_ids').filtered(lambda r: r.state == 'done')
                if purchase_move_ids:
                    move_ids = purchase_move_ids
                elif sale_move_ids:
                    move_ids = sale_move_ids
                elif line.invoice_id.picking_id:
                    # Left for historic data
                    move_ids = line_sudo.invoice_id.picking_id.move_lines.filtered(lambda r: r.state == 'done')
                    # Gather up all other related moves
                    move_ids |= self.env['stock.move'].search(
                        [('invoice_line_id', '=', line.id), ('state', '=', 'done')]
                    )
                else:
                    line.cost = 0.0
                    line.gp = revenue
                    line.no_stock_moves = True
                    continue
                product_move_ids = move_ids
                proportion = 1.0
                if line_sudo.invoice_id.picking_id:
                    product_move_ids = move_ids.filtered(lambda r: r.product_id == line.product_id)
                    # If there's no moves and current line has mapping and it's invoice type is 'in',
                    # search for moves with mapped product instead of the main one
                    if not product_move_ids and not out_inv:
                        product_move_ids = line.sudo().product_id.get_mapped_moves(
                            moves=move_ids,
                            partner=line.invoice_id.partner_id,
                        )
                    total_invoice_product_qty = sum(
                        line_sudo.invoice_id.invoice_line_ids.filtered(lambda r: r.product_id == line.product_id).mapped(
                            'quantity'))
                    if total_invoice_product_qty > 0:
                        proportion = line.quantity / float(total_invoice_product_qty)

                invoice_qty_proportion = 1.0
                sale_invoice_lines = line_sudo.mapped('sale_line_ids.invoice_lines').filtered(lambda r: r.invoice_id.state in ['open', 'paid'])
                if len(sale_invoice_lines) > 1:
                    total_invoice_product_qty = sum(line_sudo.mapped('sale_line_ids.invoice_lines').filtered(
                        lambda r: r.product_id == line.product_id).mapped('quantity'))
                    if total_invoice_product_qty > 0:
                        invoice_qty_proportion = line.quantity / float(total_invoice_product_qty)

                non_error_quant_recs = product_move_ids.mapped('non_error_quant_ids')
                cost = sum(q.cost * q.qty for q in non_error_quant_recs) * proportion * invoice_qty_proportion
                # Calculate cost at the date of the invoice by subtracting all valuation adjustments
                # that were done for this batch of non_error_quant_ids after the month of current invoice date
                adjusted_amount_after = 0.0

                invoice_date_dt = datetime.strptime(line.invoice_id.date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_end = (invoice_date_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                for quant in non_error_quant_recs:
                    adjustments = quant.valuation_adjustment_ids.filtered(
                        lambda x: x.cost_id.date > date_end
                        # or
                        # (x.cost_id.date < line.invoice_id.date_invoice and
                        #  x.cost_id.account_move_id.line_ids.filtered(lambda r: r.account_id.code
                        #  in ['6000'] and r.product_id.id == quant.product_id.id))
                        # TODO: LEFT FOR TESTING PURPOSES
                    )
                    adjusted_amount_after += sum(adjustments.mapped(
                        lambda x: x.additional_landed_cost / (x.quantity or 1) * quant.qty))
                cost_invoice_date = cost - adjusted_amount_after

                # Check whether revenue is positive or negative amount - other calculations depend on it
                sign = 1 if tools.float_compare(revenue, 0.0, precision_digits=0) >= 0 else -1
                line.cost = cost * sign
                line.cost_invoice_date = cost_invoice_date * sign
                # Only if invoice is of 'out' type we calculate gp
                if out_inv:
                    line.gp = revenue - line.cost
                    line.gp_invoice_date = revenue - line.cost_invoice_date


class ResCompany(models.Model):
    _inherit = 'res.company'

    proforma_show_price_vat_incl = fields.Boolean(string='Išankstinėse sąskaitose rodyti sumą su PVM')
    isaf_default_day = fields.Integer(string='iSAF pateikimo termino diena', default=19)

    @api.multi
    def get_isaf_submission_earliest_and_deadline_days(self):
        """ Returns the minimum and maximum possible iSAF term days of the month so it's not too early or too late """
        earliest_default, deadline_default = 10, 20
        try:
            earliest = int(self.env['ir.config_parameter'].sudo().get_param(
                'isaf.earliest_submission_day', default=str(earliest_default)
            ))
        except ValueError:
            earliest = earliest_default
        try:
            deadline = int(self.env['ir.config_parameter'].sudo().get_param(
                'isaf.default_deadline_day', default=str(deadline_default)
            ))
        except ValueError:
            deadline = deadline_default
        earliest, deadline = max(earliest, 1), max(deadline, 1)     # Make sure it's at least the first of the month
        deadline = min(deadline, deadline_default)                  # Make sure it doesn't exceed the iSAF term.
        return earliest, deadline

    @api.constrains('isaf_default_day')
    def _check_isaf_default_day(self):
        earliest_isaf_day, isaf_deadline_day = self.get_isaf_submission_earliest_and_deadline_days()
        for rec in self:
            if not rec.isaf_default_day or not (earliest_isaf_day <= rec.isaf_default_day <= isaf_deadline_day):
                raise exceptions.ValidationError(_(
                    'Neteisinga iSAF pateikimo termino diena. Termino diena turi būti tarp {} ir {} mėnesio dienos.'
                ).format(earliest_isaf_day, isaf_deadline_day))
