# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import api, fields, models, exceptions, _, tools


class AccountAssetChangeWizard(models.TransientModel):
    _name = 'account.asset.change.wizard'

    def _asset_id(self):
        return self._context.get('asset_id')

    @api.model
    def default_get(self, fields_list):
        res = super(AccountAssetChangeWizard, self).default_get(fields_list=fields_list)
        asset_id = self._context.get('asset_id', False)
        if asset_id:
            asset_id = self.env['account.asset.asset'].browse(asset_id)
            if 'name' in fields_list:
                res['name'] = _(u'Ilgalaikio turto pagerinimas - ') + asset_id.name
            if 'debit_account_id' in fields_list:
                res['debit_account_id'] = asset_id.category_id.account_asset_id.id
            if 'tax_ids' in fields_list:
                tax_ids = self.env['account.tax'].search([('code', '=', 'PVM9'), ('type_tax_use', '=', 'sale')])
                tax_id = False
                for t_id in tax_ids:
                    if '35' in t_id.tag_ids.mapped('code'):
                        tax_id = t_id
                        break
                reverse_tax_id = self.env['account.tax'].search([('code', '=', 'A21'), ('type_tax_use', '=', 'sale')],
                                                                limit=1)
                tids = []
                if tax_id:
                    tids.append(tax_id.id)
                if reverse_tax_id:
                    tids.append(reverse_tax_id.id)
                tids = list(set(tids))
                res['tax_ids'] = tids
            return res
        else:
            return res

    type = fields.Selection([('create', 'Pakeisti vertę'), ('delete', 'Ištrinti paskutinį pagerinimą')],
                            string='Operacija', required=True, default='create')
    asset_id = fields.Many2one('account.asset.asset', string='Ilgalaikis turtas', required=True, default=_asset_id,
                               ondelete='cascade')
    invoice_ids = fields.Many2many('account.invoice', string='Sąskaitos faktūros')
    invoice_line_ids = fields.Many2many('account.invoice.line',
                                        string='Sąskaitos faktūros eilutės')
    change_amount = fields.Float(string='Pagerinimo dydis', compute='_compute_change_amount')
    extra_change_amount = fields.Float(string='Papildomo pagerinimo dydis', default=0.0,
                                       help='Papildomo pagerinimo dydis (ne iš sąskaitų faktūrų)')
    extra_credit_account = fields.Many2many('account.account', string='Papildomo pagerinimo kreditavimo sąskaita')
    date = fields.Date(string='Data')
    method_number = fields.Integer(string='Pratęsti nusidėvėjimą', required=True, default=0)

    debit_account_id = fields.Many2one('account.account', string='Debit account', domain=[('is_view', '=', False)])
    credit_account_id = fields.Many2one('account.account', string='Credit account', domain=[('is_view', '=', False)])
    tax_ids = fields.Many2many('account.tax', string='Taxes',
                               domain="[('code','in',['PVM9','PVM30','PVM31','PVM25','PVM26','PVM27'])]")
    comment = fields.Text(string='Komentaras')

    @api.constrains('extra_change_amount')
    def _check_extra_change_amount(self):
        if any(tools.float_compare(rec.extra_change_amount, 0.0, precision_digits=2) < 0 for rec in self):
            raise exceptions.ValidationError(_('Papildomo pagerinimo dydis negali būti neigiamas'))

    @api.depends('invoice_line_ids')
    def _compute_change_amount(self):
        for rec in self:
            rec.change_amount = sum(rec.invoice_line_ids.mapped('price_subtotal'))

    @api.constrains('method_number')
    def _check_method_number(self):
        if any(rec.method_number < 0 for rec in self):
            raise exceptions.ValidationError(_('Nusidėvėjimų pratęsimo skaičius privalo būti teigiamas'))

    @api.multi
    def create_asset_change(self):
        self.ensure_one()

        if self.asset_id.pirkimo_data > self.date:
            raise exceptions.UserError(_('Negalima pagerinti ilgalaikio turto prieš jo pirkimo datą'))

        depreciation_lines = self.asset_id.depreciation_line_ids
        posted_depreciation_lines = depreciation_lines.filtered(lambda l: l.move_check)
        if posted_depreciation_lines.filtered(lambda l: l.depreciation_date >= self.date):
            raise exceptions.UserError(_('Ilgalaikis turtas šiai datai negali būti pagerintas, nes egzistuoja '
                                         'užregistruoti nusidėvėjimo įrašai. Pirmiausia atšaukite šiuos įrašus.'))

        residual_quantity = self.with_context(date=self.date).asset_id.residual_quantity
        if tools.float_is_zero(residual_quantity, precision_digits=2):
            sale_invoices = self.asset_id.sale_line_ids.filtered(lambda s: s.used_in_calculations).mapped('invoice_id')
            sale_dates = sale_invoices.mapped('date_invoice')
            if sale_dates:
                latest_sale_date = max(sale_dates)
                if latest_sale_date < self.date:
                    raise exceptions.UserError(_('Ilgalaikis turtas negali būti pagerintas, nes šis turtas bus '
                                                 'parduotas prieš šio pagerinimo datą'))

        if self.method_number < 1 and depreciation_lines and max(depreciation_lines.mapped('depreciation_date')) < self.date:
            raise exceptions.UserError(_('Pagerinant ilgalaikį turtą po jo numatomo nudevėjimo pabaigos privaloma '
                                         'nurodyti per kokį periodų skaičių šis pagerinimas turėtų būti nudėvimas'))

        if tools.float_is_zero(self.extra_change_amount + self.change_amount, precision_digits=2):
            raise exceptions.UserError(_('Nenustatyta pagerinimo vertė'))

        if not self.invoice_ids and not self.invoice_line_ids and \
                tools.float_is_zero(self.extra_change_amount, precision_rounding=2):
            raise exceptions.ValidationError(_('Papildomo pagerinimo dydis negali būti lygus nuliui'))

        category = self.asset_id.category_id
        journal_id = category.journal_id.id
        partner_id = self.asset_id.partner_id.id

        account_move_lines = []

        base_move_line_vals = {
            'name': self.asset_id.name,
            'credit': 0.0,
            'debit': 0.0,
            'journal_id': journal_id,
            'partner_id': partner_id,
            'currency_id': False,
            'amount_currency': 0.0,
            'date': self.date,
        }

        for invoice_line in self.invoice_line_ids:
            move_line = base_move_line_vals.copy()
            invoice_partner_id = invoice_line.invoice_id.partner_id.id
            move_line.update({
                'account_id': invoice_line.account_id.id,
                'credit': invoice_line.price_subtotal,
                'partner_id': invoice_partner_id,
            })
            account_move_lines.append((0, 0, move_line))

        if not tools.float_is_zero(self.extra_change_amount, precision_digits=2):
            if not self.extra_credit_account:
                raise exceptions.UserError(_('Nenustatytą kurią sąskaitą papildomai kredituoti'))
            move_line = base_move_line_vals.copy()
            move_line.update({
                'account_id': self.extra_credit_account.id,
                'credit': self.extra_change_amount
            })
            account_move_lines.append((0, 0, move_line))

        debit_acc = category.account_asset_id.id
        if not debit_acc:
            raise exceptions.UserError(_('Ilgalaikio turto kategorijoje nenustatyta ilgalaikio turto sąskaita'))

        move_line = base_move_line_vals.copy()
        move_line.update({
            'account_id': debit_acc,
            'debit': self.extra_change_amount + self.change_amount
        })
        account_move_lines.append((0, 0, move_line))
        move_vals = {
            'ref': self.asset_id.code,
            'date': self.date,
            'journal_id': journal_id,
            'line_ids': account_move_lines,
        }
        reval_move = self.env['account.move'].create(move_vals)
        reval_move.post()
        self.asset_id.write({
            'revaluation_move_ids': [(4, reval_move.id, 0)]
        })

        self.env['account.asset.change.line'].create({
            'asset_id': self.asset_id.id,
            'invoice_line_ids': [(6, 0, self.invoice_line_ids.ids)],
            'change_amount': self.change_amount + self.extra_change_amount,
            'date': self.date,
            'comment': self.comment,
            'method_number': self.method_number,
        })

        self.asset_id.compute_depreciation_board()

    @api.multi
    def delete_last(self):
        self.ensure_one()
        change_lines = self.asset_id.change_line_ids
        if not change_lines:
            raise exceptions.UserError(_('Ilgalaikio turto vertė nebuvo pakeista'))
        else:
            last_line = change_lines.sorted(key=lambda r: r.date, reverse=True)[0]
            if self.asset_id.depreciation_line_ids.filtered(
                    lambda r: r.move_check and r.depreciation_date >= last_line.date):
                raise exceptions.UserError(_('Negalima ištrinti, nes sukurti vėlesni nudėvėjimai'))
            revaluation_moves = last_line.asset_id.revaluation_move_ids.filtered(
                lambda m: m.date == last_line.date and
                          tools.float_compare(m.amount, last_line.change_amount, precision_digits=2) == 0 and
                          all(l.partner_id.id in last_line.mapped('invoice_ids.partner_id.id') for l in m.line_ids)
            )
            for revaluation_move in revaluation_moves.filtered(lambda m: m.state == 'posted'):
                revaluation_move.button_cancel()
            revaluation_moves.unlink()
            last_line.unlink()
            self.asset_id.compute_depreciation_board()

    @api.multi
    def confirm(self):
        self.ensure_one()
        use_sudo = self.env.user.has_group('ilgalaikis_turtas.group_asset_manager')
        if use_sudo and not self.env.user.has_group('base.group_system'):
            self.asset_id.message_post('Changing the value of asset')
            self = self.sudo()

        if self.type == 'create':
            self.create_asset_change()
        else:
            self.delete_last()


AccountAssetChangeWizard()
