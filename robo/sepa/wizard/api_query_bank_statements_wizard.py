# -*- encoding: utf-8 -*-
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.sepa import api_bank_integrations as abi
from dateutil.relativedelta import relativedelta
from datetime import datetime
import pytz


class APIQueryBankStatementsWizard(models.TransientModel):
    _name = 'api.query.bank.statements.wizard'

    @api.model
    def _default_date_to(self):
        """Default date to - day before current day"""
        offset = int(datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%z')[1:3])
        return datetime.utcnow() - relativedelta(days=1, hour=23, minute=59, second=59, hours=offset)

    @api.model
    def _default_date_from(self):
        """Default date from - start of the month"""
        offset = int(datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%z')[1:3])
        return datetime.utcnow() - relativedelta(day=1, hour=0, minute=0, second=0, hours=offset)

    date_from = fields.Datetime(string='Data nuo', default=_default_date_from)
    date_to = fields.Datetime(string='Data iki', default=_default_date_to)
    journal_id = fields.Many2one('account.journal', string='Žurnalas', inverse='_set_journal_id')
    display_psd2_warning = fields.Boolean(compute='_compute_display_psd2_warning')

    @api.multi
    def _set_journal_id(self):
        """If integration is of non-SEPA type, set date_to to current time instead of day before"""
        self.ensure_one()
        if self.journal_id.api_bank_type in abi.INTEGRATED_NON_SEPA_BANKS:
            self.date_to = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @api.multi
    def _compute_display_psd2_warning(self):
        """Check whether warning for SEPA/PSD2 mismatch-skipping should be displayed"""
        for rec in self:
            if rec.journal_id.api_bank_type == 'enable_banking' and rec.journal_id.api_integrated_journal:
                rec.display_psd2_warning = True

    @api.multi
    def query_bank_statements(self):
        """
        Method that is used to query bank statements for
        specific account journal that is integrated.
        Method fetches corresponding model and method
        based on journal integration type
        :return: result of the specific bank query method
        """
        self.ensure_one()

        def localize_date(date_string):
            """Localizes passed datetime string to Vilnius TZ"""
            date_from_dt = datetime.strptime(date_string, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            offset = int(pytz.timezone('Europe/Vilnius').localize(date_from_dt).strftime('%z')[1:3])
            date_local = (date_from_dt + relativedelta(
                hours=offset)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            return date_local

        # Check basic constraints
        if not self.date_to or not self.date_from:
            raise exceptions.ValidationError(
                _('Kviečiant banko išrašų sinchronizavimo vedlį privaloma nurodyti datą nuo ir datą iki!'))

        if self.date_from > self.date_to:
            raise exceptions.ValidationError(_('Date from must be earlier than date to!'))

        # Ensure that statement query cannot be sent for a period earlier than lock date
        accounting_lock_date = self.env.user.company_id.get_user_accounting_lock_date()
        if accounting_lock_date and self.date_from < accounting_lock_date:
            raise exceptions.ValidationError(
                _('You cannot fetch bank statements earlier than the lock date {}!').format(accounting_lock_date)
            )

        if not self.journal_id:
            raise exceptions.ValidationError(
                _('Kviečiant banko išrašų sinchronizavimo vedlį privaloma nurodyti žurnalą!'))

        # Create bank statement fetch job record, and wait for the cron to pick it up
        # for execution. Do not manually call the cron because it can lead to concurrency
        vals = {
            'journal_id': self.journal_id.id,
            'statement_start_date': localize_date(self.date_from),
            'statement_end_date': localize_date(self.date_to),
            'state': 'waiting',
            'user_id': self.env.user.id,
        }
        self.env['bank.statement.fetch.job'].create(vals)
