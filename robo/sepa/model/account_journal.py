# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools
from odoo.tools import float_compare
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .. import api_bank_integrations as abi


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    type = fields.Selection(inverse='_set_account_journal_type')
    bank_statements_source = fields.Selection(inverse='_set_default_import_type')
    import_file_type = fields.Selection([('sepa', 'SEPA'),
                                         ('globalnet', 'Global-Net'),
                                         ('luminor', 'Luminor'),
                                         ('mistertango', 'MisterTango'),
                                         ('opay', 'OPAY'),
                                         ('payally', 'PayAlly'),
                                         ('payoneer', 'Payoneer'),
                                         ('paypal', 'PayPal'),
                                         ('revolut', 'Revolut'),
                                         ('skrill', 'Skrill'),
                                         ('soldo', 'SOLDO'),
                                         ('stripe', 'Stripe'),
                                         ('transferwise', 'TransferWise'),
                                         ('worldfirst', 'WorldFirst'),
                                         ('braintree_api', 'Braintree'),
                                         ('walletto', 'Walletto'),
                                         ('nexpay', 'Nexpay'),
                                         ('mypos', 'MyPOS'),
                                         ('bitsafe', 'Bitsafe'),
                                         ('coingate', 'CoinGate'),
                                         ('banking_circle', 'BankingCircle'),
                                         ], string='Importuojamo failo tipas', default='sepa')
    import_rule_ids = fields.One2many('bank.statement.import.rule', 'journal_id', string='Importavimo taisyklės')
    gateway_deactivated = fields.Boolean(string='Sąskaita deaktyvuota Gateway lygyje')

    paypal_api_id = fields.Many2one('paypal.api', string='Paypal API nustatymai')
    revolut_api_id = fields.Many2one('revolut.api', related='revolut_account_id.revolut_api_id', string='Revolut API nustatymai')
    has_api_import = fields.Boolean(compute='_compute_has_api_import')
    revolut_account_id = fields.Many2one(
        'revolut.account', groups='robo_basic.group_robo_premium_accountant', inverse='_set_revolut_account_id',
    )
    skip_bank_statement_normalization = fields.Boolean(string='Praleisti banko išrašų normalizavimą')
    force_bank_statement_normalization = fields.Boolean(
        string='Force bank statement normalization',
        help='Upward statement normalization will be applied even if no starting journal entry is found',
    )
    bank_commission_account_id = fields.Many2one('account.account', string='Banko komisinių nurašymo sąskaita')

    # FIELDS USED IF JOURNAL IS OF BANK TYPE AND THE BANK IS API INTEGRATED
    # --------------------------------------------------------------------
    api_integrated_bank = fields.Boolean(compute='_compute_api_integrated_bank', store=True)
    api_integrated_journal = fields.Boolean(compute='_compute_api_integrated_bank')
    api_full_integration = fields.Boolean(compute='_compute_api_integrated_bank')

    api_bank_type = fields.Selection(abi.INTEGRATED_BANKS, compute='_compute_api_integrated_bank', store=True)
    api_end_balance = fields.Monetary(string='Realus banko likutis', groups='robo_basic.group_robo_premium_manager')
    api_balance_update_date = fields.Datetime(string='Likučio sinchronizavimo laikas')
    api_end_balance_company_currency = fields.Monetary(
        string='Realus banko likutis (kompanijos valiuta)',
        compute='_compute_api_end_balance_company_currency', store=True,
        groups='robo_basic.group_robo_premium_manager'
    )
    # --------------------------------------------------------------------

    @api.multi
    @api.depends('currency_id', 'api_balance_update_date', 'api_end_balance')
    def _compute_api_end_balance_company_currency(self):
        """
        Compute //
        Calculate the balance in company currency based on account.journal
        res.currency, API update date and actual API end balance
        :return: None
        """

        # Base values
        date_now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        company_currency = self.env.user.sudo().company_id.currency_id

        for rec in self.filtered(lambda x: x.api_integrated_bank):
            # Get latest API balance update date, if it does not exist, use utc-now
            date = rec.api_balance_update_date if rec.api_balance_update_date else date_now
            context = self._context.copy()
            context.update({'date': date})
            # Check whether journal currency exists, and whether it differs from company
            # currency. If it does, calculate balance in company currency
            if rec.currency_id.id and rec.currency_id.id != company_currency.id:
                rec.api_end_balance_company_currency = rec.currency_id.with_context(context).compute(
                    rec.api_end_balance, company_currency)
            else:
                rec.api_end_balance_company_currency = rec.api_end_balance

    @api.multi
    @api.depends('bank_id.bic', 'bank_id', 'bank_account_id.bank_id', 'bank_account_id.bank_id.bic')
    def _compute_api_integrated_bank(self):
        """
        Compute //
        Check whether account journal belongs to API integrated bank
        (can be reset to False if integration uses tokens that expired)
        :return: None
        """
        for rec in self:
            # Get API configuration data for specific journal.
            data = self.env['api.bank.integrations'].check_api_configuration(rec)

            # Check if bank of the journal is integrated, whether the integration
            # is full or partial and whether IBAN that is contained in this journal
            # is not externally disabled or unauthorized.
            rec.api_bank_type = data.get('api_bank_type')
            rec.api_integrated_bank = data.get('int_bank')
            rec.api_integrated_journal = data.get('int_journal')
            rec.api_full_integration = data.get('full_int')

    @api.one
    @api.depends('import_file_type', 'paypal_api_id', 'revolut_api_id')
    def _compute_has_api_import(self):
        if self.import_file_type == 'paypal' and self.paypal_api_id:
            self.has_api_import = True
        elif self.import_file_type == 'revolut' and self.revolut_account_id:
            self.has_api_import = True
        else:
            self.has_api_import = False

    @api.multi
    def _set_revolut_account_id(self):
        for rec in self:
            if not rec.revolut_account_id.bank_account_iban or rec.import_file_type != 'revolut':
                continue
            if rec.bank_acc_number and rec.bank_acc_number != rec.revolut_account_id.bank_account_iban:
                raise exceptions.ValidationError(_('IBAN of the journal does not match the Revolut account IBAN.'))
            rec.bank_acc_number = rec.revolut_account_id.bank_account_iban
            rec.bank_id = self.env['res.bank'].search([
                ('bic', '=', rec.revolut_account_id.bank_account_bic)
            ], limit=1).id

    @api.multi
    def _set_account_journal_type(self):
        """
        Set bank statement source, create default import rules to bank
        journals and check whether there's any enable banking connectors to activate
        """
        bank_journals = self.filtered(lambda j: j.type == 'bank')
        bank_journals.write({'bank_statements_source': 'file_import'})
        bank_journals._create_default_import_rules()
        # Loop through bank journals and activate enable banking connectors if any
        for bank_journal in bank_journals:
            self.env['enable.banking.connector'].activate_connectors(journal=bank_journal)

    @api.multi
    def _set_default_import_type(self):
        for rec in self:
            if rec.bank_statements_source == 'file_import' and not rec.import_file_type:
                rec.import_file_type = 'sepa'

    @api.multi
    @api.constrains('revolut_account_id')
    def _check_revolut_account_id_unique(self):
        company_curr = self.env.user.company_id.currency_id
        for rec in self.filtered('revolut_account_id'):
            journal_currency = rec.currency_id or company_curr
            if rec.revolut_account_id.currency_id != journal_currency:
                raise exceptions.ValidationError(_('Buhalterinės sąskaitos ir žurnalo valiuta skiriasi'))
            if self.env['account.journal'].search_count(
                    [('revolut_account_id', '=', rec.revolut_account_id.id),
                     ('id', '!=', rec.id)]):
                raise exceptions.ValidationError(_('Du žurnalai negali jungtis prie to paties Revolut API'))

    @api.constrains('import_file_type', 'bank_acc_number')
    def _check_bank_account_number_set(self):
        for rec in self:
            if rec.import_file_type == 'walletto' and not rec.bank_acc_number:
                raise exceptions.ValidationError(_('You have to set the bank account number for Walletto journal.'))

    @api.model
    def _get_default_import_rule_account_code(self):
        return '631203'

    @api.model
    def _get_default_import_rule_line_names(self):
        return [
            'už pervedimą banko viduje internetu',
            'už pervedimą į kitą banką internetu',
            'Komisinis mokestis',
            'Komisinis už pervedimą',
            'SIBV vietinio pavedimo mokestis',
            'MP banko mokestis SIBV',
            'TMP banko mokestis',
        ]

    @api.model
    def get_journal_code_bank(self):
        """
        Return code for account.journal of bank type
        Method checks whether the code is not yet taken
        :return: code (str)
        """
        for i in range(1, 100):
            code = 'BNK' + str(i)
            if not self.sudo().env['account.journal'].with_context(
                    active_test=False).search_count([('code', '=', code)]):
                return code
        raise exceptions.ValidationError(_('Nebėra laisvų banko kodų'))

    @api.multi
    def _create_default_import_rules(self):
        account = self.env['account.account'].sudo().search([('code', '=', self._get_default_import_rule_account_code())])
        if not account:
            return
        account_id = account.id
        line_names = self._get_default_import_rule_line_names()
        for journal in self:
            existing_rules = journal.import_rule_ids.filtered(
                lambda r: r.amount_type == 'negative' and not r.line_imported_partner_name and not r.line_imported_partner_code
            ).mapped('line_name')
            journal.write({
                'import_rule_ids': [(0, 0, {'line_name': name,
                                            'amount_type': 'negative',
                                            'force_account_id': account_id, })
                                    for name in line_names if name not in existing_rules]
            })

    # Overrides method defined in account to stop changing bank_statements_source field to manual
    @api.multi
    def create_bank_statement(self):
        """return action to create a bank statements. This button should be called only on journals with type =='bank'"""
        action = self.env.ref('account.action_bank_statement_tree').read()[0]
        action.update({
            'views': [[False, 'form']],
            'context': "{'default_journal_id': " + str(self.id) + "}",
        })
        return action

    @api.multi
    def import_via_api(self):
        self.ensure_one()
        if not self.has_api_import:
            return
        action_name = 'sepa.account_bank_statement_api_import_' + self.import_file_type
        [action] = self.env.ref(action_name).read()
        action.update({'context': (u"{'default_journal_id': " + str(self.id) + u"}")})
        return action

    @api.multi
    def import_statement(self):
        self.ensure_one()
        action_name = 'sepa.account_bank_statement_import_%s' % self.import_file_type
        try:
            [action] = self.env.ref(action_name).read()
        except ValueError:
            raise exceptions.UserError(_('Nenustatytas žurnalo importo tipas'))
        # Note: this drops action['context'], which is a dict stored as a string, which is not easy to update
        action.update({'context': (u"{'default_journal_id': " + str(self.id) + u"}")})
        return action

    @api.multi
    def action_open_api_bank_query_wizard(self):
        """
        Method that opens the wizard from which user
        can manually query bank statements for a bank
        that is integrated with our system
        :return: JS action (dict)
        """
        self.ensure_one()
        self._compute_api_integrated_bank()

        if not self.api_integrated_bank:
            raise exceptions.ValidationError(_('Operacija galima tik integruotiems bankams!'))

        # Create wizard record
        wizard = self.env['api.query.bank.statements.wizard'].create({
            'journal_id': self.id
        })
        # Return the form for bank statement querying
        return {
            'name': _('Banko išrašų sinchronizavimas'),
            'type': 'ir.actions.act_window',
            'res_model': 'api.query.bank.statements.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('sepa.form_api_query_bank_statements_wizard').id,
        }

    @api.multi
    def action_open_statement_balance_recalculation_wizard(self):
        """
        Method that opens the wizard from which user
        can manually recalculate balances for any
        bank journal in descending/ascending fashion.
        :return: JS action (dict)
        """
        self.ensure_one()

        # Create wizard record and set defaults
        wizard = self.env['bank.statement.balance.recalculation.wizard'].create({
            'journal_id': self.id,
        })

        # Return the form for bank statement balance recalculation
        return {
            'name': _('Bank statement balance recalculation'),
            'type': 'ir.actions.act_window',
            'res_model': 'bank.statement.balance.recalculation.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'res_id': wizard.id,
            'view_id': self.env.ref('sepa.bank_statement_balance_recalculation_wizard_view_form').id,
        }

    @api.multi
    def get_journal_dashboard_datas(self):
        self.ensure_zero_or_one()
        res = super(AccountJournal, self).get_journal_dashboard_datas()
        if self.type in ['bank', 'cash']:
            self.env.cr.execute("""SELECT COUNT(DISTINCT(statement_line_id))
                        FROM account_move where statement_line_id
                        IN (SELECT line.id
                            FROM account_bank_statement_line AS line
                            LEFT JOIN account_bank_statement AS st
                            ON line.statement_id = st.id
                            WHERE st.journal_id IN %s
                              AND st.state = 'open'
                              AND st.sepa_imported = True
                              AND line.sepa_duplicate = False)""",
                                (tuple(self.ids),))
            already_reconciled = self.env.cr.fetchone()[0]
            self.env.cr.execute("""SELECT COUNT(line.id)
                                FROM account_bank_statement_line AS line
                                LEFT JOIN account_bank_statement AS st
                                ON line.statement_id = st.id
                                WHERE st.journal_id IN %s
                                  AND st.state = 'open'
                                  AND st.sepa_imported = True
                                  AND line.sepa_duplicate = False""",
                                (tuple(self.ids),))
            all_lines = self.env.cr.fetchone()[0]
            number_to_reconcile = all_lines - already_reconciled
            res['number_to_reconcile'] = number_to_reconcile
        return res

    @api.multi
    def has_psd2_statements(self):
        self.ensure_one()
        if self.env['account.bank.statement'].search_count([('journal_id', '=', self.id),
                                                            ('psd2_statement', '=', True)]):
            return True
        return False

    @api.model
    def cron_fetch_revolut_transactions(self):
        now = datetime.now()
        date_from = now + relativedelta(days=-1, hour=0, minute=0, second=0)
        date_to = now + relativedelta(hour=0, minute=0, second=0)
        journals = self.env['account.journal'].search([
            ('revolut_account_id', '!=', False),
            ('revolut_account_id.revolut_api_id.disabled', '!=', True),
        ])
        for journal in journals:
            revolut_api = journal.revolut_api_id
            if not revolut_api.client_id:
                continue
            transactions = revolut_api.with_context(importing_to_journal=journal).get_transactions(date_from=date_from, date_to=date_to, count=-1)
            transactions.mapped('leg_ids').create_statements(filtered_journal=journal,
                                                             apply_import_rules=True)

    @api.model
    def cron_revolut_weekly_transaction_refetch(self):
        now = datetime.now()
        date_from = now + relativedelta(days=-8, hour=0, minute=0, second=0)
        date_to = now + relativedelta(hour=0, minute=0, second=0)
        journals = self.env['account.journal'].search([
            ('revolut_account_id', '!=', False),
            ('revolut_account_id.revolut_api_id.disabled', '!=', True),
        ])
        for journal in journals:
            revolut_api = journal.revolut_api_id
            if not revolut_api.client_id:
                continue
            transactions = revolut_api.with_context(importing_to_journal=journal).get_transactions(date_from=date_from, date_to=date_to, count=-1)
            transactions.mapped('leg_ids').create_statements(filtered_journal=journal,
                                                             apply_import_rules=True)


