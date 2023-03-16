# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools import float_compare
from odoo.tools.translate import _

from six import iteritems


class fr0573Report(models.Model):
    _name = 'fr.0573.report'

    _order = 'partner_id'

    partner_id = fields.Many2one('res.partner', string='Darbuotojas', required=True)
    date = fields.Date(string='Data', required=True)
    original_date = fields.Date(string='Originali data', readonly=True)
    a_klase_kodas_id = fields.Many2one('a.klase.kodas', string='A klasės kodas')
    b_klase_kodas_id = fields.Many2one('b.klase.kodas', string='B klasės kodas')
    amount_bruto = fields.Float(string='Bruto')
    amount_neto = fields.Float(string='Neto')
    amount_npd = fields.Float(string='NPD')
    amount_pnpd = fields.Float(string='PNPD')
    amount_tax = fields.Float(string='GPM')
    amount_tax_paid = fields.Float(string='Sumokėtas GPM')
    gpm_for_responsible_person_amount = fields.Float(string='Išmokas išmokėjusio asmens lėšomis sumokėta GPM suma')
    foreign_paid_gpm_amount = fields.Float(string='Užsienio valstybėje sumokėta GPM suma')
    foreign_country_id = fields.Many2one('res.country', string='Užsienio valstybė')
    original_amount_bruto = fields.Float(string='Originalus Bruto', readonly=True)
    original_amount_neto = fields.Float(string='Originalus Neto', readonly=True)
    original_amount_npd = fields.Float(string='Originalus NPD', readonly=True)
    original_amount_tax = fields.Float(string='Originalus GPM', readonly=True)
    original_amount_tax_paid = fields.Float(string='Originalus Sumokėtas GPM', readonly=True)
    iki_15 = fields.Boolean(string='Iki 15 d', compute='_iki_15', store=True)
    document_type = fields.Selection([('payslip', 'Pagrindinis atlyginimas'),
                                      ('advance', 'Avansas'),
                                      ('holidays', 'Atostoginiai'),
                                      ('allowance', 'Dienpinigiai'),
                                      ('natura', 'Natūra'),
                                      ('imported', 'Importuota'),
                                      ('other', 'Kita'),
                                      ('own_expense', 'Savom lėšom')], string='Dokumento tipas')
    origin = fields.Char(string='Kilmės dokumentas')
    payslip_id = fields.Many2one('hr.payslip', string='Susijęs algalapis')
    correction = fields.Boolean(string='Koreguota eilutė')
    employer_payout = fields.Boolean(string='Darbdavio išmoka')
    payslip_amount_bruto = fields.Float(string='Algalapio Bruto', readonly=True)
    payslip_amount_neto = fields.Float(string='Algalapio Neto', readonly=True)
    payslip_amount_tax = fields.Float(string='Algalapio GPM', readonly=True)

    @api.onchange('date', 'partner_id', 'origin', 'document_type', 'amount_npd', 'amount_bruto',
                  'amount_neto', 'amount_tax', 'amount_tax_paid')
    def onchange_fields(self):
        self.correction = True

    @api.one
    @api.depends('date')
    def _iki_15(self):
        self.iki_15 = not self.date or datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT).day <= 15

    @api.model
    def get_gpm_account_ids(self):
        return self.env['account.account'].search([('code', 'in', ['4481', '4487'])]).ids

    @api.model
    def quick_create(self, vals):
        if not isinstance(vals, list):
            vals = [vals]

        if not vals:
            return

        columns = []
        for val in vals:
            for field in ['amount_bruto', 'amount_neto', 'amount_npd', 'amount_tax', 'amount_tax_paid', 'date']:
                if field in val:
                    val['original_' + field] = val.get(field)
        for val in vals:
            for k, v in iteritems(val):
                field = self._fields[k]
                if field.store and field.column_type and field.name not in columns:
                    columns.append(field.name)

        value_list = []
        for val in vals:
            if not val.get('partner_id', False):
                raise exceptions.UserError(_('Nenurodytas partneris %s') % val.get('origin', ''))
            if not val.get('a_klase_kodas_id'):
                continue  # PVZ sudengta su 0,01 apvalinimo sąnaudomis perkeliant duomenis
            for column in columns:
                column_value = val.get(column)
                column_type = self._fields[column].type
                # TODO FIX ME. This is not the best approach to create an SQL query
                if column_type == 'many2one' and not column_value:
                    column_value = None
                value_list.append(column_value)
        query = "INSERT INTO " + self._table + " (" + ', '.join(columns) + ") VALUES " + \
                ', '.join(['(' + ', '.join(['%s' for y in range(0, len(columns))]) + ')' for x in range(0, len(vals))])
        self._cr.execute(query, value_list)

    @api.model
    def get_report_values(self, amount_transaction, amounts_total, tot_tax_paid, npd_tot=0, pnpd_tot=0,
                          default_vals=None, payment=False, orig_date=False):
        tot_neto = amounts_total['neto']
        ratio = float(amount_transaction) / tot_neto if tot_neto > 0 else 0.0
        amount_tax = ratio * amounts_total['gpm']
        amount_bruto = ratio * amounts_total['bruto']
        if payment and len(payment.payment_line_ids) > 1 and orig_date:
            line = payment.payment_line_ids.filtered(lambda r: r.date_to == orig_date)
            if line:
                bruto, amount_tax = payment.with_context(force_payment_lines=line)._get_theoretical_gpm()
                line_ratio = amount_transaction / line.amount_paid
                amount_tax = line_ratio * amount_tax
                amount_bruto = line_ratio * bruto
        vals = {'amount_bruto': amount_bruto,
                'amount_npd': ratio * npd_tot,
                'amount_pnpd': ratio * pnpd_tot,
                'amount_tax': amount_tax,
                'amount_tax_paid': amount_tax,
                'amount_neto': amount_transaction,
                }
        if default_vals:
            vals.update(default_vals)
        date = vals.get('date', '')
        if date:
            vals['iki_15'] = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).day <= 15
        return vals

    @api.model
    def get_invoice_values(self, debt_lines):
        res = []
        invoices = debt_lines.mapped('invoice_id').filtered(lambda r: r.gpm_move)
        for invoice in invoices:
            line = invoice.gpm_move.line_ids.filtered(lambda r: r.a_klase_kodas_id)
            matched_debit_ids = invoice.move_id.line_ids.filtered(lambda r: r.a_klase_kodas_id).mapped(
                'matched_debit_ids.debit_move_id')
            matched_debit_ids_total_debit = sum(matched_debit_ids.mapped('debit'))
            for matched_debit_id in matched_debit_ids:
                ratio = matched_debit_id.debit / float(matched_debit_ids_total_debit)
                date_paid = matched_debit_id.date
                if not date_paid:
                    date_paid = line.date
                vals = {
                    'amount_bruto': abs(line.balance) * ratio,
                    'amount_npd': 0.0,
                    'amount_neto': 0.0,
                    'amount_pnpd': 0.0,
                    'amount_tax': abs(line.balance) * ratio,
                    'amount_tax_paid': abs(line.balance) * ratio,
                    'partner_id': invoice.partner_id.id,
                    'date': date_paid,
                    'a_klase_kodas_id': line.a_klase_kodas_id.id,
                    'document_type': 'own_expense',
                    'origin': invoice.reference,
                }
                if date_paid:
                    vals['iki_15'] = datetime.strptime(date_paid, tools.DEFAULT_SERVER_DATE_FORMAT).day <= 15
                res.append(vals)
        return res

    @api.model
    def get_imported_payslip_values(self, date_from, date_to, a_kodas_main, a_kodas_komand, employees=None):
        res = []
        domain = [
            ('state', '=', 'done'),
            ('date_from', '>=', date_from),
            ('date_from', '<=', date_to),
            ('imported', '=', True)
        ]
        if employees:
            domain.append(('employee_id', 'in', employees.ids))
        imported_payslips = self.env['hr.payslip'].search(domain)
        for payslip in imported_payslips:
            amount_with_tax = sum(payslip.line_ids.filtered(lambda r: r.code in ['MEN', 'VAL']).mapped('total')) - sum(
                payslip.line_ids.filtered(lambda r: r.code in ['AM']).mapped('total'))
            # amount_to_pay = sum(payslip.line_ids.filtered(lambda r: r.code in ['M']).mapped('total'))
            total_tax_amount = sum(payslip.line_ids.filtered(lambda r: r.code in ['GPM']).mapped('total'))
            pnpd = sum(payslip.line_ids.filtered(lambda r: r.code in ['PNPD']).mapped('total'))
            npd = sum(payslip.line_ids.filtered(lambda r: r.code in ['NPD']).mapped('total')) - pnpd
            amount_neto = sum(payslip.line_ids.filtered(lambda r: r.code in ['M']).mapped('total'))
            base_vals = {
                'partner_id': payslip.employee_id.address_home_id.id,
                'date': payslip.date_to,
                'document_type': 'imported',
                'origin': payslip.name,
                'amount_npd': 0,
                'amount_pnpd': 0,
                'amount_tax': 0,
                'amount_tax_paid': 0,
            }
            vals = base_vals.copy()
            vals.update({
                'a_klase_kodas_id': a_kodas_main,
                'amount_bruto': amount_with_tax,
                'amount_npd': npd,
                'amount_pnpd': pnpd,
                'amount_neto': amount_neto,
                'amount_tax': total_tax_amount,
                'amount_tax_paid': total_tax_amount,  # todo nebūtinai!
            })
            res.append(vals)
            amount_allowance = sum(payslip.line_ids.filtered(lambda r: r.code in ['NAKM']).mapped('total'))
            if float_compare(amount_allowance, 0, precision_digits=2) > 0:
                vals = base_vals.copy()
                vals.update({
                    'a_klase_kodas_id': a_kodas_komand,
                    'amount_bruto': amount_allowance,
                    'amount_neto': amount_allowance,
                })
                res.append(vals)
            for line in payslip.other_line_ids:
                vals = base_vals.copy()
                vals.update({
                    'a_klase_kodas_id': line.a_klase_kodas_id.id,
                    'amount_bruto': line.amount if line.type == 'priskaitymai' else 0.0,
                    'amount_neto': line.amount if line.type == 'priskaitymai' else -line.amount if line.type == 'gpm' else 0.0,
                    'amount_tax': line.amount if line.type == 'gpm' else 0.0,
                    'amount_tax_paid': line.amount if line.type == 'gpm' else 0.0,
                })
                res.append(vals)
        return res

    @api.model
    def get_fully_deducted_payslip_values(self, date_from, date_to, a_kodas_main, a_kodas_komand, employees=None):
        def line_total_by_code(lines, codes):
            if not isinstance(codes, list):
                codes = [codes]
            return sum(lines.filtered(lambda l: l.code in codes).mapped('total'))

        res = []
        domain = [
            ('state', '=', 'done'),
            ('date_from', '>=', date_from),
            ('date_from', '<=', date_to),
            ('imported', '=', False)
        ]
        if employees:
            domain.append(('employee_id', 'in', employees.ids))
        payslips = self.env['hr.payslip'].search(domain)
        for payslip in payslips:
            lines = payslip.line_ids
            deduction_amount = line_total_by_code(lines, 'IŠSK')
            if tools.float_is_zero(deduction_amount, precision_digits=2):
                continue
            to_pay_amount = line_total_by_code(lines, 'M')
            if tools.float_compare(to_pay_amount, deduction_amount, precision_digits=2) == 0:
                amount_with_tax = line_total_by_code(lines, ['MEN', 'VAL']) - line_total_by_code(lines, ['AM'])
                total_tax_amount = line_total_by_code(lines, ['GPM'])
                pnpd = line_total_by_code(lines, ['PNPD'])
                npd = line_total_by_code(lines, ['NPD'])

                date = payslip.date_to
                if payslip.contract_id.date_end and payslip.contract_id.date_end < date:
                    date = payslip.contract_id.date_end
                else:
                    date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    salary_payment_day = payslip.company_id.salary_payment_day or 15
                    date_dt += relativedelta(months=1, day=salary_payment_day)
                    date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                base_vals = {
                    'partner_id': payslip.employee_id.address_home_id.id,
                    'date': date,
                    'document_type': 'payslip',
                    'origin': payslip.name,
                    'amount_npd': 0,
                    'amount_pnpd': 0,
                    'amount_tax': 0,
                    'amount_tax_paid': 0,
                }
                vals = base_vals.copy()
                vals.update({
                    'a_klase_kodas_id': a_kodas_main,
                    'amount_bruto': amount_with_tax,
                    'amount_npd': npd,
                    'amount_pnpd': pnpd,
                    'amount_neto': to_pay_amount,
                    'amount_tax': total_tax_amount,
                    'amount_tax_paid': total_tax_amount,
                })
                res.append(vals)
                amount_allowance = line_total_by_code(lines, ['NAKM'])
                if float_compare(amount_allowance, 0, precision_digits=2) > 0:
                    vals = base_vals.copy()
                    vals.update({
                        'a_klase_kodas_id': a_kodas_komand,
                        'amount_bruto': amount_allowance,
                        'amount_neto': amount_allowance,
                    })
                    res.append(vals)
        return res

    @api.model
    def refresh_report(self, date_from, date_to, force=False, partner_ids=None, is_annual_declaration=False):
        # Check for existing report and if it does exist use it
        report_exists = self.search_count([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('correction', '=', True)
        ])
        if report_exists and not force:
            self.fill_payslip_amounts(date_from, date_to)
            return True

        # Refresh the report
        self._cr.execute('''DELETE FROM fr_0573_report where date >= %s and date <= %s''', (date_from, date_to))
        search_domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            '|',
            ('matched_debit_ids.debit_move_id.a_klase_kodas_id', '!=', False),
            ('matched_credit_ids.credit_move_id.a_klase_kodas_id', '!=', False)
        ]
        account_codes_only_included_in_annual_tax_declaration = ['4488']
        no_tax_transaction_account_codes = ['4488']

        if not is_annual_declaration:
            search_domain.append(('account_id.code', 'not in', account_codes_only_included_in_annual_tax_declaration))
        if partner_ids:
            # Pension fund transfers have pension funds as partners but the amounts should be assigned to the employee
            search_domain += [
                '|',
                ('matched_credit_ids.credit_move_id.move_id.pension_fund_transfer_id', '!=', False),
                ('partner_id', 'in', partner_ids)
            ]
        reconciled_with_a_klase = self.env['account.move.line'].search(search_domain)

        payslip_move_ids = self.env['hr.payslip'].search([
            ('move_id.line_ids', 'in', reconciled_with_a_klase.ids)
        ]).mapped('move_id')

        # Filter out payslip lines and tax institution payments
        reconciled_with_a_klase = reconciled_with_a_klase.filtered(lambda r: r.move_id.id not in payslip_move_ids.ids
                                                                             and not r.partner_id.mokesciu_institucija)
        # Filter out deductions
        deduction_lines = self.env['hr.employee.isskaitos'].search([
            ('move_id', 'in', reconciled_with_a_klase.mapped('move_id').ids)
        ]).mapped('move_id.line_ids')
        deduction_lines = reconciled_with_a_klase.filtered(lambda l: l.id in deduction_lines.ids)
        # Filter out by journal
        reconciled_with_a_klase = reconciled_with_a_klase.filtered(lambda r: r.journal_id.type in ['cash', 'bank'] or
                                                                             r.counterpart == '24450')

        # Get related lines
        debt_lines = reconciled_with_a_klase.mapped('matched_debit_ids.debit_move_id')
        debt_lines |= reconciled_with_a_klase.mapped('matched_credit_ids.credit_move_id')

        values_to_be_created = []
        aprs_komandiruotes_ids = []
        gpm_account_ids = self.get_gpm_account_ids()
        a_kodas_main = self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id
        a_kodas_komand = self.env.ref('l10n_lt_payroll.a_klase_kodas_4').id
        a_kodas_liga = self.env.ref('l10n_lt_payroll.a_klase_kodas_3').id
        a_kodas_du_before_2019 = self.env.ref('l10n_lt_payroll.a_klase_kodas_53').id

        # Gets the invoice values only
        values_to_be_created += self.get_invoice_values(debt_lines)

        partial_reconciles = reconciled_with_a_klase.mapped('matched_credit_ids') | \
                             reconciled_with_a_klase.mapped('matched_debit_ids')
        all_moves = self.env['account.move']
        for partial_reconcile in partial_reconciles:
            if partial_reconcile.credit_move_id.a_klase_kodas_id:
                all_moves |= partial_reconcile.credit_move_id.move_id
            elif partial_reconcile.debit_move_id.a_klase_kodas_id:
                all_moves |= partial_reconcile.debit_move_id.move_id

        reconciled_with_a_klase |= deduction_lines
        for account_move_line in reconciled_with_a_klase:
            move_line_partial_reconciles = account_move_line.matched_credit_ids | account_move_line.matched_debit_ids
            for apr in move_line_partial_reconciles:  # account.partial.reconcile
                # Find the original account move line
                if apr.credit_move_id.a_klase_kodas_id:
                    orig_aml = apr.credit_move_id
                    sign = 1
                elif apr.debit_move_id.a_klase_kodas_id:
                    orig_aml = apr.debit_move_id
                    sign = -1
                else:
                    continue

                # Skip if it's related to business trip (for now, handle it later)
                if orig_aml.a_klase_kodas_id.id == a_kodas_komand:
                    aprs_komandiruotes_ids.append(apr.id)
                    continue

                # Ensure each entry has a partner
                partner_id = account_move_line.partner_id.id
                if not partner_id:
                    aml = account_move_line
                    msg = _('Įrašas "{0}" [{1} {2} {3}] neturi nurodyto partnerio!')
                    msg = msg.format(aml.name, aml.move_id.name, aml.move_id.ref, aml.move_id.date)
                    raise exceptions.UserError(msg)

                amount_paid = sign * apr.amount

                date_to_use = account_move_line.date

                pension_fund_transfers = account_move_line.mapped(
                    'matched_credit_ids.credit_move_id.move_id.pension_fund_transfer_id'
                )

                if account_move_line in deduction_lines:
                    # All the taxes are calculated with the payslip move line calculations. This is used just to show
                    # the deduction amount in report for accountants. Does not impact the report itself due to the NETO
                    # amounts not having impact in the report.
                    values_to_be_created.append({
                        'partner_id': partner_id,
                        'date': orig_aml.date,
                        'a_klase_kodas_id': a_kodas_main,
                        'document_type': 'other',
                        'origin': _('Išskaita'),
                        'amount_bruto': 0.0,
                        'amount_npd': 0.0,
                        'amount_pnpd': 0.0,
                        'amount_tax': 0.0,
                        'amount_tax_paid': 0.0,
                        'amount_neto': amount_paid,
                    })
                    continue
                elif account_move_line.account_code in no_tax_transaction_account_codes:
                    # Untaxed dynamic workplace compensations should go to the declaration as is without any tax
                    # calculations
                    values_to_be_created.append({
                        'partner_id': partner_id,
                        'date': date_to_use,
                        'a_klase_kodas_id': orig_aml.a_klase_kodas_id.id,
                        'document_type': 'other',
                        'origin': account_move_line.account_id.name,
                        'amount_bruto': amount_paid,
                        'amount_npd': 0.0,
                        'amount_pnpd': 0.0,
                        'amount_tax': 0.0,
                        'amount_tax_paid': 0.0,
                        'amount_neto': amount_paid,
                    })
                    continue
                elif pension_fund_transfers:
                    # Pension funds have pension funds as the partner but should go to the employee in the declaration
                    pension_fund_transfer = pension_fund_transfers[0]
                    partner = pension_fund_transfer.employee_id.address_home_id
                    if partner_ids and partner.id not in partner_ids:
                        continue

                    values_to_be_created.append({
                        'partner_id': partner.id,
                        'date': orig_aml.date,
                        'a_klase_kodas_id': orig_aml.a_klase_kodas_id.id,
                        'document_type': 'other',
                        'origin': pension_fund_transfer._get_transfer_purpose(),
                        'amount_bruto': amount_paid,
                        'amount_npd': 0.0,
                        'amount_pnpd': 0.0,
                        'amount_tax': 0.0,
                        'amount_tax_paid': 0.0,
                        'amount_neto': amount_paid,
                    })
                    continue

                a_klase_amounts = self.env['e.vmi.fr0572'].get_a_klase_amounts(orig_aml.move_id, gpm_account_ids)

                bruto, neto, gpm, gpm_paid, npd, pnpd = (a_klase_amounts[k] for k in
                                                         ['bruto', 'neto', 'gpm', 'gpm_paid', 'npd', 'pnpd'])

                amounts_total = {'bruto': bruto, 'neto': neto, 'gpm': gpm}
                if not tools.float_is_zero(neto, precision_digits=2):
                    amounts_total.update({
                        'neto': neto - a_klase_amounts.get('other_untaxed_amounts_that_are_not_declared', 0.0)
                    })

                default_vals = {
                    'partner_id': partner_id,
                    'date': date_to_use,
                    'a_klase_kodas_id': orig_aml.a_klase_kodas_id.id,
                    'document_type': a_klase_amounts.get('document_type', ''),
                    'origin': a_klase_amounts.get('origin', ''),
                    'payslip_id': a_klase_amounts.get('payslip_id', False)
                }

                # Switch A class code from 01 (DU related) to 04 if the payment date is after Jan 1st 2019 but the
                # payment was for 2018
                if orig_aml.a_klase_kodas_id.id == a_kodas_main and default_vals.get('date') >= '2019-01-01':
                    date_to_period = False
                    if default_vals.get('payslip_id'):
                        payslip = self.env['hr.payslip'].browse(default_vals.get('payslip_id'))
                        date_to_period = payslip.date_to
                    elif a_klase_amounts.get('payment'):
                        date_to_period = a_klase_amounts.get('payment').date_to

                    if date_to_period and '2018-01-01' <= date_to_period < '2019-01-01':
                        default_vals['a_klase_kodas_id'] = a_kodas_du_before_2019

                payment = a_klase_amounts.get('payment', False)
                rep_vals = self.get_report_values(amount_paid, amounts_total, gpm_paid, npd_tot=npd, pnpd_tot=pnpd,
                                                      default_vals=default_vals, payment=payment, orig_date=orig_aml.date)

                if a_klase_amounts.get('payslip_id'):
                    payslip = self.env['hr.payslip'].browse(a_klase_amounts['payslip_id'])

                    # Check that there's a payment on the payslip
                    neto = payslip.neto_for_reports
                    if tools.float_compare(neto, 0.0, precision_digits=2) <= 0:
                        values_to_be_created.append(rep_vals)
                        continue

                    # Check if natura or liga exists
                    natura = sum(payslip.line_ids.filtered(lambda r: r.code in ['NTR']).mapped('total'))
                    natura_employer_pays_tax = sum(payslip.line_ids.filtered(lambda r: r.code in ['NTRD']).mapped('total'))
                    liga = a_klase_amounts.get('liga', 0.0)
                    natura_is_zero = tools.float_is_zero(natura, precision_digits=2)
                    liga_is_zero = tools.float_is_zero(liga, precision_digits=2)
                    if natura_is_zero and liga_is_zero:
                        values_to_be_created.append(rep_vals)
                        continue

                    # Grab the tax rates
                    tax_rates = payslip.contract_id.with_context(
                        date=payslip.date_to, dont_check_is_tax_free=True
                    ).get_payroll_tax_rates(['gpm_proc', 'gpm_ligos_proc'])
                    gpm_proc = tax_rates['gpm_proc'] / 100.0
                    gpm_ligos_proc = tax_rates['gpm_ligos_proc'] / 100.0

                    neto -= a_klase_amounts.get('other_untaxed_amounts_that_are_not_declared', 0.0)

                    # Create separate natura entry
                    if not natura_is_zero:
                        natura_employee_pays_tax = max(natura - natura_employer_pays_tax, 0.0)

                        natura_employee_ratio = natura_employee_pays_tax / float(natura)
                        natura_employer_ratio = natura_employer_pays_tax / float(natura)

                        natura_paid = natura_employee_pays_tax * amount_paid * natura_employee_ratio / neto
                        natura_npd = a_klase_amounts.get('natura_npd', 0.0)
                        max_npd_to_use = natura_employee_ratio * natura_npd
                        natura_npd_to_use = min(max_npd_to_use, natura_employee_pays_tax)
                        leftover_npd = max(max_npd_to_use - natura_npd_to_use, 0.0)
                        gpm_nat = max(0.0, (natura_employee_pays_tax - natura_npd_to_use)) * gpm_proc
                        gpm_paid_nat = natura_paid * gpm_proc
                        amounts_total = {'bruto': natura, 'neto': natura, 'gpm': gpm_nat}
                        default_vals.update({'document_type': 'natura'})
                        if not tools.float_is_zero(natura_paid, precision_digits=2):
                            natura_rep_vals = self.get_report_values(natura_paid, amounts_total, gpm_paid_nat,
                                                              default_vals=default_vals)

                            # Move benefit in kind income tax to report values
                            rep_vals['amount_tax'] += natura_rep_vals.get('amount_tax', 0.0)
                            natura_rep_vals['amount_tax'] = 0.0

                            values_to_be_created.append(natura_rep_vals)
                        if not tools.float_is_zero(natura_employer_pays_tax, precision_digits=2):
                            natura_paid = natura_employer_pays_tax * amount_paid * natura_employer_ratio / neto
                            max_npd_to_use = natura_employer_ratio * natura_npd + leftover_npd
                            natura_npd_to_use = min(max_npd_to_use, natura_employer_pays_tax)
                            gpm_nat = max(0.0, (natura_employer_pays_tax - natura_npd_to_use)) * gpm_proc
                            gpm_paid_nat = natura_paid * gpm_proc
                            amounts_total = {'bruto': natura, 'neto': natura, 'gpm': gpm_nat}
                            default_vals.update({'document_type': 'natura'})
                            if not tools.float_is_zero(natura_paid, precision_digits=2):
                                natura_rep_vals = self.get_report_values(natura_paid, amounts_total, gpm_paid_nat,
                                                                  default_vals=default_vals)
                                # Add natura amount tax to report values rather than the natura line
                                natura_amount_tax = natura_rep_vals.get('amount_tax', 0.0)
                                natura_rep_vals['gpm_for_responsible_person_amount'] = 0.0
                                natura_rep_vals['amount_tax_paid'] = 0.0
                                # Set zero amount tax and move the tax to payslip income tax for responsible person
                                # amount only for the annual declaration
                                if is_annual_declaration:
                                    natura_rep_vals['amount_tax'] = 0.0
                                    rep_vals['gpm_for_responsible_person_amount'] = \
                                        rep_vals.get('gpm_for_responsible_person_amount', 0.0) + natura_amount_tax
                                values_to_be_created.append(natura_rep_vals)
                    # Create separate illness entry
                    if not liga_is_zero:
                        liga_paid = liga * amount_paid / neto
                        liga_npd = a_klase_amounts.get('liga_npd', 0.0)
                        gpm_lig = max(0.0, (liga - liga_npd)) * gpm_ligos_proc
                        gpm_paid_lig = liga_paid * gpm_ligos_proc
                        amounts_total = {'bruto': liga, 'neto': liga, 'gpm': gpm_lig}
                        default_vals.update({
                            'document_type': 'payslip',
                            'a_klase_kodas_id': a_kodas_liga,
                            'origin': default_vals.get('origin', '') + ' nedarbingumas'
                        })
                        illness_rep_vals = self.get_report_values(liga_paid, amounts_total, gpm_paid_lig,
                                                          default_vals=default_vals)
                        illness_rep_vals['amount_neto'] = 0.0
                        values_to_be_created.append(illness_rep_vals)
                values_to_be_created.append(rep_vals)
        apr_payslip_map = {}
        payment_payslip_map = {}
        mb_payment_apr_map = {}

        # Handle business trips
        for apr_id in aprs_komandiruotes_ids:
            payment = self.env['hr.employee.payment'].search([
                '|',
                ('account_move_id.line_ids.matched_debit_ids', 'in', apr_id),
                ('account_move_ids.line_ids.matched_debit_ids', 'in', apr_id)
            ], limit=1)
            if payment:
                if payment.id in payment_payslip_map:
                    apr_payslip_map[apr_id] = payment_payslip_map[payment.id]
                else:
                    payslip = self.env['hr.payslip'].search([
                        ('employee_id', '=', payment.employee_id.id),
                        ('date_from', '=', payment.date_from),
                        ('state', '=', 'done')
                    ], limit=1)
                    if payslip:
                        payment_payslip_map[payment.id] = payslip.id
                        apr_payslip_map[apr_id] = payslip.id
                    elif payment.employee_id.type == 'mb_narys':
                        payment_aprs = mb_payment_apr_map.get(payment.id, [])
                        payment_aprs.append(apr_id)
                        mb_payment_apr_map[apr_id] = payment_aprs

        payslip_apr_map = {}
        non_payslip_apr_ids = []

        for apr_id, payslip_id in iteritems(apr_payslip_map):
            if payslip_id:
                payslip_apr_map.setdefault(payslip_id, []).append(apr_id)
            else:
                non_payslip_apr_ids.append(apr_id)

        for payment_id, apr_ids in iteritems(mb_payment_apr_map):
            aprs = self.env['account.partial.reconcile'].browse(apr_ids)  # account.partial.reconcile
            aprs = aprs.sorted(lambda r: r.debit_move_id.move_id.date)
            payment = self.env['hr.employee.payment'].browse(payment_id)

            for apr in aprs:
                if apr.credit_move_id.a_klase_kodas_id:
                    amount_non_taxable = apr.amount
                    payment_move = apr.debit_move_id
                    orig_move = apr.credit_move_id
                else:
                    amount_non_taxable = -apr.amount
                    payment_move = apr.credit_move_id
                    orig_move = apr.debit_move_id
                amounts_total = {
                    'bruto': amount_non_taxable,
                    'neto': amount_non_taxable,
                    'gpm': 0
                }
                default_vals = {
                    'partner_id': apr.credit_move_id.partner_id.id,
                    'date': payment_move.date,
                    'a_klase_kodas_id': a_kodas_komand,
                    'document_type': 'allowance',
                    'origin': orig_move.ref or '',
                }
                vals = self.get_report_values(amount_non_taxable, amounts_total, 0, npd_tot=0, pnpd_tot=0,
                                              default_vals=default_vals)
                values_to_be_created.append(vals)

        for payslip_id in payslip_apr_map:
            payslip = self.env['hr.payslip'].browse(payslip_id)
            dp_lines = payslip.line_ids.filtered(lambda l: l.code == 'DP')
            nakm_lines = payslip.line_ids.filtered(lambda l: l.code == 'NAKM')
            km_lines = payslip.line_ids.filtered(lambda l: l.code == 'KM')
            amount_nakm = sum(nakm_lines.mapped('total'))
            original_amount_nakm = amount_nakm
            amount_km = sum(km_lines.mapped('total'))
            original_amount_km = amount_km
            amount_dp = sum(dp_lines.mapped('total'))
            whole_payslip_allowance_amount_is_untaxed = tools.float_compare(
                amount_km, amount_nakm, precision_digits=2
            ) == 0

            all_allowance_payments = self.env['hr.employee.payment'].search([
                ('date_from', '=', payslip.date_from),
                ('employee_id', '=', payslip.employee_id.id),
                ('a_klase_kodas_id', '=', a_kodas_komand)
            ])

            all_aprs = self.env['account.partial.reconcile'].search([
                ('credit_move_id.move_id', 'in', (all_allowance_payments.mapped('account_move_id') |
                                                  all_allowance_payments.mapped('account_move_ids')).ids)
            ])

            all_apr_ids = set(all_aprs.ids)
            aprs_in_report = payslip_apr_map[payslip_id]
            if any(apr_id not in all_apr_ids for apr_id in aprs_in_report):
                raise exceptions.UserError(_('Nerastas mokėjimas. Kreipkitės į sistemos administratorių'))

            all_aprs = all_aprs.sorted(lambda r: r.debit_move_id.move_id.date)
            # Sort by amount closest to the untaxed allowance amount so that if a single allowance is on payslip (where
            # multiple allowances exist) - hopefully a full amount of one of the apr amounts will be used to calculate
            # based on the untaxed amount rather than partial.
            # Example: 45 EUR untaxed allowance on payslip, 3 APRS with amounts [75, 45, 30] - first use the APR
            # of 45 EUR to set that all of the untaxed allowance from payslip has been used for this APR and then when
            # creating values for the [75, 30] APR amounts no untaxed amount will be found on payslip hence it will be
            # determined that the full APR amount is untaxed.
            for apr in all_aprs.sorted(key=lambda a: abs(amount_nakm - a.amount)):
                if apr.credit_move_id.a_klase_kodas_id:  # todo order matters
                    nakm_used = amount_nakm
                    # Either no payslip or amounts not in payslip (still 0.0)
                    if tools.float_is_zero(amount_nakm, precision_digits=2) and \
                            tools.float_is_zero(amount_dp, precision_digits=2) and \
                            whole_payslip_allowance_amount_is_untaxed:
                        nakm_used = apr.amount
                    amount_non_taxable = min(apr.amount, nakm_used)
                    payment_move = apr.debit_move_id
                    orig_move = apr.credit_move_id
                else:
                    amount_non_taxable = -apr.amount
                    payment_move = apr.credit_move_id
                    orig_move = apr.debit_move_id
                amount_nakm -= amount_non_taxable
                amount_nakm = max(amount_nakm, 0.0)
                if apr.id in aprs_in_report:
                    amounts_total = {
                        'bruto': amount_non_taxable,
                        'neto': amount_non_taxable,
                        'gpm': 0
                    }
                    default_vals = {
                        'partner_id': apr.credit_move_id.partner_id.id,
                        'date': payment_move.date,
                        'a_klase_kodas_id': a_kodas_komand,
                        'document_type': 'allowance',
                        'origin': orig_move.ref or '',
                    }
                    vals = self.get_report_values(amount_non_taxable, amounts_total, 0, npd_tot=0, pnpd_tot=0,
                                                  default_vals=default_vals)
                    values_to_be_created.append(vals)
                    amount_taxable = apr.amount - amount_non_taxable
                    if tools.float_compare(amount_taxable, 0, precision_digits=2) > 0:
                        existing_payslip_values = [
                            values for values in values_to_be_created if values.get('payslip_id') == payslip.id and
                                                                         values.get('document_type') == 'payslip'
                        ]
                        total_payslip_bruto_for_declaration = sum(existing_val.get('amount_bruto') for existing_val in existing_payslip_values)
                        total_payslip_neto_for_declaration = sum(existing_val.get('amount_neto') for existing_val in existing_payslip_values)
                        a_klase_amounts = self.env['e.vmi.fr0572'].get_payslip_amounts(payslip, gpm_account_ids)
                        total_amount, amount_to_pay, total_amount_tax, gpm_paid, npd, pnpd = (a_klase_amounts[k] for k
                                                                                              in
                                                                                              ['bruto', 'neto', 'gpm',
                                                                                               'gpm_paid', 'npd',
                                                                                               'pnpd'])

                        # Since the entire taxable allowance has been paid, the payslip total payable amount is the NET
                        # amount plus the taxable allowance that's been paid. Untaxed allowance is not included in the
                        # report
                        amount_to_pay += original_amount_km - original_amount_nakm

                        # The allowance was paid with the payslip payment and a separate value should not be created
                        bruto_declared_with_payslip_difference = total_payslip_bruto_for_declaration - total_amount
                        neto_declared_with_payslip_difference = total_payslip_neto_for_declaration - amount_to_pay
                        if tools.float_is_zero(bruto_declared_with_payslip_difference, precision_digits=2) and \
                            tools.float_is_zero(neto_declared_with_payslip_difference, precision_digits=2):
                            continue

                        amounts_total = {'bruto': total_amount,
                                         'neto': amount_to_pay,
                                         'gpm': total_amount_tax}
                        amount_paid = amount_taxable
                        default_vals = {'partner_id': apr.credit_move_id.partner_id.id,
                                        'date': payment_move.date,
                                        'a_klase_kodas_id': a_kodas_main,
                                        'document_type': 'allowance',
                                        'origin': orig_move.ref or '',
                                        }
                        vals = self.get_report_values(amount_paid, amounts_total, gpm_paid, npd_tot=npd, pnpd_tot=pnpd,
                                                      default_vals=default_vals)
                        values_to_be_created.append(vals)

                        # Remove taxable allowance amount from payslip amounts so the values are not in both.
                        keys_to_subtract = ['amount_npd', 'amount_tax', 'amount_neto', 'amount_bruto', 'amount_tax_paid']
                        values_to_subtract = {key: vals.get(key) for key in keys_to_subtract}
                        for existing_payslip_value in existing_payslip_values:
                            if existing_payslip_value.get('a_klase_kodas_id') != a_kodas_main:
                                continue  # Only subtract from payroll related values.
                            for key, amount in iteritems(values_to_subtract):
                                amount_to_subtract = min(
                                    existing_payslip_value.get(key, 0.0), values_to_subtract.get(key, 0.0)
                                )
                                values_to_subtract[key] -= amount_to_subtract
                                existing_payslip_value[key] -= amount_to_subtract

        for apr in self.env['account.partial.reconcile'].browse(non_payslip_apr_ids):
            if apr.credit_move_id.a_klase_kodas_id:
                sign = 1
                payment_move = apr.debit_move_id
                orig_move = apr.credit_move_id
            elif apr.debit_move_id.a_klase_kodas_id:
                sign = -1
                payment_move = apr.credit_move_id
                orig_move = apr.debit_move_id
            else:
                continue
            vals = {
                'partner_id': apr.credit_move_id.partner_id.id,
                'date': payment_move.date,
                'a_klase_kodas_id': a_kodas_komand,
                'amount_bruto': sign * apr.amount,
                'amount_neto': sign * apr.amount,
                'amount_npd': 0,
                'amount_pnpd': 0,
                'amount_tax': 0,
                'amount_tax_paid': 0,
                'document_type': 'allowance',
                'origin': orig_move.ref,
            }
            values_to_be_created.append(vals)

        # Get advance payments based on darbo.avansas records. Ignore the factual payment due to the changed
        # functionality of advance payments
        # Advance payments from last month
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_tom_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        advance_period_from_dt = date_from_dt + relativedelta(months=-1, day=1)
        advance_period_to_dt = date_tom_dt + relativedelta(months=-1, day=31)
        advance_period_from = advance_period_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        advance_period_to = advance_period_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        domain = [
            ('state', '=', 'done'),
            ('date_from', '<=', advance_period_to),
            ('date_to', '>=', advance_period_from),
        ]
        employees = None
        if partner_ids:
            employees = self.env['res.partner'].browse(partner_ids).with_context(active_test=False).mapped('employee_ids')
            domain.append(('employee_id', 'in', employees.ids))
        advances_for_last_month = self.env['darbo.avansas'].search(domain)

        base_advance_vals = {
            'a_klase_kodas_id': a_kodas_main,
            'document_type': 'advance',
        }

        bad_advance_records = self.env['darbo.avansas']

        for advance in advances_for_last_month:
            advance_vals = base_advance_vals.copy()

            advance_date_from_dt = datetime.strptime(advance.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_month_after_advance = advance_date_from_dt + relativedelta(months=1)

            move_lines = advance.mapped('account_move_id.line_ids.matched_credit_ids.credit_move_id')
            move_lines |= advance.mapped('account_move_id.line_ids.matched_debit_ids.debit_move_id')
            move_lines = move_lines.mapped('move_id.line_ids')
            move_line_matched_lines = move_lines.mapped('matched_credit_ids.credit_move_id') + \
                                      move_lines.mapped('matched_debit_ids.debit_move_id')
            journals = move_line_matched_lines.mapped('journal_id')
            journal_types = journals.mapped('type')
            if not any(journal_type in ['cash', 'bank'] for journal_type in journal_types):
                bad_advance_records |= advance
                continue

            advance_vals.update({
                'date': next_month_after_advance.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'partner_id': advance.employee_id.address_home_id.id,
                'origin': advance.name,
            })
            income_tax = advance.theoretical_gpm

            advance_slip = self.env['hr.payslip'].search([
                ('employee_id', '=', advance.employee_id.id),
                ('date_from', '<=', advance.date_to),
                ('date_to', '>=', advance.date_from),
            ], limit=1)
            if advance_slip:
                amounts_total = {
                    'bruto': sum(advance_slip.line_ids.filtered(lambda r: r.code in ['BRUTON']).mapped('total')),
                    'neto': sum(advance_slip.line_ids.filtered(lambda r: r.code in ['NET']).mapped('total')),
                    'gpm': sum(advance_slip.line_ids.filtered(lambda r: r.code in ['GPM']).mapped('total'))
                }
                rep_vals = self.get_report_values(advance.suma, amounts_total, income_tax,
                                                  default_vals=advance_vals, orig_date=advance.operation_date)
                values_to_be_created.append(rep_vals)
                continue

            advance_vals.update({
                'amount_bruto': advance.theoretical_bruto,
                'amount_neto': advance.suma,
                'amount_tax': income_tax,
                'amount_tax_paid': income_tax,
                'amount_npd': 0.0,
                'amount_pnpd': 0.0,
            })
            values_to_be_created.append(advance_vals)

        if bad_advance_records:
            try:
                ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
                subject = 'Generuojant GPM ataskaitą buvo rasti galimai neapmokėti avansų įrašai [%s]' % self._cr.dbname
                body = """Generuojant GPM deklaraciją kai kuriems darbuotojams buvo įtraukti avansų įrašai, kurie 
                galimai nėra apmokėti, nes nei viena iš avanso žurnalo įrašo sudengtų eilučių neturi žurnalo, kurio 
                tipas būtų "Grynieji" arba "Bankas". Šie avansai buvo įtraukti į GPM deklaraciją, tačiau reikėtų 
                peržiūrėti, ar jie tikrai buvo išmokėti. Jei manote, kad šis pranešimas neteisingas - informuokite 
                support@robolabs.lt.\n\nĮtraukti, bet galimai nesumokėti avansai:\n\n"""

                err_str = ''
                for advance in bad_advance_records:
                    err_str += 'Darbuotojui {} nuo {} iki {} ({}) \n'.format(
                        advance.employee_id.name,
                        advance.date_from,
                        advance.date_to,
                        advance.operation_date
                    )

                body += err_str

                vals = {
                    'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'ticket_record_id': False,
                    'name': subject,
                    'ticket_user_login': self.env.user.login,
                    'ticket_user_name': self.env.user.name,
                    'description': body,
                    'ticket_type': 'accounting',
                    'user_posted': self.env.user.name
                }

                res = ticket_obj.create_ticket(**vals)
                if not res:
                    raise exceptions.UserError('The distant method did not create the ticket.')
            except Exception as e:
                message = 'Failed to create ticket for advance sanity check.\nException: %s' % (str(e.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

        values_to_be_created += self.get_imported_payslip_values(date_from, date_to, a_kodas_main, a_kodas_komand,
                                                                 employees=employees)
        values_to_be_created += self.get_fully_deducted_payslip_values(advance_period_from, advance_period_to,
                                                                       a_kodas_main, a_kodas_komand,
                                                                       employees=employees)

        self.quick_create(values_to_be_created)
        self.fill_payslip_amounts(date_from, date_to)

    @api.model
    def fill_payslip_amounts(self, date_from, date_to):
        self.search([('date', '>=', date_from), ('date', '<=', date_to)]).write({
            'payslip_amount_bruto': 0,
            'payslip_amount_neto': 0,
            'payslip_amount_tax': 0,
        })
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt += relativedelta(day=1)
        date_to_dt += relativedelta(day=1)
        self.env.cr.execute('select DISTINCT(partner_id) from fr_0573_report where date >= %s and date <= %s',
                            (date_from, date_to,))
        res = self.env.cr.dictfetchall()
        partner_ids = []
        for row in res:
            if row.get('partner_id'):
                partner_ids.append(row.get('partner_id'))
        while date_from_dt <= date_to_dt:
            search_payslip_date_from = (date_from_dt - relativedelta(months=1, day=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            search_date_from = (date_from_dt - relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            search_date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            for partner_id in partner_ids:
                payslips = self.env['hr.payslip'].search(
                    [('date_from', '=', search_payslip_date_from), ('employee_id.address_home_id', '=', partner_id),
                     ('state', '=', 'done')], limit=1)
                payslips |= self.env['hr.payslip'].search(
                    [('date_from', '=', search_date_from), ('employee_id.address_home_id', '=', partner_id),
                     ('state', '=', 'done'), ('employee_is_being_laid_off', '=', True)], limit=1)
                for payslip in payslips:
                    line = self.search([('date', '>=', search_date_from), ('date', '<=', search_date_to),
                                        ('payslip_id', '=', payslip.id)], limit=1)
                    if not line:
                        line = self.search([('date', '>=', search_date_from), ('date', '<=', search_date_to)], limit=1)
                    if line:
                        payslip_bruto = self.env['hr.payslip.line'].search(
                            [('slip_id', '=', payslip.id), ('code', 'in', ['MEN', 'VAL'])], limit=1).amount
                        payslip_neto = sum(self.env['hr.payslip.line'].search(
                            [('slip_id', '=', payslip.id), ('code', 'in', ['BENDM', 'AVN', 'IŠSK'])]).mapped('amount'))
                        payslip_gpm = self.env['hr.payslip.line'].search(
                            [('slip_id', '=', payslip.id), ('code', '=', 'GPM')], limit=1).amount
                        line.write({
                            'payslip_amount_bruto': payslip_bruto,
                            'payslip_amount_neto': payslip_neto,
                            'payslip_amount_tax': payslip_gpm,
                        })
            date_from_dt += relativedelta(months=1)


fr0573Report()
