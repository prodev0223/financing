# -*- encoding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools
from odoo.addons.queue_job.job import job, identity_exact
import logging
_logger = logging.getLogger(__name__)


class RevolutImportJob(models.Model):
    _name = 'revolut.import.job'
    _inherit = 'mail.thread'

    def _get_default_journal_id(self):
        return self.env['account.journal'].search([('revolut_account_id', '!=', False)], limit=1)

    journal_id = fields.Many2one('account.journal', required=True, default=_get_default_journal_id,
                                 domain=[('revolut_account_id', '!=', False)])
    date_from = fields.Datetime('Date from', required=True)
    date_to = fields.Datetime('Date to', required=True)
    completion_date = fields.Datetime('Completion date')
    state = fields.Selection([('to_run', 'Not imported'),
                              ('imported', 'Imported'),
                              ('error', 'Failed')], string='Status', default='to_run')
    error_message = fields.Char(string='Store error message')

    @api.constrains('date_to', 'date_from')
    def _check_dates(self):
        for rec in self:
            if rec.date_to <= rec.date_from:
                raise exceptions.UserError('Date from should be before date to')

    @api.multi
    def name_get(self):
        return [(rec.id, 'Import on %s between %s and %s' % (rec.journal_id.name, rec.date_from, rec.date_to)) for rec in self]

    @api.model
    def create_jobs(self, journal, date_from, date_to, hour_gap=6):
        """
        Create import jobs
        param: journal: account.journal record
        param: date_from: datetime object
        param: date_to: datetime object
        param: hour_gap: maximum gap between date_from and date_to, splits into multiple jobs if necessary. Do not anything if < 1

        returns: None
        """
        if not journal.revolut_account_id:
            raise exceptions.UserError('You can only create jobs for integrated revolut journals')

        if hour_gap > 0:
            jobs = self.env['revolut.import.job']
            start = date_from
            end = start + relativedelta(hours=hour_gap)
            while start < date_to:
                jobs |= self.create_jobs(journal, start, end, 0)
                start, end = end, min(end + relativedelta(hours=hour_gap), date_to)
            for job in jobs:
                job.with_delay(eta=30, channel='root.statement_import', identity_key=identity_exact).process_job()
        else:
            return self.create({
                'journal_id': journal.id,
                'date_from': date_from.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'date_to': date_to.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            })

    @api.model
    def cron_process_revolut_jobs(self):
        jobs = self.search([('state', '=', 'to_run'),
                           ('date_to', '<=', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)),])
        for job in jobs:
            job.with_delay(eta=5, channel='root.statement_import', identity_key=identity_exact).process_job()

    @api.multi
    @job
    def process_job(self):
        """ Process Revolut import job """
        for job in self:
            if job.state == 'imported':
                continue
            try:
                _logger.info("processing job %d", job.id)
                journal = job.journal_id
                revolut_api = journal.revolut_api_id.with_context(importing_to_journal=journal)
                transactions = revolut_api.get_transactions(date_from=job.date_from, date_to=job.date_to, count=-1)
                transactions.mapped('leg_ids').create_statements(filtered_journal=journal,
                                                                 apply_import_rules=True)
                job.write({
                    'state': 'imported',
                    'completion_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'error_message': False,
                })

                self.env.cr.commit()
            except Exception as e:
                self.env.cr.rollback()
                message = str(e.args[0] if e.args else e)
                job.write({
                    'state': 'error',
                    'completion_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                    'error_message': message,
                })

    @api.model
    def cron_inform_about_failed_jobs(self):
        lim = (datetime.utcnow() + relativedelta(minutes=-75)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        failed_jobs = self.search([('state', '=', 'error'), ('completion_date', '>=', lim)], count=True)
        if failed_jobs:
            self.env['robo.bug'].create({
                'error_message': 'There are %d failed Revolut import jobs in the last 75 minutes' % failed_jobs,
            })
