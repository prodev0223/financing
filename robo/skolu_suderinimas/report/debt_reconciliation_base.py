# -*- coding: utf-8 -*-

from odoo import models, fields, exceptions, _, api
from datetime import timedelta
from odoo.tools import float_compare, float_is_zero
from six import iteritems


def get_default_line_dict(st_bal=0.0, end_bal=0.0):
    return {'lines': [],
            'start_balance': st_bal,
            'end_balance': end_bal,
            'debit': 0.0,
            'credit': 0.0}


def get_data_by_account_code(data_by_partner_id):
    """ Creates a regrouped dictionary of data collected by partner
    Returned structure:
    { account_code: { partner_id: { currency_id: { 'debit': 0.0, 'credit': 0.0 } } } }
    :param data_by_partner_id: Dictionary of data grouped by partner ID
    :return: Dictionary of data regrouped by account code
    """
    data_by_account_code = {}
    for partner_key, partner_value in iteritems(data_by_partner_id):
        for currency_key, currency_value in iteritems(partner_value):
            for line in currency_value['lines']:
                account_key = int(line['account_code'])
                if account_key not in data_by_account_code:
                    data_by_account_code[account_key] = {
                        partner_key: {
                            currency_key: {
                                'debit': line['debit'],
                                'credit': line['credit']
                            }
                        }
                    }
                elif partner_key not in data_by_account_code[account_key]:
                    data_by_account_code[account_key][partner_key] = {
                        currency_key: {
                            'debit': line['debit'],
                            'credit': line['credit']
                        }
                    }
                elif currency_key not in data_by_account_code[account_key][partner_key]:
                    data_by_account_code[account_key][partner_key][currency_key] = {
                        'debit': line['debit'],
                        'credit': line['credit']
                    }
                else:
                    data_by_account_code[account_key][partner_key][currency_key]['debit'] += line['debit']
                    data_by_account_code[account_key][partner_key][currency_key]['credit'] += line['credit']

    return data_by_account_code


def _format_text(text):
    chunks = text.split(' ')
    formatted_text = '<span>'
    for chunk in chunks:
        text_left = chunk
        while len(text_left) >= 30:
            part_1 = chunk[:30]
            formatted_text += part_1 + '<br/>'
            text_left = text_left[30:]
        formatted_text += text_left + ' '
    return formatted_text + '</span>'


