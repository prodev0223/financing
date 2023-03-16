# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, _, tools, exceptions
from odoo.tools import float_compare


class AccountMoveLineReconcileDifferentWizard(models.TransientModel):
    _name = 'account.move.line.reconcile.different.wizard'

    def _default_ref(self):
        return _('Užskaita')

    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True, lt_string='Žurnalas')
    ref = fields.Char(string='Sudengimo elementų nuoroda', default=_default_ref, required=True)
    reconciliation_date = fields.Date(string='Sudengimo data', required=True)
    lines_to_reconcile = fields.Many2many('account.move.line', relation='rel_tab_reconcil_wizard_move_lines',
                                          string='Sudengiamos eilutės')
    multiple_partners = fields.Boolean(string='Keli partneriai', compute='_multiple_partners')
    writeoff_journal_id = fields.Many2one('account.journal', string='Nurašymo žurnalas')
    writeoff_account_id = fields.Many2one('account.account', string='Nurašymo saskaita')

    #FIXME: This could probably use a rewrite to update functionality, and make it more uniform depending on cases.
    @api.depends('lines_to_reconcile.partner_id')
    def _multiple_partners(self):
        self.multiple_partners = len(set(self.lines_to_reconcile.mapped('partner_id'))) > 1

    @api.model
    def default_get(self, fields_list):
        res = super(AccountMoveLineReconcileDifferentWizard, self).default_get(fields_list)
        lines_to_reconcile = self.env['account.move.line'].browse(self._context.get('active_ids', []))

        if 'lines_to_reconcile' in fields_list:
            if lines_to_reconcile:
                res.update({'lines_to_reconcile': [(6, 0, lines_to_reconcile.ids)]})

        if 'reconciliation_date' in fields_list:
            date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if lines_to_reconcile:
                dates = lines_to_reconcile.mapped('date')
                if dates:
                    date = max(dates)
            res.update({'reconciliation_date': date})

        if 'journal_id' in fields_list:
            journal_id = self.env['account.journal'].search([('code', '=', 'KITA')], limit=1)
            res.update({'journal_id': journal_id.id})

        return res

    @api.multi
    def create_reconciliation(self):
        #  Constraints are also checked when calling the wizard
        debit_lines, credit_lines, single_partner, single_debit_account, single_credit_account =\
            self.env['account.move.line'].check_offsetting_wizard_lines(self.lines_to_reconcile)

        if single_partner and not(single_credit_account and single_debit_account):
            return self._create_reconciliation_multiple_accounts()

        comp_currency = self.env.user.sudo().company_id.currency_id
        currency = set(line.currency_id.id if line.currency_id else comp_currency.id for line in self.lines_to_reconcile)
        amount_debit = sum(debit_lines.mapped('amount_residual'))
        amount_credit = abs(sum(credit_lines.mapped('amount_residual')))
        amount = min(amount_credit, amount_debit)
        amount_currency_debit = sum(debit_lines.mapped('amount_residual_currency')) if comp_currency.id not in currency else 0
        amount_currency_credit = -sum(credit_lines.mapped('amount_residual_currency')) if comp_currency.id not in currency else 0
        amount_currency = min(amount_currency_credit, amount_currency_debit)

        line_1_vals = {
            'account_id': credit_lines.mapped('account_id').id,
            'partner_id': credit_lines.mapped('partner_id').id,
            'currency_id': False if comp_currency.id in currency else list(currency)[0],
            'ref': _('Užskaita'),
            'name': credit_lines.name if len(credit_lines) == 1 else _('Kredito eilutės'),
            'debit': amount,
        }

        line_2_vals = {
            'account_id': debit_lines.mapped('account_id').id,
            'partner_id': debit_lines.mapped('partner_id').id,
            'currency_id':  False if comp_currency.id in currency else list(currency)[0],
            'ref': _('Užskaita'),
            'name': debit_lines.name if len(debit_lines) == 1 else _('Debeto eilutės'),
            'credit': amount,
        }

        if amount_currency:
            line_1_vals.update({'amount_currency': amount_currency})
            line_2_vals.update({'amount_currency': -amount_currency})

        move_vals = {
            'journal_id': self.journal_id.id,
            'line_ids': [(0, 0, line_1_vals), (0, 0, line_2_vals)],
            'name': self.ref,
            'date': self.reconciliation_date,
        }

        extra_move = self.env['account.move'].create(move_vals)
        extra_move.offsetting_front_move = self._context.get('offsetting_front_move', False)
        extra_move.post()
        new_line_ids = extra_move.line_ids
        assert len(new_line_ids) == 2

        new_line_1 = new_line_ids.filtered(lambda l: l.partner_id.id == line_1_vals['partner_id'] and
                                                     l.account_id.id == line_1_vals['account_id'])
        new_line_2 = new_line_ids.filtered(lambda l: l.partner_id.id == line_2_vals['partner_id'] and
                                                     l.account_id.id == line_2_vals['account_id'])

        if len(new_line_1) != 1 or len(new_line_2) != 1:
            raise exceptions.UserError(
                _('Nepavyko atlikti sudengimo operacijos. Kreipkitės į sistemos administratorių'))

        self.env['account.move.line'].browse((credit_lines | new_line_1).ids).auto_reconcile_lines()
        self.env['account.move.line'].browse((debit_lines | new_line_2).ids).auto_reconcile_lines()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_move_form').id,
            'target': 'current',
            'res_id': extra_move.id,
        }

    @api.multi
    def _create_reconciliation_multiple_accounts(self):
        # TODO: maybe pass lines as parameters
        lines_to_reconcile = self.lines_to_reconcile
        comp_currency = self.env.user.sudo().company_id.currency_id
        currency = set(line.currency_id.id if line.currency_id else comp_currency.id for line in lines_to_reconcile)
        if len(currency) > 1:
            raise exceptions.UserError(_('Elementai turi turėti tą pačią valiutą'))

        # For mutiple account reconciliation, we only allow currency in company currency
        if len(lines_to_reconcile) > 2 and comp_currency.id not in currency:
            raise exceptions.UserError(_('Negalite sudengti daugiau nei dviejų įrašų, jei valiuta nėra %s')
                                       % comp_currency.name)
        rounding = comp_currency.rounding
        credit_lines = lines_to_reconcile.filtered(lambda l:float_compare(l.amount_residual, 0.0, precision_rounding=rounding) < 0)
        debit_lines = lines_to_reconcile.filtered(lambda l:float_compare(l.amount_residual, 0.0, precision_rounding=rounding) > 0)
        credit = - sum(credit_lines.mapped('amount_residual'))
        debit = sum(debit_lines.mapped('amount_residual'))

        writeoff = True if float_compare(debit, credit, precision_rounding=rounding) else False
        writeoff_amount = debit - credit
        if writeoff:
            if not self.writeoff_account_id:
                raise exceptions.UserError(_('Nenurodyta nurašymo saiskaita'))

        account_ids = set((credit_lines + debit_lines).mapped('account_id').ids)
        partner_id = self.lines_to_reconcile.mapped('partner_id').id
        data_by_account = {}
        dest_account_id = False
        max_lines = 0
        for account_id in account_ids:
            acc_credit_lines = credit_lines.filtered(lambda l: l.account_id.id == account_id)
            acc_debit_lines = debit_lines.filtered(lambda l: l.account_id.id == account_id)
            credit_amt = - sum(acc_credit_lines.mapped('amount_residual'))
            debit_amt = sum(acc_debit_lines.mapped('amount_residual'))
            n_lines = len(acc_credit_lines) + len(acc_debit_lines)
            if n_lines > max_lines:
                max_lines = n_lines
                dest_account_id = account_id
            data_by_account.update({account_id: {'number_of_lines': n_lines,
                                                 'debit': debit_amt,
                                                 'credit': credit_amt,
                                                 'lines': acc_credit_lines + acc_debit_lines}})
        line_vals = []
        for account_id in account_ids:
            if account_id == dest_account_id:
                continue
            debit, credit = data_by_account.get(account_id).get('debit'), data_by_account.get(account_id).get('credit')
            if not debit and not credit:
                continue
            lines = data_by_account.get(account_id).get('lines')
            amount = debit - credit
            if not tools.float_is_zero(amount, precision_rounding=rounding):
                line_vals.append({
                    'account_id': dest_account_id,
                    'partner_id': partner_id,
                    'ref': self.ref or _('Užskaita'),
                    'name': lines.name if len(lines) == 1 else _('Užskaitos eilutės (saskaita %s)') % lines.mapped('account_id').code, #todo:fix
                    'debit': max(0.0, amount),
                    'credit': max(0.0, - amount),
                })
                line_vals.append({
                    'account_id': account_id,
                    'partner_id': partner_id,
                    'ref': self.ref or _('Užskaita'),
                    'name': credit_lines.name if len(credit_lines) == 1 else _('Užskaita'),
                    'debit': max(0.0, - amount),
                    'credit': max(0.0, amount),
                })

        if writeoff:
            writeoff_line_vals = [{
                'account_id': dest_account_id,
                'partner_id': partner_id,
                'ref': self.ref or _('Užskaita'),
                'name': _('Užskaitos nurašymas'),
                'debit': max(0.0, - writeoff_amount),
                'credit': max(0.0, writeoff_amount),
            }, {
                'account_id': self.writeoff_account_id.id,
                'partner_id': partner_id,
                'ref': self.ref or _('Užskaita'),
                'name': _('Užskaitos nurašymas'),
                'debit': max(0.0, writeoff_amount),
                'credit': max(0.0, - writeoff_amount),
            }]

            writeoff_move = self.env['account.move'].create({
                'journal_id': self.writeoff_journal_id.id if self.writeoff_journal_id else self.journal_id.id,
                'line_ids': [(0, 0, vals) for vals in writeoff_line_vals],
                'name': self.ref + _(' (Nurašymas)'),
                'date': self.reconciliation_date,
            })

            writeoff_move.post()

        move_vals = {
            'journal_id': self.journal_id.id,
            'line_ids': [(0, 0, vals) for vals in line_vals],
            'name': self.ref,
            'date': self.reconciliation_date,
        }

        extra_move = self.env['account.move'].create(move_vals)
        extra_move.post()
        new_line_ids = extra_move.line_ids
        for account_id in account_ids:
            lines = data_by_account[account_id]['lines'] + new_line_ids.filtered(lambda l: l.account_id.id == account_id)
            if writeoff and account_id == dest_account_id:
                lines += writeoff_move.line_ids.filtered(lambda l: l.account_id.id == account_id)
            lines.auto_reconcile_lines()
        if writeoff:
            action = self.env.ref('account.action_move_journal_line').read()[0]
            action['domain'] = [('id', 'in', (extra_move + writeoff_move).ids)]
            return action
        else:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_type': 'form',
                'view_mode': 'form',
                'view_id': self.env.ref('account.view_move_form').id,
                'target': 'current',
                'res_id': extra_move.id,
            }
