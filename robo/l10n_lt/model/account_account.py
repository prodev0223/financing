# -*- coding: utf-8 -*-
import sys
from odoo import models, fields, tools, api, _, exceptions
from datetime import datetime
from odoo.tools import float_round
from dateutil.relativedelta import relativedelta
from six import iteritems, itervalues


class AccountAccount(models.Model):
    _inherit = 'account.account'

    use_rounding = fields.Boolean('Apvalinti mokėjimus', default=False)
    structured_code = fields.Char(String='Struktūruotas kodas',
                                  help='struktūruotas kodas, kuris bus naudojamas atliekant eksportą')
    active = fields.Boolean(string='Aktyvus', default=True, inverse='_set_active')
    exclude_from_reports = fields.Boolean(string='Netraukti į skolų suderinimo aktus')
    is_view = fields.Boolean(string='Is view', compute='_is_view', store=True)
    parent_id = fields.Many2one('account.account', string='Computed parent', compute='_parent_id_compute',
                                inverse='_set_parent_id', store=True, help='Parent computed from account code', readonly=False)
    is_direct_parent = fields.Boolean(string='Is a direct parent', compute='_parent_id_compute', store=True, readonly=False)
    hierarchy_level = fields.Integer(string='Hierarchy level', compute='_hierarchy_level_compute', store=True)
    deprecated = fields.Boolean(inverse='_set_deprecated', lt_string='Nebeaktyvi sąskaita')
    code = fields.Char(inverse='_set_code')
    locked = fields.Boolean(string='Locked for non-admins')
    currency_id = fields.Many2one('res.currency', inverse='_set_currency_id')

    @api.multi
    @api.depends('code')
    def _is_view(self):
        accounts = self.env['account.account']
        for rec in self:
            children = accounts.search([('parent_id', '=', rec.id)])
            if children:
                rec.is_view = True
            else:
                rec.is_view = False

    @api.depends('code')
    def _parent_id_compute(self):
        for rec in self:
            rec.compute_account_parent()

    @api.depends('parent_id.hierarchy_level')
    def _hierarchy_level_compute(self):
        """ Return an integer representing hierarchy level code': code example: 120000"""
        for rec in self:
            if not rec.parent_id:
                rec.hierarchy_level = 2
            else:
                rec.hierarchy_level = rec.parent_id.hierarchy_level + 1

    @api.multi
    def _set_active(self):
        for rec in self:
            children = self.env['account.account'].with_context(active_test=False).search(
                [('parent_id', '=', rec.id), ('company_id', '=', rec.company_id.id)])
            children.write({'active': rec.active})

    @api.multi
    def _set_parent_id(self):
        self.mapped('parent_id')._is_view()

    @api.multi
    def _set_deprecated(self):
        for rec in self:
            children = self.env['account.account'].search([('parent_id', '=', rec.id), ('company_id', '=', rec.company_id.id)])
            children.write({'deprecated': rec.deprecated})

    @api.multi
    def _set_code(self):
        self = self.with_context(show_views=True)
        self.mapped('parent_id')._is_view()
        children = self.env['account.account'].with_context(show_views=True).sudo().search(
            [('parent_id', 'in', self.ids + self.mapped('parent_id').ids)])
        children._parent_id_compute()

    @api.multi
    def _set_currency_id(self):
        company_currency = self.env.user.company_id.currency_id
        self.filtered(
            lambda a: a.currency_id and a.currency_id != company_currency and not a.currency_revaluation).write(
            {'currency_revaluation': True}
        )

    # Field is only used in debt report for the moment, the more general
    # name was given because the need to expand this functionality may arise in the future
    @api.multi
    @api.constrains('active')
    def _check_deactivate_no_linked_amls(self):
        for rec in self:
            if not rec.active and self.env['account.move.line'].search_count([('account_id', '=', rec.id)]):
                raise exceptions.ValidationError(
                    _('Negalima deaktyvuoti sąskaitos %s nes ji turi susijusių apskaitos įrašų.') % rec.code)

    @api.multi
    @api.constrains('code')
    def check_project_code_saving(self):
        for rec in self:
            if not rec.code.isdigit() and '--test-enable' not in sys.argv:
                raise exceptions.ValidationError(_('Kodą gali sudaryti tik skaitmenys.'))

    @api.model
    def create(self, vals):
        if '--test-enable' not in sys.argv and 'code' in vals:
            code = vals['code']
            if 'company_id' in vals:
                company_id = vals['company_id']
            else:
                company_id = self.env.user.company_id.id
            parent_status, parent_code = self.is_parent_can_become_view(code, company_id)
            if not parent_status:
                raise exceptions.ValidationError(
                    _("Negalima sukurti '%s' DK sąskaitos, nes tėvinė DK sąskaita (%s) turi žurnalo įrašų.")
                    % (code, parent_code)
                )
        if 'currency_id' in vals:
            company_currency_id = self.env.user.company_id.sudo().currency_id.id
            if vals.get('currency_id') == company_currency_id:
                vals.pop('currency_id')
        self = self.with_context(show_views=True)
        res = super(AccountAccount, self).create(vals)
        if res.parent_id:
            res.parent_id.is_view = True
        accounts_with_parent = self.env['account.account'].sudo().search([('is_direct_parent', '=', False),
                                                                          ('parent_id', '!=', False)])
        for account in accounts_with_parent:
            account.compute_account_parent()
        return res

    @api.multi
    def write(self, vals):
        if 'currency_id' in vals:
            company_currency_id = self.env.user.company_id.sudo().currency_id.id
            if vals.get('currency_id') == company_currency_id:
                vals.update(currency_id=False)
        if any(account.locked for account in self) and not self.env.user.has_group('base.group_system') and \
                not self._context.get('skip_locked_check'):
            raise exceptions.AccessError(_('This account is locked for edition. Please contact your system administrator'))
        return super(AccountAccount, self).write(vals)

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti sąskaitų. Archyvuokite jas.'))
        for rec in self:
            childs = self.env['account.account'].search([('parent_id', '=', rec.parent_id.id)])
            if len(childs) == 1 and rec in childs and rec.parent_id:
                rec.parent_id.is_view = False
        res = super(AccountAccount, self).unlink()

        accounts_without_parent = self.env['account.account'].search([('parent_id', '=', False)])
        for account in accounts_without_parent:
            account.compute_account_parent()
        return res

    @api.model
    def set_chart_of_accounts(self):
        if not self.env.user._is_admin():
            raise exceptions.Warning(_('Only administrator can change these settings'))
        for company in self.env['res.company'].search([]):
            saskaitu_planas = self.env.ref('l10n_lt.lt_chart_template')
            if not company.chart_template_id:
                wizard = self.env['wizard.multi.charts.accounts'].create({
                    'company_id': company.id,
                    'chart_template_id': saskaitu_planas.id,
                    'code_digits': saskaitu_planas.code_digits,
                    'transfer_account_id': saskaitu_planas.transfer_account_id.id,
                    'currency_id': saskaitu_planas.currency_id.id,
                    'bank_account_code_prefix': saskaitu_planas.bank_account_code_prefix,
                    'cash_account_code_prefix': saskaitu_planas.cash_account_code_prefix,
                })
                wizard.onchange_chart_template_id()
                wizard.with_context(show_views=True).execute()
            company.tax_calculation_rounding_method = 'round_globally'
            if not company.bank_account_code_prefix:
                company.bank_account_code_prefix = '271'
            if not company.cash_account_code_prefix:
                company.cash_account_code_prefix = '272'
            company.set_default_accounts()
            company.set_default_taxes()
            company.set_default_vat_accounts()

            # multi currency copy paste
            ir_model = self.env['ir.model.data']
            group_user = ir_model.get_object('base', 'group_user')
            group_product = ir_model.get_object('product', 'group_sale_pricelist')
            group_user.write({'implied_ids': [(4, group_product.id)]})
            sale_journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
            if sale_journal and not self.env['account.move'].search([('journal_id', '=', sale_journal.id)],
                                                                    limit=1):  # yra constraintas, kad negalima keisti kodo, kai jau yra įrašų
                sale_journal.write({'code': _('KL'),
                                    'name': _('Klientų sąskaitos')})
                if sale_journal.sequence_id:
                    sale_journal.sequence_id.write({'implementation': 'no_gap',
                                                    'use_date_range': False,
                                                    'prefix': 'KL'})
            purchase_journal = self.env['account.journal'].search([('type', '=', 'purchase')], limit=1)
            if purchase_journal and not self.env['account.move'].search([('journal_id', '=', purchase_journal.id)],
                                                                        limit=1):
                purchase_journal.write({'code': _('TK'),
                                        'name': _('Tiekėjų sąskaitos')})
            exchange_journal = self.env['account.journal'].search([('type', '=', 'general'),
                                                                   ('sequence', '=', 9)], limit=1)
            if exchange_journal and not self.env['account.move'].search([('journal_id', '=', exchange_journal.id)],
                                                                        limit=1):
                exchange_journal.write({'code': _('VAL'),
                                        'name': _('Valiutų kursai')})
            misc_journal = self.env['account.journal'].search([('type', '=', 'general'),
                                                               ('sequence', '=', 7)], limit=1)
            if misc_journal and not self.env['account.move'].search([('journal_id', '=', misc_journal.id)], limit=1):
                misc_journal.write({'code': _('KITA'),
                                    'name': _('Kitos operacijos')})
            expense_product = self.env['product.product'].search([('default_code', '=', 'EXP')])
            if expense_product:
                expense_product.unlink()
            bank_journal = self.env['account.journal'].search([('type', '=', 'bank'), ('code', '=', 'BNK1')], limit=1)
            if bank_journal:
                bank_journal.write({
                    'bank_statements_source': 'file_import',
                    'display_on_footer': True,
                })

    @api.model
    def create_pvm_record(self, date_from, date_to, company_id, journal_id):
        company = self.env['res.company'].browse(company_id)
        rounding = company.currency_id.rounding
        vat_account_ids = company.vat_account_ids.ids
        vat_target_account_id = company.vat_account_id
        date_maturity = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(months=1, day=25)
        vmi_partner = self.env.ref('l10n_lt_payroll.vmi_partner', raise_if_not_found=False)
        if not vmi_partner:
            vmi_partner = self.env['res.partner'].search([('kodas', '=', '188659752')])
        if date_maturity.weekday() == 5:
            date_maturity -= relativedelta(days=1)
        elif date_maturity.weekday() == 6:
            date_maturity -= relativedelta(days=2)
        while self.env['sistema.iseigines'].search(
                [('date', '=', date_maturity.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
            date_maturity -= relativedelta(days=1)
        account_move_ids = []
        self._cr.execute('''
            SELECT account_move_line.account_id, SUM(account_move_line.debit) AS debit, SUM(account_move_line.credit) AS credit FROM account_move_line
                JOIN account_move ON account_move_line.move_id = account_move.id
                WHERE account_move.state='posted' AND account_move_line.date>=%s AND account_move_line.date <= %s AND account_id in %s
                GROUP BY account_move_line.account_id
            ''', (date_from, date_to, tuple(vat_account_ids)))
        result = self._cr.fetchall()
        values_by_account = {}
        for line in result:
            acc_id, debit, credit = line
            values_by_account[acc_id] = debit - credit
        difference = sum(itervalues(values_by_account))
        account_move_lines = []
        for acc_id, amount in iteritems(values_by_account):
            amount = float_round(amount, precision_rounding=rounding)
            if amount != 0:
                new_line = {'name': '/',
                            'account_id': acc_id,
                            'debit': abs(amount) if amount < 0 else 0.0,
                            'credit': abs(amount) if amount > 0 else 0.0,
                            }
                account_move_lines.append((0, 0, new_line))
        difference = float_round(difference, precision_rounding=rounding)
        if difference != 0:
            new_line = {'name': '/',
                        'account_id': vat_target_account_id.id,
                        'date': date_to,
                        'date_maturity': date_maturity.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                        'debit': abs(difference) if difference > 0 else 0.0,
                        'credit': abs(difference) if difference < 0 else 0.0,
                        'partner_id': vmi_partner.id if vmi_partner else False,
                        }
            account_move_lines.append((0, 0, new_line))
        if account_move_lines:
            account_move_val = {'name': 'PVM %s' % date_to,
                                'date': date_to,
                                'journal_id': journal_id,
                                'line_ids': account_move_lines}
            account_move = self.env['account.move'].create(account_move_val)
            account_move_ids.append(account_move.id)

        import_vat_account_ids = company.import_vat_account_ids.ids
        import_vat_target_account_id = company.import_vat_account_id
        self._cr.execute('''
                SELECT account_move_line.account_id, SUM(account_move_line.debit) AS debit, SUM(account_move_line.credit) AS credit FROM account_move_line
                    JOIN account_move ON account_move_line.move_id = account_move.id
                    WHERE account_move.state='posted' AND account_move_line.date>=%s AND account_move_line.date <= %s AND account_id in %s
                    GROUP BY account_move_line.account_id
                ''', (date_from, date_to, tuple(import_vat_account_ids)))
        result = self._cr.fetchall()
        values_by_account = {}
        for line in result:
            acc_id, debit, credit = line
            values_by_account[acc_id] = debit - credit
        difference = sum(itervalues(values_by_account))
        account_move_lines = []
        for acc_id, amount in iteritems(values_by_account):
            amount = float_round(amount, precision_rounding=rounding)
            if amount != 0:
                new_line = {'name': '/',
                            'account_id': acc_id,
                            'debit': abs(amount) if amount < 0 else 0.0,
                            'credit': abs(amount) if amount > 0 else 0.0,
                            }
                account_move_lines.append((0, 0, new_line))
        difference = float_round(difference, precision_rounding=rounding)
        if difference != 0:
            new_line = {'name': '/',
                        'account_id': import_vat_target_account_id.id,
                        'partner_id': vmi_partner.id if vmi_partner else False,
                        'date': date_to,
                        'debit': abs(difference) if difference > 0 else 0.0,
                        'credit': abs(difference) if difference < 0 else 0.0,
                        }
            account_move_lines.append((0, 0, new_line))
        if account_move_lines:
            account_move_val = {'name': ' Importo PVM %s' % date_to,
                                'date': date_to,
                                'journal_id': journal_id,
                                'line_ids': account_move_lines}
            account_move = self.env['account.move'].create(account_move_val)
            account_move.post()
            account_move_ids.append(account_move.id)
        if account_move_ids:
            return account_move_ids
        else:
            raise exceptions.UserError(_('Nebuvo padaryta jokių įrašų'))

    def compute_account_parent(self):
        self.ensure_one()
        accounts = self.env['account.account']
        parent_code = self.get_parent_code(self.code)
        is_direct_parent = True
        while parent_code:
            account_id = accounts.search([('code', '=', parent_code), ('company_id', '=', self.company_id.id)])
            if len(account_id) > 1:
                raise exceptions.Warning(_('More than one account with the same code. Please contact support.'))
            if account_id:
                self.parent_id = account_id.id
                self.is_direct_parent = is_direct_parent
                return
            parent_code = self.get_parent_code(parent_code)
            is_direct_parent = False

    @api.model
    def recalculate_hierarchy_api_model(self):
        self.recalculate_hierarchy()

    @api.multi
    def recalculate_hierarchy(self):
        accounts = self.env['account.account'].with_context(show_views=True).search([])
        for acc in accounts:
            acc._parent_id_compute()
            acc._hierarchy_level_compute()

    def is_parent_can_become_view(self, code, company_id):
        accounts = self.env['account.account']
        parent_code = self.get_parent_code(code)
        while parent_code:
            account_id = accounts.search([('code', '=', parent_code), ('company_id', '=', company_id)])
            if account_id:
                acc_move_lines = self.env['account.move.line'].search([('account_id', '=', account_id.id)])
                if acc_move_lines:
                    return False, parent_code
                else:
                    return True, parent_code

            parent_code = self.get_parent_code(parent_code)
        return True, parent_code

    def get_parent_code(self, code):
        """ Generate presumptive parent code """
        try:
            parent_code = code[:-1]
            if parent_code[0] == '0':
                return False
            return parent_code
        except:
            return False

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):

        if not args:
            args = []
        args = args[:]
        if name:
            ids = self.search(['|', ('name', operator, name), ('code', '=like', name+'%'), ('is_view', '=', False)] + args,
                              limit=limit)
        else:
            ids = self.search(args, limit=limit)
        return ids.name_get()

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if not self._context.get('show_views', False):
            args = list(args)
            args += [('is_view', '=', False)]
        return super(AccountAccount, self).search(args, offset, limit, order, count=count)

    @api.multi
    def onchange(self, values, field_name, field_onchange):
        self = self.with_context(show_views=True)
        return super(AccountAccount, self).onchange(values, field_name, field_onchange)