class ReportDebtReconciliationBase(models.AbstractModel):

    """
    Base model that is inherited by debt reconciliation report multi and
    debt reconciliation report multi minimal
    """

    _name = 'report.debt.reconciliation.base'

    @api.model
    def get_default_payable_receivable(self, mode='payable_receivable'):
        """
        return default payable receivable accounts (2410/4430)
        :param mode: all/payable_receivable/receivable/payable
        :return: account.account ID's (list)
        """
        receivable_type_id = self.env.ref('account.data_account_type_receivable').id
        payable_type_id = self.env.ref('account.data_account_type_payable').id

        default_receivable_accounts = self.env['account.account'].search(
            [('user_type_id', '=', receivable_type_id),
             ('exclude_from_reports', '=', False)]
        )
        default_payable_accounts = self.env['account.account'].search(
            [('user_type_id', '=', payable_type_id),
             ('exclude_from_reports', '=', False)]
        )

        if mode in ['payable_receivable', 'all']:
            default_payable_accounts |= default_receivable_accounts
            return default_payable_accounts.ids
        if mode in ['receivable']:
            return default_receivable_accounts.ids
        if mode in ['payable']:
            return default_payable_accounts.ids

    def get_irreconcilable_account_amount(self, partner_id, account_ids, date_to):
        """
        Get total amounts of irreconcilable accounts to additionally include in debt report
        :param partner_id: ID of the partner
        :param account_ids: list of irreconcilable accounts' IDs
        :param date_to: upper date limit (included)
        :return: list of dictionaries containing debit/credit amounts of each account
        """
        AccountMoveLine = self.env['account.move.line']
        res = []
        account_move_line_domain = [('partner_id', '=', partner_id),
                                    ('move_id.state', '=', 'posted'),
                                    ('account_id.reconcile', '=', False),
                                    ('date', '<=', date_to)]
        for account_id in account_ids:
            account_move_lines = AccountMoveLine.search(account_move_line_domain + [('account_id.id', '=', account_id)])
            if not account_move_lines:
                continue
            credit = sum(x.credit for x in account_move_lines)
            debit = sum(x.debit for x in account_move_lines)
            if float_is_zero(debit - credit, precision_digits=2):
                continue

            res.append({
                'debit': debit,
                'credit': credit,
                'account_id': account_id
            })
        return res

    def get_raw_residual_move_line_data(self, partner_id, account_ids, date, filter_account_ids=False):
        """
        Get raw residual value from account move lines
        :param partner_id: id of the partner (integer)
        :param account_ids: list of account ids
        :param date: upper date limit (included)
        :param filter_account_ids: extra account restrictions if provided (list of account ids)
        :return: list of dictionaries containing AML records, and some amount and currency information
        """
        company_currency = self.env.user.company_id.currency_id
        query = '''
            SELECT
                aml.id
            FROM
                account_move_line AS aml
            INNER JOIN
                account_move AS am 
                    ON am.id = aml.move_id
            WHERE
                aml.partner_id = %s
                AND aml.date <= %s
                AND am.state = 'posted'
                AND aml.account_id IN %s
        '''
        args = [partner_id, date, tuple(account_ids)]
        if filter_account_ids:
            query += ''' AND aml.account_id in %s'''
            args.append(tuple(filter_account_ids))

        self.env.cr.execute(query, tuple(args))
        aml_ids = self.env.cr.fetchall()
        all_account_move_line_ids = [x[0] for x in aml_ids]
        if not all_account_move_line_ids:
            return []
        later_reconciled = self.env['account.partial.reconcile'].search(
            ['|', '&', ('credit_move_id', 'in', all_account_move_line_ids),
             ('debit_move_id.date', '>', date), '&',
             ('debit_move_id', 'in', all_account_move_line_ids), ('credit_move_id.date', '>', date)])

        later_reconciled_move_line_ids = later_reconciled.mapped('credit_move_id.id') + later_reconciled.mapped(
            'debit_move_id.id')
        filtered_move_lines = self.env['account.move.line'].search([('id', 'in', all_account_move_line_ids),
                                                                    '|',
                                                                        ('reconciled', '=', False),
                                                                        ('id', 'in', later_reconciled_move_line_ids)])
        amount_residual_company_curr_by_id = dict([(aml.id, aml.amount_residual) for aml in filtered_move_lines])
        amount_residual_currency_by_id = dict([(aml.id, aml.amount_residual_currency) for aml in filtered_move_lines])
        for apr in later_reconciled:
            if apr.credit_move_id.id in amount_residual_company_curr_by_id:
                amount_residual_company_curr_by_id[apr.credit_move_id.id] -= apr.amount
            if apr.debit_move_id.id in amount_residual_company_curr_by_id:
                amount_residual_company_curr_by_id[apr.debit_move_id.id] += apr.amount
            if apr.credit_move_id.id in amount_residual_currency_by_id:
                amount_residual_currency_by_id[apr.credit_move_id.id] -= apr.amount_currency
            if apr.debit_move_id.id in amount_residual_currency_by_id:
                amount_residual_currency_by_id[apr.debit_move_id.id] += apr.amount_currency
        res = []
        for aml in filtered_move_lines:
            amount_company = amount_residual_company_curr_by_id.get(aml.id, 0.0)
            if aml.currency_id and aml.currency_id != company_currency:
                currency = aml.currency_id
                amount_currency = amount_residual_currency_by_id.get(aml.id, 0.0)
            else:
                currency = company_currency
                amount_currency = 0
            if float_compare(amount_company, 0, precision_rounding=company_currency.rounding) == 0 \
                    and float_compare(amount_currency, 0, precision_rounding=currency.rounding) == 0:
                continue
            res.append({
                'amount_company': amount_company,
                'amount_currency': amount_currency,
                'currency_id': currency.id,
                'aml': aml
            })
        return res

    def get_raw_turnover_move_line_data(self, partner_id, account_ids, date_from,
                                        date_to, include_full_reconcile_ids=None):
        # full reconcile cancels out to zero
        company_currency = self.env.user.company_id.currency_id
        all_account_move_line_domain = [('partner_id', '=', partner_id),
                                        ('move_id.state', '=', 'posted'),
                                        ('account_id.id', 'in', account_ids),
                                        ('date', '<=', date_to)]
        if date_from:
            all_account_move_line_domain.append(('date', '>=', date_from))
        if include_full_reconcile_ids:
            all_account_move_line_domain.extend(['|',
                                                 ('full_reconcile_id', '=', False),
                                                 ('full_reconcile_id', 'in', include_full_reconcile_ids)])
        account_move_lines = self.env['account.move.line'].search(all_account_move_line_domain, order='date asc')
        res = []
        for aml in account_move_lines:
            amount_company = aml.balance
            if aml.currency_id and aml.currency_id != company_currency:
                currency = aml.currency_id
                amount_currency = aml.amount_currency
            else:
                currency = company_currency
                amount_currency = 0
            if float_compare(amount_company, 0, precision_rounding=company_currency.rounding) == 0 and \
                    float_compare(amount_currency, 0, precision_rounding=currency.rounding) == 0:
                continue
            res.append({
                'amount_company': amount_company,
                'amount_currency': amount_currency,
                'currency_id': currency.id,
                'aml': aml
            })
        return res

    def get_all_account_move_line_data(self, partner_id, account_ids, report_type,
                                       date, date_from, date_to, original_amount_group_by):
        company_currency = self.env.user.company_id.currency_id
        company_currency_id = company_currency.id
        starting_balances = {}
        raw_data = []
        irreconcilable_data = []
        if report_type == 'unreconciled':
            if date is None:
                raise exceptions.UserError(_('Report date is not set'))
            accounts = self.env['account.account'].browse(account_ids)
            reconcilable_account_ids = accounts.filtered(lambda x: x.reconcile).ids
            # Irreconcilable accounts may be selected when generating report
            # Their total amounts should be additionally included in the report
            irreconcilable_account_ids = accounts.filtered(lambda x: not x.reconcile).ids
            if reconcilable_account_ids:
                raw_data = self.sudo().get_raw_residual_move_line_data(partner_id, reconcilable_account_ids, date)
            if irreconcilable_account_ids:
                irreconcilable_data = self.sudo().get_irreconcilable_account_amount(partner_id,
                                                                                    irreconcilable_account_ids, date)
        else:
            if date_from is None or date_to is None:
                raise exceptions.UserError(_('Report date range is not set'))
            self._cr.execute('''SELECT DISTINCT(full_reconcile_id) from account_move_line where date >= %s''', (date_from,))
            full_reconcile_ids = [row[0] for row in self._cr.fetchall() if row[0]]
            date_to_historical = fields.Date.to_string(fields.Date.from_string(date_from) - timedelta(days=1))
            historical_raw_data = self.get_raw_turnover_move_line_data(
                partner_id, account_ids, False, date_to_historical, include_full_reconcile_ids=full_reconcile_ids)
            raw_data = self.get_raw_turnover_move_line_data(partner_id, account_ids, date_from, date_to)
            for h_data_line in historical_raw_data:
                if original_amount_group_by:
                    grouped_currency = h_data_line['currency_id']
                    grouped_amount = h_data_line['amount_currency'] if \
                        h_data_line['currency_id'] != company_currency_id else h_data_line['amount_company']
                else:
                    grouped_currency = company_currency_id
                    grouped_amount = h_data_line['amount_company']
                starting_balances.setdefault(grouped_currency, 0)
                starting_balances[grouped_currency] += grouped_amount
        full_data = {}

        for data_line in raw_data:
            aml = data_line['aml']
            display_original = True if data_line['currency_id'] != company_currency_id or original_amount_group_by else False
            if original_amount_group_by:
                grouped_currency = data_line['currency_id']
                pre_grouped_amount = data_line['amount_company']
                pre_grouped_currency = company_currency_id
                grouped_amount = data_line['amount_currency'] if \
                    data_line['currency_id'] != company_currency_id else data_line['amount_company']
            else:
                grouped_currency = company_currency_id
                pre_grouped_amount = data_line['amount_currency']
                grouped_amount = data_line['amount_company']
                pre_grouped_currency = data_line['currency_id']

            currency_data = full_data.setdefault(grouped_currency, {})
            currency_data.setdefault('credit', 0)
            currency_data.setdefault('debit', 0)
            credit = -grouped_amount if grouped_amount < 0 else 0.0
            debit = grouped_amount if grouped_amount > 0 else 0.0
            ref = aml.name
            record_id, record_model = aml.id, 'account.move.line'

            date_operation = ''
            if aml.move_id.statement_line_id:
                doc_type = 'payment'
            elif aml.invoice_id:
                doc_type = 'invoice'
                date_operation = aml.invoice_id.operacijos_data or ''
                if aml.invoice_id.type in ['out_invoice', 'out_refund']:
                    ref = aml.invoice_id.number
                    record_id, record_model = aml.invoice_id.id, 'account.invoice'
            else:
                doc_type = ''
            lines = currency_data.setdefault('lines', [])
            line = {'ref': ref,
                    'credit': credit,
                    'debit': debit,
                    'date': aml.date,
                    'date_operation': date_operation,
                    'date_maturity': aml.date_maturity,
                    'doc_type': doc_type,
                    'orig_amount': pre_grouped_amount,
                    'orig_currency': self.sudo().env['res.currency'].browse(pre_grouped_currency),
                    'display_original': display_original,
                    'account_code': aml.account_id.code,
                    'record_id': record_id,
                    'record_model': record_model
                    }
            currency_data['debit'] += debit
            currency_data['credit'] += credit
            lines.append(line)

        # Additionally include total amounts of irreconcilable accounts
        for data_line in irreconcilable_data:
            account = self.env['account.account'].browse(data_line['account_id'])
            currency_data = full_data.setdefault(company_currency_id, {})
            currency_data.setdefault('credit', 0)
            currency_data.setdefault('debit', 0)
            lines = currency_data.setdefault('lines', [])
            balance = data_line['debit'] - data_line['credit']
            debit = balance if balance > 0 else 0.0
            credit = -balance if balance < 0 else 0.0
            line = {'ref': account.name,
                    'credit': credit,
                    'debit': debit,
                    'date': date,
                    'date_operation': '',
                    'date_maturity': '',
                    'doc_type': 'account',
                    'orig_amount': debit - credit,
                    'orig_currency': company_currency,
                    'display_original': False,
                    'account_code': account.code
                    }
            currency_data['debit'] += debit
            currency_data['credit'] += credit
            lines.append(line)

        for currency_id in full_data:
            full_data[currency_id]['start_balance'] = starting_balances.get(currency_id, 0.0)
            full_data[currency_id]['end_balance'] = starting_balances.get(
                currency_id, 0.0) + full_data[currency_id]['debit'] - full_data[currency_id]['credit']
        for currency_id in starting_balances:
            if currency_id not in full_data:
                full_data[currency_id] = get_default_line_dict(st_bal=starting_balances[currency_id],
                                                               end_bal=starting_balances[currency_id])
        if not raw_data and not irreconcilable_data:
            full_data[company_currency_id] = get_default_line_dict()
        return full_data


ReportDebtReconciliationBase()
