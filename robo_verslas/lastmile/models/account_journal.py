# -*- encoding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import fields, models, _, api, exceptions, tools
from odoo.addons.sepa.wizard.account_revolut_import import find_partner_name
from collections import defaultdict


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.multi
    def import_from_csv_table(self, date_min='2020-10-01', date_max=None, ttype='CARD_PAYMENT', limit=100, account=None):
        """ Import from CSV table """
        self.ensure_one()
        if self.import_file_type != 'revolut':
            raise exceptions.UserError(_('This is not a Revolut journal'))
        params = [self.id, date_min, ttype]
        query = '''
        SELECT t.* FROM revolut_csv_import t
        LEFT JOIN account_bank_statement_line l ON l.entry_reference = t.transaction_id AND l.journal_id = %s
        WHERE l.id IS NULL
        AND t.date_completed >= %s
        AND t.ttype = %s
        '''
        if account:
            query += ''' AND account like %s '''
            params.append(account)
        if date_max:
            query += ''' AND t.date_completed <= %s '''
            params.append(date_max)
        query += '''
        ORDER BY date_completed
        LIMIT %s
        ;
        '''
        params.append(limit)
        self.env.cr.execute(query, tuple(params))
        data = defaultdict(list)
        for transaction in self.env.cr.dictfetchall():
            date = transaction.get('date_completed')
            #Try to guess partner:
            partner_name = ''
            try:
                transaction_type = transaction.get('ttype')
                desc = transaction.get('description')
                partner_name = find_partner_name(transaction_type, desc)
                partner_name = partner_name or transaction.merchant_name
                partner_id = self.env['sepa.csv.importer'].get_partner_id(partner_name=partner_name)
            except:
                partner_id = False
            vals = {
                'date': transaction.get('date_completed'),
                'completed_at': transaction.get('date_completed'),
                'journal_id': self.id,
                'entry_reference': transaction.get('transaction_id'),
                'partner_id': partner_id,
                'info_type': 'unstructured',
                'name': transaction.get('description'),
                'ref': 'CSV import',
                'imported_partner_name': partner_name,
                'amount': transaction.get('amount'),
            }
            data[date.split()[0]].append(vals)
        self.env['revolut.api.transaction.leg']._create_statements({self.id: data}, self._context.get('apply_import_rules', True))

    @api.model
    def cron_fetch_revolut_transactions(self):
        now = datetime.now()
        date_from = now + relativedelta(days=-1, hour=0, minute=0, second=0)
        date_to = now + relativedelta(hour=0, minute=0, second=0)
        journals = self.env['account.journal'].search([('revolut_account_id', '!=', False)])
        for journal in journals:
            self.env['revolut.import.job'].sudo().create_jobs(journal, date_from, date_to)

    @api.model
    def cron_revolut_weekly_transaction_refetch(self):
        now = datetime.now()
        date_from = now + relativedelta(days=-8, hour=0, minute=0, second=0)
        date_to = now + relativedelta(hour=0, minute=0, second=0)
        journals = self.env['account.journal'].search([('revolut_account_id', '!=', False)])
        for journal in journals:
            self.env['revolut.import.job'].sudo().create_jobs(journal, date_from, date_to)
