# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions, _
from odoo.addons.sepa import api_bank_integrations as abi
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    info_type = fields.Selection(
        [('unstructured', 'Nestruktūruota'), ('structured', 'Struktūruota')],
        default='unstructured', string='Mokėjimo paskirties struktūra', required=True,
    )
    sepa_instruction_id = fields.Char(
        inverse='_inverse_sepa_instruction_id',
        string='Sepa Instruction id', readonly=True, copy=False,
    )
    sepa_duplicate = fields.Boolean(string='Duplicate', default=False)
    entry_reference = fields.Char(string='Statement reference')
    commission_of_id = fields.Many2one('account.bank.statement.line', string='Commission of')
    family_code = fields.Char(string='Family code')
    sub_family_code = fields.Char(string='Sub family code')
    is_fee = fields.Boolean(string='Is fee', inverse='_inverse_sepa_instruction_id')
    imported_partner_name = fields.Char(string='Importuotas partnerio pavadinimas', readonly=True)
    imported_partner_code = fields.Char(string='Importuotas partnerio kodas', readonly=True)
    imported_partner_iban = fields.Char(string='Importuota partnerio banko sąskaita', readonly=True)
    invoice_ids = fields.Many2many('account.invoice', string='Susijusios sąskaitos faktūros')
    aml_ids = fields.Many2many('account.move.line', string='Susiję žurnalo įrašai')
    reconciled = fields.Boolean(compute='_reconciled', string='Sudengta')
    post_export_residual = fields.Float(string='Menamas susijusios sąskaitos likutis po banko eksporto')

    ultimate_debtor_id = fields.Many2one('res.partner', string='Pradinis mokėtojas')
    sepa_imported = fields.Boolean(compute='_compute_sepa_imported')

    # Bank export data fields
    bank_export_job_ids = fields.One2many(
        'bank.export.job', 'bank_statement_line_id',
        string='Banko eksporto darbai'
    )
    has_export_job_ids = fields.Boolean(
        string='Turi susijusių eksportų', copy=False,
        compute='_compute_bank_export_job_data'
    )
    has_file_export_job_ids = fields.Boolean(
        compute='_compute_bank_export_job_data'
    )
    bank_exports_to_sign = fields.Boolean(
        string='Turi eksportuotų transakcijų kurias galima pasirašyti',
        compute='_compute_bank_export_job_data'
    )
    bank_export_state = fields.Selection(
        abi.BANK_EXPORT_STATES, string='Paskutinė eksportavimo būsena',
        store=True, compute='_compute_bank_export_job_data', copy=False
    )
    bank_export_state_html = fields.Html(
        compute='_compute_bank_export_state_html',
        sanitize=False
    )

    company_currency_id = fields.Many2one(
        'res.currency', compute='_compute_company_currency_id'
    )
    amount_company_currency = fields.Monetary(
        string='Suma (Kompanijos valiuta)',
        compute='_compute_amount_company_currency', store=True,
        currency_field='company_currency_id'
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('statement_id.journal_id.currency_id', 'date', 'amount')
    def _compute_amount_company_currency(self):
        """Computes bank statement line amount in company currency"""
        company_currency = self.env.user.sudo().company_id.currency_id
        for rec in self:
            journal_currency_id = rec.statement_id.journal_id.currency_id
            amount_company_currency = rec.amount
            if journal_currency_id and journal_currency_id != company_currency:
                amount_company_currency = journal_currency_id.with_context(date=rec.date).compute(
                    rec.amount, company_currency)
            rec.amount_company_currency = amount_company_currency

    @api.multi
    def _compute_company_currency_id(self):
        """Computes company currency on bank statement"""
        currency = self.env.user.sudo().company_id.currency_id
        for rec in self:
            rec.company_currency_id = currency

    @api.multi
    @api.depends('bank_export_job_ids', 'bank_export_job_ids.available_for_signing', 'bank_export_job_ids.export_state')
    def _compute_bank_export_job_data(self):
        """
        Compute //
        Check whether account statement line has any related bank export jobs and
        whether any bank.export.jobs related export jobs are 'available_for_signing'
        (has_export_job_ids used as a separate boolean, so it behaves nicely in form view)
        :return: None
        """
        for rec in self:
            live_exports = rec.bank_export_job_ids.filtered(lambda x: not x.xml_file_download)
            if live_exports:
                latest_export = live_exports.sorted(key=lambda c: c.id, reverse=True)[0]
                rec.bank_export_state = latest_export.export_state
                rec.bank_exports_to_sign = any(x.available_for_signing for x in live_exports)
                rec.has_export_job_ids = True
            else:
                rec.bank_export_state = 'no_action'
                rec.has_export_job_ids = rec.bank_exports_to_sign = False
            rec.has_file_export_job_ids = rec.bank_export_job_ids

    @api.multi
    @api.depends('bank_export_state')
    def _compute_bank_export_state_html(self):
        """
        Compute //
        Make html badge based on bank export state
        Which visually displays it.
        :return: None
        """
        for rec in self:
            rec.bank_export_state_html = self.env['api.bank.integrations'].get_bank_export_state_html_data(
                model=self._name,  # No singleton issue
                state=rec.bank_export_state,
            )

    @api.multi
    @api.depends('statement_id.sepa_imported')
    def _compute_sepa_imported(self):
        """Compute whether line is sepa_imported based on parent statement"""
        for rec in self:
            rec.sepa_imported = rec.statement_id.sepa_imported

    @api.multi
    @api.depends('journal_entry_ids', 'account_id')
    def _reconciled(self):
        for rec in self:
            rec.reconciled = True if rec.journal_entry_ids.ids or rec.account_id.id else False

    @api.multi
    def _inverse_sepa_instruction_id(self):
        # front.bank.statement.line inherits account.bank.statement.line, and so, this inverse method. However, for
        # font lines, entry_reference should always be False so it is ok, we never enter the if clause
        for rec in self:
            prev_lines_reconciled = False
            # FIXME: should use float_compare here ?    v
            if rec.sepa_instruction_id and rec.amount < 0 and rec.entry_reference:
                prev_lines = self.env['account.bank.statement.line'].search(
                    [('sepa_instruction_id', '=', rec.sepa_instruction_id),
                     ('journal_id', '=', rec.journal_id.id),
                     ('id', '!=', rec.id),
                     ('amount', '<', 0),
                     ('entry_reference', '=', False)])
                prev_lines_reconciled = prev_lines.filtered(lambda r: r.journal_entry_ids)
                prev_lines_not_reconciled = prev_lines.filtered(lambda r: not r.journal_entry_ids)
                prev_lines_not_reconciled.write({'sepa_duplicate': True})
            rec.sepa_duplicate = prev_lines_reconciled

    # On-changes ------------------------------------------------------------------------------------------------------

    @api.onchange('partner_id')
    def _onchange_partner_id_bank_account(self):
        """Set bank account to preferred bank of currently set partner"""
        bank_account = False
        if self.partner_id and self.journal_id:
            bank_account = self.partner_id.get_preferred_bank(self.journal_id)
        self.bank_account_id = bank_account

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.constrains('currency_id', 'amount_currency')
    def _check_amount_currency_not_null(self):
        """ Do not let save bank statement line with secondary currency set and amount 0 """
        for rec in self:
            if not rec.currency_id or rec.journal_id.currency_id == rec.currency_id:
                continue
            if tools.float_is_zero(rec.amount_currency, precision_rounding=rec.currency_id.rounding):
                raise exceptions.ValidationError(_('Suma valiuta negali būti nulis'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def relate_line_partners(self):
        """
        Tries to find related partner for current
        statement line based on the imported information
        :return: None
        """
        # Try to get the partner ID for the lines that
        # do not have any partner before each run
        for rec in self.filtered(lambda x: not x.partner_id):
            if not rec.partner_id:
                partner_id = self.env['account.sepa.import'].get_partner_id(
                    partner_name=rec.imported_partner_name,
                    partner_identification=('kodas', rec.imported_partner_code),
                    partner_iban=rec.imported_partner_iban,
                )
                # If partner was found, write it to the record
                if partner_id:
                    rec.write({'partner_id': partner_id})

    @api.multi
    def get_move_lines_for_reconciliation(
            self, excluded_ids=None, str=False, offset=0, limit=None, additional_domain=None, overlook_partner=False):
        """Override add-ons method by adding additional domain that skips advance accounts"""

        # Initialize additional domain
        if additional_domain is None:
            additional_domain = []

        # If advance account is set, append it to the domain and filter it
        advance_account = self.env.user.company_id.get_employee_advance_account()
        if advance_account:
            additional_domain.append(('account_id', '!=', advance_account.id))

        return super(AccountBankStatementLine, self).get_move_lines_for_reconciliation(
            excluded_ids, str, offset, limit, additional_domain, overlook_partner
        )

    @api.multi
    def auto_reconcile_with_accounting_entries(self, lines_to_skip=None):
        if self.sudo().env.user.company_id.disable_automatic_reconciliation:
            return

        advance_account = self.env.user.company_id.get_employee_advance_account()
        aml_obj = self.env['account.move.line']
        # Prepare the filters
        lines_to_skip = self.env['account.bank.statement.line'] if lines_to_skip is None else lines_to_skip
        lines_to_skip |= self.env['account.move'].search(
            [('statement_line_id', 'in', self.ids)]).mapped('statement_line_id')
        company = self.sudo().env.user.company_id

        # Check for excluded partners, accounts and journals
        excluded_partners = company.auto_reconciliation_excluded_partner_ids
        excluded_accounts = company.auto_reconciliation_excluded_account_ids | advance_account
        included_accounts = company.auto_reconciliation_included_account_ids
        excluded_journals = company.auto_reconciliation_excluded_journal_ids

        skip_structured = company.disable_automatic_structured_reconciliation
        aml_sorting = company.automatic_reconciliation_sorting
        aml_filtering = company.automatic_reconciliation_filtering

        # Try to assign the partners to the lines
        self.relate_line_partners()

        # Filter passed lines
        filtered_records = self.filtered(
            lambda x: not x.reconciled and x.partner_id and x.partner_id not in excluded_partners
            and x not in lines_to_skip and x.journal_id not in excluded_journals and not (
                    x.journal_entry_ids or x.account_id)
        )

        for line in filtered_records:
            if skip_structured and line.info_type in ['structured']:
                continue  # Can't use it properly in lambda, because it ignores the skip_structured value
            search_domain = [
                ('partner_id', '=', line.partner_id.id),
                ('reconciled', '=', False),
                ('account_id.reconcile', '=', True),
                '|',
                ('invoice_id', '=', False),
                ('invoice_id.skip_global_reconciliation', '=', False),
            ]
            # Always give priority to explicitly included accounts
            if included_accounts:
                search_domain.append(('account_id', 'in', included_accounts.ids))
            elif excluded_accounts:
                search_domain.append(('account_id', 'not in', excluded_accounts.ids))

            if tools.float_compare(line.amount, 0.0, precision_digits=2) < 0:
                search_domain.append(('balance', '<', 0))
            else:
                search_domain.append(('balance', '>', 0))

            order = 'date_maturity desc' if aml_sorting == 'date_desc' else 'date_maturity asc'
            lines = aml_obj.search(search_domain, order=order)
            if lines:
                # Only filter the lines by payment name
                if aml_filtering == 'payment_name':
                    matched_lines = lines.get_best_matching_lines_by_name(line.name)
                # Only filter by payment amount
                elif aml_filtering == 'payment_amount':
                    matched_lines = aml_obj.get_best_matching_lines_by_amount(lines, line.amount)
                else:
                    # Check whether specific line can be matched by name, otherwise match by amount
                    reduced_line_batch = lines.get_best_matching_lines_by_name(line.name)
                    # Even if we match lines by name, we run them through amount matcher
                    # which checks if partial reconciliation is available in the system
                    reduced_line_batch = reduced_line_batch or lines
                    matched_lines = aml_obj.get_best_matching_lines_by_amount(reduced_line_batch, line.amount)
                    # If nothing got matched by amount after reduced name batch, try
                    # searching again with full batch of lines matching only by amount
                    if not matched_lines:
                        matched_lines = aml_obj.get_best_matching_lines_by_amount(lines, line.amount)
                if matched_lines:
                    line.reconcile_with_move_lines(matched_lines, perfect_balance_match=False)

    def get_statement_line_for_reconciliation_widget(self):
        res = super(AccountBankStatementLine, self).get_statement_line_for_reconciliation_widget()
        res.update({'imported_partner_name': self.imported_partner_name,
                    'imported_partner_code': self.imported_partner_code})
        return res

    @api.multi
    def _auto_create_commision_record(self):
        company_currency = self.env.user.company_id.currency_id
        for rec in self:
            if rec.currency_id and rec.currency_id != rec.statement_id.currency_id \
                    and rec.currency_id != company_currency:
                raise exceptions.UserError(
                    _('Mokesčių eilutės valiuta negali skirtis nuo pagrindinės valiutos')
                )
            # Check if bank account exists
            bank_account = rec.statement_id.journal_id.default_credit_account_id
            if not bank_account:
                raise exceptions.ValidationError(_('Nenurodyta žurnalo sąskaita'))

            # Check if commission account exists
            commision_account = rec.statement_id.journal_id.bank_commission_account_id
            if not commision_account:
                commision_account = rec.statement_id.company_id.bank_commission_account_id
            if not commision_account:
                raise exceptions.ValidationError(_('Nenurodyta kompanijos banko komisinių sąskaita'))

            currency = rec.currency_id or rec.statement_id.currency_id
            amount_currency = rec.amount_currency if rec.currency_id else rec.amount
            amount_company_currency = currency.with_context(date=rec.date).compute(amount_currency, company_currency)

            name = 'Komisiniai ' + rec.date
            move_line = {
                'name': name,
                'account_id': commision_account.id,
                'currency_id': currency.id if currency != company_currency else False,
                'amount_currency': -amount_currency if currency != company_currency else 0,
            }
            amount_to_use = amount_company_currency if rec.currency_id else amount_currency
            if amount_company_currency < 0:
                move_line['credit'] = 0
                move_line['debit'] = -amount_to_use
            else:
                move_line['credit'] = amount_to_use
                move_line['debit'] = 0
            new_aml_dicts = [move_line]
            rec.process_reconciliation(new_aml_dicts=new_aml_dicts)

    @api.multi
    def set_not_duplicate(self):
        self.write({'sepa_duplicate': False})

    @api.multi
    def _get_auto_reconcile_search_domain(self, account_type=None):
        self.ensure_one()
        if not account_type:
            return []

        account = None
        if account_type == 'sodra':
            account = self.env.user.company_id.saskaita_sodra
        elif account_type == 'gpm':
            account = self.env.user.company_id.saskaita_gpm
        if account:
            search_domain = [('account_id', '=', account.id),
                             ('partner_id', '=', self.partner_id.id),
                             ('reconciled', '=', False)]
            if tools.float_compare(self.amount, 0.0, precision_digits=2) < 0:
                search_domain.append(('balance', '<', 0))
            else:
                search_domain.append(('balance', '>', 0))
            return search_domain

    @api.multi
    def reconcile_with_move_lines(self, account_move_lines, perfect_balance_match=True):
        """
        Function that reconciles account bank statement line with
        passed account move line records. Partial reconciliation
        is supported with the flag.
        :param account_move_lines: account.move.line -- RECORDSET
        :param perfect_balance_match: indicates whether reconciliation
               should be done partially -- BOOLEAN
        :return: None
        """
        self.ensure_one()
        st_line_amount = self.amount
        lines_to_reconcile = self.env['account.move.line']
        sign = -1 if tools.float_compare(st_line_amount, 0.0, precision_digits=2) < 0 else 1
        reconcilable_residual = 0.0
        # Ensure that batch amount does not exceed st line amount
        #  with several lines, one line's amount can exceed
        for aml in account_move_lines:
            reconcilable_residual += aml.amount_residual
            lines_to_reconcile |= aml
            if tools.float_compare(reconcilable_residual, st_line_amount, precision_digits=2) * sign >= 0:
                break
        # Do not reconcile the entries that have more than two non company currencies in overall cluster.
        # Check moved from add-ons without the raise, so that we skip this error, but catch the others
        cluster_currencies = lines_to_reconcile.get_reconcile_cluster().mapped('currency_id')
        if len(cluster_currencies - self.env.user.company_id.currency_id) > 1:
            return
        # We only support partial reconciliation if move line amount is higher than statement line amount
        # in other words - we do not want to leave statement line partially reconciled.
        full_reconciliation = tools.float_is_zero(reconcilable_residual - st_line_amount, precision_digits=2)
        supported_partial = tools.float_compare(reconcilable_residual, st_line_amount, precision_digits=2) * sign > 0
        if not perfect_balance_match and supported_partial or full_reconciliation:
            counterpart_aml_dicts = []
            # Support for partial reconciliations
            amount_leftovers = st_line_amount
            for m_line in lines_to_reconcile.sorted(lambda x: abs(x.amount_residual)):
                # Skip on the lines with zero residual
                if tools.float_is_zero(m_line.amount_residual, precision_digits=2):
                    continue
                # Build counterpart move line data dict
                counterpart_values = {'name': m_line.name, 'debit': 0.0, 'credit': 0.0, }
                # Get the amount dictionary key based on the sign
                amount_key = 'credit' if tools.float_compare(
                    m_line.amount_residual, 0.0, precision_digits=2) > 0 else 'debit'
                # Get the amount to use - in partial reconciliations we do not want to use
                # full amount residual of the line, but the virtual 'residual' of the statement amount
                if tools.float_compare(abs(m_line.amount_residual), abs(amount_leftovers), precision_digits=2) > 0:
                    balance_to_use = amount_leftovers
                else:
                    balance_to_use = m_line.amount_residual
                    amount_leftovers -= balance_to_use
                # Update counterpart move line data dict
                counterpart_values.update({
                    amount_key: abs(balance_to_use),
                    'counterpart_aml_id': m_line.id,
                })
                counterpart_aml_dicts.append(counterpart_values)
            # Create account move line counterparts
            self.process_reconciliations([
                {'counterpart_aml_dicts': counterpart_aml_dicts, 'payment_aml_rec': [], 'new_aml_dicts': []}
            ])

    @api.multi
    def _reconcile_with_sodra(self):
        for line in self:
            search_domain = line._get_auto_reconcile_search_domain(account_type='sodra')
            if not search_domain:
                continue
            amls = self.env['account.move.line'].search(search_domain, order='date_maturity')
            line.reconcile_with_move_lines(amls)

    @api.multi
    def _reconcile_with_gpm(self):
        for line in self:
            search_domain = line._get_auto_reconcile_search_domain(account_type='gpm')
            if not search_domain:
                continue
            amls = self.env['account.move.line'].search(search_domain, order='date_maturity')
            line.reconcile_with_move_lines(amls)

    @api.multi
    def button_cancel_reconciliation(self):
        super(AccountBankStatementLine, self).button_cancel_reconciliation()
        self.write({'account_id': False})

    @api.multi
    def mark_related_objects_as_exported(self):
        """Marks related invoices and move lines as SEPA exported"""
        exported_values = {
            'exported_sepa': True,
            'exported_sepa_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        }
        self.sudo().mapped('invoice_ids').filtered(lambda x: not x.exported_sepa).write(exported_values)
        # Update export values
        exported_values.update({
            'eksportuota': True,
        })
        self.sudo().mapped('aml_ids').filtered(lambda x: not x.exported_sepa).with_context(
            check_move_validity=False).write(exported_values)

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        self.write({'move_name': False})
        if not self._context.get('allow_commission_unlink') and any(rec.commission_of_id for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti komisinių neištrinant tikro įrašo'))
        commission_lines = self.search([('commission_of_id', 'in', self.ids)])
        if commission_lines:
            commission_lines.button_cancel_reconciliation()
            commission_lines.write({'move_name': False})
            commission_lines.with_context(allow_commission_unlink=True).unlink()
        super(AccountBankStatementLine, self).unlink()

    @api.model
    def create(self, vals):
        line = super(AccountBankStatementLine, self).create(vals)
        if line.commission_of_id:
            line._auto_create_commision_record()
        if line.sub_family_code == 'FEES':
            line.is_fee = True
            line._auto_create_commision_record()
        return line
