# -*- coding: utf-8 -*-


from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools

MAX_DEST = 100


class AccountAgedTrialBalance(models.TransientModel):
    _name = 'account.aged.trial.balance'
    _inherit = ['account.aged.trial.balance', 'robo.threaded.report']

    involved_partners = fields.Char(string='Partnerių skaičius', compute='_compute_involved_partners')
    skip_partners_without_email = fields.Boolean(string='Praleisti partnerius su nenurodytu el. pašto adresu')
    skip_recently_sent = fields.Boolean(string='Praleisti partnerius, kuriems neseniai buvo išsiųstos skolų ataskaitos',
                                        default=True,
                                        help='Jei pažymėta, visi partneriai, kuriems skolų ataskaita buvo siųsta per pastarąjį mėnesį, bus praleisti')
    show_unreconciled_warning = fields.Boolean(compute='_compute_unreconciled_warning')
    unreconciled_warning = fields.Text(compute='_compute_unreconciled_warning')
    force_lang = fields.Selection([
        ('lt_LT', 'Lithuanian'),
        ('en_US', 'English'),
    ], string='Report language', default=lambda self: self.env.user.lang or 'lt_LT', )

    @api.multi
    @api.depends('result_selection')
    def _compute_unreconciled_warning(self):
        """
        Compute //
        # Dummy api.depends to trigger compute even when the record is not saved #
        Check whether there are any unreconciled (SEPA/API imported) bank statements
        that are earlier than threshold date, and display a warning if it's the case.
        :return: None
        """
        # Threshold date is one week prior
        threshold_date = (datetime.utcnow() - relativedelta(days=7)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            # Check for unreconciled bank statement lines, that are sepa imported and
            # are earlier than threshold date, if we get at least one, compose a warning
            unreconciled_entries = self.env['account.bank.statement.line'].search_count(
                [('journal_entry_ids', '=', False),
                 ('statement_id.sepa_imported', '=', True),
                 ('statement_id.date', '<', threshold_date)]
            )
            if unreconciled_entries:
                warning_message = _('Rekomenduojame nesiųsti skolų suderinimo aktų klientams - sistemoje rasta '
                                    'nesudengtų bankinių išrašų ankstesnių nei {}.').format(threshold_date)
                rec.show_unreconciled_warning = True
                rec.unreconciled_warning = warning_message

    @api.one
    @api.depends('result_selection', 'display_partner', 'filtered_partner_ids', 'account_ids', 'dont_show_zero_values',
                 'skip_partners_without_email', 'skip_recently_sent')
    def _compute_involved_partners(self):
        if self.display_partner == 'filter':
            self.involved_partners = str(len(self.filtered_partner_ids))
        else:
            partner_data = self._get_partners_data(MAX_DEST)
            self.involved_partners = len(partner_data)

    @api.model
    def _calculate_aged_amount(self, wizard_form):
        if wizard_form['result_selection'] == 'customer':
            account_type = ['receivable']
        elif wizard_form['result_selection'] == 'supplier':
            account_type = ['payable']
        else:
            account_type = ['payable', 'receivable']

        date_from = wizard_form['date_from']
        target_move = wizard_form['target_move']
        filtered_partner_ids = wizard_form['filtered_partner_ids']

        _model = self.env['report.sl_general_report.report_agedpartnerbalance_sl']
        _model.total_account = []  # ROBO: very good api :)

        if wizard_form['display_partner'] == 'filter':
            partner_movelines = _model.with_context(filtered_partner_ids=filtered_partner_ids)._get_partner_move_lines(
                wizard_form, account_type, date_from, target_move)
            movelines = partner_movelines
        else:
            without_partner_movelines = _model._get_move_lines_with_out_partner(wizard_form, account_type, date_from,
                                                                                target_move)
            partner_movelines = _model._get_partner_move_lines(wizard_form, account_type, date_from, target_move)
            movelines = partner_movelines + without_partner_movelines

        return movelines

    @api.model
    def _get_partners_aged_amount(self):

        # ROBO: mimic 'report.sl_general_report.report_agedpartnerbalance_sl' calculation
        wizard_form = {
            'date_from': self.date_from or fields.Date.today(),
            'display_partner': self.display_partner,
            'target_move': self.target_move,
            'result_selection': self.result_selection,
            'journal_ids': self.journal_ids.ids,
            'period_length': self.period_length,
            'date_to': self.date_to,
            'id': self.id,
            'filtered_partner_ids': self.filtered_partner_ids.ids,
            'account_ids': self.account_ids.ids,
        }

        # ROBO: prepare report header (just api)
        start = fields.Date.from_string(wizard_form['date_from'])
        res = {}
        for i in range(5)[::-1]:
            stop = start - relativedelta(days=self.period_length - 1)
            res[str(i)] = {
                'name': (i != 0 and (
                        str((5 - (i + 1)) * self.period_length) + '-' + str((5 - i) * self.period_length)) or (
                                 '+' + str(4 * self.period_length))),
                'stop': fields.Date.to_string(start),
                'start': (i != 0 and fields.Date.to_string(stop) or False),
            }
            start = stop - relativedelta(days=1)
        wizard_form.update(res)

        return self._calculate_aged_amount(wizard_form), wizard_form

    @api.multi
    def _get_partners_data(self, max_length=None):
        """
        Get information about partner's debt
        :return:
        """
        self.ensure_one()
        date_from = self.date_from_debt
        date_to = self.date_to
        if self.result_selection == 'customer':
            account_type_filter = 'receivable'
        elif self.result_selection == 'supplier':
            account_type_filter = 'payable'
        elif self.result_selection == 'customer_supplier':
            account_type_filter = 'payable_receivable'
        else:
            account_type_filter = 'all'
        filtered_account_ids = self.account_ids.ids
        # Irreconcilable accounts may be selected when generating report
        # Their total amounts are included in the report additionally when account_type_filter is 'all'
        irreconcilable_account_ids = self.account_ids.filtered(lambda x: not x.reconcile).ids
        reconcilable_account_ids = self.account_ids.filtered(lambda x: x.reconcile).ids
        show_irreconcilable_accounts = True if account_type_filter == 'all' and irreconcilable_account_ids else False

        filtered_partner_ids = self.filtered_partner_ids
        if filtered_partner_ids:
            if self.skip_recently_sent:
                filtered_partner_ids = filtered_partner_ids.filtered(
                    lambda p: p.balance_reconciliation_send_date <= (
                            datetime.today() - relativedelta(months=1)).strftime(
                        tools.DEFAULT_SERVER_DATETIME_FORMAT))
            partner_ids = filtered_partner_ids.ids
        else:
            arg_list = [date_from, date_to]
            extra_query = ''
            if not show_irreconcilable_accounts:
                extra_query += """
              AND at.type IN %s"""
                arg_list.append(('receivable', 'payable') if account_type_filter == 'payable_receivable'
                                else (account_type_filter,))
            if filtered_account_ids:
                extra_query += """
              AND aml.account_id IN %s"""
                arg_list.append(tuple(filtered_account_ids))

            if self.skip_recently_sent:
                extra_query += """
              AND (p.balance_reconciliation_send_date IS NULL OR p.balance_reconciliation_send_date <= %s)"""
                arg_list.append(
                    (datetime.today() - relativedelta(months=1)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT))
            if self.skip_partners_without_email:
                extra_query += """
              AND p.email IS NOT NULL AND p.email <> ''"""

            query = """
            SELECT DISTINCT(p.id)
            FROM res_partner p
            INNER JOIN account_move_line AS aml ON aml.partner_id = p.id
            INNER JOIN account_move AS am ON am.id = aml.move_id
            INNER JOIN account_account AS ac ON aml.account_id = ac.id
            INNER JOIN account_account_type AS at ON at.id = ac.user_type_id
            WHERE aml.date >= %s
              AND aml.date <= %s
              AND am.state = 'posted'""" + extra_query

            self.env.cr.execute(query, tuple(arg_list))
            partner_ids = set(row[0] for row in self.env.cr.fetchall())
        res = []
        skip_limit = self.env.context.get('admin_skip_dest_limit')
        employee_partner_ids = set(
            self.env['hr.employee'].search([('address_home_id', 'in', list(partner_ids))]).mapped('address_home_id.id'))
        account_ids = self.env['report.debt.reconciliation.base'].sudo().get_default_payable_receivable(
            mode=account_type_filter)
        for partner_id in partner_ids:
            if partner_id in employee_partner_ids:
                continue
            total = 0
            if not filtered_account_ids or reconcilable_account_ids:
                data = self.env['report.debt.reconciliation.base'].sudo().get_raw_residual_move_line_data(
                    partner_id, account_ids, date_to, reconcilable_account_ids)
                total += sum(x.get('amount_company') for x in data)
            # Additionally include total amounts of irreconcilable accounts
            if show_irreconcilable_accounts:
                irreconcilable_data = self.env['report.debt.reconciliation.base'].sudo().\
                    get_irreconcilable_account_amount(partner_id, irreconcilable_account_ids, date_to)
                total += sum(x.get('debit') - x.get('credit') for x in irreconcilable_data)
            if self.dont_show_zero_values and tools.float_is_zero(total,
                                                                  precision_rounding=0.01) and partner_id not in filtered_partner_ids.ids:
                continue
            res.append({'partner_id': partner_id, 'total': total})
            if max_length and not skip_limit and len(res) >= max_length:
                break

        return res

    @api.multi
    def send_report(self):
        self.ensure_one()

        template = self.env.ref('robo.email_template_aged_balance', False)
        compose_form = self.env.ref('robo.robo_email_compose_message_wizard_form', False)

        if self.result_selection == 'customer':
            account_type_filter = 'receivable'
        elif self.result_selection == 'supplier':
            account_type_filter = 'payable'
        elif self.result_selection == 'customer_supplier':
            account_type_filter = 'payable_receivable'
        else:
            account_type_filter = 'all'

        partner_data = self._get_partners_data(MAX_DEST)

        if len(partner_data) > MAX_DEST and not self.skip_recently_sent and not self.env.context.get(
                'admin_skip_dest_limit'):
            raise exceptions.UserError(_('Negalite siųsti daugiau, nei %s partneriams(-ių) vienu kartu') % MAX_DEST)
        if len(partner_data) > MAX_DEST and not self.env.context.get('admin_skip_dest_limit'):
            partner_data = partner_data[:MAX_DEST]

        partner_ids = [r['partner_id'] for r in partner_data]

        if not partner_ids:
            raise exceptions.UserError(_('Nerasta partnerių, atitinkančių pasirinktus paieškos filtrus.'))

        ctx = dict(
            default_model='robo.mail.mass.mailing.partners',
            default_use_template=bool(template),
            default_template_id=template.id,
            default_composition_mode='mass_mail',
            # force_send_message=True,
            partners_movelines=partner_data,
            partner_ids=partner_ids,
            date=self.date_to or fields.Date.today(),
            account_type_filter=account_type_filter,
            # wizard_form=wizard_form,
            filtered_account_ids=self.account_ids.ids,
            default_detail_level=self.detail_level,
            default_date_to=self.date_to,
            default_date_from_debt=self.date_from_debt,
            default_date_to_debt=self.date_to,
            default_type=self.type,
            default_show_original_amounts=self.show_original_amounts,
            default_show_accounts=self.show_accounts,
            default_date_from=self.date_to,
            lang=self.force_lang or 'lt_LT',
        )

        return {
            'name': _('Rašyti laišką'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'robo.mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'current',
            'context': ctx,
            'flags': {'form': {'action_buttons': False}}
            # TODO: special button cancel does not close wizard in current mode. why?
        }

    @api.multi
    def button_generate_report(self):
        """
        Generate debt act report, based on value stored in res.company determine
        whether to use threaded calculation or not
        :return: Result of specified method
        """
        method_name_mapper = {
            'check_report': _('Skolų vėlavimo ataskaita'),
            'create_debt_act_wizard': _('Skolų likučių ataskaita'),
        }
        method_name = self._context.get('method_name')
        forced_xls = self._context.get('xls_report')
        if method_name and hasattr(self, method_name):
            report_name = method_name_mapper.get(method_name)
            return self.env['robo.report.job'].with_context(lang=self.force_lang or self.env.user.lang).generate_report(
                self, method_name, report_name, forced_xls=forced_xls)
