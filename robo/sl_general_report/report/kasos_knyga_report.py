# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.tools import float_compare, float_round
from six import iteritems


class ReportKasosKnyga(models.AbstractModel):
    _name = 'report.sl_general_report.report_kasos_knyga_template'

    def get_lines(self, date_from, date_to, journal_id, include_canceled):
        """
        Gather data for account.payment report generation.
        Data is gathered from move lines, and if 'include_canceled' is ticked
        account.payment records are searched.
        :param date_from: report date_from
        :param date_to: report date_to
        :param journal_id: journal_id of the entries (move lines, payments)
        :param include_canceled: signifies whether canceled account.payments should be included
        :return: grouped data or empty dict (dict)
        """
        journal = self.env['account.journal'].browse(journal_id)
        if not journal.default_debit_account_id or not journal.default_credit_account_id:
            return dict()
        account_ids = (journal.default_debit_account_id.id, journal.default_credit_account_id.id)

        # Fetch the initial balance
        query = '''SELECT SUM(balance) FROM account_move_line aml
            WHERE aml.account_id in %s
            AND aml.date < %s'''
        params = (account_ids, date_from)
        self._cr.execute(query, params)

        # Prepare the variables and create initial line
        lines = []
        num_in = num_out = 0
        starting_balance = float_round(self._cr.dictfetchall()[0]['sum'] or 0.00, precision_digits=2)
        starting_line = {'date': date_from, 'balance': starting_balance}

        company_partner_name = self.env.user.company_id.partner_id.name
        extra_data = []
        if include_canceled:
            # No need to use the query here - It's relatively fast and does not make much of a difference
            canceled_payments = self.env['account.payment'].search(
                [('payment_date', '>=', date_from), ('payment_date', '<=', date_to),
                 ('journal_id', '=', journal_id), ('state', '=', 'canceled'), ('name', '!=', False)])

            # Loop through canceled payments
            for payment in canceled_payments:
                # Round the payment amount and determine payment type
                amount = float_round(payment.amount, precision_digits=2)

                is_out = payment.payment_type in ('outbound', 'transfer')
                account = payment.force_destination_account_id or payment.destination_account_id
                # Prepare the dictionary of lines
                extra_data.append({'date': payment.payment_date,
                                   'partner_name': payment.partner_id.name,
                                   'account_name': account.name,
                                   'account_code': account.code,
                                   'debit': amount if not is_out else 0.0,
                                   'credit': amount if is_out else 0.0,
                                   'balance': amount * -1 if is_out else amount,
                                   'name': payment.display_name,
                                   'canceled': True,
                                   })

        # Query to fetch account move_lines that belong to a move that has one or more lines
        # that do belong to the accounts and one or more lines that do not
        aml_query = '''
            SELECT aml.name, aml.account_id, aml.move_id, aml.date, aml.id AS aml_id,
                   aml.credit, aml.debit, aml.balance, rp.name AS partner_name, 
                   aa.code AS account_code, aa.name AS account_name 
            FROM account_move_line AS aml
                LEFT JOIN res_partner AS rp ON rp.id = aml.partner_id
                INNER JOIN account_account AS aa ON aa.id = aml.account_id
            WHERE move_id IN
            (SELECT move_id FROM account_move_line aml 
                INNER JOIN account_move am ON am.id = aml.move_id 
                WHERE
                   aml.date >= %(df)s
                   AND aml.date <= %(dt)s
                   AND am.state = 'posted' 
                   AND aml.account_id IN %(a_ids)s
                GROUP BY move_id) ORDER BY move_id
        '''
        self.env.cr.execute(aml_query, {'df': date_from, 'dt': date_to, 'a_ids': account_ids})
        move_lines = self.env.cr.dictfetchall()

        aml_by_move = {}
        aml_data = []

        # We group fetched lines by move_id
        for line in move_lines:
            aml_by_move.setdefault(line['move_id'], [])
            aml_by_move[line['move_id']].append(line)

        # Loop through the lines/moves dict
        for move_id, m_lines in iteritems(aml_by_move):
            sanitized_line_data = {}

            # Main line is the first line of the move that contains the account
            main_line = next(x for x in m_lines if x['account_id'] in account_ids)

            # Secondary line is any other line that is not the main line
            secondary_line = next(x for x in m_lines if x['aml_id'] != main_line['aml_id'])

            # Take every bit of data from main line except account data
            for key, val in secondary_line.items():
                if key in ['account_name', 'account_code']:
                    sanitized_line_data[key] = val
            for key, val in main_line.items():
                if key not in ['account_name', 'account_code']:
                    sanitized_line_data[key] = val
            # Append it to final data set
            aml_data.append(sanitized_line_data)

        # Order the collected data
        ordered_data = sorted(aml_data + extra_data, key=lambda x: x.get('date'))

        # Loop through the lines and prepare the final data
        for line in ordered_data:
            income = expense = 0
            if float_compare(line['credit'], 0, precision_digits=2) > 0:
                expense = float_round(line['credit'], precision_digits=2)
                num_out += 1
            else:
                income = float_round(line['debit'], precision_digits=2)
                num_in += 1
            starting_balance += float_round(line['balance'], precision_digits=2)
            next_line = {'date': line.get('date', '-'),
                         'partner_name': line.get('partner_name') or company_partner_name,
                         'account_name': '{} {}'.format(line.get('account_code', '-'), line.get('account_name', '-')),
                         'income': income,
                         'expense': expense,
                         'number': line.get('name', '-'),
                         'balance': starting_balance,
                         'canceled': line.get('canceled')
                         }
            lines.append(next_line)
        # Return final data in the dict
        return {
            'starting_line': starting_line,
            'lines': lines,
            'starting_balance': starting_balance,
            'num_in': num_in,
            'num_out': num_out
        }

    @api.multi
    def render_html(self, doc_ids, data=None):
        company = self.env.user.company_id
        date_from = data['form']['date_from']
        date_to = data['form']['date_to']
        journal_id = data['form']['journal_id'][0]
        include_canceled = data['form']['include_canceled']
        data = self.get_lines(date_from, date_to, journal_id, include_canceled)
        if not data:
            return  # Exception is already raised on the wizard
        total_income = sum(l['income'] for l in data['lines'])
        total_expense = sum(l['expense'] for l in data['lines'])
        docargs = {
            'doc_ids': doc_ids,
            'starting_line': data['starting_line'],
            'lines': data['lines'],
            'date_from': date_from,
            'date_to': date_to,
            'company': company,
            'total_income': total_income,
            'total_expense': total_expense,
            'balance': data['starting_balance'],
            'num_in': data['num_in'],
            'num_out': data['num_out'],
            'include_canceled': include_canceled
        }
        return self.env['report'].render('sl_general_report.report_kasos_knyga_template', docargs)


ReportKasosKnyga()
