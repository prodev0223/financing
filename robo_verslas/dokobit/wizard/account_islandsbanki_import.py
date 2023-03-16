# -*- encoding: utf-8 -*-
import base64
from datetime import datetime
from collections import defaultdict
from lxml import etree
from odoo import models, fields, api, _, tools
from odoo import exceptions


class AccountIslandsbankiImport(models.TransientModel):
    _name = 'account.islandsbanki.import'

    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True)

    file_data = fields.Binary(string='Dokumentas', required=True)
    file_fname = fields.Char(string='Dokumento pavadinimas', invisible=True)

    apply_import_rules = fields.Boolean(string='Taikyti importavimo taisykles', default=True)
    skip_import_rules_error = fields.Boolean(string='Praleisti eilutes su importavimo taisyklių klaidomis',
                                             default=False,
                                             help=(
                                                 'Jei nustatyta, kai eilutė atitinka kelias taisykles su nesuderinamomis'
                                                 ' instrukcijomis, ji praleidžiama. Jei išjungta, iškeliama klaida.'))

    def file_parsing(self):
        """
        Islandsbanki XMl parser, parses uploaded XML file and
        updates/creates 'account.bank.statement' and populates
        it with 'account.bank.statement.line' elements extracted
        from the uploaded Icelandic XML.
        """
        try:
            xml_str = base64.decodestring(self.file_data)
            root = etree.fromstring(xml_str)
            values = self._parse_account_data(root.find('reikningur'))
            transaction_data = values.get('transactions', {})
            statements = self.env['account.bank.statement']
            for date_str, lines in transaction_data.items():
                statement = self._create_statement(lines)
                statements |= statement

            if statements and self.apply_import_rules:
                statements.with_context(
                    skip_error_on_import_rule=self.skip_import_rules_error).apply_journal_import_rules()

            if statements:
                action = self.env.ref('account.action_bank_statement_tree')
                return {
                    'name': action.name,
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'res_model': action.res_model,
                    'domain': [('id', 'in', statements.ids)],
                    'context': action.context,
                    'type': 'ir.actions.act_window',
                }
            else:
                raise exceptions.UserError(_('Panašu, kad nebuvo naujų importuojamų eilučių'))
        except Exception as e:
            raise exceptions.UserError(
                'Problema importuojant Islandsbanki išrašą. Susisiekite su sistemos administratoriais\n{0}'.format(e))

    def _create_statement(self, lines):
        """
        Creates or fetches an 'account.bank.statement' and creates and adds
        a relation to imported 'account.bank.statement.line' lines.
        Argument 'lines' is a list or tuple of dicts, where each
        dict contains values for a line that needs to be created.
        ALL LINE DICTS MUST SHARE THE SAME DATE
        """
        statement = self.env['account.bank.statement'].search([
            ('journal_id', '=', self.journal_id.id),
            ('sepa_imported', '=', True),
            ('date', '=', lines[0].get('date'))
        ], limit=1)
        if not statement:
            statement = self.env['account.bank.statement'].create({
                'name': 'Islandsbanki import',
                'journal_id': self.journal_id.id,
                'sepa_imported': True,
                'date': lines[0].get('date'),
            })
        if statement.state != 'open':
            statement.write({'state': 'open'})

        statement.line_ids = [(0, 0, line) for line in lines]
        statement.balance_end_real = statement.balance_end
        return statement

    def _parse_account_data(self, account_element):
        """
        Parses bank account data from a supplied 'account_element'
        argument. 'account_element' argument is an XML element.
        """
        return {
            'transactions': self._parse_transactions(account_element.find('faerslur')),
        }

    def _parse_transactions(self, transactions):
        """
        Parses transactions data from a supplied 'transactions' argument.
        'transactions' argument is an XML element.
        Returns a dict of transactions, where key is the date of transactions
        and the value is a list of transactions made that day.
        """
        partners_by_name = {}
        transactions_by_date = defaultdict(list)
        for transaction in transactions:
            transaction_date = transaction.find('dagsetning').text
            transaction_date = datetime.strptime(transaction_date, '%d.%m.%Y').strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            details_text = transaction.find('textalykill').text
            partners_name = transaction.find('motadili').text
            amount = transaction.find('hreyfing').text
            name = '%s %s %s %s' % (transaction_date, partners_name, amount, details_text)
            transaction = {
                'date': transaction_date,
                'name': name,
                'info_type': 'unstructured',
                'amount': amount,
            }
            # If partner has not been queried, query it, else fetch from cache
            if partners_name not in partners_by_name.keys():
                partner = self.env['res.partner'].search([('name', '=', partners_name)])
                if len(partner) > 1:
                    continue
                partners_by_name[partners_name] = partner if partner else None
            else:
                partner = partners_by_name.get(partners_name)
            # Append either partner or partners name to transaction, depending on if partner exists
            if partner and details_text == u'Millif\xe6rt':
                transaction['partner_id'] = partner.id
            transaction['imported_partner_name'] = partners_name
            transactions_by_date[transaction_date].append(transaction)

        return transactions_by_date
