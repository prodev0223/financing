# -*- coding: utf-8 -*-
import time
from odoo import api, fields, models, _, tools, exceptions
from datetime import date, datetime
import calendar


class CashBalanceWizard(models.TransientModel):
    _name = 'cashbalance.wizard'

    def _compute_period_start_date(self):
        current_time = date.today()
        date_from = datetime(year=current_time.year, month=current_time.month, day=1)
        return date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _compute_period_end_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    report_start = fields.Date(string='Date From', required=True, default=_compute_period_start_date)
    report_end = fields.Date(string='Date To', required=True, default=_compute_period_end_date)

    @api.multi
    def print_report(self):
        self.ensure_one()
        data = {
            'ids': self._context.get('active_ids', []),
            'model': 'res.partner',
            'form': {},
        }
        data['form']['ids'] = data['ids']
        data['form']['date_start'] = self.report_start,
        data['form']['date_end'] = self.report_end,

        return self.env['report'].get_action(self, 'avansine_apyskaita.report_cashbalance_template', data=data)


CashBalanceWizard()


class ReportCashAdvance(models.AbstractModel):
    _name = 'report.avansine_apyskaita.report_cashbalance_template'

    def _get_account_move_lines(self, partner_ids, statement_start, statement_end, account_id):

        move_lines = dict(map(lambda x: (x, []), partner_ids))

        self.env.cr.execute(
            '''
            SELECT foo.move_id, foo.date, foo.name, foo.ref, foo.partner_id, foo.debit, foo.credit,
                code, foo.invoice_id, foo.origin, foo.amount_total_company_signed, foo.amount_untaxed_signed, foo.reference, foo.create_date, foo.invoice_number, foo.invoice_partner_name, foo.advance_payment_amount
            FROM
                (
                    SELECT m.name AS move_id, l.date, l.name, l.ref, l.partner_id, l.debit, l.credit,
                            a.code, l.invoice_id, NULL as origin, NULL as amount_total_company_signed, NULL as amount_untaxed_signed, NULL as reference, NULL as create_date, NULL as invoice_number, NULL as invoice_partner_name, NULL as advance_payment_amount
                        FROM account_move_line l
                        JOIN account_move m ON (l.move_id = m.id)
                        LEFT JOIN account_account a on (a.id = l.account_id)
                        LEFT JOIN cash_receipt cr ON (cr.move_name = m.name)
                        WHERE l.partner_id IN %s AND l.account_id = %s and l.invoice_id is NULL
                        and l.date between %s and %s
                    UNION (
                        SELECT MAX(m.name) AS move_id, l.date, MAX(l.name), NULL as ref, l.partner_id, SUM(l.debit),
                            SUM(l.credit), a.code, i.id as invoice_id, MAX(i.origin), MAX(i.amount_total_company_signed), MAX(i.amount_untaxed_signed), i.reference, i.create_date, i.number as invoice_number, rp.name as invoice_partner_name, i.advance_payment_amount as advance_payment_amount
                        FROM account_move_line l
                        JOIN account_move m ON (l.move_id = m.id)
                        LEFT JOIN account_invoice i on (l.invoice_id = i.id)
                        LEFT JOIN account_account a on (a.id = l.account_id)
                        LEFT JOIN res_partner rp on (rp.id = i.partner_id)
                        WHERE l.partner_id IN %s AND l.account_id = %s and l.invoice_id is not NULL
                         and l.date between %s and %s
                        group by l.date, l.partner_id, a.code, i.id, i.create_date, i.reference, i.number, rp.name
                    )
                 ) AS foo ORDER BY date asc
            ''', (tuple(partner_ids), account_id, statement_start, statement_end,
                  tuple(partner_ids), account_id, statement_start, statement_end))

        for row in self.env.cr.dictfetchall():
            move_lines[row['partner_id']].append(row)

        # Antišlaidžiai - avanso likutis iki periodo pradžios
        likuciai = dict(map(lambda x: (x, []), partner_ids))

        self.env.cr.execute(
            '''
            SELECT l.partner_id, sum(l.debit-l.credit) as likutis
            FROM account_move_line l
            WHERE l.partner_id IN %s AND l.account_id = %s
                and l.date < %s
            group by l.partner_id, l.currency_id
            ''', (tuple(partner_ids), account_id, statement_start))
        for row in self.env.cr.dictfetchall():
            likuciai[row['partner_id']].append(row)

        return move_lines, likuciai

    @api.multi
    def render_html(self, doc_ids, data=None):
        advance_id = self.env.user.company_id.cash_advance_account_id.id or False
        if not advance_id:
            raise exceptions.UserError(_('Neteisingi nustatymai. Kreipkitės į buhalterį.'))

        ids = data['form']['ids']
        if not self.env.user.is_manager() and not self.env.user.is_hr_manager() \
                and any(p_id not in self.env.user.employee_ids.mapped('address_home_id.id') for p_id in ids):
            return

        totals = {}
        lines_to_display = {}

        lines, avanso_likutis = self._get_account_move_lines(ids, data['form']['date_start'][0],
                                                             data['form']['date_end'][0], advance_id)
        for partner_id in ids:
            lines_to_display[partner_id] = []
            totals[partner_id] = {}
            totals[partner_id] = dict(
                dict((fn, 0.0) for fn in ['total', 'credit', 'debit', 'likutis']).items() +
                {key1: {key2: 0.0 for key2 in ['gauta', 'isleista']} for key1 in ['bePVM', 'PVM', 'suPVM']}.items()
            )
            # totals[partner_id] = {key1:{key2: 0.0 for key2 in ['gauta', 'isleista']} for key1 in ['bePVM', 'PVM', 'suPVM']}
            for raw_line in lines[partner_id]:
                line = raw_line.copy()
                lines_to_display[partner_id].append(line)
                totals[partner_id]['total'] += line['debit'] - line['credit']
                totals[partner_id]['debit'] += line['debit']
                totals[partner_id]['credit'] += line['credit']
                if line['create_date']:
                    if line['debit']:
                        sign = -1
                        kur = 'gauta'
                    else:
                        sign = 1
                        kur = 'isleista'

                    totals[partner_id]['bePVM'][kur] += line['amount_untaxed_signed'] * sign
                    totals[partner_id]['PVM'][kur] += (line['amount_total_company_signed'] - line[
                        'amount_untaxed_signed']) * sign
                    totals[partner_id]['suPVM'][kur] += line['amount_total_company_signed'] * sign

            for line in avanso_likutis[partner_id]:
                totals[partner_id]['likutis'] += line['likutis']

        pick_date = datetime.strptime(data['form']['date_end'][0], tools.DEFAULT_SERVER_DATE_FORMAT)
        period_start = datetime.strptime(data['form']['date_start'][0], tools.DEFAULT_SERVER_DATE_FORMAT)
        docargs = {
            'doc_ids': ids,
            'doc_model': 'res.partner',
            'docs': self.env['res.partner'].browse(ids),
            'Lines': lines_to_display,
            'Totals': totals,
            'date': pick_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'period_start': period_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'period_end': pick_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'nr': pick_date.strftime("%m.%Y"),
            'Manager': self.env.user.company_id.with_context(
                date=pick_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)).vadovas.name,
            'currency': self.env.user.company_id.sudo().currency_id,
            'print_person': self.env.user.sudo().company_id.vadovas.name or self.env.user.name,
            # 'print_person': self.env.user.name
        }
        return self.env['report'].render('avansine_apyskaita.report_cashbalance_template', values=docargs)


ReportCashAdvance()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def open_cashbalance_wizard(self):
        form_id = self.env.ref('avansine_apyskaita.cashbalance_wizard').id
        res = self.env['cashbalance.wizard'].create({})
        return {
            'name': _('Cash Balance Date'),
            'type': 'ir.actions.act_window',
            'res_id': res.id,
            'res_model': 'cashbalance.wizard',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(form_id, 'form')],
            'view_id': form_id,
            'context': self._context,
            'target': 'new',
        }


ResPartner()
