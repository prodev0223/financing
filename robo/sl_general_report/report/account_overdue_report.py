# -*- coding: utf-8 -*-
import time
from odoo import api, fields, models, tools
from odoo.tools import float_compare

class ReportOverdue(models.AbstractModel):
    _name = 'report.account.report_overdue'

    def _get_account_move_lines(self, partner_ids):
        res = dict(map(lambda x: (x, []), partner_ids))
        self.env.cr.execute(
            "SELECT m.name AS move_id, l.date, l.name, l.ref, l.date_maturity, l.partner_id, l.blocked, l.amount_residual_currency, l.amount_currency, l.currency_id, at.type, "
            "CASE WHEN at.type = 'receivable' "
                "THEN SUM(l.debit) "
                "ELSE SUM(l.credit * -1) "
            "END AS debit, "
            "CASE WHEN at.type = 'receivable' "
                "THEN SUM(l.debit - l.amount_residual) "
                "ELSE SUM(-l.credit - l.amount_residual) "
            "END AS credit, "
            "CASE WHEN l.date_maturity < %s "
                "THEN SUM(l.amount_residual) "
                "ELSE 0 "
            "END AS mat "
            "FROM account_move_line l "
            "JOIN account_account_type at ON (l.user_type_id = at.id) "
            "JOIN account_move m ON (l.move_id = m.id) "
            "WHERE l.partner_id IN %s AND at.type IN ('receivable', 'payable') and l.reconciled = false "
            "GROUP BY l.date, l.name, l.ref, l.date_maturity, l.partner_id, at.type, l.blocked, "
            "l.amount_residual_currency, l.amount_currency, l.currency_id, l.move_id, m.name, at.type "
            "ORDER BY date_maturity",
            ((fields.date.today(),) + (tuple(partner_ids),)))
        for row in self.env.cr.dictfetchall():
            res[row.pop('partner_id')].append(row)
        return res

    @api.multi
    def render_html(self, doc_ids, data=None):
        lang = self.env.user.company_id.partner_id.lang if self.env.user.company_id.partner_id and self.env.user.company_id.partner_id.lang else 'lt_LT'
        self = self.with_context(lang=lang)
        totals = {}
        lines = self._get_account_move_lines(doc_ids)
        lines_to_display = {}
        company_currency = self.env.user.company_id.currency_id
        for partner_id in doc_ids:
            lines_to_display[partner_id] = {}
            totals[partner_id] = {}
            for line_tmp in lines[partner_id]:
                line = line_tmp.copy()
                currency = line['currency_id'] and self.env['res.currency'].browse(line['currency_id']) or company_currency
                if currency not in lines_to_display[partner_id]:
                    lines_to_display[partner_id][currency] = []
                    totals[partner_id][currency] = dict((fn, 0.0) for fn in ['due', 'paid', 'mat', 'total'])
                if line['debit'] and line['currency_id']:
                    line['debit'] = line['amount_currency']
                if line['credit'] and line['currency_id']:
                    # prepaid
                    if line['type'] == 'receivable' and float_compare(line['amount_residual_currency'], 0,
                                                                      precision_rounding=currency.rounding) < 0 or \
                                            line['type'] == 'payable' and float_compare(line['amount_residual_currency'], 0, precision_rounding=currency.rounding) > 0:
                        line['credit'] = - line['amount_residual_currency']
                    else:
                        line['credit'] = line['amount_currency'] - line['amount_residual_currency']
                if line['mat'] and line['currency_id']:
                    line['mat'] = line['amount_currency']
                if tools.float_is_zero(line['debit'], precision_rounding=currency.rounding) and \
                        tools.float_is_zero(line['credit'], precision_rounding=currency.rounding) and \
                        tools.float_is_zero(line['mat'], precision_rounding=currency.rounding):
                    continue
                lines_to_display[partner_id][currency].append(line)
                if not line['blocked']:
                    totals[partner_id][currency]['due'] += line['debit']
                    totals[partner_id][currency]['paid'] += line['credit']
                    totals[partner_id][currency]['mat'] += line['mat']
                    totals[partner_id][currency]['total'] += line['debit'] - line['credit']
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': 'res.partner',
            'docs': self.env['res.partner'].browse(doc_ids),
            'time': time,
            'Lines': lines_to_display,
            'Totals': totals,
            'Date': fields.date.today(),
        }
        return self.env['report'].render('account.report_overdue', values=docargs)
