# -*- encoding: utf-8 -*-
from odoo import models, api, exceptions, tools, fields, _
from odoo.addons.queue_job.job import identity_exact, job
from dateutil.relativedelta import relativedelta
from datetime import datetime

SODRA_STRUCTURED_CODE = '252'
GPM_STRUCTURED_CODE = '1311'


class AccountBankStatement(models.Model):

    _name = 'account.bank.statement'
    _inherit = ['account.bank.statement', 'exportable.bank.statement']

    # Computed balance currency fields
    balance_start_currency = fields.Monetary(
        compute='_compute_balance_start_currency', store=True
    )
    balance_end_currency = fields.Monetary(
        compute='_compute_balance_end_currency', store=True
    )
    balance_end_factual_company_currency = fields.Monetary(
        string='Faktinis pabaigos balansas iš banko kompanijos valiuta',
        compute='_compute_balance_end_factual_company_currency', store=True
    )
    # Factual balance fields -- amounts from the bank
    balance_end_factual = fields.Monetary(string='Faktinis pabaigos balansas iš banko')
    balance_start_factual = fields.Monetary(string='Faktinis pradžios balansas iš banko')

    partial_statement = fields.Boolean(default=False, string='Dalinis išrašas')
    psd2_statement = fields.Boolean(string='PSD2 Entry statement')

    statement_id_bank = fields.Char(string='Pranešimo id')
    sepa_imported = fields.Boolean(string='Imported from sepa', default=False, copy=False)
    artificial_statement = fields.Boolean(copy=False)

    @api.multi
    @api.depends('line_ids', 'balance_start_currency', 'line_ids.amount_company_currency')
    def _compute_balance_end_currency(self):
        """Computes balance end currency by adding total encoding to starting balance"""
        for rec in self:
            total_entry_encoding = sum(line.amount_company_currency for line in rec.line_ids)
            rec.balance_end_currency = rec.balance_start_currency + total_entry_encoding

    @api.multi
    @api.depends('journal_id.currency_id', 'date', 'balance_end_factual')
    def _compute_balance_end_factual_company_currency(self):
        """Computes factual end balance in journal currency"""
        company_currency = self.env.user.sudo().company_id.currency_id
        for rec in self:
            factual_end_bal = rec.balance_end_factual
            if rec.journal_id.currency_id and rec.journal_id.currency_id != company_currency:
                factual_end_bal = rec.journal_id.currency_id.with_context(
                    date=rec.date).compute(rec.balance_end_factual, company_currency)
            rec.balance_end_factual_company_currency = factual_end_bal

    @api.multi
    @api.depends('journal_id.currency_id', 'date', 'balance_start')
    def _compute_balance_start_currency(self):
        """Computes start balance in journal currency"""
        company_currency = self.env.user.sudo().company_id.currency_id
        for rec in self:
            start_bal = rec.balance_start
            if rec.journal_id.currency_id and rec.journal_id.currency_id != company_currency:
                start_bal = rec.journal_id.currency_id.with_context(
                    date=rec.date).compute(rec.balance_start, company_currency)
            rec.balance_start_currency = start_bal

    @api.multi
    @api.depends('line_ids.journal_entry_ids')
    def _check_lines_reconciled(self):
        for rec in self:
            rec.all_lines_reconciled = all(
                [line.journal_entry_ids.ids or line.account_id.id or line.sepa_duplicate for line in rec.line_ids]
            )

    @api.multi
    def update_balance_from_revolut_legs(self):
        """
        Update statement balances using the revolut.api.transaction.legs associated with the statement
        """
        for statement in self.sorted(lambda s: s.date):
            if not statement.journal_id.revolut_account_id:
                continue

            legs = self.env['revolut.api.transaction.leg'].search([
                ('transaction_id.uuid', 'in', statement.mapped('line_ids.entry_reference')),
                ('revolut_account_id', '=', statement.journal_id.revolut_account_id.id)
            ])
            if not legs:
                continue
            # we need to use SQL ordering because time data is more complete than when read through ORM
            self._cr.execute('''
            SELECT id FROM revolut_api_transaction WHERE id in %s ORDER BY completed_at;
            ''', (tuple(legs.mapped('transaction_id.id')), ))
            order = {row[0]: idx for idx, row in enumerate(self._cr.fetchall())}
            legs = legs.sorted(key=lambda l: order.get(l.transaction_id.id))
            prev_statement = self.env['account.bank.statement'].search([('journal_id', '=', statement.journal_id.id),
                                                                        ('date', '<', statement.date)],
                                                                       order='date desc', limit=1)
            if prev_statement:
                balance_start = prev_statement.balance_end_real
            else:
                balance_start = legs[0].balance - (legs[0].amount - abs(legs[0].fee))
            balance_end = legs[-1].balance
            statement.write({
                'balance_start': balance_start,
                'balance_end_real': balance_end,
            })

    @api.model
    def _get_allowed_file_type_for_normalization(self):
        return ['stripe', 'walletto', 'paypal']

    @api.multi
    def action_normalize_balances_ascending_from(self):
        """
        Update statements start and end balances in a journal starting from the provided statement, going chronologically
        for
        :param: statement: account.bank.statement record
        :return: None
        """
        if len(self) != 1:
            raise exceptions.UserError(
                _('Negalite pasirinkti daugiau negu vieno įrašo. '
                  'Jeigu norite, kad būtų normalizuojami visi įrašai, pasirinkite patį ankščiausią įrašą.')
            )
        allowed_file_type = self._get_allowed_file_type_for_normalization()
        if self.journal_id.import_file_type not in allowed_file_type:
            raise exceptions.UserError(
                _('You cannot use this action for journal importing %s') % self.journal_id.import_file_type)
        self._normalize_balances_ascending_from(self)
        return {'type': 'ir.actions.do_nothing'}

    @api.model
    def _normalize_balances_ascending_from(self, statement):
        """
        Update statements start/end balances in a journal starting from the provided statement, going chronologically
        :param: statement: account.bank.statement record
        :return: None
        """
        if not statement:
            return
        statements = self.env['account.bank.statement'].search([
            ('sepa_imported', '=', True),
            ('journal_id', '=', statement.journal_id.id),
            ('date', '>=', statement.date),
        ], order='date, create_date desc')

        if statements[0] == statement:
            last_stmt = self.env['account.bank.statement'].search([
                ('sepa_imported', '=', True),
                ('journal_id', '=', statement.journal_id.id),
                ('date', '<', statement.date),
            ], order='date desc, create_date desc', limit=1)
        else:
            for st in statements:
                if st == statement:
                    break
                last_stmt = st

        for st in statements:
            if not last_stmt:
                last_stmt = st
                continue
            if tools.float_compare(st.balance_start, last_stmt.balance_end, precision_digits=2) != 0:
                st.write({
                    'balance_start': last_stmt.balance_end,
                })
            if tools.float_compare(st.balance_end_real, st.balance_end, precision_digits=2) != 0:
                st.balance_end_real = st.balance_end
            last_stmt = st

    @api.multi
    def reconciliation_widget_preprocess(self):
        res = super(AccountBankStatement, self).reconciliation_widget_preprocess()
        statement_line_ids = res['st_lines_ids']
        if not statement_line_ids:
            return res
        sql_query = """SELECT stl.id
                FROM account_bank_statement_line stl
                INNER JOIN account_bank_statement st ON
                st.id = stl.statement_id
                WHERE stl.id in %s AND stl.sepa_duplicate = FALSE
                AND st.sepa_imported = TRUE
                ORDER BY stl.id;
        """
        params = (tuple(statement_line_ids),)
        self.env.cr.execute(sql_query, params)
        res['st_lines_ids'] = [line.get('id') for line in self.env.cr.dictfetchall()]
        return res

    @api.multi
    @job
    def apply_journal_import_rules(self):
        skip_error = self.env.context.get('skip_error_on_import_rule')
        lines_to_auto_reconcile = self.env['account.bank.statement.line']
        for rec in self:
            import_rule_ids = rec.journal_id.import_rule_ids
            if not import_rule_ids:
                continue
            for line in rec.line_ids.filtered(
                    lambda l: not l.is_fee and not l.journal_entry_ids and not l.sepa_duplicate and not l.account_id):
                matching_rules = import_rule_ids.find_match(line)
                if not matching_rules:
                    continue
                if len(set(matching_rules.mapped('force_account_id.id'))) > 1:
                    if skip_error:
                        continue
                    raise exceptions.UserError(
                        _('Derinamos importavimo taisyklės eilutei (pavadinimas: %s, importuotas partnerio pavadinimas:'
                          ' %s, importuota partnerio kodas: %s) klaida, grąžintos kelios sąskaitos')
                        % (line.name, line.imported_partner_name, line.imported_partner_code))
                if len(set([rule.force_partner_id and rule.force_partner_id.id or 0 for rule in matching_rules])) > 1:
                    if skip_error:
                        continue
                    raise exceptions.UserError(
                        _('Derinamos importavimo taisyklės eilutei (pavadinimas: %s, importuotas partnerio pavadinimas:'
                          ' %s, importuota partnerio kodas: %s) klaida, grąžinti keli partneriai')
                        % (line.name, line.imported_partner_name, line.imported_partner_code))
                force_account_id = matching_rules.mapped('force_account_id').id
                force_partner = matching_rules.mapped('force_partner_id')
                line.write({'account_id': force_account_id, })
                if force_partner:
                    line.write({'partner_id': force_partner.id})
                lines_to_auto_reconcile |= line

        if lines_to_auto_reconcile:
            lines_to_auto_reconcile.fast_counterpart_creation()

        # Filter out successfully reconciled lines, and only return them
        successfully_reconciled = lines_to_auto_reconcile.filtered(lambda x: x.journal_entry_ids)
        # If some lines were not reconciled, remove forced account_id, it causes further errors
        # Because bank statement line is treated as 'reconciled' if it has journal_entry_ids or
        # account_id, however only place that it gets account is during the reconciliation
        # and it would require addons refactoring
        not_reconciled = lines_to_auto_reconcile.filtered(lambda x: not x.journal_entry_ids)
        not_reconciled.write({'account_id': False})

        return successfully_reconciled

    @api.multi
    def action_apply_bank_import_rules(self):
        for rec in self:
            rec.with_delay(
                eta=5, channel='root.statement_import', identity_key=identity_exact).apply_journal_import_rules()

    @api.multi
    def _auto_reconcile_SODRA_and_GPM(self):
        """
        Used to automatically reconcile SODRA and GPM
        structured bank statement lines with move lines
        :return: None
        """

        # Get global reconciliation settings
        company = self.sudo().env.user.company_id
        skip_structured = company.disable_automatic_structured_reconciliation
        excluded_partners = company.auto_reconciliation_excluded_partner_ids
        excluded_journals = company.auto_reconciliation_excluded_journal_ids

        used_lines = self.env['account.bank.statement.line']
        # If skip structured reconciliation is set, we return,
        # because all of the lines are structured
        if skip_structured:
            return used_lines

        # Get statement lines and try to assign the partners to them
        statement_lines = self.mapped('line_ids')
        statement_lines.relate_line_partners()

        # Filter out statement lines
        lines_to_reconcile = statement_lines.filtered(
            lambda l: l.info_type == 'structured' and not l.journal_entry_ids
            and l.partner_id and l.partner_id not in excluded_partners
            and l.journal_id not in excluded_journals
        )

        # Filter out SODRA and GPM lines, use one loop instead of lambda on same recordset
        sodra_lines = gpm_lines = self.env['account.bank.statement.line']
        for line in lines_to_reconcile:
            if line.name == SODRA_STRUCTURED_CODE:
                sodra_lines |= line
            elif line.name == GPM_STRUCTURED_CODE:
                gpm_lines |= line

        # Reconcile the lines
        sodra_lines._reconcile_with_sodra()
        gpm_lines._reconcile_with_gpm()
        used_lines = gpm_lines | sodra_lines
        return used_lines

    @api.multi
    def mark_as_sepa_imported(self):
        self.write({'sepa_imported': True})

    @api.multi
    def unlink(self):
        for statement in self:
            if statement.state != 'open':
                raise exceptions.UserError(
                    _('Jei norite ištrinti banko įrašą, pirmiausia turite jį atšaukti, '
                      'kad ištrintumėte susijusius žurnalo elementus.')
                )
            statement.line_ids.filtered(lambda line: not line.commission_of_id).unlink()
        return super(AccountBankStatement, self).unlink()

    @api.model
    def action_server_normalize_upward(self):
        action = self.env.ref('sepa.action_server_normalize_upward', False)
        if action:
            action.create_action()

    @api.model
    def action_server_apply_bank_import_rule(self):
        action = self.env.ref('sepa.action_server_apply_bank_import_rule', False)
        if action:
            action.create_action()

    @api.model
    def cron_apply_new_import_rules(self):
        """ Checks for recently updated import rules and tries to auto-reconcile non reconciled statement lines """
        accounting_lock_date = self.env.user.company_id.get_user_accounting_lock_date()
        date_min = (datetime.utcnow() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        rules = self.env['bank.statement.import.rule'].search([('write_date', '>=', date_min)])
        statements = self.env['account.bank.statement'].search([
            ('date', '>', accounting_lock_date),
            ('state', '!=', 'confirm'),
            ('sepa_imported', '=', True),
            ('journal_id', 'in', rules.mapped('journal_id.id'))
        ])
        statements.with_context(skip_error_on_import_rule=True).apply_journal_import_rules()
