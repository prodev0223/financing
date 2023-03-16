# -*- encoding: utf-8 -*-
from lxml import etree
from odoo import api, models
from odoo.osv.orm import setup_modifiers


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        result = super(AccountInvoice, self).fields_view_get(view_id, view_type, toolbar=toolbar, submenu=submenu)
        doc = etree.XML(result['arch'])
        tree_expenses = view_type == 'tree_expenses_robo' and result['name'] == 'Expenses tree'
        tree_income = view_type == 'tree_robo' and result['name'] == 'Pajamos_tree'
        if tree_expenses or tree_income:
            show_main_analytic = self.env.user.has_group('robo_analytic.group_main_analytic_account_invoice_tree')
            show_analytic_codes = self.env.user.has_group('robo_analytic.group_robo_invoice_tree_analytic_codes')
            show_amount_untaxed = self.env.user.has_group('robo.group_amount_untaxed_invoice_tree')
            if tree_income:
                if show_amount_untaxed and show_analytic_codes and show_main_analytic:
                    self._hide_field(doc, result, 'amount_untaxed_signed')
            if tree_expenses:
                if show_main_analytic and show_analytic_codes:
                    if show_amount_untaxed:
                        self._hide_field(doc, result, 'amount_untaxed_signed')
                    if doc.xpath("//field[@name='amount_total_signed']"):
                        self._hide_field(doc, result, 'amount_total_signed')
                elif show_amount_untaxed and (show_main_analytic or show_analytic_codes):
                    self._hide_field(doc, result, 'amount_total_signed')
        result['arch'] = etree.tostring(doc)
        return result

    @api.model
    def _hide_field(self, doc, result, field_name):
        try:
            node = doc.xpath("//field[@name='{}']".format(field_name))[0]
            node.set('invisible', '1')
            setup_modifiers(node, result['fields']['{}'.format(field_name)], in_tree_view=True)
        except IndexError:
            return
