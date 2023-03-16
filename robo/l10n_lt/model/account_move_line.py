# -*- coding: utf-8 -*-
import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, tools, api, _, exceptions
from odoo.tools import float_compare
from six import iteritems


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    product_category = fields.Many2one('product.category', string='Product Category', compute='_product_category',
                                       store=True)
    account_code = fields.Char(string='Sąskaitos kodo pradžia', compute='_compute_account_code', readonly=True,
                               search='_account_code')
    account_id = fields.Many2one(inverse='change_line_account')
    reverse_balance = fields.Float(compute='_reverse_balance', store=True, string='Ataskaitinė suma',
                                   lt_string='Ataskaitinė suma')
    receipt_id = fields.Many2one('cash.receipt', string='Originator Payment', lt_string='Čekis',
                                 help="Receipt that created this entry", copy=False)

    @api.multi
    @api.constrains('amount_currency', 'debit', 'credit', 'currency_id')
    def _constrain_currency_amount_dc(self):
        journal_id = self.sudo().env.user.company_id.default_currency_reval_journal_id
        if self.mapped('move_id.journal_id') == journal_id:
            return  # Skip constrain on currency re-eval journal
        for line in self:
            if line.currency_id and not \
                    tools.float_is_zero(line.amount_currency, precision_rounding=line.currency_id.rounding) and \
                    tools.float_is_zero(line.credit, precision_rounding=line.currency_id.rounding) and \
                    tools.float_is_zero(line.debit, precision_rounding=line.currency_id.rounding):
                ctx = self._context.copy()
                ctx.update({'date': line.date or line.move_id.date})
                company_curr = self.env.user.sudo().company_id.currency_id
                real_time_amount = line.currency_id.with_context(ctx).compute(line.amount_currency, company_curr)
                if not tools.float_is_zero(real_time_amount, precision_rounding=company_curr.rounding):
                    raise exceptions.ValidationError(_('Nurodyta suma valiuta, '
                                                       'tačiau neįvestas nei kreditas nei debetas.'))

    @api.one
    @api.depends('balance', 'account_id.code')
    def _reverse_balance(self):
        if self.balance and (self.account_id.code.startswith('6') or self.account_id.code.startswith('5')):
            self.reverse_balance = self.balance * -1

    @api.one
    def change_line_account(self):
        if self.invoice_id and self.product_id and self.account_id:
            lines = self.invoice_id.invoice_line_ids
            line = lines.filtered(lambda r: r.product_id.id == self.product_id.id and r.quantity == self.quantity)
            if not line or len(line) > 1:
                send = {
                    'body': _('Susijusi sąskaita neatnaujinta, rekomenduojame atnaujinti sąskaitą rankiniu būdu'),
                    'subtype': 'mail.mt_note',
                }
                self.move_id.robo_message_post(**send)
            else:
                line.write({'account_id': self.account_id.id})

    def _compute_account_code(self):
        for rec in self:
            rec.account_code = rec.account_id.code

    def _account_code(self, operator, value):
        if operator != 'ilike':
            raise exceptions.Warning(_('Negalima ieškoti pagal šį operatorių. Ieškokite pagal operatorių \'turi\'.'))
        account_ids = self.env['account.account'].search([('code', '=like', '%s%%' % value)])
        return [('account_id', 'in', account_ids.ids)]

    @api.one
    @api.depends('product_id.categ_id')
    def _product_category(self):
        if self.product_id:
            self.product_category = self.product_id.categ_id.id

    @api.onchange('amount_currency', 'currency_id')
    def _onchange_amount_currency(self):
        if self.date and self.move_id.company_id and self.currency_id:
            amount_company = self.currency_id.with_context(date=self.date).compute(self.amount_currency,
                                                                                   self.move_id.company_id.currency_id)
            if amount_company > 0:
                self.debit = amount_company
                self.credit = 0
            else:
                self.credit = -amount_company
                self.debit = 0

    @api.one
    def set_amount_currency(self):
        if self.move_id.company_id and self.currency_id:
            amount = self.balance
            self.amount_currency =\
                self.move_id.company_id.currency_id.with_context(date=self.date).compute(amount, self.currency_id)

    @api.multi
    def force_partner_change(self):
        action = self.env.ref('l10n_lt.action_partner_change_wizard').read()[0]
        action['context'] = {'line_ids': self.ids}
        return action

    @api.model
    def create_account_move_line_force_partner_action(self):
        action = self.env.ref('l10n_lt.account_move_line_force_partner_action')
        if action:
            action.create_action()

    @api.multi
    def force_account_change(self):
        action = self.env.ref('l10n_lt.action_account_change_wizard').read()[0]
        action['context'] = {'line_ids': self.ids}
        return action

    @api.model
    def create_account_move_line_force_account_action(self):
        action = self.env.ref('l10n_lt.account_move_line_force_account_action')
        if action:
            action.create_action()

    @api.multi
    def get_reconcile_cluster(self):
        # self.ensure_one()
        cluster = self
        additional_layer = cluster
        while True:
            additional_layer = (additional_layer.mapped('matched_credit_ids.credit_move_id')
                                | additional_layer.mapped('matched_debit_ids.debit_move_id'))\
                               - cluster
            if not additional_layer:
                break
            cluster |= additional_layer
        return cluster

    @api.model
    def create(self, vals):
        account = self.env['account.account'].browse(vals['account_id'])
        if account.is_view and '--test-enable' not in sys.argv:  # constraint should not be applied during tests
            raise exceptions.ValidationError(
                _("Negalite naudoti suminės DK sąskaitos (%s).") % account.code)
        if 'debit' in vals:
            vals['debit'] = self.env.user.company_id.currency_id.round(vals.get('debit'))
        if 'credit' in vals:
            vals['credit'] = self.env.user.company_id.currency_id.round(vals.get('credit'))
        move_lines = super(AccountMoveLine, self).create(vals)
        move_lines.create_employee_advance_records()
        return move_lines

    @api.multi
    def create_employee_advance_records(self):
        """
            Creates advance records based on the move line and its payments. Used when an employee has been paid more
            than he should have been paid and the amount over is written off to the advance payment account.
        """

        # When creating a write off from payment to the advance account - we should create an employee advance payment.
        advance_account = self.env.user.company_id.employee_advance_account
        for rec in self.filtered(lambda r: r.payment_id and r.account_id == advance_account and
                                           not tools.float_is_zero(r.amount_residual, precision_digits=2)):
            # Find employee id
            employees = rec.payment_id.partner_id.employee_ids
            employee = employees[0] if employees else False
            if not employee:
                continue

            # Compute dates
            payment_date = rec.payment_id.payment_date
            payment_date_dt = datetime.strptime(payment_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            month_start = (payment_date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            month_end = (payment_date_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            # Find contract
            contract = employee.with_context(date=payment_date).contract_id
            if not contract:
                contracts = employee.contract_ids.filtered(lambda c: c.date_start <= month_end and
                                                                     (not c.date_end or c.date_end >= month_start))
                contract = contracts[0] if contract else False
                if not contract:
                    continue

            if contract.date_end and contract.date_end <= month_end:
                contract_end_dt = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
                next_day_after_contract_ends = (contract_end_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                work_relation_continues = employee.contract_ids.filtered(lambda c:
                                                                         c.date_start == next_day_after_contract_ends)
                if not work_relation_continues:
                    raise exceptions.UserError(_('Darbuotojo darbo santykiai baigiasi tą patį mėnesį. Nurašyti, kaip '
                                                 'avansą negalima.'))

            # Find appointment
            appointment = contract.with_context(date=payment_date).appointment_id
            if not appointment:
                appointments = contract.appointment_ids.filtered(lambda a: a.date_start <= month_end and
                                                                           (not a.date_end or a.date_end >= month_start))
                appointment = appointments[0] if appointments else False
                if not appointment:
                    continue

            # If the employee receives advance payments - we should not create another advance record.
            if appointment.avansu_politika:
                continue

            advance_exists = self.env['darbo.avansas'].search_count([
                ('date_from', '=', month_start),
                ('date_to', '=', month_end),
                ('contract_id', '=', contract.id),
                ('employee_id', '=', employee.id)
            ])
            if advance_exists:
                continue

            # Create advance record
            advance_record = self.env['darbo.avansas'].create({
                'date_from': month_start,
                'date_to': month_end,
                'operation_date': payment_date,
                'contract_id': contract.id,
                'employee_id': contract.employee_id.id,
                'avansu_politika': 'fixed_sum',
                'avansu_politika_suma': abs(rec.amount_residual)
            })
            advance_record.atlikti()

            balancing_move = self.env['account.move'].create({
                'journal_id': advance_record.journal_id.id,
                'company_id': self.env.user.company_id.id,
                'date': payment_date,
                'ref': rec.move_id.ref,
                'name': rec.name,
            })
            aml_vals = {
                'payment_id': rec.payment_id.id,
                'account_id': False,
                'statement_id': rec.statement_id.id,
                'credit': 0.0,
                'date_maturity': payment_date,
                'debit': 0.0,
                'partner_id': rec.payment_id.partner_id.id,
                'move_id': balancing_move.id,
                'name': rec.name
            }
            aml_vals.update({
                'debit': abs(rec.amount_residual),
                'credit': 0.0,
                'account_id': advance_record.saskaita_kreditas.id
            })
            self.with_context(check_move_validity=False, apply_taxes=True).create(aml_vals)
            aml_vals.update({
                'debit': 0.0,
                'credit': abs(rec.amount_residual),
                'account_id': advance_record.saskaita_debetas.id
            })
            credit_move_id = self.with_context(check_move_validity=False, apply_taxes=True).create(aml_vals)
            (rec | credit_move_id).reconcile()
            balancing_move.post()

    @api.multi
    def get_line_vals_to_post(self):
        res = {}
        for line in self:
            res[line.id] = {
                'analytic_account_id': line.analytic_account_id.id,
                'debit_or_credit': 'Debetinė' if line.debit else 'Kreditinė',
                'account_code': line.account_id.code,
            }
        return res

    @api.multi
    def write(self, vals):
        if 'debit' in vals:
            vals['debit'] = self.env.user.company_id.currency_id.round(vals.get('debit'))
        if 'credit' in vals:
            vals['credit'] = self.env.user.company_id.currency_id.round(vals.get('credit'))
        if 'analytic_account_id' in vals:
            prev_line_values = self.get_line_vals_to_post() or {}
            post_message = False
            message = '''<strong>Buvusios reikšmės:\n</strong>
                            <table border="2" width=100%%>
                                <tr>
                                    <td><b>Sąskaita</b></td>
                                    <td><b>Eilutė</b></td>
                                    <td><b>Eilutės tipas</b></td>
                                    <td><b>Analitinė Sąskaita</b></td>
                                </tr>'''
            for rec in self:
                if not prev_line_values.get(rec.id, {}).get('analytic_account_id', False):
                    continue
                post_message = True
                for prev_line_id, prev_line_vals in prev_line_values.items():
                    new_line = rec.filtered(lambda r: r.id == prev_line_id)
                    if len(new_line) > 1:
                        continue
                    new_line = '''<tr>'''
                    new_line += '<td>%s</td>' % prev_line_vals.get('account_code', False)
                    new_line += '<td>%s</td>' % rec.name
                    new_line += '<td>%s</td>' % prev_line_vals.get('debit_or_credit', False)
                    new_line += '<td>%s</td>' % self.env['account.analytic.account'].browse(
                        prev_line_vals.get('analytic_account_id', False)).display_name
                    new_line += '''</tr>'''
                    message += new_line
            message += '</table>'
            if post_message and len(prev_line_values.keys()):
                for rec in self.mapped('move_id'):
                    rec.message_post(body=message, subtype='robo.mt_robo_front_message', front_message=True)
        # Skip move validity checking if only analytic account is written to move line
        if 'analytic_account_id' in vals and len(vals) == 1:
            return super(AccountMoveLine, self.with_context(check_move_validity=False)).write(vals)
        return super(AccountMoveLine, self).write(vals)

    @api.multi
    def unlink(self):
        if self.mapped('matched_debit_ids') | self.mapped('matched_credit_ids'):
            raise exceptions.UserError(_('Negalite ištrinti dalinai sudengtų įrašų. Pirmiau atidenkite.'))
        return super(AccountMoveLine, self).unlink()

    @api.multi
    def reconcile(self, writeoff_acc_id=False, writeoff_journal_id=False):
        if len(self.get_reconcile_cluster().mapped('currency_id') - self.env.user.company_id.currency_id) >= 2:
            raise exceptions.ValidationError(
                _('Negalima sudengti dviejų skirtingų užsienio valiutų įrašų su tuo pačiu mokėjimu.'))
        try:
            return super(AccountMoveLine, self).reconcile(writeoff_acc_id=writeoff_acc_id, writeoff_journal_id=writeoff_journal_id)
        except exceptions.UserError as exc:
            if self.env.user.is_accountant():
                raise exc
            else:
                raise exceptions.UserError(_('Negalima sudengti įrašų.'))

    @api.multi
    def js_call_reconcile_different_wizard(self, data):
        invoice = self.env['account.invoice'].browse(data)
        aml = invoice.move_id.line_ids.filtered(lambda x: x.account_id.id == invoice.account_id.id)
        aml |= self
        self.with_context(active_ids=aml.ids, offsetting_front_move=True).call_reconcile_different_wizard()

    @api.model
    def check_offsetting_wizard_lines(self, lines_to_reconcile):
        comp_currency = self.env.user.sudo().company_id.currency_id
        currency = set([line.currency_id.id if line.currency_id else comp_currency.id for line in lines_to_reconcile])
        if len(currency) > 1:
            raise exceptions.UserError(_('Elementai turi turėti tą pačią valiutą'))

        if len(lines_to_reconcile) > 2 and comp_currency.id not in currency:
            raise exceptions.UserError(_('Negalite sudengti daugiau nei dviejų įrašų, jei valiuta nėra %s')
                                       % comp_currency.name)

        if comp_currency.id in currency:
            credit_lines = lines_to_reconcile.filtered(
                lambda l: float_compare(l.amount_residual, 0.0, precision_rounding=0.0001) < 0)
            debit_lines = lines_to_reconcile.filtered(
                lambda l: float_compare(l.amount_residual, 0.0, precision_rounding=0.0001) > 0)
        else:
            credit_lines = lines_to_reconcile.filtered(
                lambda l: float_compare(l.amount_residual_currency, 0.0, precision_rounding=l.currency_id.rounding) < 0)
            debit_lines = lines_to_reconcile.filtered(
                lambda l: float_compare(l.amount_residual_currency, 0.0, precision_rounding=l.currency_id.rounding) > 0)

        credit_partners = set(line.partner_id for line in credit_lines)
        debit_partners = set(line.partner_id for line in debit_lines)
        single_partner = True if len(credit_partners | debit_partners) == 1 else False
        single_credit_partner = True if len(credit_partners) == 1 else False
        single_debit_partner = True if len(debit_partners) == 1 else False
        single_credit_account = True if len(credit_lines.mapped('account_id')) == 1 else False
        single_debit_account = True if len(debit_lines.mapped('account_id')) == 1 else False

        if not(single_credit_partner and single_debit_partner):
            raise exceptions.UserError(_('Galite turėti tik vieną partnerį kredite ir vieną debete.'))

        if not single_partner and not(single_credit_account and single_debit_account):
            raise exceptions.UserError(_('Galite turėti tik vieną sąskaitą kredite ir vieną debete.'))

        if not credit_lines or not debit_lines:
            raise exceptions.UserError(_('Elementai negali vienu metu būti debetiniai ir kreditiniai'))

        if single_partner and len(lines_to_reconcile.mapped('account_id')) == 1:
            raise exceptions.UserError(
                _('Prašome naudoti numatytąjį Sudengimo įrašų veiksmą kai naudojama ta pati sąskaita ir partneris'))

        body = str()
        for account_id in lines_to_reconcile.mapped('account_id'):
            if not account_id.reconcile:
                body += '{} \n'.format(account_id.display_name or '')
        if body:
            raise exceptions.UserError(_('Šios sąskaitos negali būti sudengiamos:\n' + body))

        return debit_lines, credit_lines, single_partner, single_debit_account, single_credit_account

    @api.multi
    def call_reconcile_different_wizard(self):
        ctx = self._context.copy()

        line_ids = self._context.get('active_ids', False)
        lines_to_reconcile = self.env['account.move.line'].browse(line_ids)
        if len(lines_to_reconcile) <= 1:
            raise exceptions.UserError(_('Privalote pasirinkti bent du įrašus!'))

        self.check_offsetting_wizard_lines(lines_to_reconcile)

        if self._context.get('offsetting_front_move', False):
            wiz_id = self.sudo().env['account.move.line.reconcile.different.wizard'].with_context(ctx).create({})
            wiz_id.create_reconciliation()
        else:
            return {
                'context': ctx,
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'account.move.line.reconcile.different.wizard',
                'type': 'ir.actions.act_window',
                'target': 'new',
            }

    @api.model
    def create_acc_reconcile_different_account(self):
        action = self.env.ref('l10n_lt.journal_entries_reconcile_different_account_action')
        if action:
            action.create_action()

    @api.multi
    def action_line_change_analytics(self):
        self.ensure_one()
        if self.invoice_id:
            raise exceptions.ValidationError(_('The line is related to an invoice (Invoice: {}), change analytics on '
                                               'the invoice instead.').format(self.invoice_id.number))

        if self.move_id.asset_depreciation_ids and self.move_id.asset_depreciation_ids[0].asset_id:
            raise exceptions.ValidationError(
                _('The line is related to an asset (Asset: {}). Change analytic account on the asset instead.').format(
                    self.move_id.asset_depreciation_ids[0].asset_id.name))

        obj = self.env['account.move.line.analytic.wizard']
        vals = {
            'analytic_id': self.analytic_account_id.id,
        }
        wiz_id = obj.create(vals)
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move.line.analytic.wizard',
            'view_id': self.env.ref('robo.aml_change_analytics_wizard_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': wiz_id.id,
            'context': {'active_ids': self.move_id.line_ids.ids}
        }

    @api.multi
    def action_backend_view(self):
        action = self.env.ref('account.action_account_moves_all_a')
        if not action or not self.env.user.is_accountant() or not self:
            return {}
        action = action.read()[0]
        view_type = 'form' if len(self) == 1 else 'tree'
        action.update({
            'view_type': view_type,
            'view_mode': view_type,
        })
        if view_type == 'form':
            form_view_id = self.env.ref('account.view_move_line_form').id
            action['res_id'] = self.id
            action['view_id'] = form_view_id
            action['views'] = [(form_view_id, 'form')]
        else:
            action['domain'] = [('id', 'in', self.ids)]
        return action