AccountJournal()


class BankStatementImportRule(models.Model):
    _name = 'bank.statement.import.rule'

    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True, ondelete='cascade')
    line_name = fields.Char(string='Pavadinimas')
    reference = fields.Char(string='Numeris')
    line_imported_partner_name = fields.Char(string='Importuotas partnerio pavadinimas')
    line_imported_partner_code = fields.Char(string='Importuotas partnerio kodas')
    force_account_id = fields.Many2one('account.account', string='Priverstinė sąskaita', required=True)
    force_partner_id = fields.Many2one('res.partner', string='Priverstinis partneris')
    amount_type = fields.Selection([('all', 'Visos'),
                                    ('positive', 'Teigiamos'),
                                    ('negative', 'Neigiamos')], string='Sumos', default='all',
                                   help='Taikyti tik toms eilutėms, kurių suma yra šio ženklo')

    @api.multi
    @api.constrains('line_imported_partner_code', 'line_imported_partner_name', 'line_name', 'reference')
    def _check_atleast_one_criterion(self):
        for rec in self:
            if not (rec.line_name or rec.line_imported_partner_name or rec.line_imported_partner_code or rec.reference):
                raise exceptions.ValidationError(_('Turite nurodyti bent vieną kriterijų atitikimo taisyklėms.'))

    @api.multi
    @api.constrains('force_account_id', 'force_partner_id')
    def _check_partner_if_reconcilable_account(self):
        for rec in self:
            if rec.force_account_id and rec.force_account_id.reconcile and not rec.force_partner_id:
                raise exceptions.ValidationError(_('Turite nurodyti partnerį sudengiamai sąskaitai.'))

    @api.onchange('line_name')
    def _onchange_line_name(self):
        if self.line_name:
            self.line_name = self.line_name.lstrip()

    @api.onchange('reference')
    def _onchange_reference(self):
        if self.reference:
            self.reference = self.reference.lstrip()

    @api.onchange('line_imported_partner_name')
    def _onchange_line_imported_partner_name(self):
        if self.line_imported_partner_name:
            self.line_imported_partner_name = self.line_imported_partner_name.lstrip()

    @api.onchange('line_imported_partner_code')
    def _onchange_line_imported_partner_code(self):
        if self.line_imported_partner_code:
            self.line_imported_partner_code = self.line_imported_partner_code.strip()

    @api.multi
    def find_match(self, st_line):
        """
        Find rules that match the line
        :param st_line: an account.bank.statement.line record
        :return: all the rules from self that match the lines
        :rtype: RecordSet
        """
        st_line.ensure_one()
        return self.filtered(lambda r: r._match_line(st_line))

    @api.multi
    def _match_line(self, line):
        """
        Check a statement line against an import rule, and returns True if they match
        :param line: account.bank.statement.line single record
        :return: True/False
        """
        self.ensure_one()
        pcode_match = not self.line_imported_partner_code \
                      or self.line_imported_partner_code == line.imported_partner_code
        if not pcode_match:
            return False
        if self.amount_type != 'all':
            amount_cmp_zero = float_compare(line.amount, 0.0, precision_digits=2)
            if amount_cmp_zero < 0 and self.amount_type == 'positive' \
                    or amount_cmp_zero > 0 and self.amount_type == 'negative':
                return False
        name_match = not self.line_name or self.line_name in line.name
        if not name_match:
            return False
        reference_match = not self.reference or line.ref and self.reference in line.ref
        if not reference_match:
            return False
        pname_match = not self.line_imported_partner_name or line.imported_partner_name \
                      and self.line_imported_partner_name in line.imported_partner_name
        if not pname_match:
            return False
        return True


BankStatementImportRule()
