# -*- coding: utf-8 -*-
from __future__ import division
from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime
from urlparse import urljoin


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    partner_id = fields.Many2one('res.partner', string='Partner', compute='_partner_id', store=True)
    invoice_id = fields.Many2one('account.invoice', string='Invoice', copy=False)
    stockable_product = fields.Boolean(string='Is Stockable?', compute='_product_type')
    picking_id = fields.Many2one('stock.picking', string='Related picking', groups='account.group_account_user',
                                 copy=False)
    show_pdf = fields.Boolean(string='Show PDF', compute='_pdf')
    pdf = fields.Binary(string='PDF', compute='_pdf')
    show_html = fields.Boolean(string='Show HTML', compute='_pdf')
    html = fields.Text(string='HTML', compute='_pdf', readonly=False)

    @api.one
    @api.depends('expense_line_ids.attachment')
    def _pdf(self):
        self.show_pdf = False
        self.pdf = False
        self.html = False
        self.show_html = False
        if len(self.expense_line_ids) == 1 and self.expense_line_ids.attachment:
            attachment = self.env['ir.attachment'].search([('res_field', '=', 'attachment'),
                                                           ('res_model', '=', 'hr.expense'),
                                                           ('res_id', '=', self.expense_line_ids.id)], limit=1)
            if attachment.mimetype == 'application/pdf':
                self.show_pdf = True
                self.pdf = self.expense_line_ids.attachment
            elif 'image' in attachment.mimetype:
                self.show_html = True
                base_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
                local_url = attachment.local_url
                image_url = urljoin(base_url, local_url)
                self.html = '<html><img height="350px" src="%s"></html>' % image_url

    @api.one
    @api.depends('expense_line_ids.product_id.type')
    def _product_type(self):
        if 'product' in self.mapped('expense_line_ids.product_id.type'):
            self.stockable_product = True
        else:
            self.stockable_product = False

    @api.one
    @api.depends('expense_line_ids.partner_id', 'expense_line_ids.employee_id')
    def _partner_id(self):
        if self.expense_line_ids and self.expense_line_ids.partner_id:
            self.partner_id = self.expense_line_ids.partner_id.id
        elif self.expense_line_ids and self.expense_line_ids.employee_id and self.expense_line_ids.sudo().employee_id.advance_accountancy_partner_id:
            self.partner_id = self.expense_line_ids.sudo().employee_id.advance_accountancy_partner_id.id

    # todo: ar teisingas total_amount?
    @api.multi
    def generate_invoice(self):
        self.ensure_one()
        invoice_vals = {
            'name': '',
            'origin': self.name,
            'type': 'in_invoice',
            'account_id': self.partner_id.property_account_payable_id.id,
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'payment_term_id': False,
            'company_id': self.company_id.id,
            'user_id': self.env.user.id,
            'expense_id': self.id,
            'date_invoice': self.accounting_date or datetime.utcnow(),
            'operacijos_data': self.accounting_date or datetime.utcnow(),
            'date_due': self.accounting_date or datetime.utcnow(),
        }
        invoice_id = self.env['account.invoice'].create(invoice_vals)
        for expense in self.expense_line_ids:
            if expense.representation:
                product_obj = self.env['product.product']
                tax_obj = self.env['account.tax']
                company_id = self.company_id
                categ_id = self.env.ref('l10n_lt.product_category_16')
                product_r25 = product_obj.search([('default_code', '=', 'R25'), ('company_id', '=', company_id.id)],
                                                 limit=1)
                product_r75 = product_obj.search([('default_code', '=', 'R75'), ('company_id', '=', company_id.id)],
                                                 limit=1)
                if not product_r25:
                    product_r25 = product_obj.create({
                        'default_code': 'R25',
                        'name': _(u'Reprezentacinės sąnaudos 25%'),
                        'categ_id': categ_id.id,
                        'type': 'service',
                        'company_id': company_id.id,
                    })
                if not product_r75:
                    product_r75 = product_obj.create({
                        'default_code': 'R75',
                        'name': _(u'Reprezentacinės sąnaudos 75%'),
                        'categ_id': categ_id.id,
                        'type': 'service',
                        'company_id': company_id.id,
                    })
                # Representation costs must be split into 2 lines
                account_r25 = product_r25.property_account_expense_id.id \
                    if product_r25.property_account_expense_id else False
                if not account_r25:
                    category = product_r25.categ_id
                    while category.parent_id and not category.property_account_expense_categ_id:
                        category = category.parent_id
                    account_r25 = category.property_account_expense_categ_id.id \
                        if category.property_account_expense_categ_id else False
                account_r75 = product_r75.property_account_expense_id.id \
                    if product_r75.property_account_expense_id else False
                if not account_r75:
                    category = product_r75.categ_id
                    while category.parent_id and not category.property_account_expense_categ_id:
                        category = category.parent_id
                    account_r75 = category.property_account_expense_categ_id.id \
                        if category.property_account_expense_categ_id else False
                total_cost = expense.total_amount
                price1 = tools.float_round(total_cost * 0.5, precision_digits=2)
                price2 = total_cost - price1
                vat = total_cost - expense.unit_amount
                # P3:DivOK
                tax_rate = vat / expense.unit_amount * 100.0
                vat_code = 'PVM1'
                tax1_id = False
                tax2_id = False
                if not tools.float_compare(tax_rate, 21.0, precision_digits=0):
                    vat_code = 'PVM1'
                elif not tools.float_compare(tax_rate, 9.0, precision_digits=0):
                    vat_code = 'PVM2'
                elif not tools.float_compare(tax_rate, 5.0, precision_digits=0):
                    vat_code = 'PVM3'
                if vat_code:
                    tax1_id = tax_obj.search([('code', '=', vat_code), ('nondeductible', '=', False),
                                              ('type_tax_use', '=', 'purchase')], limit=1)
                    tax2_id = tax_obj.search([('code', '=', vat_code), ('nondeductible', '=', True),
                                              ('type_tax_use', '=', 'purchase')], limit=1)
                if not tax1_id or not tax2_id:
                    raise exceptions.UserError(_('Reprezentacinės sąnaudos turi būti apmokestinamos PVM mokesčiu, '
                                                 'tačiau kvitas neturi nurodytų mokesčių.'))
                self.env['account.invoice.line'].create({
                    'product_id': product_r75.id,
                    'name': expense.name + u' (Reprezentacinės sąnaudos 50%)',
                    'quantity': 1.0,
                    'price_unit': price1,
                    'account_id': account_r75,
                    'invoice_line_tax_ids': [(4, tax1_id.id)],
                    'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
                    'invoice_id': invoice_id.id,
                })
                self.env['account.invoice.line'].create({
                    'product_id': product_r25.id,
                    'name': expense.name + u' (Reprezentacinės sąnaudos 50%)',
                    'quantity': 1.0,
                    'price_unit': price2,
                    'account_id': account_r25,
                    'invoice_line_tax_ids': [(4, tax2_id.id)],
                    'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
                    'invoice_id': invoice_id.id,
                })
            else:
                account = expense.account_id or expense.product_id.property_account_expense_id
                if not account:
                    product_category = expense.product_id.categ_id
                    while product_category and not account:
                        account = product_category.property_account_expense_categ_id
                        product_category = product_category.parent_id
                if not account:
                    if self.env.user.has_group('base.group_system'):
                        raise exceptions.UserError(
                            _('Please define expense account for this product: "%s" (id:%d) - or for its category: "%s".') % \
                            (expense.product_id.name, expense.product_id.id, expense.product_id.categ_id.name))
                    else:
                        raise exceptions.UserError(_('Neteisingi produkto nustatymai.'))
                if not expense.tax_ids:
                    tax_ids = self.env['account.tax'].search([('code', '=', 'PVM100')], limit=1).mapped('id')
                else:
                    tax_ids = expense.tax_ids.mapped('id')
                inv_line_vals = {
                    'name': expense.name,
                    'origin': 'AVN: ' + expense.name,
                    'account_id': account.id,
                    'price_unit': expense.unit_amount,
                    'quantity': expense.quantity,
                    'uom_id': expense.product_uom_id.id,
                    'product_id': expense.product_id.id or False,
                    'invoice_line_tax_ids': [(6, 0, tax_ids)],
                    'invoice_id': invoice_id.id,
                    'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
                }
                self.env['account.invoice.line'].create(inv_line_vals)
        self.write({'invoice_id': invoice_id.id})

        # Necessary to force computation of taxes. In account_invoice, they are triggered
        # by onchanges, which are not triggered when doing a create.
        invoice_id.compute_taxes()

        action = self.env.ref('account.action_invoice_tree1')
        form_view_id = self.env.ref('account.invoice_supplier_form')
        context = {
            'type': 'in_invoice',
            'default_type': 'in_invoice',
        }
        return {
            'name': action.name,
            'help': action.help,
            'type': action.type,
            'views': [(form_view_id.id, 'form')],
            'target': action.target,
            'context': context,
            'res_model': action.res_model,
            'res_id': invoice_id.id,
        }

    @api.multi
    def generate_picking(self):
        self.ensure_one()
        ctx = self._context.copy()
        ctx['expense_id'] = self.id
        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.expense.picking.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }




