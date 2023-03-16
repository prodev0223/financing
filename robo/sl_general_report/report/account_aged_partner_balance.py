# -*- coding: utf-8 -*-
import time
from collections import defaultdict

from odoo import api, models, _, tools
from odoo.tools import float_is_zero
from datetime import datetime


class ReportAgedPartnerBalance(models.AbstractModel):

    _name = 'report.sl_general_report.report_agedpartnerbalance_sl'

    @staticmethod
    def _get_account_code_mapping():
        return {'payable': ['4430'],
                'receivable': ['2410']}

    def _get_account_code_tuple(self, account_type):
        code_map = self._get_account_code_mapping()
        return tuple(code for t in account_type for code in code_map[t])

    def _get_partner_move_lines(self, form, account_type, date_from, target_move, short=False):

        res = []
        self.total_account = []
        cr = self.env.cr
        user_company = self.env.user.company_id.id
        move_state = ['draft', 'posted']
        if target_move == 'posted':
            move_state = ['posted']
        account_ids = form.get('account_ids')
        if account_ids and self.env.user.has_group('robo.group_select_account_in_account_aged_trial_balance'):
            account_codes = tuple(set(self.env['account.account'].browse(account_ids).mapped('code')))
        else:
            account_codes = self._get_account_code_tuple(account_type)
        arg_list = (tuple(move_state), account_codes)
        #build the reconciliation clause to see what partner needs to be printed
        reconciliation_clause = '(l.reconciled IS FALSE)'
        cr.execute('SELECT debit_move_id, credit_move_id FROM account_partial_reconcile where reconcile_date > %s', (date_from,))
        reconciled_after_date = []
        for row in cr.fetchall():
            reconciled_after_date += [row[0], row[1]]
        if reconciled_after_date:
            reconciliation_clause = '(l.reconciled IS FALSE OR l.id IN %s)'
            arg_list += (tuple(reconciled_after_date),)
        arg_list += (date_from, user_company)
        if short:
            query = '''
            SELECT DISTINCT res_partner.id AS id, res_partner.is_company AS is_company, res_partner.name AS name, UPPER(res_partner.name) AS uppername
            FROM res_partner,account_move_line AS l, account_account, account_move am
            WHERE (l.account_id = account_account.id)
                AND (l.move_id = am.id)
                AND (am.state IN %s)
                AND (account_account.code IN %s)
                AND ''' + reconciliation_clause + '''
                AND (l.partner_id = res_partner.id)
                AND (l.date <= %s)
                AND l.company_id = %s
                AND (res_partner.is_company IS FALSE)
            ORDER BY UPPER(res_partner.name)'''
        else:
            query = '''
            SELECT DISTINCT res_partner.id AS id, res_partner.is_company AS is_company, res_partner.name AS name, UPPER(res_partner.name) AS uppername
            FROM res_partner,account_move_line AS l, account_account, account_move am
            WHERE (l.account_id = account_account.id)
                AND (l.move_id = am.id)
                AND (am.state IN %s)
                AND (account_account.code IN %s)
                AND ''' + reconciliation_clause + '''
                AND (l.partner_id = res_partner.id)
                AND (l.date <= %s)
                AND l.company_id = %s
            ORDER BY UPPER(res_partner.name)'''
        cr.execute(query, arg_list)

        partners = cr.dictfetchall()
        # put a total of 0
        for i in range(7):
            self.total_account.append(0)

        # Build a string like (1,2,3) for easy use in SQL query
        partner_ids = [partner['id'] for partner in partners]
        return_amounts = False
        if self._context.get('filtered_partner_ids'):
            partner_ids = self._context['filtered_partner_ids']
            return_amounts = True
        if not partner_ids:
            return []

        # This dictionary will store the not due amount of all partners
        future_past = {}
        query = '''SELECT l.id
                FROM account_move_line AS l, account_account, account_move am
                WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                    AND (am.state IN %s)
                    AND (account_account.code IN %s)
                    AND (COALESCE(l.date_maturity,l.date) > %s)\
                    AND (l.partner_id IN %s)
                AND (l.date <= %s)
                AND l.company_id = %s'''
        cr.execute(query, (tuple(move_state), tuple(account_codes), date_from, tuple(partner_ids), date_from, user_company))
        aml_ids = cr.fetchall()
        aml_ids = aml_ids and [x[0] for x in aml_ids] or []
        amls = self.sudo().env['account.move.line'].browse(aml_ids)
        aml_ids_by_partner = defaultdict(list)
        for line in amls:
            if line.partner_id.id not in future_past:
                future_past[line.partner_id.id] = 0.0
            line_amount = line.balance
            if line.balance == 0:
                continue
            for partial_line in line.matched_debit_ids:
                if not partial_line.reconcile_date:
                    partial_line._reconcile_date()
                if partial_line.reconcile_date[:10] <= date_from:
                    line_amount += partial_line.amount
            for partial_line in line.matched_credit_ids:
                if not partial_line.reconcile_date:
                    partial_line._reconcile_date()
                if partial_line.reconcile_date[:10] <= date_from:
                    line_amount -= partial_line.amount
            aml_ids_by_partner[line.partner_id.id].append(line.id)
            future_past[line.partner_id.id] += line_amount

        # Use one query per period and store results in history (a list variable)
        # Each history will contain: history[1] = {'<partner_id>': <partner_debit-credit>}
        history = []
        for i in range(5):
            args_list = (tuple(move_state), tuple(account_codes), tuple(partner_ids),)
            dates_query = '(COALESCE(l.date_maturity,l.date)'

            if form[str(i)]['start'] and form[str(i)]['stop']:
                dates_query += ' BETWEEN %s AND %s)'
                args_list += (form[str(i)]['start'], form[str(i)]['stop'])
            elif form[str(i)]['start']:
                dates_query += ' >= %s)'
                args_list += (form[str(i)]['start'],)
            else:
                dates_query += ' <= %s)'
                args_list += (form[str(i)]['stop'],)
            args_list += (date_from, user_company)

            query = '''SELECT l.id
                    FROM account_move_line AS l, account_account, account_move am
                    WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                        AND (am.state IN %s)
                        AND (account_account.code IN %s)
                        AND (l.partner_id IN %s)
                        AND ''' + dates_query + '''
                    AND (l.date <= %s)
                    AND l.company_id = %s'''
            cr.execute(query, args_list)
            partners_amount = {}
            aml_ids = cr.fetchall()
            aml_ids = aml_ids and [x[0] for x in aml_ids] or []
            for line in self.sudo().env['account.move.line'].browse(aml_ids):
                if line.partner_id.id not in partners_amount:
                    partners_amount[line.partner_id.id] = 0.0
                line_amount = line.balance
                if line.balance == 0:
                    continue
                for partial_line in line.matched_debit_ids:
                    if not partial_line.reconcile_date:
                        partial_line._reconcile_date()
                    if partial_line.reconcile_date[:10] <= date_from:
                        line_amount += partial_line.amount
                for partial_line in line.matched_credit_ids:
                    if not partial_line.reconcile_date:
                        partial_line._reconcile_date()
                    if partial_line.reconcile_date[:10] <= date_from:
                        line_amount -= partial_line.amount
                aml_ids_by_partner[line.partner_id.id].append(line.id)
                partners_amount[line.partner_id.id] += line_amount
            history.append(partners_amount)

        for partner in partners:
            values = {}
            # Query here is replaced by one query which gets the all the partners their 'after' value
            after = False
            if partner['id'] in future_past:  # Making sure this partner actually was found by the query
                after = [future_past[partner['id']]]

            self.total_account[6] = self.total_account[6] + (after and after[0] or 0.0)
            values['direction'] = after and after[0] or 0.0
            at_least_one_amount = False
            if not float_is_zero(values['direction'], precision_rounding=self.env.user.company_id.currency_id.rounding):
                at_least_one_amount = True

            for i in range(5):
                during = False
                if partner['id'] in history[i]:
                    during = [history[i][partner['id']]]
                # Adding counter
                self.total_account[(i)] = self.total_account[(i)] + (during and during[0] or 0)
                values[str(i)] = during and during[0] or 0.0
                if not float_is_zero(values[str(i)], precision_rounding=self.env.user.company_id.currency_id.rounding):
                    at_least_one_amount = True
            values['total'] = sum([values['direction']] + [values[str(i)] for i in range(5)])
            ## Add for total
            self.total_account[(i + 1)] += values['total']
            values['name'] = partner['name']
            values['partner_id'] = partner['id']
            partner_rec = self.env['res.partner'].browse(partner['id'])
            values['phone'] = partner_rec.phone
            values['email'] = partner_rec.email
            values['record_ids'] = aml_ids_by_partner.get(partner['id'], [])
            values['record_model'] = 'account.move.line'
            if at_least_one_amount:
                res.append(values)

        total = 0.0
        totals = {}
        for r in res:
            total += float(r['total'] or 0.0)
            for i in range(5) + ['direction']:
                totals.setdefault(str(i), 0.0)
                totals[str(i)] += float(r[str(i)] or 0.0)

        if short:
            if res:
                return {'title': 'Fiziniai asmenys',
                        'total': sum(x['total'] for x in res),
                        '0': sum(x['0'] for x in res),
                        '1': sum(x['1'] for x in res),
                        '2': sum(x['2'] for x in res),
                        '3': sum(x['3'] for x in res),
                        '4': sum(x['4'] for x in res),
                        'direction': sum(x['direction'] for x in res)}
            else:
                return {}
        else:
            #FIXME: returning different type breaks stuff. We should fix that, look for occurences and replace (always return tuple, maybe with None instead)
            if return_amounts:
                return res, self.total_account
            else:
                return res

    def _get_move_lines_with_out_partner(self, form, account_type, date_from, target_move):
        res = []
        cr = self.env.cr
        move_state = ['draft', 'posted']
        if target_move == 'posted':
            move_state = ['posted']

        user_company = self.env.user.company_id.id
        ## put a total of 0
        for i in range(7):
            self.total_account.append(0)

        # This dictionary will store the not due amount of the unknown partner
        future_past = {'Unknown Partner': 0}
        account_ids = form.get('account_ids')
        if account_ids and self.env.user.is_accountant():
            account_codes = tuple(set(self.env['account.account'].browse(account_ids).mapped('code')))
        else:
            account_codes = self._get_account_code_tuple(account_type)
        query = '''SELECT l.id
                FROM account_move_line AS l, account_account, account_move am
                WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                    AND (am.state IN %s)
                    AND (account_account.code IN %s)
                    AND (COALESCE(l.date_maturity,l.date) > %s)\
                    AND (l.partner_id IS NULL)
                AND (l.date <= %s)
                AND l.company_id = %s'''
        cr.execute(query, (tuple(move_state), account_codes, date_from, date_from, user_company))
        aml_ids = cr.fetchall()
        aml_ids = aml_ids and [x[0] for x in aml_ids] or []
        amls = self.env['account.move.line'].browse(aml_ids)
        for line in amls:
            line_amount = line.balance
            if line.balance == 0:
                continue
            for partial_line in line.matched_debit_ids:
                if not partial_line.reconcile_date:
                    partial_line._reconcile_date()
                if partial_line.reconcile_date[:10] <= date_from:
                    line_amount += partial_line.amount
            for partial_line in line.matched_credit_ids:
                if not partial_line.reconcile_date:
                    partial_line._reconcile_date()
                if partial_line.reconcile_date[:10] <= date_from:
                    line_amount -= partial_line.amount
            future_past['Unknown Partner'] += line_amount

        history = []
        for i in range(5):
            args_list = (tuple(move_state), tuple(account_codes))
            dates_query = '(COALESCE(l.date_maturity,l.date)'
            if form[str(i)]['start'] and form[str(i)]['stop']:
                dates_query += ' BETWEEN %s AND %s)'
                args_list += (form[str(i)]['start'], form[str(i)]['stop'])
            elif form[str(i)]['start']:
                dates_query += ' > %s)'
                args_list += (form[str(i)]['start'],)
            else:
                dates_query += ' < %s)'
                args_list += (form[str(i)]['stop'],)
            args_list += (date_from, user_company)
            query = '''SELECT l.id
                    FROM account_move_line AS l, account_account, account_move am
                    WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                        AND (am.state IN %s)
                        AND (account_account.code IN %s)
                        AND (l.partner_id IS NULL)
                        AND ''' + dates_query + '''
                    AND (l.date <= %s)
                    AND l.company_id = %s'''
            cr.execute(query, args_list)
            history_data = {'Unknown Partner': 0}
            aml_ids = cr.fetchall()
            aml_ids = aml_ids and [x[0] for x in aml_ids] or []
            for line in self.sudo().env['account.move.line'].browse(aml_ids):
                line_amount = line.balance
                if line.balance == 0:
                    continue
                for partial_line in line.matched_debit_ids:
                    if not partial_line.reconcile_date:
                        partial_line._reconcile_date()
                    if partial_line.reconcile_date[:10] <= date_from:
                        line_amount += partial_line.amount
                for partial_line in line.matched_credit_ids:
                    if not partial_line.reconcile_date:
                        partial_line._reconcile_date()
                    if partial_line.reconcile_date[:10] <= date_from:
                        line_amount -= partial_line.amount
                history_data['Unknown Partner'] += line_amount
            history.append(history_data)

        values = {}
        after = False
        if 'Unknown Partner' in future_past:
            after = [future_past['Unknown Partner']]
        self.total_account[6] = self.total_account[6] + (after and after[0] or 0.0)
        values['direction'] = after and after[0] or 0.0

        for i in range(5):
            during = False
            if 'Unknown Partner' in history[i]:
                during = [history[i]['Unknown Partner']]
            self.total_account[(i)] = self.total_account[(i)] + (during and during[0] or 0)
            values[str(i)] = during and during[0] or 0.0

        values['total'] = sum([values['direction']] + [values[str(i)] for i in range(5)])
        ## Add for total
        self.total_account[(i + 1)] += values['total']
        values['name'] = _('Unknown Partner')
        values['record_ids'] = amls.ids
        values['record_model'] = 'account.move.line'

        if values['total']:
            res.append(values)

        total = 0.0
        totals = {}
        for r in res:
            total += float(r['total'] or 0.0)
            for i in range(5) + ['direction']:
                totals.setdefault(str(i), 0.0)
                totals[str(i)] += float(r[str(i)] or 0.0)
        return res

    def get_invoices(self, date_from, period, account_type, include_proforma=False, short=False):
        def get_invoice_name(invoice):
            invoice_name = None
            if invoice.state in ['proforma', 'proforma2']:
                invoice_name = 'ProForma ' + str(invoice.id)
            elif invoice.type in ('in_refund', 'in_invoice'):
                invoice_name = invoice.reference
            return invoice_name or invoice.move_name

        partner_ids = self._context.get('filtered_partner_ids', False)
        if include_proforma:
            domain = [('state', 'in', ['proforma', 'proforma2', 'open'])]
        else:
            domain = [('state', 'in', ['open'])]
        if len(account_type) < 2:
            if 'payable' in account_type:
                domain.append(('type', 'in', ['out_refund', 'in_invoice']))
            else:
                domain.append(('type', 'in', ['out_invoice', 'in_refund']))
        rows = []
        result = {'rows': rows, }
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        invoices = self.env['account.invoice'].search(domain).sorted(key=lambda r: r.partner_id)
        for invoice in invoices:
            sign = -1 if invoice.type in ['out_refund', 'in_invoice'] else 1
            date_due = invoice.date_due
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_due_dt = datetime.strptime(date_due, tools.DEFAULT_SERVER_DATE_FORMAT)
            delta = (date_from_dt - date_due_dt).days
            residual = tools.float_round(invoice.residual_company_signed, precision_digits=2)
            if short:
                rows.append({
                    'invoice_name': get_invoice_name(invoice),
                    'record_id': invoice.id,
                    'record_model': 'account.invoice',
                    'partner_name': 'Fiziniai asmenys',
                    'no_delay': residual if delta < 0 else 0.0,
                    '0': residual * sign if period > delta >= 0 else 0.0,
                    '1': residual * sign if period * 2 > delta >= period else 0.0,
                    '2': residual * sign if period * 3 > delta >= period * 2 else 0.0,
                    '3': residual * sign if period * 4 > delta >= period * 3 else 0.0,
                    '4': residual * sign if delta >= period * 4 else 0.0,
                    'total': residual * sign,
                })
            else:
                rows.append({
                    'invoice_name': get_invoice_name(invoice),
                    'record_id': invoice.id,
                    'record_model': 'account.invoice',
                    'partner_name': invoice.partner_id.name,
                    'partner_mail': invoice.partner_id.email,
                    'partner_phone': invoice.partner_id.phone,
                    'no_delay': residual if delta < 0 else 0.0,
                    '0': residual * sign if period > delta >= 0 else 0.0,
                    '1': residual * sign if period * 2 > delta >= period else 0.0,
                    '2': residual * sign if period * 3 > delta >= period * 2 else 0.0,
                    '3': residual * sign if period * 4 > delta >= period * 3 else 0.0,
                    '4': residual * sign if delta >= period * 4 else 0.0,
                    'total': residual * sign,
                })
        result['totals'] = {
            'no_delay': sum(rec['no_delay'] for rec in result['rows']),
            '0': sum(rec['0'] for rec in result['rows']),
            '1': sum(rec['1'] for rec in result['rows']),
            '2': sum(rec['2'] for rec in result['rows']),
            '3': sum(rec['3'] for rec in result['rows']),
            '4': sum(rec['4'] for rec in result['rows']),
            'total': sum(rec['total'] for rec in result['rows']),
        }
        result['names'] = [
            '0-'+str(period),
            str(period)+'-'+str(period * 2),
            str(period * 2) + '-' + str(period * 3),
            str(period * 3) + '-' + str(period * 4),
            str(period * 4) + '+',
        ]
        return result

    @api.multi
    def render_html(self, doc_ids, data=None):
        render_data = self.get_full_render_data(doc_ids, data)
        return self.env['report'].render('sl_general_report.report_agedpartnerbalance_sl', render_data)

    @api.multi
    def get_full_render_data(self, doc_ids, data=None):
        lang = data.get('form').get('used_context').get('lang') or self.env.user.lang or 'lt_LT'
        self = self.with_context(lang=lang)
        self.total_account = []
        self.model = self.env.context.get('active_model') or u'account.aged.trial.balance'
        docs = self.env[self.model].browse(doc_ids)
        target_move = data['form'].get('target_move', 'posted')
        date_from = data['form'].get('date_from', time.strftime('%Y-%m-%d'))

        if data['form']['result_selection'] == 'customer':
            account_type = ['receivable']
        elif data['form']['result_selection'] == 'supplier':
            account_type = ['payable']
        else:
            account_type = ['payable', 'receivable']

        display_partner = data['form']['display_partner']
        filtered_partner_ids = data['form']['filtered_partner_ids']
        invoices_only = data['form']['invoices_only']
        include_proforma = data['form']['include_proforma']
        short_report = data['form']['short_report']
        movelines = []
        invoices = []
        if invoices_only:
            period = data['form']['period_length']
            if display_partner == 'filter' and filtered_partner_ids:
                invoices = self.with_context(filtered_partner_ids=filtered_partner_ids).get_invoices(date_from, period, account_type, include_proforma, short=short_report)
            else:
                invoices = self.get_invoices(date_from, period, account_type, include_proforma, short=short_report)
        else:
            if short_report:
                if filtered_partner_ids:
                    partner_movelines = self.with_context(filtered_partner_ids=filtered_partner_ids)._get_partner_move_lines(data['form'], account_type, date_from, target_move, short=short_report)
                else:
                    partner_movelines = self._get_partner_move_lines(data['form'], account_type, date_from, target_move, short=short_report)
                movelines = partner_movelines
            else:
                if display_partner == 'filter' and filtered_partner_ids:
                    for i in range(7):
                        self.total_account.append(0)
                    # self._get_move_lines_with_out_partner(data['form'], account_type, date_from,
                    #                                                                   target_move)
                    partner_movelines, tot_list = self.with_context(filtered_partner_ids=filtered_partner_ids)._get_partner_move_lines(data['form'], account_type, date_from, target_move)
                    movelines = partner_movelines
                else:
                    without_partner_movelines = self._get_move_lines_with_out_partner(data['form'], account_type, date_from, target_move)
                    tot_list = self.total_account
                    partner_movelines = self._get_partner_move_lines(data['form'], account_type, date_from, target_move)

                    movelines = partner_movelines + without_partner_movelines

                for i in range(7):
                    self.total_account[i] += tot_list[i]

        render_data = {
            'doc_ids': doc_ids,
            'doc_model': self.model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_partner_lines': movelines,
            'invoices': invoices,
            'invoices_only': invoices_only,
            'get_direction': self.total_account,
            'short': short_report
        }
        return render_data
