# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from odoo.tools import float_compare, float_is_zero
from datetime import datetime, timedelta
from six import iteritems
from odoo.addons.robo_basic.models.utils import validate_email
from email.utils import formataddr
import traceback


class StartingEntriesException(Exception):
    pass


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def default_get(self, fields_list):
        res = super(ResPartner, self).default_get(fields_list)
        if self.env.user.company_id.sudo().apr_enabled_by_default:
            company = self.env.user.company_id.sudo()
            d = {
                'apr_send_reminders': True,
                'apr_send_before': company.apr_send_before,
                'apr_send_before_ndays': company.apr_send_before_ndays,
                'apr_send_on_date': company.apr_send_on_date,
                'apr_send_after': company.apr_send_after,
                'apr_send_after_ndays': company.apr_send_after_ndays,
                'apr_min_amount_to_send': company.apr_min_amount_to_send,
                'apr_email_cc': company.apr_email_cc,
            }
            res.update(**{k: v for k, v in iteritems(d) if k in fields_list})
        return res

    def _default_get_apr_send_reminders(self):
        return self.env.user.company_id.sudo().apr_enabled_by_default

    apr_send_reminders = fields.Boolean(string='Aktyvuoti automatinius priminimus',
                                        help=('Nustačius klientas gaus automatinius el. Laiškus apie mokėjimo terminus'
                                              ' (Turi būti aktyvuota ir kompanijos nustatymuose)'),
                                        default=_default_get_apr_send_reminders)

    apr_send_before = fields.Boolean(string='Siųsti automatinius priminimus prieš mokėjimo terminą',
                                     help='Jei užstatyta, klientas gaus automatinius mokėjimo priminimus prieš mokėjimo terminą',
                                     default=False)

    apr_send_before_ndays = fields.Integer(string='Dienų skaičius iki mokėjimo termino',
                                           help='Priminimas bus siunčiamas ... dienų iki mokėjimo termino',
                                           default=0)

    apr_send_on_date = fields.Boolean(string='Siųsti priminimą termino dieną',
                                      help='Jei užstatyta, klientas gaus automatinius mokėjimo priminimus',
                                      default=False)

    apr_send_after = fields.Boolean(string='Siųsti automatinius priminimus po mokėjimo termino',
                                    help='Jei užstatyta, klientas gaus automatinius mokėjimo priminimus',
                                    default=False)

    apr_send_after_ndays = fields.Integer(string='Dienų skaičius nuo mokėjimo termino',
                                          help='Priminimas bus siunčiamas ... dienų nuo mokėjimo termino',
                                          default=0)

    apr_min_amount_to_send = fields.Float(string='Mažiausia suma, nuo kurios siųsti mokėjimo priminimus',
                                          default=10.0)

    apr_date_last_sent = fields.Date(string='Paskutinė mokėjimo terminų priminimo data')

    apr_sendto_emails = fields.Text(string='Siųsti automatinius priminimus į šiuos el pašto adresus',
                                    help='Jei pateikiami keli el. pašto adresai, jie turi būti atskirti kabliataškiu (;)')
    apr_email_cc = fields.Text(string='Siųsti laiškų kopijas el. paštu',
                               help='Jei pateikiami keli el. pašto adresai, jie turi būti atskirti kabliataškiu (;)')
    enabled_reminders = fields.Boolean(string='Aktyvuoti priminimai', compute='_compute_enabled_reminders')

    def _compute_enabled_reminders(self):
        enabled_reminders = self.env.user.sudo().company_id.apr_send_reminders
        for rec in self:
            rec.enabled_reminders = enabled_reminders

    @api.multi
    def toggle_reminders(self):
        if not self.env.user.has_group('robo_basic.group_robo_apr_settings'):
            raise exceptions.AccessError(_('Tik vadovas gali pakeisti šį nustatymą'))
        if not self.env.user.sudo().company_id.apr_send_reminders:
            raise exceptions.UserError(_('Kompanijos nustatymuose neįjungti automatiniai priminimai.'))
        for record in self:
            # if not record.apr_sendto_emails and record.email:
            #     record.apr_sendto_emails = record.email
            try:
                record.sanitize_apr_emails_list()
            except:
                pass
            record.apr_send_reminders = not record.apr_send_reminders
        self.set_default_send_reminders_settings()

    @api.onchange('apr_sendto_emails')
    def sanitize_apr_emails_list(self):
        sanitized_emails = []
        if self.apr_sendto_emails:
            for email in self.apr_sendto_emails.split(';'):
                email = email.strip().lower()
                sanitized_emails.append(email)
                if not validate_email(email, verify=False, check_mx=False):
                    raise exceptions.Warning(_('Nurodytas neteisingas el. pašto adresas.'))
        if sanitized_emails:
            self.apr_sendto_emails = ';'.join(sanitized_emails)

    @api.onchange('apr_email_cc')
    def sanitize_apr_emails_cc_list(self):
        sanitized_emails = []
        if self.apr_email_cc:
            for email in self.apr_email_cc.split(';'):
                email = email.strip().lower()
                sanitized_emails.append(email)
                if not validate_email(email, verify=False, check_mx=False):
                    raise exceptions.Warning(_('Nurodytas neteisingas el. pašto adresas.'))
        if sanitized_emails:
            self.apr_email_cc = ';'.join(sanitized_emails)

    @api.onchange('apr_send_reminders')
    def _onchange_apr_send_reminders(self):
        if self.apr_send_reminders:
            company = self.env.user.company_id
            self.apr_send_after_ndays = company.apr_send_after_ndays
            self.apr_min_amount_to_send = company.apr_min_amount_to_send
            self.apr_send_before_ndays = company.apr_send_before_ndays
            self.apr_send_before = company.apr_send_before
            self.apr_send_on_date = company.apr_send_on_date
            self.apr_send_after = company.apr_send_after
            if not self.apr_email_cc:
                self.apr_email_cc = company.apr_email_cc

    @api.multi
    @api.constrains('apr_send_reminders', 'apr_send_before', 'apr_send_before_ndays')
    def constrain_send_before_ndays(self):
        for rec in self:
            if rec.apr_send_reminders and rec.apr_send_before and rec.apr_send_before_ndays <= 0:
                raise exceptions.ValidationError(_('Mažiausias leistinas dienų skaičius yra 1 diena'))

    @api.multi
    @api.constrains('apr_send_reminders', 'apr_send_after', 'apr_send_after_ndays')
    def constrain_send_after_ndays(self):
        for rec in self:
            if rec.apr_send_after_ndays <= 0 and rec.apr_send_reminders and rec.apr_send_after:
                raise exceptions.ValidationError(_('Mažiausias leistinas dienų skaičius yra 1 diena'))

    @api.multi
    def write(self, vals):
        if not self.env.user.has_group('robo_basic.group_robo_apr_settings'):
            for f in ['apr_send_reminders', 'apr_send_after', 'apr_send_after_ndays', 'apr_send_before', 'apr_email_cc',
                      'apr_send_before_ndays', 'apr_sendto_emails', 'apr_send_on_date', 'apr_min_amount_to_send', 'apr_date_last_sent']:
                vals.pop(f, None)
        return super(ResPartner, self).write(vals)

    @api.model
    def _get_account_move_lines(self, partners_id=None):
        if partners_id is None:
            partners_id = [self.id]
        res = dict(map(lambda x: (x, []), partners_id))
        self.env.cr.execute('''
            SELECT m.name AS move_id
                 , l.date
                 , l.name
                 , l.ref
                 , l.date_maturity
                 , l.partner_id
                 , l.blocked
                 , l.journal_id
                 , l.amount_residual_currency
                 , l.amount_currency
                 , l.currency_id
                 , CASE WHEN at.type = 'receivable'
                        THEN SUM(l.debit)
                        ELSE SUM(l.credit * -1)
                    END AS debit
                 , CASE WHEN at.type = 'receivable'
                        THEN SUM(l.debit - l.amount_residual)
                        ELSE SUM(l.credit + l.amount_residual)
                    END AS credit
                 , SUM(l.amount_residual) AS mat
                 , account_invoice.number AS inv_name 
            FROM account_move_line l
            JOIN account_account_type at ON (l.user_type_id = at.id)
            JOIN account_move m ON (l.move_id = m.id)
            LEFT JOIN account_invoice ON l.invoice_id = account_invoice.id 

            WHERE l.partner_id IN %s
              AND at.type IN ('receivable', 'payable')
              AND l.reconciled = false 

            GROUP BY l.date, l.name, l.ref, l.date_maturity, l.partner_id, at.type, l.blocked, l.journal_id,
                     l.amount_residual_currency, l.amount_currency, l.currency_id, l.move_id, m.name, account_invoice.number 
            ORDER BY date_maturity''',
                            (tuple(partners_id),))
        for row in self.env.cr.dictfetchall():
            partner_id = row.pop('partner_id')
            if not self.env.user.has_group('hr.group_hr_manager') and (
                    self.sudo().env['hr.employee'].search(['|',
                                                           ('address_home_id', '=', partner_id),
                                                           ('advance_accountancy_partner_id', '=', partner_id)])
                    or
                    self.sudo().env['hr.employee'].search(['|',
                                                           ('address_home_id', '=', partner_id),
                                                           ('advance_accountancy_partner_id', '=', partner_id),
                                                           ('active', '=', False)])):
                continue

            res[partner_id].append(row)
        return res

    @api.multi
    def set_default_send_reminders_settings(self):
        """ Apply the default company settings """
        company = self.env.user.company_id
        self.filtered('apr_send_reminders').write({
            'apr_send_after_ndays': company.apr_send_after_ndays,
            'apr_min_amount_to_send': company.apr_min_amount_to_send,
            'apr_send_before_ndays': company.apr_send_before_ndays,
            'apr_send_before': company.apr_send_before,
            'apr_send_on_date': company.apr_send_on_date,
            'apr_send_after': company.apr_send_after,
        })
        self.filtered(lambda p: not p.apr_email_cc).write({'apr_email_cc': company.apr_email_cc})

    @api.multi
    def create_pdf(self, partner_id, date):
        self.ensure_one()
        wizard_id = self.env['debt.act.wizard'].create({'date': date,
                                                        'partner_ids': [(4, partner_id)],
                                                        'all_partners': False,
                                                        'account_type_filter': 'payable_receivable',
                                                        'type': 'unreconciled',
                                                        'detail_level': 'detail',
                                                        'show_original_amounts': False})
        data = wizard_id.get_data()
        data['payment_reminder'] = True
        report_name = 'skolu_suderinimas.report_aktas_multi'
        result, out_format = self.env['ir.actions.report.xml'].render_report(wizard_id._ids,
                                                                             report_name,
                                                                             data=data)
        if out_format == 'pdf':
            result = result.encode('base64')
        else:
            result = False
        return result

    @api.model
    def _get_payment_details(self, lang='lt_LT'):
        def trans(name):
            try:
                value = tools.translate(self._cr, 'addons/due_payments/model/automatic_reminder.py', 'code', lang=lang, source=name)
            except:
                value = False
            return value or name

        account = self.env['account.journal'].search([('display_on_footer', '=', True)], limit=1)
        company = self.env.user.company_id
        detail_names = {  # This is here to have the translations for the terms
            'bank_name': _('Bank name'),
            'bank_code': _('Bank code'),
            'acc_num': _('Account number'),
            'bic': _('BIC'),
            'comp_name': _('Beneficiary'),
            'reg_num': _('Registration number'),
            'vat_code': _('VAT code')
        }
        d = {
            'bank_name': ['Bank name', account.bank_id.name],
            'bank_code': ['Bank code', account.bank_id.kodas],
            'acc_num': ['Account number', account.bank_acc_number],
            'bic': ['BIC', account.bank_id.bic],
            'comp_name': ['Beneficiary', company.name],
            'reg_num': ['Registration number', company.company_registry or ""],
            'vat_code': ['VAT code', company.vat or ""]
        }

        return '\n'.join(['<p>' + trans(d[j][0]) + ': ' + d[j][1] + '</p>' for j in ['comp_name',
                                                                                     'reg_num',
                                                                                     'vat_code',
                                                                                     'bank_name',
                                                                                     'bank_code',
                                                                                     'acc_num',
                                                                                     'bic'] if d[j][1]])

    @api.model
    def _get_apr_template_dict(self):
        return {'before': 'due_payments.apr_email_template_res_partner_before_invoice',
                'today': 'due_payments.apr_email_template_res_partner_on_date_invoice',
                'after': 'due_payments.apr_email_template_res_partner_after_invoice'}

    @api.multi
    def _get_apr_email_context_from_settings(self, settings):
        self.ensure_one()
        return {
            'invoice': settings.get('invoices'),
            'amount': settings.get('total_payable_amount'),
            'payment_details': self._get_payment_details(self.lang or 'lt_LT'),
            'date_due': settings.get('date_due'),
            'n_days': self.apr_send_before_ndays,
            'lang': self.lang or 'lt_LT',
        }

    @api.multi
    def _apr_send_invoice_reminder_email(self, settings):
        self.ensure_one()
        template_dict = self._get_apr_template_dict()
        company = self.env.user.company_id

        apr_type = settings['type']
        template = self.env.ref(template_dict.get(apr_type))
        email_context = self._get_apr_email_context_from_settings(settings)
        report_date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        vals = self.env['mail.compose.message'].with_context(email_context).generate_email_for_composer(template.id,
                                                                                                        self.id)
        attachment_id = self.env['ir.attachment'].create(
            {'name': _('Balance ') + datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
             'datas_fname': datetime.now().strftime('%Y_%m_%d') + '.pdf',
             'datas': self.create_pdf(self.id, report_date)
             })
        reply_to = company.apr_email_reply_to or company.partner_id.email or company.vadovas.work_email
        vals.update({
            'composition_mode': 'mass_mail',
            'template_id': template.id,
            'model': 'res.partner',
            'res_id': self.id,
            'subject': vals['subject'] + company.name,
            'reply_to': '<%s>' % reply_to,
            'attachment_ids': [(4, attachment_id.id)],
        })
        emails_to = self.apr_sendto_emails or self.email
        force_message_vals = {
            'email_to': '<' + '>;<'.join(emails_to.lower().replace(' ', '').split(';')) + '>',
            'reply_to': vals.get('reply_to'),  #Is it really needed to override force it again?
        }
        if self.apr_email_cc:   #Is it really needed to override force it again?
            force_message_vals['email_cc'] = '<' + '>;<'.join(
                self.apr_email_cc.lower().replace(' ', '').split(';')) + '>'
        mail_rec = self.env['mail.compose.message'].create(vals)
        mail_rec.with_context(force_message_vals=force_message_vals, client_company=True).send_mail()
        self.apr_date_last_sent = datetime.utcnow()

    @api.multi
    def _apr_check_and_send_reminders(self, lines=None):  # WARNING : this method commits to the database
        self.ensure_one()

        date_lim = (datetime.now() + timedelta(days=-max(1, self.apr_send_after_ndays))).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)

        date_last_sent = self.apr_date_last_sent or date_lim
        if self.apr_send_after and date_last_sent <= date_lim:
            self._apr_send_after_if_necessary(lines)
        self._cr.commit()

        date_last_sent = self.apr_date_last_sent or date_lim
        if self.apr_send_on_date and date_last_sent <= date_lim:
            self._apr_send_on_date_if_necessary(lines)
        self._cr.commit()

        date_last_sent = self.apr_date_last_sent or date_lim
        if self.apr_send_before and date_last_sent <= date_lim:
            self._apr_send_before_if_necessary(lines)

    @api.model
    def _update_lines(self, lines):
        company_currency = self.env.user.company_id.currency_id
        totals = {}
        lines_to_display = {}
        updated_lines = []
        start_journal = self.env['account.journal'].search([('code', '=', 'START')])
        if start_journal and all(line['journal_id'] == start_journal.id for line in lines):
            # We don't want the reminder to be triggered only by imported debts, as there would be no invoice,
            # but we want the amount included if there are also non-imported ones
            raise StartingEntriesException()
        for line_tmp in lines:
            line = line_tmp.copy()
            currency = line['currency_id'] and self.env['res.currency'].browse(line['currency_id']) or company_currency
            if currency not in lines_to_display:
                lines_to_display[currency] = []
                totals[currency] = dict((fn, 0.0) for fn in ['due', 'paid', 'mat', 'total'])
            if line['debit'] and line['currency_id']:
                line['debit'] = line['amount_currency']
            if line['credit'] and line['currency_id']:
                # prepaid
                if line['amount_residual_currency'] < 0:
                    line['credit'] = abs(line['amount_residual_currency'])
                else:
                    line['credit'] = line['amount_currency'] - line['amount_residual_currency']
            if line['mat'] and line['currency_id']:
                line['mat'] = line['amount_residual_currency']
            if float_is_zero(line['debit'], precision_rounding=currency.rounding) and \
                    float_is_zero(line['credit'], precision_rounding=currency.rounding) and \
                    float_is_zero(line['mat'], precision_rounding=currency.rounding):
                continue
            lines_to_display[currency].append(line)
            updated_lines.append(line)
            if not line['blocked']:
                totals[currency]['due'] += line['debit']
                totals[currency]['paid'] += line['credit']
                totals[currency]['mat'] += line['mat']
                totals[currency]['total'] += line['debit'] - line['credit']
        if start_journal and all(line['journal_id'] == start_journal.id for line in updated_lines):
            raise StartingEntriesException()
        return updated_lines, totals

    @api.multi
    def _apr_send_before_if_necessary(self, lines=None):
        self.ensure_one()
        if lines is None:
            lines = self._get_account_move_lines()[self.id]
        try:
            lines, totals = self._update_lines(lines)
        except StartingEntriesException:
            return

        company_currency = self.env.user.company_id.currency_id
        date_to = (datetime.now() +
                   timedelta(days=self.apr_send_before_ndays)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        apr_send_before_message = False
        invoices = []
        amounts_before = []
        currencies_to_pay = self.env['res.currency']
        total_amount_left_unpaid = 0.0  # Assuming single currency
        for currency in totals:
            if float_compare(totals[currency]['mat'], 0.0, precision_rounding=currency.rounding) > 0:
                if currency != company_currency:
                    relevant_lines = [l for l in lines if l['currency_id'] == currency.id]
                else:
                    relevant_lines = [l for l in lines if l['currency_id'] == currency.id or not l['currency_id']]

                amount_paid = - sum(l['mat'] for l in relevant_lines if l['mat'] < 0)
                # due payments
                unpaid_lines = [l for l in relevant_lines if
                                float_compare(l['mat'], 0, precision_rounding=currency.rounding) > 0 and l[
                                    'date_maturity'] <= date_to]
                unpaid_lines.sort(key=lambda r: r['date_maturity'])
                while unpaid_lines and float_compare(amount_paid, 0, precision_rounding=currency.rounding) >= 0:
                    amount = unpaid_lines[0]['mat']
                    if float_compare(amount_paid, amount, precision_rounding=currency.rounding) >= 0:
                        amount_paid -= amount
                        unpaid_lines.pop(0)
                    else:
                        break
                if unpaid_lines:
                    min_amount_to_send = self.apr_min_amount_to_send
                    amount_before = 0
                    for l in unpaid_lines:
                        if l['date_maturity'] == date_to:
                            inv_name = l['inv_name']
                            if inv_name:
                                invoices.append(inv_name)
                                amount_before += l['mat']
                    if invoices and amount_before > min_amount_to_send:
                        apr_send_before_message = True
                        currencies_to_pay |= currency
                        total_amount_left_unpaid += amount_before
                        if currency.position == 'after':
                            amounts_before.append('%.02f%s' % (amount_before, currency.symbol))
                        else:
                            amounts_before.append('%s%.02f' % (currency.symbol, amount_before))
        if apr_send_before_message:
            if len(invoices) == 1:
                invoice_str = _('sąskaitą %s, kurios') % invoices[0]
            else:
                invoice_str = _('sąskaitas %s, kurių bendra') % ', '.join(i for i in invoices)
            amount = ', '.join(amounts_before)
            email_settings = {'type': 'before',
                              'total_payable_amount': amount,
                              'invoices': invoice_str,
                              'currencies': currencies_to_pay,
                              'total_amount_left_unpaid': total_amount_left_unpaid,
                              }
            self._apr_send_invoice_reminder_email(email_settings)

    @api.multi
    def _apr_send_after_if_necessary(self, lines=None):
        self.ensure_one()
        if lines is None:
            lines = self._get_account_move_lines()[self.id]
        try:
            lines, totals = self._update_lines(lines)
        except StartingEntriesException:
            return

        date_to = (datetime.now() - timedelta(days=self.apr_send_after_ndays)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        company_currency = self.env.user.company_id.currency_id

        send_due_message = False
        invoices = []
        due_date = False
        amounts_due = []
        currencies_to_pay = self.env['res.currency']
        total_amount_left_unpaid = 0.0  # Assuming single currency
        for currency in totals:
            if float_compare(totals[currency]['mat'], 0.0, precision_rounding=currency.rounding) > 0:
                if currency != company_currency:
                    relevant_lines = [l for l in lines if l['currency_id'] == currency.id]
                else:
                    relevant_lines = [l for l in lines if l['currency_id'] == currency.id or not l['currency_id']]
                amount_paid = - sum(l['mat'] for l in relevant_lines if l['mat'] < 0)
                # due payments
                unpaid_lines = [l for l in relevant_lines if
                                float_compare(l['mat'], 0, precision_rounding=currency.rounding) > 0 and
                                l['date_maturity'] <= date_to]
                unpaid_lines.sort(key=lambda r: r['date_maturity'])
                while unpaid_lines and float_compare(amount_paid, 0, precision_rounding=currency.rounding) >= 0:
                    amount = unpaid_lines[0]['mat']
                    if float_compare(amount_paid, amount, precision_rounding=currency.rounding) >= 0:
                        amount_paid -= amount
                        unpaid_lines.pop(0)
                    else:
                        break
                if unpaid_lines:
                    total_payable_amount = sum(l['mat'] for l in unpaid_lines) - amount_paid
                    min_amount_to_send = self.apr_min_amount_to_send
                    if float_compare(total_payable_amount, min_amount_to_send,
                                     precision_rounding=currency.rounding) > 0:
                        for l in unpaid_lines:
                            inv_name = l['inv_name']
                            if inv_name:
                                invoices.append(inv_name)
                        if not due_date:
                            due_date = unpaid_lines[0]['date_maturity']
                        else:
                            due_date = min(due_date, unpaid_lines[0]['date_maturity'])
                        send_due_message = True
                        currencies_to_pay |= currency
                        total_amount_left_unpaid += total_payable_amount
                        if currency.position == 'after':
                            amounts_due.append('%.02f %s' % (total_payable_amount, currency.symbol))
                        else:
                            amounts_due.append('%s%.02f' % (currency.symbol, total_payable_amount))

        if send_due_message and invoices:
            if len(invoices) == 1:
                invoice_str = _('sąskaitą %s, kurios') % invoices[0]
            else:
                invoice_str = _('sąskaitas %s, kurių bendra') % ', '.join(i for i in invoices)
            amount = ', '.join(amounts_due)
            email_settings = {'type': 'after',
                              'total_payable_amount': amount,
                              'invoices': invoice_str,
                              'date_due': due_date,
                              'currencies': currencies_to_pay,
                              'total_amount_left_unpaid': total_amount_left_unpaid,
                              }
            self._apr_send_invoice_reminder_email(email_settings)

    @api.multi
    def _apr_send_on_date_if_necessary(self, lines=None):
        self.ensure_one()
        if lines is None:
            lines = self._get_account_move_lines()[self.id]
        try:
            lines, totals = self._update_lines(lines)
        except StartingEntriesException:
            return

        company_currency = self.env.user.company_id.currency_id
        current_date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        send_today_message = False
        invoices = []
        amounts_today = []
        currencies_to_pay = self.env['res.currency']
        total_amount_left_unpaid = 0.0  # Assuming single currency
        for currency in totals:
            if float_compare(totals[currency]['mat'], 0.0, precision_rounding=currency.rounding) > 0:
                if currency != company_currency:
                    relevant_lines = [l for l in lines if l['currency_id'] == currency.id]
                else:
                    relevant_lines = [l for l in lines if l['currency_id'] == currency.id or not l['currency_id']]
                amount_paid = - sum(l['mat'] for l in relevant_lines if l['mat'] < 0)
                # due payments
                unpaid_lines = [l for l in relevant_lines if
                                float_compare(l['mat'], 0, precision_rounding=currency.rounding) > 0 and l[
                                    'date_maturity'] <= current_date]
                unpaid_lines.sort(key=lambda r: r['date_maturity'])
                while unpaid_lines and float_compare(amount_paid, 0, precision_rounding=currency.rounding) >= 0:
                    amount = unpaid_lines[0]['mat']
                    if float_compare(amount_paid, amount, precision_rounding=currency.rounding) >= 0:
                        amount_paid -= amount
                        unpaid_lines.pop(0)
                    else:
                        break
                if unpaid_lines:
                    min_amount_to_send = self.apr_min_amount_to_send
                    amount_today = 0
                    for l in unpaid_lines:
                        if l['date_maturity'] == current_date:
                            inv_name = l['inv_name']
                            if inv_name:
                                invoices.append(inv_name)
                                amount_today += l['mat']

                    if invoices and amount_today > min_amount_to_send:
                        send_today_message = True
                        currencies_to_pay |= currency
                        total_amount_left_unpaid += amount_today
                        if currency.position == 'after':
                            amounts_today.append('%.02f%s' % (amount_today, currency.symbol))
                        else:
                            amounts_today.append('%s%.02f' % (currency.symbol, amount_today))

        if send_today_message and invoices:
            if len(invoices) == 1:
                invoice_str = _('sąskaitą %s, kurios') % invoices[0]
            else:
                invoice_str = _('sąskaitas %s, kurių bendra') % ', '.join(i for i in invoices)
            amount = ', '.join(amounts_today)
            email_settings = {'type': 'today',
                              'total_payable_amount': amount,
                              'invoices': invoice_str,
                              'currencies': currencies_to_pay,
                              'total_amount_left_unpaid': total_amount_left_unpaid,
                              }
            self._apr_send_invoice_reminder_email(email_settings)

    @api.model
    def cron_apr_send_reminders(self):
        if datetime.now().weekday() in (5, 6):
            return

        if not self.env.user.sudo().company_id.apr_send_reminders:
            return

        partners = self.env['res.partner'].search([('apr_send_reminders', '=', True),
                                                   '|',
                                                   ('apr_sendto_emails', '!=', False),
                                                   ('email', '!=', False)])
        if not partners:
            return

        lines = self.env['res.partner']._get_account_move_lines([x.id for x in partners])
        partners_not_sent = {}
        for partner in partners:
            if not self.env['account.invoice'].search_count(
                    [('partner_id', '=', partner.id), ('type', 'in', ['out_invoice', 'out_refund'])]):
                continue
            try:
                partner.with_context(lang=partner.lang)._apr_check_and_send_reminders(lines[partner.id])
            except Exception as e:
                self._cr.rollback()
                message = 'Error while sending emails:\n' + e.message
                traceback_message = '\n Traceback: \n\n'
                traceback_message += traceback.format_exc()
                partners_not_sent.update({partner.id: {'message': message, 'traceback': traceback_message}})

            self._cr.commit()

        if partners_not_sent:
            raise ValueError(partners_not_sent)

