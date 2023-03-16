# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import _, api, exceptions, fields, models, tools


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Hide
    blocked = fields.Boolean(sequence=100)
    tax_exigible = fields.Boolean(sequence=100)
    payment_id = fields.Many2one(sequence=100)
    company_currency_id = fields.Many2one(sequence=100)
    storno = fields.Boolean(sequence=100)
    eksportuota = fields.Boolean(sequence=100)
    reconciled_with_a_klase = fields.Boolean(sequence=100)
    company_id = fields.Many2one(sequence=100)
    gl_balance = fields.Float(sequence=100)
    gl_currency_rate = fields.Float(sequence=100)
    gl_foreign_balance = fields.Float(sequence=100)
    gl_revaluated_balance = fields.Float(sequence=100)

    # Reorder
    date = fields.Date(sequence=0)
    account_id = fields.Many2one(sequence=1)
    product_id = fields.Many2one(sequence=2)
    product_category = fields.Many2one(sequence=3)
    partner_id = fields.Many2one(sequence=4)
    invoice_id = fields.Many2one(sequence=5)
    debit = fields.Monetary(sequence=6)
    credit = fields.Monetary(sequence=7)
    balance = fields.Monetary(sequence=8, lt_string='Suma')
    analytic_account_id = fields.Many2one(sequence=9)
    date_maturity = fields.Date(sequence=10)
    journal_id = fields.Many2one(sequence=11)

    a_klase_kodas_id = fields.Many2one(sequence=70)
    b_klase_kodas_id = fields.Many2one(sequence=71)

    create_date = fields.Datetime(sequence=99)
    create_uid = fields.Many2one('res.users', sequence=99)
    write_date = fields.Datetime(sequence=99)
    write_uid = fields.Many2one('res.users', sequence=99)

    sanity_checks = fields.One2many('account.move.line.sanity.check', 'line_id', string='Apskaitos testai',
                                    groups='base.group_system')
    forced_analytic_default = fields.Boolean(string='Priverstinė analitinė taisyklė')

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        move = None
        if default and 'move_id' in default:
            move = self.env['account.move'].browse(default.get('move_id')).exists()
        if not move:
            move = self.move_id
        if move.state == 'posted':
            raise exceptions.UserError(_('You cannot copy a line on a posted journal entry'))
        return super(AccountMoveLine, self).copy(default)

    @api.model
    def server_action_aml_analytics(self):
        action = self.env.ref('robo.server_action_aml_analytics_act')
        if action:
            action.create_action()

    @api.multi
    def server_action_aml_analytics_wizard(self):
        wiz_id = self.env['account.move.line.analytic.wizard'].create({})
        wiz_id.with_context(active_ids=self._context.get('active_ids'))._tax_line_warning()
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move.line.analytic.wizard',
            'view_id': self.env.ref('robo.aml_analytics_wizard_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': wiz_id.id,
            'context': {'active_ids': self._context.get('active_ids')}
        }

    @api.multi
    def remove_move_reconcile(self):
        # If reconciliation tracking is enabled, collect reconciled line IDs
        reconciled_lines = []
        if not self._context.get('disable_reconciliation_tracking'):
            for rec in self.filtered(lambda x: x.matched_credit_ids or x.matched_debit_ids):
                reconciled_lines.append(rec.id)

        res = super(AccountMoveLine, self.sudo()).remove_move_reconcile()

        # If reconciliation tracking is not disabled, check whether lines that were reconciled previously
        # Were successfully unreconciled, if they were -- post a message to related account move
        if not self._context.get('disable_reconciliation_tracking'):
            user_name = self.env.user.name
            unreconciled_lines = self.env['account.move.line']
            for line in self:
                try:
                    if not line.matched_credit_ids and not line.matched_debit_ids and line.id in reconciled_lines:
                        unreconciled_lines |= line
                except exceptions.MissingError:
                    # If move line is of non company currency, entries that even-out currencies are unlinked
                    # during un-reconciliation, and since this batch is not-yet committed we get the missing error
                    # so we just pass on such line if that is the case
                    pass
            account_moves = unreconciled_lines.mapped('move_id')
            for account_move in account_moves:
                message_to_post = '''Naudotojas "{}" modifikavo šių eilučių sudengimus:\n
                <table border="2" width=100%%>
                    <tr>
                        <td><b>Pavadinimas</b></td>
                        <td><b>Suma</b></td>
                    </tr>'''.format(user_name)
                for line in unreconciled_lines.filtered(lambda x: x.move_id == account_move):
                    message_to_post += '''
                        <tr>
                            <td>{}</td>
                            <td>{}</td>
                        <tr>
                    '''.format(line.name, line.balance)
                message_to_post += '</table>'
                account_move.message_post(body=message_to_post)
        return res

    @api.multi
    def delete_move_reconcile(self):
        self.ensure_one()
        if not self.create_uid.is_accountant() or self.env.user.is_accountant():
            self.remove_move_reconcile()
            self.move_id.write({'state': 'draft'})
            self.move_id.unlink()

    @api.multi
    def delete_move_reconcile_offsetting(self):
        self.ensure_one()
        if self.env.user.is_manager():
            line_ids = self.move_id.line_ids
            line_ids.remove_move_reconcile()
            self.move_id.write({'state': 'draft'})
            self.move_id.unlink()

    # @api.model
    # def fields_get(self, allfields=None, attributes=None):
    #     fields_list = super(AccountMoveLine, self).fields_get(allfields=allfields, attributes=attributes)
    #     if self._context.get('view_type', '') == 'pivot' and not self.env['res.users'].browse(self._uid).is_accountant():
    #         if 'company_currency_id' in fields_list:
    #             fields_list.pop('company_currency_id')
    #         if 'tax_exigible' in fields_list:
    #             fields_list.pop('tax_exigible')
    #         if 'payment_id' in fields_list:
    #             fields_list.pop('payment_id')
    #         if 'storno' in fields_list:
    #             fields_list.pop('storno')
    #     return fields_list

    @api.multi
    def create_analytic_lines(self):
        super(AccountMoveLine, self).create_analytic_lines()
        lock_type = 'freeze' if self.sudo().env.user.company_id.analytic_lock_type in ['freeze'] else 'block'
        for line in self:
            if line.analytic_account_id and not line.analytic_line_ids and lock_type not in ['freeze']:
                raise exceptions.UserError(_('Nepavyko sukurti analitikos įrašų.'))

    @api.one
    def _prepare_analytic_line(self):
        res = super(AccountMoveLine, self)._prepare_analytic_line()
        if type(res) == list:
            res = res[0]
        if 'move_partner_id' not in res:
            if self.partner_id:
                res['move_partner_id'] = self.partner_id.id
            elif self.move_id.partner_id:
                res['move_partner_id'] = self.move_id.partner_id.id
        return res

    def force_reverse_analytics(self, move_lines, used_lines=None):
        """
        Forces analytic accounts on picking move lines
        that are related to a picking being returned.
        Analytic account is taken from the picking move line
        :param move_lines: Lines to match from
        :param used_lines: Lines already matched
        :return: Lines matched
        """

        self.ensure_one()

        used_lines = self.env['account.move.line'] if used_lines is None else used_lines

        line_matched = move_lines.filtered(lambda x: x.product_id.id == self.product_id.id
                                                     and x.debit == self.credit
                                                     and x.credit == self.debit
                                                     and x.account_id.code.startswith('6')
                                                     and x not in used_lines)

        if len(line_matched) == 1:
            self.mapped('analytic_line_ids').unlink()
            self.write({'analytic_account_id': line_matched.analytic_account_id.id})
            self.create_analytic_lines()
            used_lines |= line_matched

        return used_lines

    @api.model
    def get_account_move_line_front_action(self, category=None, date_str=None, is_preliminary=None):
        if not category:
            return
        if date_str:
            dates = date_str.split(' - ')
            if len(dates) != 2:
                raise exceptions.UserError(_('Wrong dates!'))
            date_from = dates[0]
            date_to = dates[1]
        else:
            raise exceptions.UserError(_('Dates not provided!'))

        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        range_date_from = (date_from_dt + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        range_date_to = (date_to_dt + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        AccountAccount = self.env['account.account']
        company = self.env.user.sudo().company_id
        departments = self.env['hr.department'].sudo().search([])
        contracts = self.env['hr.contract'].sudo().search([
            ('date_start', '<=', range_date_to),
            '|',
            ('date_end', '>=', range_date_from),
            ('date_end', '=', False)
        ])

        journal_id = False
        if category == 'VAT':
            account_ids = company.vat_account_ids.ids if is_preliminary == 'true' else company.vat_account_id.ids
            journal_id = company.vat_journal_id.id if is_preliminary != 'true' else False
            group_by = ['account_id']
        elif category == 'SODRA':
            accounts = company.saskaita_sodra | departments.mapped('saskaita_sodra') | \
                       contracts.mapped('sodra_credit_account_id')
            account_ids = accounts.ids
            journal_id = company.salary_journal_id.id
            group_by = ['account_id', 'partner_id']
        elif category == 'GPM':
            accounts = AccountAccount.search([('code', '=', '4487')], limit=1) | company.saskaita_gpm | \
                       departments.mapped('saskaita_gpm') | contracts.mapped('gpm_credit_account_id')
            account_ids = accounts.ids
            journal_id = company.salary_journal_id.id
            group_by = ['account_id', 'partner_id']
        domain = [
            ('date', '>=', range_date_from),
            ('date', '<=', range_date_to),
            ('move_id.state', '=', 'posted'),
            ('account_id', 'in', account_ids)
        ]
        if journal_id:
            domain += [('journal_id', '=', journal_id)]
        ctx = {'col_group_by': ['date:month'], 'pivot_measures': ['balance', 'amount_residual'],
               'group_by': group_by}
        return {
            'context': ctx,
            'name': _('Accounting analysis'),
            'res_model': 'account.move.line',
            'target': 'current',
            'domain': domain,
            'type': 'ir.actions.act_window',
            'view_id': self.env.ref('robo.account_move_line_pivot_view').id,
            'views': [[self.env.ref('robo.account_move_line_pivot_view').id, 'pivot']],
            'view_mode': 'pivot',
        }
