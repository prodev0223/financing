# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, exceptions, tools
from datetime import datetime
from dateutil.relativedelta import relativedelta
from calendar import monthrange


class AccountFullReconcile(models.Model):

    _inherit = 'account.full.reconcile'

    @api.multi
    def unlink(self):
        aml_obj = self.env['account.move.line']
        exchange_move_ids = tuple(self.mapped('exchange_move_id.id'))
        res = super(AccountFullReconcile, self).unlink()
        if not exchange_move_ids:
            return res
        self._cr.execute('SELECT id FROM account_move WHERE id IN %s', (tuple(exchange_move_ids),))
        data = self._cr.fetchall()
        exchange_move_ids = [c[0] for c in data]
        for account_move_id in exchange_move_ids:
            account_move = self.env['account.move'].browse(account_move_id)
            related_line_ids = []
            for aml in account_move.line_ids:
                if aml.account_id.reconcile:
                    related_line_ids.extend(
                        [r.debit_move_id.id for r in aml.matched_debit_ids] if aml.credit > 0 else
                        [r.credit_move_id.id for r in aml.matched_credit_ids])
                    # FIXME: should we use float_compare to check aml.credit?             ^
            related_line_ids = list(set(related_line_ids))
            related_lines = aml_obj.browse(related_line_ids)
            related_move = related_lines.mapped('move_id')
            if len(related_move) == 1:
                unlink_records = True
                for aml in related_move.line_ids:
                    if aml.account_id.reconcile:
                        rel_lines = [r.debit_move_id for r in aml.matched_debit_ids] if aml.credit > 0 else [r.credit_move_id for r in aml.matched_credit_ids]
                        # FIXME: should we use float_compare to check aml.credit ?                 ^
                        if any(l.move_id != account_move for l in rel_lines):
                            unlink_records = False
                moves = account_move | related_move
                value_by_account = {}
                for aml in moves.mapped('line_ids'):
                    if aml.account_id.id not in value_by_account:
                        value_by_account[aml.account_id.id] = 0
                    value_by_account[aml.account_id.id] += aml.debit - aml.credit
                for acc_id in value_by_account:
                    if not tools.float_is_zero(value_by_account[acc_id], precision_rounding=account_move.company_id.currency_id.rounding):
                        unlink_records = False
                if unlink_records:
                    moves = account_move | related_move
                    moves.mapped('line_ids').remove_move_reconcile()
                    moves.button_cancel()
                    moves.unlink()
        return res


AccountFullReconcile()


