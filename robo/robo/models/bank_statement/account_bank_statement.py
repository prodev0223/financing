# -*- coding: utf-8 -*-
from six import iteritems
from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo.addons.sepa import api_bank_integrations as abi


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    reported_front = fields.Boolean(compute='_compute_reported_front')
    front_statements = fields.One2many('front.bank.statement', 'statement_id')
    auto_partner_id = fields.Many2one('res.partner', string='Priverstinis partneris', readonly=True,
                                      states={'open': [('readonly', False)]})
    auto_account_id = fields.Many2one('account.account', string='Priverstinė sąskaita', readonly=True,
                                      states={'open': [('readonly', False)]})
    informed = fields.Boolean(string='Informuotas vadovas', readonly=True)

    # Computes/Inverses -------------------------------------------------------------------------------------

    @api.multi
    @api.depends('front_statements.statement_id')
    def _compute_reported_front(self):
        for rec in self:
            rec.reported_front = True if rec.front_statements else False

    @api.model
    def get_grouped_statement_normalization_data(self, journal_ids=None, extra_domain=None):
        """
        Returns grouped bank statement data, that is used
        for ascending/descending statement balance normalization
        :param journal_ids: IDs of journals to filter
        :param extra_domain: Extra domain for search filtering
        :return: Grouped statements {JOURNAL: [statement records]}
        """
        # Prevent mutable default arguments
        journal_ids = [] if journal_ids is None else journal_ids
        search_domain = [
            ('sepa_imported', '=', True),
            ('partial_statement', '=', False),
        ]
        # Append extra domain if it's passed
        if extra_domain:
            search_domain += extra_domain

        # Extend the domain with passed journals if any. If specific journals are passed
        # We do not filter for explicit import file types for the journal
        # If empty list is passed, we keep it and get no statements
        if journal_ids is not None:
            search_domain += [('journal_id', 'in', journal_ids)]
        else:
            search_domain += [
                '|', ('journal_id.import_file_type', 'in', ['sepa', 'braintree_api']),
                ('journal_id.import_file_type', '=', False),
            ]
        # Search for the statements and group them
        statements = self.env['account.bank.statement'].search(search_domain)

        grouped_data = {}
        for statement in statements:
            # Loop through lines and build dict of dicts with following mapping
            # {JOURNAL: account.bank.statement}...
            journal = statement.journal_id
            grouped_data.setdefault(journal, self.env['account.bank.statement'])
            grouped_data[journal] |= statement
        return grouped_data

    @api.model
    def normalize_balances_ascending(self, journal_ids=None, force_normalization=False, extra_domain=None):
        """
        * Normalizes bank statement starting and ending
        balances in a zipper principle from bottom to to top:
            -1st statements' ending balance is moved to
            2nd statements' starting balance and so on.
        :param journal_ids: List of journal_ids can be passed so the search is narrowed
        :param force_normalization: Indicates whether ascending normalization
        should be forced even if no starting entry was found
        :param extra_domain: Extra domain for custom record filtering
        :return: True if at least one of the journals was normalized, else False
        """

        normalized = False
        # Starting balance journal. If it's not found, skip normalization altogether
        start_journal = self.env['account.journal'].search([('code', '=', 'START')], limit=1)
        if not start_journal:
            return
        company_currency = self.sudo().env.user.company_id.currency_id
        # Get grouped normalization data
        grouped_data = self.get_grouped_statement_normalization_data(
            journal_ids, extra_domain=extra_domain,
        )
        # Loop through grouped data
        for journal, statements in iteritems(grouped_data):
            # Collect the journal accounts
            journal_accounts = journal.default_debit_account_id | journal.default_credit_account_id
            if not journal_accounts:
                continue
            # Check whether normalization should be forced - if journal has forced normalization set,
            # it takes priority over method's argument, if it's set to False, method argument value is used.
            normalize_journal = force_normalization
            if not normalize_journal:
                normalize_journal = journal.force_bank_statement_normalization

            min_date = min(statements.mapped('date'))
            # Only search for move lines that are one day earlier than earliest statement
            start_date = (
                    datetime.strptime(min_date, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
            ).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            # Check for starting balance move lines, if they do not exist, skip normalization for this journal
            move_lines = self.env['account.move.line'].search([
                ('journal_id', '=', start_journal.id),
                ('account_id', 'in', journal_accounts.ids),
                ('date', '=', start_date),
            ])
            if not move_lines and not normalize_journal:
                continue

            if move_lines:
                # Sum the total starting balance, it's used as a starting point for normalization
                if journal.currency_id and journal.currency_id != company_currency:
                    starting_statement_balance = sum(move_lines.mapped('amount_currency'))
                else:
                    starting_statement_balance = sum(move_lines.mapped('balance'))
            else:
                starting_statement_balance = statements.filtered(lambda x: x.date == min_date).balance_start

            latest_statement = self.env['account.bank.statement']
            # Sort the entries by date and create date, and whether normalization should be skipped for this journal
            statements = sorted(statements, key=lambda k: (k.date, k.create_date))
            # Loop through statements, normalize them and fill in the gaps
            for statement in statements:
                # First iteration, use starting statement balance
                if not latest_statement:
                    calculated_st_balance = starting_statement_balance
                else:
                    calculated_st_balance = latest_statement.balance_end_real
                latest_statement = statement

                # Check difference between latest statement end balance (or starting AML balance) and current statement
                statement_diff = tools.float_compare(
                    statement.balance_start, calculated_st_balance, precision_digits=2
                )
                # If there's a difference, normalize the balances
                if statement_diff or not statement.is_difference_zero:
                    # Calculate balances, and write it to the statement
                    ending_balance = calculated_st_balance + statement.total_entry_encoding
                    statement.write({
                        'balance_end_real': ending_balance,
                        'balance_end_factual': ending_balance,
                        'balance_start': calculated_st_balance,
                    })
            # Set the value as normalized if at least one journal of the batch was
            normalized = True
        return normalized

    @api.model
    def normalize_balances_descending(self, journal_ids=None, extra_domain=None):
        """
        * Normalizes bank statement starting and ending
        balances in a zipper principle from top to bottom:
            -1st statements' starting balance is moved to
            2nd statements' ending balance and so on.
        * Creates empty entries is there is a gap of days
        between two current adjacent statements
        :param journal_ids: List of journal_ids can be passed so the search is narrowed
        :param extra_domain: Extra domain for custom record filtering
        :return: account.bank.statement record set of created empty entries (if any)
        """
        def confirm_statement(b_statement):
            """Try to confirm the bank statement that has no lines"""
            if not b_statement.line_ids and b_statement.state == 'open':
                try:
                    b_statement.button_confirm_bank()
                except (exceptions.UserError, exceptions.ValidationError):
                    pass

        # Get grouped normalization data
        grouped_data = self.get_grouped_statement_normalization_data(
            journal_ids, extra_domain=extra_domain,
        )
        # Search for any sepa imported statements that are not partial
        created_statements = self.env['account.bank.statement']

        for journal, corresponding in iteritems(grouped_data):
            latest_stmt = self.env['account.bank.statement']

            # Sort the entries by date and create date, and whether normalization should be skipped for this journal
            corresponding = sorted(corresponding, key=lambda k: (k.date, k.create_date), reverse=True)
            skip_norm = journal.skip_bank_statement_normalization

            # Loop through statements, normalize them and fill in the gaps
            for en, statement in enumerate(corresponding):
                # On first loop execute
                if not en:
                    latest_stmt = statement
                    # Check whether normalization should be skipped
                    if not skip_norm:
                        # If latest entry is zero, force skipping of normalization unless
                        # zero amount came from API and update_date is later than yesterday
                        if tools.float_is_zero(statement.balance_end_factual, precision_digits=2):
                            # Get API update date and check whether it's usable in this calculation
                            api_update_date = journal.api_balance_update_date
                            deprecated_update_date = not api_update_date or api_update_date <= (
                                    datetime.utcnow() - relativedelta(days=1)
                            ).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                            # If date is not usable or API balance is not zero - we skip normalization
                            if deprecated_update_date or not tools.float_is_zero(
                                    journal.api_end_balance, precision_digits=2):
                                skip_norm = True
                                continue

                        # Calculate the balances of the entry
                        factual_end = statement.balance_end_factual
                        statement.balance_end_real = factual_end
                        statement.balance_start = factual_end - statement.total_entry_encoding
                        confirm_statement(statement)
                    continue

                # Check whether there is a difference between statement
                # start balance and end balance of the previous statement
                diff = tools.float_compare(latest_stmt.balance_start, statement.balance_end_real, precision_digits=2)
                # is_difference_zero checks whether entry encoding matches end - start balances
                if not skip_norm and (diff or not statement.is_difference_zero):
                    factual_end = latest_stmt.balance_start
                    # Write previous statements' start balance, to current statements' end balance
                    statement.write({'balance_end_real': factual_end,
                                     'balance_start': factual_end - statement.total_entry_encoding})
                    confirm_statement(statement)

                # Try to fill in the gaps with empty statements if there is at least two statements
                if len(corresponding) > 1 and latest_stmt:

                    # Get dates of two adjacent statements for the specified journal
                    latest_stmt_date_dt = datetime.strptime(latest_stmt.date, tools.DEFAULT_SERVER_DATE_FORMAT)
                    earliest_stmt_date_dt = datetime.strptime(statement.date, tools.DEFAULT_SERVER_DATE_FORMAT)

                    # Get days to check in string and datetime format (one day earlier than latest date)
                    day_to_check_dt = latest_stmt_date_dt - relativedelta(days=1)
                    day_to_check = day_to_check_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                    # Check each day and see if there are any gaps between two statements
                    missing_days = []
                    while day_to_check_dt >= earliest_stmt_date_dt:

                        day_before_statement = self.env['account.bank.statement'].search(
                            [('journal_id', '=', journal.id),
                             ('date', '=', day_to_check),
                             ('sepa_imported', '=', True)], limit=1)

                        if not day_before_statement:
                            # Create the artificial statement
                            bank_statement = self.env['account.bank.statement'].create(
                                {'name': '/',
                                 'date': day_to_check,
                                 'journal_id': journal.id,
                                 'balance_start': latest_stmt.balance_start,
                                 'balance_end_real': latest_stmt.balance_start,
                                 'balance_end_factual': latest_stmt.balance_start,
                                 'artificial_statement': True,
                                 'sepa_imported': True,
                                 })
                            missing_days.append(day_to_check_dt)
                            bank_statement.button_confirm_bank()
                            created_statements |= bank_statement

                        # Subtract one day and repeat the process
                        day_to_check_dt -= relativedelta(days=1)
                        day_to_check = day_to_check_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                    # if we have missing days and object is API integrated SEPA journal, try to fetch statements
                    if missing_days and journal.api_integrated_journal and not journal.gateway_deactivated and \
                            abi.INTEGRATION_TYPES.get(journal.api_bank_type) == 'sepa_xml':
                        date_from_dt = min(missing_days)
                        date_to_dt = max(missing_days)

                        # Make the gap include day before and after
                        date_from = (date_from_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        date_to = (date_to_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

                        model_name, method_name = self.env['api.bank.integrations'].get_bank_method(
                            journal, m_type='query_transactions_non_threaded')
                        method_instance = getattr(self.env[model_name], method_name)

                        # Base querying method must always expect account.journal, date_from and date_to parameters
                        method_instance(journal, date_from, date_to)

                latest_stmt = statement
        return created_statements

    @api.model
    def merge_bank_statements(self):
        """
        ! METHOD MEANT TO BE USED IN A SCRIPT, NOT CALLED ANYWHERE IN THE CODE !
        Merges partial (half day) statements into one full bank statement
        :return: None
        """
        bank_statements = self.env['account.bank.statement'].search([('sepa_imported', '=', True)])
        journal_ids = bank_statements.mapped('journal_id')
        for journal in journal_ids:
            corresponding_parent = bank_statements.filtered(lambda x: x.journal_id.id == journal.id)
            dates = list(set(corresponding_parent.mapped('date')))
            for date_s in dates:
                corresponding = corresponding_parent.filtered(lambda x: x.date == date_s)
                if len(corresponding) > 1:
                    parent_set = max(corresponding, key=lambda x: len(x.line_ids))
                    entry_ref_list = parent_set.mapped('line_ids.entry_reference')
                    child_sets = corresponding.filtered(lambda x, re_id=parent_set.id: x.id != re_id)
                    to_unlink = self.env['account.bank.statement.line']
                    to_merge = self.env['account.bank.statement.line']
                    for child_set in child_sets:
                        for line in child_set.line_ids:
                            entry_reference = line.entry_reference
                            if entry_reference in entry_ref_list:
                                to_unlink += line
                            else:
                                to_merge += line
                    to_merge.write({'statement_id': parent_set.id})
                    for child_set in child_sets:
                        child_set.button_draft()
                    corresponding_parent -= child_sets
                    bank_statements -= child_sets
                    child_sets.unlink()
                    to_unlink.unlink()
        self.env['account.bank.statement'].normalize_balances_descending()

    @api.model
    def show_front_action(self):
        action = self.env.ref('robo.show_front_server_action')
        if action:
            action.create_action()

    @api.multi
    def show_front(self):
        if not self.env.user.is_accountant():
            return
        # Check if system should try to send
        # created front statement to bank
        auto_send_flag = self._context.get('auto_send_to_bank')
        for rec in self.filtered(lambda x: not x.front_statements):
            for line in rec.line_ids:
                line.sepa_instruction_id = self.env['bank.export.job'].get_next_sepa_code()

            lines = [(0, 0, {
                'date': line.date,
                'name': line.name,
                'partner_id': line.partner_id.id,
                'currency_id': line.currency_id.id,
                'bank_account_id': line.bank_account_id.id,
                'amount_currency': line.amount_currency,
                'info_type': line.info_type,
                'invoice_id': line.invoice_id.id if line.invoice_id else False,
                'amount': line.amount,
                'ref': line.ref,
                'sepa_instruction_id': line.sepa_instruction_id,
            }) for line in rec.line_ids]

            f_statement = self.env['front.bank.statement'].create({
                'statement_id': rec.id,
                'name': rec.name,
                'journal_id': rec.journal_id.id,
                'date': rec.date,
                'line_ids': lines,
                'kas_sumoka': rec.kas_sumoka,
                'company_id': rec.company_id.id,
            })
            f_statement.action_generate_sepa_xml()

            # Auto send the statement to bank if we receive the context
            # and journal belongs to fully integrated bank API
            auto_send = auto_send_flag and f_statement.api_integrated_journal and f_statement.api_full_integration
            if auto_send:
                f_statement.send_to_bank()

            # If auto send is executed, do not inform the CEO about the creation,
            # they get another message when the front statement is sent
            if not self._context.get('front_statements') and not auto_send:
                f_statement.sudo().inform()

    @api.multi
    def inform(self):
        self.ensure_one()
        if self.front_statements:
            self.front_statements[0].inform()

    @api.multi
    def auto_process_reconciliation(self):
        self.ensure_one()
        if self.auto_account_id and self.auto_partner_id:
            vals = {
                'line_ids': [(6, 0, [line.id for line in self.line_ids if not (
                        line.journal_entry_ids.ids or line.account_id.id or line.sepa_duplicate)])],
                'auto_partner_id': self.auto_partner_id.id,
                'auto_account_id': self.auto_account_id.id,
                'parent_id': self.id
            }

            wiz_id = self.env['auto.process.reconciliation'].create(vals)

            return {
                'name': _('Priverstinis Sudengimas'),
                'view_type': 'form',
                'view_mode': 'form',
                'view_id': self.env.ref('robo.auto_process_reconciliation_wizard').id,
                'res_id': wiz_id.id,
                'res_model': 'auto.process.reconciliation',
                'type': 'ir.actions.act_window',
                'target': 'new',
            }

        else:
            raise exceptions.Warning(_('Nurodykite priverstinį partnerį ir sąskaitą.'))
