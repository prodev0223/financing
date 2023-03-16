# -*- coding: utf-8 -*-
from odoo import fields, models, exceptions, _, api
from six import iterkeys


class AccountAccountLine(models.Model):

    _inherit = 'account.move.line'

    # By convention added columns stats with gl_.
    gl_foreign_balance = fields.Float('Aggregated Amount curency')
    gl_balance = fields.Float('Aggregated Amount')
    gl_revaluated_balance = fields.Float('Revaluated Amount')
    gl_currency_rate = fields.Float('Currency rate')
    storno = fields.Boolean('STORNO įrašas')


class AccountAccount(models.Model):

    _inherit = 'account.account'

    currency_revaluation = fields.Boolean('Allow Currency revaluation', default=False)

    _sql_mapping = {
            'balance': "COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance",
            'debit': "COALESCE(SUM(l.debit), 0) as debit",
            'credit': "COALESCE(SUM(l.credit), 0) as credit",
            'foreign_balance': "COALESCE(SUM(l.amount_currency), 0) as foreign_balance",
            }

    @api.multi
    def get_grouped_accounts(self, revaluation_date):
        partner_id = self._context.get('partneris', False)
        account_id = self._context.get('saskaita', False)
        all_account_move_line_domain = [('date', '<=', revaluation_date),
                                        ('move_id.state', '=', 'posted'),
                                        ('account_id', 'in', self.ids),
                                        ('currency_id', '!=', False)]
        if partner_id:
            all_account_move_line_domain.append(('partner_id', '=', partner_id))
        if account_id:
            all_account_move_line_domain.append(('account_id', '=', account_id))

        all_account_move_line_ids = self.env['account.move.line'].search(all_account_move_line_domain).ids
        later_reconciled = self.env['account.partial.reconcile'].search(['|',
                                                                         '&',
                                                                         ('credit_move_id', 'in',
                                                                          all_account_move_line_ids),
                                                                         ('debit_move_id.date', '>', revaluation_date),
                                                                         '&',
                                                                         ('debit_move_id', 'in',
                                                                          all_account_move_line_ids),
                                                                         ('credit_move_id.date', '>', revaluation_date),
                                                                         ])
        later_reconciled_move_line_ids = later_reconciled.mapped('credit_move_id.id') + later_reconciled.mapped(
            'debit_move_id.id')
        filtered_move_lines = self.env['account.move.line'].search([('id', 'in', all_account_move_line_ids),
                                                                    '|',
                                                                    ('reconciled', '=', False),
                                                                    ('id', 'in', later_reconciled_move_line_ids)])

        amount_residual_by_id = dict([(aml.id, {
            'amount_residual_currency': aml.amount_residual_currency if aml.account_id.reconcile else aml.amount_currency,
            'amount_residual': aml.amount_residual if aml.account_id.reconcile else aml.balance}) for aml in
                                      filtered_move_lines])
        for apr in later_reconciled:
            amount_currency = apr.amount_currency
            amount = apr.amount
            if apr.credit_move_id.id in amount_residual_by_id:
                amount_residual_by_id[apr.credit_move_id.id]['amount_residual'] -= amount
                amount_residual_by_id[apr.credit_move_id.id]['amount_residual_currency'] -= amount_currency
            if apr.debit_move_id.id in amount_residual_by_id:
                amount_residual_by_id[apr.debit_move_id.id]['amount_residual'] += amount
                amount_residual_by_id[apr.debit_move_id.id]['amount_residual_currency'] += amount_currency

        res = {}
        for aml_id in iterkeys(amount_residual_by_id):
            aml = self.env['account.move.line'].browse(aml_id)
            vals = {'balance': amount_residual_by_id[aml_id]['amount_residual'],
                    'foreign_balance': amount_residual_by_id[aml_id]['amount_residual_currency']}
            account_id = aml.account_id.id
            currency_id = aml.currency_id.id
            partner_id = aml.partner_id.id if aml.account_id.reconcile else False
            res.setdefault(account_id, {})
            res[account_id].setdefault(currency_id, {})
            res[account_id][currency_id].setdefault(partner_id, {})
            dict_to_update = res[account_id][currency_id][partner_id]
            for k in vals:
                if k not in dict_to_update:
                    dict_to_update[k] = vals[k]
                else:
                    dict_to_update[k] += vals[k]
        return res

    @api.multi
    def _revaluation_query(self, revaluation_date):
        partneris = self._context.get('partneris', False)
        saskaita = self._context.get('saskaita', False)

        partnerio_query = ''
        saskaita_query = ''
        if partneris:
            partnerio_query = 'AND l.partner_id = %s' % partneris
        if saskaita:
            saskaita_query = 'AND l.account_id = %s' % saskaita

        date_to = self._context.get('date_to', False)
        date_to = "'" + date_to + "'"
        lines_where_clause = 'l.date <= %s' % (date_to,)
        query = ("SELECT l.account_id as id, l.partner_id, l.currency_id, " +
                   ', '.join(self._sql_mapping.values()) +
                   " FROM account_move_line l, account_move m"
                   " WHERE l.move_id = m.id AND"
                   " m.state = 'posted' AND"
                   " l.account_id IN %(account_ids)s AND "
                   " l.date <= %(revaluation_date)s AND "
                   " l.currency_id IS NOT NULL AND "
                   " l.reconciled IS FALSE AND "
                        + lines_where_clause + partnerio_query + saskaita_query +
                    " GROUP BY l.account_id, l.currency_id, l.partner_id")

        params = {'revaluation_date': revaluation_date,
                  'account_ids': tuple(self._ids)}
        return query, params

    @api.multi
    def compute_revaluations(self, revaluation_date):

        accounts = {}

        #compute for each account the balance/debit/credit from the move lines
        ctx_query = self._context.copy()
        ctx_query['date_to'] = revaluation_date

        query, params = self.with_context(ctx_query)._revaluation_query(revaluation_date)
        self._cr.execute(query, params)

        lines = self._cr.dictfetchall()
        for line in lines:
            # generate a tree
            # - account_id
            # -- currency_id
            # --- partner_id
            # ----- balances
            account_id, currency_id, partner_id = \
                line['id'], line['currency_id'], line['partner_id']

            accounts.setdefault(account_id, {})
            accounts[account_id].setdefault(currency_id, {})
            accounts[account_id][currency_id].\
                setdefault(partner_id, {})
            accounts[account_id][currency_id][partner_id] = line

        return accounts