class AccountInvoiceDeferredLine(models.Model):

    _name = 'account.invoice.deferred.line'

    invoice_id = fields.Many2one('account.invoice', compute='_invoice_id', store=True)
    invoice_line_id = fields.Many2one('account.invoice.line', string='Description', required=True, readonly=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Deferred account',
                                 domain="[('is_view', '=', False),('deprecated','=',False)]")
    date_from = fields.Date(string='Date from', required=True, help='Pirmo mokėjimo data')
    number_periods = fields.Integer(string='Number of months')
    use_first_day = fields.Boolean(string='Naudoti pirmąją dieną', default=True, lt_string='Naudoti pirmąją dieną',
                                   help='Pažymėjus visi kiti įrašai bus sukurti pirmąją mėnesio dieną')
    related_moves = fields.One2many('account.move', 'deferred_line_id')

    @api.multi
    @api.depends('invoice_line_id')
    def _invoice_id(self):
        for rec in self:
            rec.invoice_id = rec.invoice_line_id.invoice_id.id

    @api.multi
    @api.constrains('number_periods')
    def constrain_number_periods(self):
        for rec in self:
            if rec.number_periods <= 0:
                raise exceptions.ValidationError(_('Periodų skaičius turi būti teigiamas'))

    @api.multi
    def create_accounting_moves(self):
        self.ensure_one()
        if not self.account_id:
            raise exceptions.UserError(_('Nenustatyta atidėta sąskaita'))
        if not self.date_from:
            raise exceptions.UserError(_('Nenustatyta atidėtos eilutės pradžios data'))
        if self.number_periods <= 0:
            raise exceptions.UserError(_('Periodų skaičius turi būti didesnis už nulį'))

        currency = self.invoice_id.company_id.currency_id
        amount_to_distribute = self.invoice_id.currency_id.with_context(
            date=self.invoice_id.operacijos_data or self.invoice_id.date_invoice or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)).compute(
            self.invoice_line_id.price_subtotal, currency)
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        move_lines = []
        n = self.number_periods
        credit_account_id = self.invoice_line_id.account_id.id if self.invoice_id.type in ['in_invoice', 'out_refund'] \
            else self.account_id.id
        debit_account_id = self.account_id.id if self.invoice_id.type in ['in_invoice', 'out_refund'] \
            else self.invoice_line_id.account_id.id

        if self.use_first_day:
            amount_period = currency.round(float(amount_to_distribute)/n)
            first_month_day = date_from.day
            num_month_days = monthrange(date_from.year, date_from.month)[1]
            amount_first = currency.round((1 - float(first_month_day - 1) / float(num_month_days)) * amount_period)
            amount_left = amount_to_distribute
            num_months = n + 1 if amount_left - (n - 1) * amount_period > 0 else n
            name_first = self.invoice_id.number + _(' (%s iš %s)') % (1, num_months)
            self.create_and_post_accounting_move(name_first, self.date_from, amount_first, debit_account_id,
                                                 credit_account_id)
            amount_left -= amount_first
            for i in range(1, n):
                date = date_from + relativedelta(months=i, day=1)
                amount = amount_period
                if tools.float_compare(abs(amount), abs(amount_left), precision_rounding=currency.rounding) > 0:
                    amount = currency.round(amount_left)
                amount_left -= amount
                name = self.invoice_id.number + _(' (%s iš %s)') % (i + 1, num_months)
                self.create_and_post_accounting_move(name, date, amount, debit_account_id, credit_account_id)
            amt_to_distr_cmp_zero = tools.float_compare(amount_to_distribute, 0, precision_rounding=currency.rounding)
            amt_left_cmp_zero = tools.float_compare(amount_left, 0, precision_rounding=currency.rounding)
            if amt_to_distr_cmp_zero * amt_left_cmp_zero < 0:
                raise exceptions.UserError(_('Per didelis paskirstymas per periodus, susisiekite su administracija'))
            if tools.float_compare(amount_left, 0, precision_digits=2) != 0:  #FIXME: why precision not currency_rounding?
                date = date_from + relativedelta(months=n, day=1)
                amount_last = currency.round(amount_left)
                name = self.invoice_id.number + _(' (%s iš %s)') % (num_months, num_months)
                self.create_and_post_accounting_move(name, date, amount_last, debit_account_id, credit_account_id)
        else:
            for i in range(self.number_periods):
                date = date_from + relativedelta(months=i)
                amount = currency.round(amount_to_distribute / (n - i))
                amount_to_distribute -= amount
                name = self.invoice_id.number + _(' (%s iš %s)') % (i + 1, self.number_periods)
                self.create_and_post_accounting_move(name, date, amount, debit_account_id, credit_account_id)
        return move_lines

    @api.multi
    def create_and_post_accounting_move(self, name, date, amount, debit_account_id, credit_account_id):
        """
        Create and post account move of deferred invoice line
        :param name: new move name
        :param date: new move date
        :param amount: new move amount
        :param debit_account_id: move line debit account ID
        :param credit_account_id: move line credit account ID
        :return: None
        """
        self.ensure_one()
        is_positive_amount = tools.float_compare(amount, 0.0, precision_digits=2) > 0
        move_line_base = {
            'name': name,
            'ref': _('Išskaidyta periodui ') + (self.invoice_line_id.name or '/'),
            'journal_id': self.invoice_id.journal_id.id,
            'partner_id': self.invoice_id.partner_id.id,
            'product_id': self.invoice_line_id.product_id.id,
            'date': date,
            'analytic_account_id': self.invoice_line_id.account_analytic_id.id,
        }

        move_line_1 = move_line_base.copy()
        move_line_1.update({
            'account_id': credit_account_id,
            'debit': 0.0 if is_positive_amount else -amount,
            'credit': amount if is_positive_amount else 0.0
        })

        move_line_2 = move_line_base.copy()
        move_line_2.update({
            'account_id': debit_account_id,
            'credit': 0.0 if is_positive_amount else -amount,
            'debit': amount if is_positive_amount else 0.0
        })

        move_vals = {
            'name': name,
            'ref': _('Išskaidyta periodui ') + (self.invoice_line_id.name or '/'),
            'date': date,
            'journal_id': self.invoice_id.journal_id.id,
            'line_ids': [(0, 0, move_line_1), (0, 0, move_line_2)],
            'deferred_line_id': self.id,
        }
        move = self.env['account.move'].create(move_vals)
        move.post()


AccountInvoiceDeferredLine()


