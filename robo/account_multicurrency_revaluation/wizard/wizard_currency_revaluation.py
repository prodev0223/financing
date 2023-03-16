# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import tools, exceptions, fields, api, models, _
from six import iteritems
import calendar
from dateutil.relativedelta import relativedelta


class WizardCurrencyrevaluation(models.TransientModel):

    _name = 'wizard.currency.revaluation'

    def _get_default_revaluation_date(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _get_default_reverse_date(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _get_default_journal_id(self):
        """
        Get default journal if one is defined in company settings
        """
        cp = self.env.user.company_id

        journal = cp.default_currency_reval_journal_id
        return journal and journal.id or False

    revaluation_date = fields.Date('Revaluation Date', default=_get_default_revaluation_date, required=True)
    journal_id = fields.Many2one('account.journal', 'Journal', domain="[('type','=','general')]",
        help='You can set the default journal in company settings.', default=_get_default_journal_id, required=True)
    label = fields.Char('Entry description', size=100,
         help="This label will be inserted in entries description."
             " You can use %(account)s, %(currency)s"
             " and %(rate)s keywords.", default='%(currency)s %(account)s %(rate)s valiutos perkainavimas', required=True)
    partneris = fields.Many2one('res.partner', 'Partneris', required=False)
    saskaita = fields.Many2one('account.account', 'Sąskaita', required=False)
    atstatymo_data = fields.Date('Atstatymo data', default=_get_default_reverse_date, required=True)

    @api.onchange('revaluation_date')
    def on_change_revaluation_date(self):
        if not self.revaluation_date:
            return
        else:
            next_date = datetime.strptime(self.revaluation_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
            return {'value': {'atstatymo_data': next_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)}}

    @api.model
    def _compute_unrealized_currency_gl(self, currency_id, balances, form):
        """
        Update data dict with the unrealized currency gain and loss
        plus add 'currency_rate' which is the value used for rate in
        computation

        @param int currency_id: currency to revaluate
        @param dict balances: contains foreign balance and balance

        @return: updated data for foreign balance plus rate value used
        """

        currency_obj = self.env['res.currency']
        # type_id = False
        # Compute unrealized gain loss
        ctx_rate = self._context.copy()
        ctx_rate['date'] = form.revaluation_date
        # ctx_rate['currency_rate_type_id'] = type_id
        cp_currency = self.env.user.company_id.currency_id

        currency = currency_obj.with_context(ctx_rate).browse(currency_id)
        foreign_balance = adjusted_balance = balances.get(
                                                'foreign_balance', 0.0)
        balance = balances.get('balance', 0.0)
        if foreign_balance:
            ctx_rate['revaluation'] = True
            adjusted_balance = currency_obj.browse(currency_id).with_context(ctx_rate).compute(foreign_balance, cp_currency)
            unrealized_gain_loss = adjusted_balance - balance
        else:
            if balance:
                if currency_id != cp_currency.id:
                    unrealized_gain_loss = 0.0 - balance
                else:
                    unrealized_gain_loss = 0.0
            else:
                unrealized_gain_loss = 0.0
        return {'unrealized_gain_loss': unrealized_gain_loss,
                'currency_rate': currency.rate,
                'revaluated_balance': adjusted_balance}

    @api.model
    def _format_label(self, text, account_id, currency_id,
                      rate):
        """
        Return a text with replaced keywords by values

        @param str text: label template, can use
            %(account)s, %(currency)s, %(rate)s
        @param int account_id: id of the account to display in label
        @param int currency_id: id of the currency to display
        @param float rate: rate to display
        """
        account_obj = self.env['account.account']
        currency_obj = self.env['res.currency']
        account = account_obj.browse(account_id)
        currency = currency_obj.browse(currency_id)
        data = {'account': account.code or False,
                'currency': currency.name or False,
                'rate': rate or False}
        return text % data

    @api.model
    def _write_adjust_balance(self, account_id, currency_id,
                              partner_id, amount, label, form, sums):
        """
        Generate entries to adjust balance in the revaluation accounts

        @param account_id: ID of account to be reevaluated
        @param amount: Amount to be written to adjust the balance
        @param label: Label to be written on each entry
        @param form: Wizard browse record containing data

        @return: ids of created move_lines
        """

        def create_move(line_ids):
            base_move = {'name': label,
                         'journal_id': form.journal_id.id,
                         'line_ids': line_ids,
                         'date': form.revaluation_date,
                         }
            return base_move

        def create_move_line(line_data, sums):
            base_line = {'name': label,
                         'partner_id': partner_id,
                         'date': form.revaluation_date,
                         'storno': True,
                         'currency_id': currency_id,
                         'amount_currency': 0.0,
                         }
            base_line.update(line_data)
            # we can assume that keys should be equals columns name + gl_
            # but it was not decide when the code was designed. So commented code may sucks
            #for k, v in sums.items():
            #    line_data['gl_' + k] = v
            base_line['gl_foreign_balance'] = sums.get('foreign_balance', 0.0)
            base_line['gl_balance'] = sums.get('balance', 0.0)
            base_line['gl_revaluated_balance'] = sums.get('revaluated_balance', 0.0)
            base_line['gl_currency_rate'] = sums.get('currency_rate', 0.0)
            return base_line

        if partner_id is None:
            partner_id = False

        company = self.env.user.company_id

        moves = []
        # over revaluation
        if amount >= 0.01:
            if company.revaluation_gain_account_id:
                # Create a move line to Debit account to be revaluated
                line_data = {'debit': amount,
                             # 'move_id': move_id,
                             'account_id': account_id,
                             }
                line_ids = []
                # created_ids.append(create_move_line(move_id, line_data, sums))
                # Create a move line to Credit revaluation gain account
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                line_data = {
                    'credit': amount,
                    'account_id': company.revaluation_gain_account_id.id,
                    'analytic_account_id' : company.revaluation_analytic_account_id and company.revaluation_analytic_account_id.id or False,
                    }
                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                move = create_move(line_ids)
                moves.append(move)
            if company.provision_bs_gain_account_id and \
               company.provision_pl_gain_account_id:
                line_ids = []
                # Create a move line to Debit provision BS gain
                line_data = {
                    'debit': amount,
                    # 'move_id': move_id,
                    'account_id': company.provision_bs_gain_account_id.id, }
                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                # Create a move line to Credit provision P&L gain
                line_data = {
                    'credit': amount,
                    'account_id': company.provision_pl_gain_account_id.id,
                    # 'move_id': move_id,
                    }
                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                move = create_move(line_ids)
                moves.append(move)
        # under revaluation
        elif amount <= -0.01:
            amount = -amount
            if company.revaluation_loss_account_id:
                line_ids = []
                # Create a move line to Debit revaluation loss account
                line_data = {
                    'debit': amount,
                    # 'move_id': move_id,
                    'account_id': company.revaluation_loss_account_id.id,
                    'analytic_account_id' : company.revaluation_analytic_account_id and company.revaluation_analytic_account_id.id or False,
                    }

                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                # Create a move line to Credit account to be revaluated
                line_data = {
                    'credit': amount,
                    # 'move_id': move_id,
                    'account_id': account_id,
                    }
                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                move = create_move(line_ids)
                moves.append(move)
            if company.provision_bs_loss_account_id and \
               company.provision_pl_loss_account_id:
                line_ids = []
                # Create a move line to Debit Provision P&L
                line_data = {
                    'debit': amount,
                    # 'move_id': move_id,
                    'account_id': company.provision_pl_loss_account_id.id, }
                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                # Create a move line to Credit Provision BS
                line_data = {
                    'credit': amount,
                    # 'move_id': move_id,
                    'account_id': company.provision_bs_loss_account_id.id, }
                # created_ids.append(create_move_line(move_id, line_data, sums))
                line_ids.append((0, 0, create_move_line(line_data, sums)))
                move = create_move(line_ids)
                moves.append(move)
        return moves

    @api.multi
    def revaluate_currency(self):
        """
        Compute unrealized currency gain and loss and add entries to
        adjust balances

        @return: dict to open an Entries view filtered on generated move lines
        """
        if self.revaluation_date >= self.atstatymo_data:
            raise exceptions.Warning(_('Atstatymo data turi būti vėlesnė už perkainavimo datą.'))

        account_obj = self.env['account.account']
        move_obj = self.env['account.move']
        account_move_line_obj = self.env['account.move.line']

        company = self.env.user.company_id

        if (not company.revaluation_loss_account_id and
            not company.revaluation_gain_account_id and
            not (company.provision_bs_loss_account_id and
                 company.provision_pl_loss_account_id) and
            not (company.provision_bs_gain_account_id and
                 company.provision_pl_gain_account_id)):
            raise exceptions.Warning(
                _("No revaluation or provision account are defined"
                  " for your company.\n"
                  "You must specify at least one provision account or"
                  " a couple of provision account."))

        created_ids = []

        form = self[0]

        # Search for accounts Balance Sheet to be eevaluated
        # on those criterions
        # - deferral method of account type is not None
        account_ids = account_obj.search([('currency_revaluation', '=', True)])

        if not account_ids:
            raise exceptions.Warning(_("No account to be revaluated found. "
                  "Please check 'Allow Currency Revaluation' "
                  "for at least one account in account form."))

        # Get balance sums
        # account_sums = account_ids.compute_revaluations(form.revaluation_date)
        account_sums = account_ids.get_grouped_accounts(form.revaluation_date)
        account_account_obj = self.env['account.account']
        for account_id, account_tree in iteritems(account_sums):
            rev_date = self.revaluation_date
            storno = self.env['account.move.line'].search([['account_id', '=', account_id], ['date', '=', rev_date], ['storno', '=', True]])
            if len(storno) > 0:
                raise exceptions.Warning(_('Nurodytą dieną jau buvo sukurtas STORNO įrašas sąskaitai ' \
                                           + self.env['account.account'].browse(account_id)[0].name))
            for currency_id, currency_tree in iteritems(account_tree):
                for partner_id, sums in iteritems(currency_tree):
                    # Update sums with compute amount currency balance
                    diff_balances = self._compute_unrealized_currency_gl(currency_id, sums, form)
                    account_sums[account_id][currency_id][partner_id].\
                        update(diff_balances)
        # Create entries only after all computation have been done
        liquidity_accounts = {}
        liquidity_accounts_rate = {}
        total_liquidity_accounts = {}
        for account_id, account_tree in iteritems(account_sums):
            for currency_id, currency_tree in iteritems(account_tree):
                total_liquidity_accounts.setdefault(account_id, {}).setdefault(currency_id, {})
                for partner_id, sums in iteritems(currency_tree):
                    for k in sums:
                        if k == 'currency_rate':
                            total_liquidity_accounts[account_id][currency_id][k] = sums[k]
                        if k in total_liquidity_accounts[account_id][currency_id]:
                            total_liquidity_accounts[account_id][currency_id][k] += sums[k]
                        else:
                            total_liquidity_accounts[account_id][currency_id][k] = sums[k]
                    adj_balance = sums.get('unrealized_gain_loss', 0.0)
                    saskaitele = account_account_obj.browse(account_id)
                    if not saskaitele.reconcile:
                        if liquidity_accounts.get(account_id):
                            liquidity_accounts[account_id] += adj_balance
                        else:
                            liquidity_accounts[account_id] = adj_balance
                        if liquidity_accounts_rate.get(account_id):
                            pass
                        else:
                            liquidity_accounts_rate[account_id] = sums.get('currency_rate', 0.0)
        for account_id, account_tree in iteritems(account_sums):
            for currency_id, currency_tree in iteritems(account_tree):
                saskaitele = account_account_obj.browse(account_id)
                if not saskaitele.reconcile:
                    adj_balance = liquidity_accounts[account_id] or 0.0
                    if not adj_balance:
                        continue
                    rate = liquidity_accounts_rate[account_id] or 0.0
                    label = self._format_label(form.label, account_id, currency_id, rate)
                    # sums = {'gl_currency_rate': rate}
                    new_ids = self._write_adjust_balance(
                            account_id,
                            currency_id,
                            False,
                            adj_balance,
                            label,
                            form,
                            total_liquidity_accounts[account_id][currency_id])
                    created_ids.extend(new_ids)
                else:
                    for partner_id, sums in iteritems(currency_tree):
                        adj_balance = sums.get('unrealized_gain_loss', 0.0)
                        if not adj_balance:
                            continue

                        rate = sums.get('currency_rate', 0.0)
                        label = self._format_label(form.label, account_id, currency_id, rate)

                        # Write an entry to adjust balance
                        new_ids = self._write_adjust_balance(
                            account_id,
                            currency_id,
                            partner_id,
                            adj_balance,
                            label,
                            form,
                            sums)
                        created_ids.extend(new_ids)

        if created_ids:
            move_ids = []
            rev_ids = []
            for move in created_ids:
                move_id = self.env['account.move'].create(move).id
                move_ids.append(move_id)
            if len(move_ids) > 0:
                for move_id in move_ids:
                    rev_ids = move_obj.browse(move_id).reverse_moves(form.atstatymo_data, form.journal_id or False)
                    for move in move_obj.browse(move_id):
                        sudengiami = {}
                        eil_nr = 0
                        for line in move.line_ids:
                            eil_nr += 1
                            if line.partner_id and line.account_id.reconcile:
                                if line.id not in sudengiami.keys():
                                    sudengiami[line.id] = {'partneris': line.partner_id.id,
                                                           'debit': line.debit,
                                                           'credit': line.credit,
                                                           'eil_nr': eil_nr}
                        eil_nr2 = 0
                        for line in self.env['account.move'].browse(rev_ids).line_ids:
                            eil_nr2 += 1
                            if line.partner_id and line.account_id.reconcile:
                                for k, v in iteritems(sudengiami):
                                    if v['partneris'] == line.partner_id.id:
                                        suma1 = abs(v['debit']) + abs(v['credit'])
                                        suma2 = abs(line.debit) + abs(line.credit)
                                        if suma1 == suma2 and v['eil_nr'] == eil_nr2:
                                            account_move_line_obj.reconcile([line.id, k])
            return {'domain': [('id', 'in', move_ids + rev_ids)],
                    'name': _("Perkainavimo eilutės"),
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'auto_search': True,
                    'res_model': 'account.move',
                    'view_id': False,
                    'search_view_id': False,
                    'type': 'ir.actions.act_window'}
        else:
            raise exceptions.Warning(_("Nebuvo padaryta jokių įrašų."))