class AccountMove(models.Model):

    _inherit = 'account.move'

    @api.multi
    def reverse_moves(self, date=None, journal_id=None):
        res = super(AccountMove, self).reverse_moves(date=date, journal_id=journal_id)
        if type(res) not in [int, list]:
            return True
        else:
            moves = self.env['account.move'].browse(res)
            for move in moves:
                move.write({'state': 'draft'})
                for line in move.line_ids:
                    line.write({'storno': False})
            return res


class AccountAccountTemplate(models.Model):

    _inherit = 'account.account.template'

    currency_revaluation = fields.Boolean('Allow Currency revaluation', default=False)

AccountAccountTemplate()


class AccountChartTemplate(models.Model):

    _inherit = 'account.chart.template'

    @api.multi
    def generate_account(self, tax_template_ref, acc_template_ref, code_digits, company):
        self.ensure_one()
        acc_template_ref = super(AccountChartTemplate, self).generate_account(tax_template_ref, acc_template_ref, code_digits, company)
        account_tmpl_obj = self.env['account.account.template']
        for account_template_id in acc_template_ref:
            account_template = account_tmpl_obj.browse(account_template_id)
            new_account = acc_template_ref[account_template_id]
            self.env['account.account'].browse(new_account).currency_revaluation = account_template.currency_revaluation
        return acc_template_ref

AccountChartTemplate()