class AccountInvoice(models.Model):

    _inherit = 'account.invoice'

    deferred_line_ids = fields.One2many('account.invoice.deferred.line', 'invoice_id', sequence=100)
    deferred = fields.Boolean(compute='_deferred')
    num_account_entries = fields.Integer(compute='_num_account_entries', string='Accounting entries', sequence=100)
    show_related_sales = fields.Boolean(compute='_show_related_sales')
    sale_ids = fields.Many2many('sale.order', 'account_invoice_sale_order_rel', 'invoice_id', 'order_id',
                                string='Sale Order', compute='_sale_ids_compute', store=True, sequence=100,
                                )

    @api.depends('invoice_line_ids.sale_line_ids')
    def _sale_ids_compute(self):
        for rec in self:
            inv_lines = rec.invoice_line_ids
            sale_ids = set()
            for inv_line in inv_lines:
                for sale_line in inv_line.sale_line_ids:
                    sale_id = sale_line.order_id.id
                    sale_ids.add(sale_id)
            rec.sale_ids = [(6, 0, list(sale_ids))]

    @api.one
    def _show_related_sales(self):
        if self.sale_ids:
            self.show_related_sales = True
        else:
            self.show_related_sales = False

    @api.multi
    def show_related_sale_orders(self):
        return {
            'name': _('Sale Orders'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'sale.order',
            'view_id': False,
            'domain': [('id', 'in', self.sale_ids.mapped('id'))]
        }

    @api.one
    def _num_account_entries(self):
        if not self.number:
            self.num_account_entries = 0
        else:
            if self.expense_move_id:
                self.num_account_entries = self.env['account.move.line'].sudo().search_count(
                    ['|', '|', ('move_id.deferred_line_id.invoice_id', '=', self.id),
                     ('move_id', '=', self.move_id.id), ('move_id', '=', self.expense_move_id.id)])
            else:
                self.num_account_entries = self.env['account.move.line'].sudo().search_count(
                    ['|', ('move_id.deferred_line_id.invoice_id', '=', self.id),
                     ('move_id', '=', self.move_id.id)])
            if self.distributed_move_id:
                self.num_account_entries += self.env['account.move.line'].sudo().search_count(
                    [('move_id', '=', self.distributed_move_id.id)])

    @api.one
    @api.depends('invoice_line_ids.deferred')
    def _deferred(self):
        if any(self.invoice_line_ids.mapped('deferred')):
            self.deferred = True
        else:
            self.deferred = False

    @api.multi
    def show_related_accounting_entries(self):
        if not self.number:
            return {
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'account.move.line',
                'view_id': False,
            }
        else:
            if self.expense_move_id:
                domain = ['|', '|', ('move_id', '=', self.move_id.id),
                               ('move_id.deferred_line_id.invoice_id', '=', self.id),
                               ('move_id', '=', self.expense_move_id.id)]
            else:
                domain = ['|', ('move_id', '=', self.move_id.id),
                          ('move_id.deferred_line_id.invoice_id', '=', self.id)]
            if self.distributed_move_id:
                domain = ['|'] + domain + [('move_id', '=', self.distributed_move_id.id)]
            return {
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'account.move.line',
                'name': _('Related accounting entries'),
                'view_id': False,
                'domain': domain,
            }

    @api.multi
    def action_cancel(self):
        for inv in self:
            for line in inv.sudo().deferred_line_ids:
                moves = line.related_moves
                moves.button_cancel()
                moves.unlink()
        return super(AccountInvoice, self).action_cancel()

    @api.multi
    def invoice_validate(self):
        res = super(AccountInvoice, self).invoice_validate()
        for inv in self:
            for inv_line in inv.invoice_line_ids:
                if inv_line.deferred:
                    deferred_lines = self.env['account.invoice.deferred.line'].sudo().search([('invoice_line_id', '=', inv_line.id)])
                    if len(deferred_lines) == 0:
                        raise exceptions.Warning(_('Klaida. Kreipkitės į buhalterį.'))
                    if len(deferred_lines) > 1:
                        raise exceptions.Warning(_('Klaida. Kreipkitės į buhalterį.'))
                    deferred_lines.create_accounting_moves()
        return res


AccountInvoice()


class AccountInvoiceLine(models.Model):

    _inherit = 'account.invoice.line'

    deferred_line_id = fields.One2many('account.invoice.deferred.line', 'invoice_line_id', help='Intended only one')
    deferred = fields.Boolean(string='Deferred', inverse='_set_deferred_lines')

    @api.multi
    @api.constrains('deferred_line_id')
    def constrain_deferred_lines(self):
        for rec in self:
            if len(rec.deferred_line_id) > 1:
                raise exceptions.ValidationError(_('Klaida. Kreipkitės į buhalterį.'))

    @api.multi
    def _set_deferred_lines(self):
        for rec in self.sudo():
            if not rec.deferred:
                rec.deferred_line_id.unlink()
            elif not rec.deferred_line_id:
                account_code = '492' if rec.invoice_id.type in ['out_invoice', 'out_refund'] else '291'
                inv_line_acc = self.env['account.account'].search([('code', '=', account_code)])
                prev_acc = rec.account_id
                vals = {'invoice_line_id': rec.id,
                        'date_from': rec.invoice_id.date_invoice or
                                     datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                        'account_id': prev_acc.id,
                        'number_periods': 12,
                        }
                self.env['account.invoice.deferred.line'].sudo().create(vals)
                rec.write({'account_id': inv_line_acc.id})


AccountInvoiceLine()


class ProductTemplate(models.Model):

    _inherit = 'product.template'

    account_deferred_income_id = fields.Many2one('account.account', string='Account Deferred Income', sequence=100)
    account_deferred_expense_id = fields.Many2one('account.account', string='Account Deferred Expense', sequence=100)


ProductTemplate()


class ProductCategory(models.Model):

    _inherit = 'product.category'

    account_deferred_income_id = fields.Many2one('account.account', string='Account Deferred Income')
    account_deferred_expense_id = fields.Many2one('account.account', string='Account Deferred Expense')


ProductCategory()


class AccountMove(models.Model):

    _inherit = 'account.move'

    deferred_line_id = fields.Many2one('account.invoice.deferred.line', string='Deferred line')


AccountMove()
