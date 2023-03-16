# -*- encoding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools


class AccountTax(models.Model):
    _inherit = 'account.tax'

    def default_group(self):
        return self.env.ref('account.tax_group_taxes')

    child_tax_ids = fields.Many2many('account.tax', 'account_children_mapping', 'parent_id', 'child_id',
                                     string='Children taxes')
    tax_group_id = fields.Many2one('account.tax.group', default=default_group, readonly=True)
    nondeductible = fields.Boolean(string='Non-deductible tax', compute='_nondeductible', store=True)
    nondeductible_profit = fields.Boolean(string='Non-deductible for profit tax', compute='_nondeductible_profit',
                                          store=True)
    non_vat_object = fields.Boolean(string='Ne PVM objektas', default=False)
    code = fields.Char(string='Code', required=True)
    description = fields.Char(translate=True)
    long_description = fields.Char(string='Description', translate=True)
    show_description = fields.Boolean(string='Show description on Invoices', default=False)

    @api.one
    @api.depends('account_id.user_type_id')
    def _nondeductible(self):
        user_type_id = self.env.ref('account.data_account_type_expenses').id
        if self.account_id and self.account_id.user_type_id and self.account_id.user_type_id.id == user_type_id:
            self.nondeductible = True
        else:
            self.nondeductible = False

    @api.one
    @api.depends('account_id')
    def _nondeductible_profit(self):
        if self.account_id and self.account_id.id == self.env.ref('l10n_lt.1_account_485').id:
            self.nondeductible_profit = True
        else:
            self.nondeductible_profit = False

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            if record.code:
                result.append((record.id, "[%s] %s" % (record.code, record.name)))
            else:
                result.append((record.id, "%s" % record.name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        if name:
            recs = self.search([('code', '=ilike', name + "%")] + args, limit=limit)
            if not recs:
                recs = self.search([('name', operator, name)] + args, limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if not self.env.user.sudo().company_id.vat_payer and self._context.get('vat_date_test', False):
            return self
        else:
            return super(AccountTax, self).search(args=args, offset=offset, limit=limit, order=order, count=count)

    @api.multi
    def find_matching_nondeductible(self):
        """
        Finds a matching nondeductible tax. If ignore_exceptions is not passed
        an error is raised if tax already non-deductible or more than one match found.
        :return: the matching nondeductible tax, or an empty RecordSet
        :rtype: RecordSet
        """
        self.ensure_one()
        if self.nondeductible:
            if self._context.get('ignore_exceptions', False):
                return self.env['account.tax']
            raise exceptions.UserError(_('Mokesčiai jau neatskaitomi'))
        new_tax = self.search([('code', '=', self.code),
                               ('price_include', '=', self.price_include),
                               ('type_tax_use', '=', self.type_tax_use),
                               ('nondeductible', '=', True),
                               ('nondeductible_profit', '=', False),])
        if not new_tax and not self._context.get('do_not_raise_if_not_found'):
            raise exceptions.UserError(_('Nepavyko atrasti atitinkamo neatskaitomo PVM mokesčio %s - %s')
                                       % (self.code, self.name))
        if len(new_tax) > 1:
            raise exceptions.UserError(
                _('Buvo atrastas daugiau nei vienas atitinkamas neatskaitomo PVM mokestis %s - %s')
                % (self.code, self.name))
        return new_tax

    @api.multi
    def find_matching_deductible(self):
        """
        Finds a matching deductible tax. If ignore_exceptions is not passed
        an error is raised if tax already deductible or more than one match found.
        :return: the matching nondeductible tax, or an empty RecordSet
        :rtype: RecordSet
        """
        self.ensure_one()
        if not self.nondeductible:
            if self._context.get('ignore_exceptions', False):
                return self.env['account.tax']
            raise exceptions.UserError(_('Mokesčiai jau atskaitomi'))
        new_tax = self.search([('code', '=', self.code),
                               ('price_include', '=', self.price_include),
                               ('type_tax_use', '=', self.type_tax_use),
                               ('nondeductible', '=', False),
                               ('nondeductible_profit', '=', False), ])
        if not new_tax and not self._context.get('do_not_raise_if_not_found'):
            raise exceptions.UserError(_('Nepavyko atrasti atitinkamo neatskaitomo PVM mokesčio %s - %s')
                                       % (self.code, self.name))
        if len(new_tax) > 1:
            raise exceptions.UserError(
                _('Buvo atrastas daugiau nei vienas atitinkamas neatskaitomo PVM mokestis %s - %s')
                % (self.code, self.name))
        return new_tax

    @api.multi
    def find_matching_nondeductible_profit(self):
        """
        Finds a matching non-deductible profit tax. If ignore_exceptions is not passed
        an error is raised if tax already non-deductible profit or more than one match found.
        :return: the matching nondeductible tax, or an empty RecordSet
        :rtype: RecordSet
        """
        self.ensure_one()
        if self.nondeductible_profit:
            if self._context.get('ignore_exceptions', False):
                return self.env['account.tax']
            raise exceptions.UserError(_('Mokesčiai jau neatskaitomi'))
        new_tax = self.search([('code', '=', self.code),
                               ('price_include', '=', self.price_include),
                               ('type_tax_use', '=', self.type_tax_use),
                               ('nondeductible', '=', True),
                               ('nondeductible_profit', '=', True)])
        if not new_tax and not self._context.get('do_not_raise_if_not_found'):
            raise exceptions.UserError(_('Nepavyko atrasti atitinkamo neatskaitomo PVM mokesčio %s - %s')
                                       % (self.code, self.name))
        if len(new_tax) > 1:
            raise exceptions.UserError(
                _('Buvo atrastas daugiau nei vienas atitinkamas neatskaitomo PVM mokestis %s - %s')
                % (self.code, self.name))
        return new_tax

    @api.multi
    def compute_all(self, price_unit, currency=None, quantity=1.0, product=None, partner=None, force_total_price=None):
        """ Returns all information required to apply taxes (in self + their children in case of a tax goup).
            We consider the sequence of the parent for group of taxes.
                Eg. considering letters as taxes and alphabetic order as sequence :
                [G, B([A, D, F]), E, C] will be computed as [A, D, F, C, E, G]

        RETURN: {
            'total_excluded': 0.0,    # Total without taxes
            'total_included': 0.0,    # Total with taxes
            'taxes': [{               # One dict for each tax in self and their children
                'id': int,
                'name': str,
                'amount': float,
                'sequence': int,
                'account_id': int,
                'refund_account_id': int,
                'analytic': boolean,
            }]
        } """
        if len(self) == 0:
            company_id = self.env.user.company_id
        else:
            company_id = self[0].company_id
        if not currency:
            currency = company_id.currency_id
        taxes = []
        # By default, for each tax, tax amount will first be computed
        # and rounded at the 'Account' decimal precision for each
        # PO/SO/invoice line and then these rounded amounts will be
        # summed, leading to the total amount for that tax. But, if the
        # company has tax_calculation_rounding_method = round_globally,
        # we still follow the same method, but we use a much larger
        # precision when we round the tax amount for each line (we use
        # the 'Account' decimal precision + 5), and that way it's like
        # rounding after the sum of the tax amounts of each line.
        # Use forced decimal precision, or take it from currency
        prec = self._context.get('forced_dp') or currency.decimal_places

        # In some cases, it is necessary to force/prevent the rounding of the tax and the total
        # amounts. For example, in SO/PO line, we don't want to round the price unit at the
        # precision of the currency.
        # The context key 'round' allows to force the standard behavior.
        round_tax = False if company_id.tax_calculation_rounding_method == 'round_globally' else True
        if self._context.get('price_include', False):
            round_tax = True
        round_total = True
        if 'round' in self.env.context:
            round_tax = bool(self.env.context['round'])
            round_total = bool(self.env.context['round'])
        base_round_prec = prec
        if not round_tax:
            prec += 5

        base_values = self.env.context.get('base_values')
        if not base_values:
            # If base round precision is higher than 2, do not use forced total price, because it has rounding of 2.
            # We recalculate the totals using price_unit * quantity in case of higher rounding
            if force_total_price and base_round_prec < 3:
                total_excluded = total_included = base = tools.float_round(
                    force_total_price, precision_digits=base_round_prec)
            else:
                total_excluded = total_included = base = tools.float_round(
                    price_unit * quantity, precision_digits=base_round_prec)
        else:
            total_excluded, total_included, base = base_values

        # Sorting key is mandatory in this case. When no key is provided, sorted() will perform a
        # search. However, the search method is overridden in account.tax in order to add a domain
        # depending on the context. This domain might filter out some taxes from self, e.g. in the
        # case of group taxes.
        for tax in self.sorted(key=lambda r: r.sequence):
            if tax.amount_type == 'group':
                children = tax.children_tax_ids.with_context(base_values=(total_excluded, total_included, base))
                ret = children.compute_all(price_unit, currency, quantity, product, partner,
                                           force_total_price=force_total_price)
                total_excluded = ret['total_excluded']
                base = ret['base'] if tax.include_base_amount else base
                total_included = ret['total_included']
                taxes += ret['taxes']
                continue

            tax_amount = tax._compute_amount(base, price_unit, quantity, product, partner)
            if not round_tax:
                tax_amount = tools.float_round(tax_amount, precision_digits=prec)
            else:
                tax_amount = currency.round(tax_amount)

            if tax.price_include:
                total_excluded -= tax_amount
                base -= tax_amount
            else:
                total_included += tax_amount

            # Keep base amount used for the current tax
            tax_base = base

            if tax.include_base_amount:
                base += tax_amount

            taxes.append({
                'id': tax.id,
                'name': tax.with_context(**{'lang': partner.lang} if partner else {}).name,
                'amount': tax_amount,
                'base': tax_base,
                'sequence': tax.sequence,
                'account_id': tax.account_id.id,
                'refund_account_id': tax.refund_account_id.id,
                'analytic': tax.analytic,
            })

        return {
            'taxes': sorted(taxes, key=lambda k: k['sequence']),
            'total_excluded': currency.round(total_excluded) if round_total else total_excluded,
            'total_included': currency.round(total_included) if round_total else total_included,
            'base': base,
        }
