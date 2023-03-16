# -*- coding: utf-8 -*-
from odoo.addons.sepa import api_bank_integrations as abi
from odoo import models, fields, tools, api, _
from dateutil.relativedelta import relativedelta
from datetime import datetime


class BankStatementFetchJob(models.Model):
    """
    Model that is used to store results of manual
    statement querying via bank APIs
    """
    _name = 'bank.statement.fetch.job'
    _inherit = ['mail.thread']
    _order = 'execution_start_date desc'

    journal_id = fields.Many2one('account.journal', string='Banko žurnalas')

    # Execution dates
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')

    # Statement dates
    statement_start_date = fields.Datetime(string='Išrašo pradžios data')
    statement_end_date = fields.Datetime(string='Išrašo pabaigos data')

    # Status/Info fields
    message_posted = fields.Boolean(string='Informuota')
    error_message = fields.Char(string='Klaidos pranešimas')
    state = fields.Selection(
        [('waiting', 'Laukiama vykdymo'),
         ('in_progress', 'Vykdoma'),
         ('in_progress_external', 'Vykdoma (nutolusioje sistemoje)'),
         ('succeeded', 'Sėkmingai įvykdyta'),
         ('failed', 'Vykdymas nepavyko')], string='Būsena',
        default='waiting'
    )

    # File information (Does not apply to integrations of non-SEPA type)
    fetched_file = fields.Binary(string='Gautas failas', attachment=True, readonly=True)
    fetched_file_name = fields.Char(string='Failo pavadinimas')

    # Extra information
    user_id = fields.Many2one('res.users', string='Naudotojas')
    user_name = fields.Char(compute='_compute_user_name', string='Naudotojas')

    @api.multi
    def _compute_user_name(self):
        """
        Gets user name from user_id, so m2o field is not displayed in form
        :return: None
        """
        for rec in self.filtered(lambda x: x.user_id):
            rec.user_name = rec.user_id.name

    # Main methods //

    @api.multi
    def close_statement_fetch_job(self, state, error_message):
        """Writes the state, execution date to the job and calls message post"""
        self.ensure_zero_or_one()
        self.write({
            'state': state,
            'error_message': error_message,
            'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
        })
        self.post_message()

    @api.multi
    def post_message(self):
        """
        Method meant to be overridden. Posts a message in the
        bank fetch job record about export status.
        :return: None
        """
        for rec in self.filtered(lambda x: x.error_message):
            rec.message_post(**{'body': rec.error_message})

    @api.multi
    def reset_state(self):
        """Used to reset the state on stuck jobs"""
        self.write({'state': 'succeeded'})

    # Utility //

    @api.multi
    def name_get(self):
        return [(rec.id, _('Išrašų užklausa #{}').format(rec.id)) for rec in self]

    # Cron-Job //

    @api.model
    def cron_bank_statement_fetch_job_cleanup(self):
        """
        Deletes jobs that are older than a week
        :return: None
        """
        # Use two days gap, so system is not clogged
        current_date_dt = (datetime.now() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        fetch_jobs = self.search([('execution_end_date', '<', current_date_dt)])
        fetch_jobs.unlink()

    @api.model
    def cron_execute_fetch_job_sequentially(self):
        """
        Cron job that runs every x minutes (small interval)
        and checks whether there are no currently running fetch jobs,
        if there aren't, it tries to execute new ones sequentially,
        based on ascending create date.
        :return: None
        """
        # Execute only if there's no 'in_progress' jobs
        if self.env['bank.statement.fetch.job'].search_count([('state', '=', 'in_progress')]):
            return
        # Get the waiting job ordering by ascending create date
        fetch_job = self.env['bank.statement.fetch.job'].search(
            [('state', '=', 'waiting')], limit=1, order='create_date')
        if fetch_job:
            # Reference the bank method based on the journal model
            model_name, method_name = self.env['api.bank.integrations'].get_bank_method(
                fetch_job.journal_id, m_type='query_transactions_non_threaded')
            method_instance = getattr(self.env[model_name], method_name)
            # Update fetch job values
            fetch_job.write({
                'state': 'in_progress',
                'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            })
            self.env.cr.commit()
            # Execute the method instance with fetch job values
            fetching_state, error_message = 'succeeded', str()
            try:
                # Try to fetch the statements
                method_instance(
                    fetch_job.journal_id, fetch_job.statement_start_date,
                    fetch_job.statement_end_date
                )
            except Exception as exc:
                self.env.cr.rollback()
                fetching_state = 'failed'
                error_message = _('Išrašų traukimo klaida - {}').format(exc.args[0] if exc.args else str())

            # Swed-bank fetch jobs are closed in internal
            if fetch_job.journal_id.bank_id.bic == abi.SWED_BANK and fetching_state == 'succeeded':
                fetch_job.write({'state': 'in_progress_external'})
            else:
                fetch_job.close_statement_fetch_job(fetching_state, error_message)
