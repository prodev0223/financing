# -*- coding: utf-8 -*-
import psycopg2
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, _, api, exceptions, tools
from odoo.tools import mute_logger


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    def default_tax(self):
        ids = self.env['account.tax'].search([('code', '=', 'PVM100'),
                                              ('type_tax_use', '=', 'purchase'),
                                              ('price_include', '=', False),
                                              ], limit=1).mapped('id')
        return [(6, 0, ids)]

    def default_amount(self):
        return self.total_amount

    partner_id = fields.Many2one('res.partner', string='Partner',
                                 readonly=True,
                                 states={'draft': [('readonly', False)], 'refused': [('readonly', False)]},
                                 required=True)
    tax_ids = fields.Many2many('account.tax', 'expense_tax', 'expense_id', 'tax_id', string='Taxes',
                               states={'done': [('readonly', True)], 'post': [('readonly', True)]}, default=default_tax)
    account_id = fields.Many2one(required=False)
    stockable_product = fields.Boolean(string='Is Stockable?', compute='_product_type')
    representation = fields.Boolean(string='Reprezentacinės išlaidos', default=False,
                                    readonly=True,
                                    states={'draft': [('readonly', False)], 'refused': [('readonly', False)]},
                                    inverse='_inverse_amount')
    attachment = fields.Binary(string='Išlaidos', attachment=True, required=False)
    name_attachment = fields.Char(string='Failo pavadinimas', default='nuotrauka.jpg')
    mime_attachment = fields.Char(string='Failo tipas', default='image/jpeg')
    state = fields.Selection([('draft', 'Juodraštis'),
                              ('reported', 'Pateikta'),
                              ('done', 'Priimta'),
                              ('refused', 'Atmesta'),
                              ('imported', 'Importuota')])
    is_fuel = fields.Boolean(compute='_is_fuel')
    is_expense_country_LT = fields.Boolean(string='Ar pirkta Lietuvoje?', default=True,
                                           readonly=True,
                                           states={'draft': [('readonly', False)], 'refused': [('readonly', False)]},
                                           inverse='_inverse_amount')
    paid_amount_with_tax = fields.Float(string='Suma su PVM', default=default_amount, inverse='_inverse_amount',
                                        readonly=True,
                                        states={'draft': [('readonly', False)], 'refused': [('readonly', False)]})
    original_message = fields.Html(string='Originali žinutė', readonly=True)
    payment_mode = fields.Selection(
        [('own_account', 'Asmeninėmis lėšomis'), ('company_account', 'Kompanijos lėšomis')],
        inverse='_inverse_payment_mode', default='own_account')
    invoice_id = fields.Many2one('account.invoice', string='Invoice', copy=False)
    imported_payment_mode = fields.Selection(
        [('own_account', 'Asmeninėmis lėšomis'), ('company_account', 'Kompanijos lėšomis')], store=False,
        states={'imported': [('required', True)]}, default=None, inverse='_set_imported_payment_mode')
    ap_employee_id = fields.Many2one('hr.employee', string='Apmokėjęs darbuotojas', copy=False)  # not used
    product_id = fields.Many2one('product.product', inverse="_inverse_change_quantity")
    need_action = fields.Boolean(string='Reikia papildomų duomenų', compute='_expense_status')
    original_vat = fields.Float(string='Pradinė PVM suma', groups='base.group_system')

    @api.one
    @api.depends('state')
    def _expense_status(self):
        if self.state == 'imported':
            self.need_action = True
        else:
            self.need_action = False

    @api.multi
    def app_exp_company(self):
        self.ensure_one()
        self.sudo().write({
            'payment_mode': 'company_account'
        })
        self.submit_cheque()
        return True

    @api.multi
    def app_exp_own(self):
        self.ensure_one()
        self.sudo().write({
            'payment_mode': 'own_account'
        })
        self.submit_cheque()
        return True

    @api.multi
    def app_confirm_cheque(self):
        self.ensure_one()
        self.submit_cheque()
        return True

    @api.constrains('partner_id', 'representation')
    def constr_representation_partner(self):
        for rec in self:
            if rec.representation and not rec.partner_id:
                raise exceptions.ValidationError(_('Būtina nurodyti reprezentacinių išlaidų tiekėją'))
            if rec.representation and rec.partner_id.advance_payment:
                raise exceptions.ValidationError(_('Reprezentacinių išlaidų tiekėjas negali būti ataskaitingas asmuo'))

    @api.constrains('representation', 'is_expense_country_LT', 'product_id')
    def constr_representation_country(self):
        for rec in self:
            if rec.representation and rec.is_fuel:
                raise exceptions.ValidationError(_('Perkant kurą reprezentacinės sąnaudos neleidžiamos.'))

    @api.constrains('partner_id', 'payment_mode', 'employee_id')
    def constr_partner_id(self):
        for rec in self:
            if rec.partner_id:
                if rec.payment_mode == 'company_account':
                    if rec.partner_id.is_employee:
                        raise exceptions.ValidationError(
                            _('Neteisingai pasirinktas čekio tiekėjas. Pasirinkite kompaniją.'))

    @api.multi
    def copy(self, default=None):
        raise exceptions.UserError(_('Negalima dublikuoti čekio.'))

    @api.one
    def _set_imported_payment_mode(self):
        if self.state == 'imported':
            self.payment_mode = self.imported_payment_mode
            self.state = 'draft'

    @api.one
    def _inverse_change_quantity(self):
        if not self.is_fuel:
            self.quantity = 1.0

    @api.one
    @api.depends('product_id')
    def _is_fuel(self):
        # Dujos, Dyzelinas, Benzinas
        degalai_ids = (self.env.ref('l10n_lt.product_category_6').id, self.env.ref('l10n_lt.product_category_26').id,
                       self.env.ref('l10n_lt.product_category_27').id)
        if self.product_id and self.product_id.categ_id.id in degalai_ids:
            self.is_fuel = True
            self.representation = False
        else:
            self.is_fuel = False

    @api.one
    def _inverse_payment_mode(self):
        # it has invoice_id with status 'imported
        if self.state == 'imported' and self.payment_mode == 'own_account':
            if not self.invoice_id:
                raise exceptions.UserError(_('Nėra susijusios sąskaitos faktūros.'))
            self.invoice_id.write({
                'advance_payment': True,
                'ap_employee_id': self.employee_id.id,
            })
        if self.state == 'draft' and self.invoice_id:
            if self.payment_mode == 'own_account':
                self.invoice_id.write({
                    'advance_payment': True,
                    'ap_employee_id': self.employee_id.id,
                })
            else:
                self.invoice_id.write({
                    'advance_payment': False,
                })

    @api.onchange('is_expense_country_LT')
    def onchange_is_expense_country_LT(self):
        if not self.is_expense_country_LT:
            self.representation = False

    @api.one
    def _inverse_amount(self):
        if len(self.tax_ids) > 1:
            raise exceptions.Warning(_('Nurodykite vieną mokestį.'))
        if self.tax_ids.price_include:
            self.unit_amount = self.paid_amount_with_tax
        elif self.tax_ids:  # ROBO: probablly called only in NO PVM
            # P3:DivOK -- amount on tax_ids is float, thus division always results in float
            taxes = self.tax_ids.amount / 100 + 1
            if taxes > 0:
                # P3:DivOK -- taxes is float, thus division always results in float
                self.unit_amount = self.paid_amount_with_tax / taxes
        elif not self.tax_ids:
            self.unit_amount = self.paid_amount_with_tax

    @api.onchange('product_id', 'is_expense_country_LT', 'payment_mode')
    def onchange_product_id(self):
        tax_ids = self.env['account.tax'].search([('code', '=', 'PVM100'), ('type_tax_use', '=', 'purchase')],
                                                                                              limit=1).mapped('id')
        self.tax_ids = [(6, 0, tax_ids)]

    @api.onchange('payment_mode', 'employee_id')
    def onchange_payment_mode(self):
        if self.payment_mode == 'company_account':
            self.employee_id = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
            return {'domain': {
                'partner_id': [('advance_payment', '=', False)]}}
        else:
            return {'domain': {'partner_id': [
                '|',
                ('id', '=', self.partner_id and self.partner_id.id or False),
                ('advance_payment', '=', False)
            ]}}

    @api.multi
    def clear(self):
        self.ensure_one()
        attachments = self.env['ir.attachment'].search([('res_model', '=', 'hr.expense'),
                                                        ('res_id', '=', self.id)])
        attachments.unlink()

    @api.one
    @api.depends('product_id.type')
    def _product_type(self):
        if self.product_id and self.product_id.type == 'product':
            self.stockable_product = True
        else:
            self.stockable_product = False

    @api.model
    def move_attachments(self, old_src=None, new_src=None, old_model=None, new_model=None, err_msg=_('Įvyko dokumentų perkėlimo klaida.')):
        if old_src and new_src:
            Model = self.env['ir.attachment']
            records = Model.sudo().search([('res_model', '=', old_model), ('res_id', '=', old_src.id)])
            try:
                with mute_logger('odoo.sql_db'), self._cr.savepoint():
                    return records.sudo().write({
                        'res_id': new_src.id,
                        'res_model': new_model,
                        'name': 'nuotrauka.jpg',
                        'datas_fname': 'nuotrauka.jpg',
                        'description': 'nuotrauka.jpg',
                    })
            except psycopg2.Error:
                raise exceptions.UserError(err_msg)

    @api.multi
    def submit_cheque_with_action(self):
        self.ensure_one()
        if self.invoice_id:
            self.submit_cheque()
            action = self.env.ref('robo.new_supplier_invoice')
            vals = action.read()[0]
            vals['res_id'] = self.invoice_id.id
            return vals

    @api.multi
    def submit_cheque(self):
        self.ensure_one()
        # check if we have one attachment
        if self.nbr_of_attachments == 0:
           raise exceptions.UserError(_('Prisekite bent vieną dokumentą!'))
        self.invoice_id.action_invoice_open()
        # move attachments to account.invoice model from hr.expense
        self.env['hr.expense'].move_attachments(old_src=self, new_src=self.invoice_id, old_model='hr.expense',
                                                new_model='account.invoice', err_msg=_('Nepavyko patvirtinti čekio.'))

        upload_id = self.sudo().env['robo.upload'].search(
            [('res_model', '=', 'hr.expense'), ('res_id', '=', self.id), ('state', '=', 'need_action')])
        if not upload_id and self.invoice_id:
            upload_id = self.sudo().env['robo.upload'].search(
                [('res_model', '=', 'account.invoice'), ('res_id', '=', self.invoice_id.id), ('state', '=', 'need_action')])
        if upload_id:
            upload_id.write({'state': 'done'})

    @api.multi
    def submit_expenses(self):
        if len(self.mapped('partner_id.id')) > 1:
            raise exceptions.UserError(_('Pateikite čekius to paties tiekėjo.'))

        if self.env.user.is_user():
            ctx = {
                'default_expense_line_ids': [line.id for line in self],
                'default_employee_id': self[0].employee_id.id,
                'default_name': self[0].name if len(self.ids) == 1 else '',
            }
            sheet_id = self.env['hr.expense.sheet'].sudo().with_context(ctx).create({})
            if self.original_message:
                if self.sudo().company_id.findir and self.sudo().company_id.findir.partner_id:
                    partner_ids = [self.sudo().company_id.findir.partner_id.id]
                else:
                    partner_ids = []
                msg_params = {
                    'body': self.original_message,
                    'subject': _('Originali žinutė'),
                    'type': 'email',
                    'subtype': 'comment',
                    'partner_ids': partner_ids,
                }
                sheet_id.message_post(**msg_params)
        else:
            return super(HrExpense, self).submit_expenses() # @api.model

    @api.multi
    def write(self, values):
        res = super(HrExpense, self).write(values)
        if self._context.get('write_from_invoice', False):
            return res
        # invoice main part has changed
        for rec in self:
            if rec.invoice_id and rec.invoice_id.with_cheque_form:
                expense = rec
                invoice_id = rec.invoice_id
                date_invoice = expense.date or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                operacijos_data = date_invoice
                if any(name in (
                'name', 'partner_id', 'currency_id', 'company_id', 'date', 'employee_id', 'payment_mode', 'reference')
                       for name in values):

                    partner = expense.partner_id
                    if partner and partner.advance_payment:
                        employee = self.sudo().env['hr.employee'].search(
                            [('advance_accountancy_partner_id', '=', partner.id)], limit=1)
                        if employee and employee.address_home_id:
                            partner = employee.address_home_id

                    rec.invoice_id.with_context(write_from_expense=True).write({
                        'origin': expense.name,
                        'account_id': expense.partner_id.property_account_payable_id.id,
                        'partner_id': expense.partner_id.id,
                        'currency_id': expense.currency_id.id,
                        'company_id': expense.company_id.id,
                        'date_invoice': operacijos_data,
                        'operacijos_data': date_invoice,
                        'date_due': date_invoice,
                        'advance_payment': True if expense.payment_mode == 'own_account' else False,
                        'ap_employee_id': expense.employee_id.id if expense.payment_mode == 'own_account' else False,
                        'reference': expense.reference,
                        'payment_mode': expense.payment_mode,
                        'partner_vat': partner and partner.vat or False,
                        'partner_kodas': partner and partner.kodas or False,
                        'partner_company_type': partner and partner.company_type or False,
                        'partner_parent_id': partner and partner.parent_id and partner.partner_id.id or False,
                        'partner_street': partner and partner.street or False,
                        'partner_zip': partner and partner.zip or False,
                        'partner_city': partner and partner.city or False,
                        'partner_country_id': partner and partner.country_id and partner.country_id.id or False,
                        'partner_phone': partner and partner.phone or False,
                        'partner_email': partner and partner.email or False,
                    })

                # invoice line has changed
                if any(name in (
                'unit_amount', 'company_id', 'representation', 'analytic_account_id', 'tax_ids', 'product_id',
                'quantity', 'paid_amount_with_tax', 'currency_id') for name in values):
                    if rec.invoice_id.state == 'draft':
                        rec.invoice_id.invoice_line_ids.unlink()
                        self.env['hr.expense'].generate_cheque_invoice_lines(invoice_id, expense)
                    else:
                        raise exceptions.UserError(
                            _('Tik juodraščio būsenos sąskaitoje galima pakeisti mokėjimo informaciją.'))
        return res

    @api.model
    def create(self, vals):
        expenses = super(HrExpense, self).create(vals)
        self.generate_cheque_invoice(expenses)
        return expenses

    @api.model
    def create_app(self, vals):
        raise exceptions.UserError('Blokuojamas dokumentų suvedimas')
        if 'reference' not in vals:
            raise exceptions.UserError('Nenurodytas sąskaitos/čekio numeris')
        if 'unit_amount' not in vals:
            vals['unit_amount'] = 0.0
        if 'partner_id' not in vals:
            if self.env.user.sudo(user=self.env.user.id).partner_id:
                partner_id = self.env.user.sudo(user=self.env.user.id).partner_id.with_context(active_test=False)
                vals['partner_id'] = partner_id.id
                if partner_id.employee_ids:
                    vals['employee_id'] = partner_id.employee_ids[0].id
        if 'is_expense_country_LT' not in vals:
            vals['is_expense_country_LT'] = True
        if not vals['is_expense_country_LT']:
            tax_ids = self.env['account.tax'].search([('code', '=', 'PVM100'),
                                                      ('type_tax_use', '=', 'purchase'),
                                                      ('price_include', '=', True)],
                                                     limit=1).mapped('id')
        else:
            tax_ids = self.env['account.tax'].search([('code', '=', 'PVM1'),
                                                      ('type_tax_use', '=', 'purchase'),
                                                      ('nondeductible', '=', True),
                                                      ('price_include', '=', True)],
                                                     limit=1).mapped('id')
            if not tax_ids:
                tax_ids = self.env['account.tax'].search([('code', '=', 'PVM1'),
                                                          ('type_tax_use', '=', 'purchase'),
                                                          ('nondeductible', '=', True),
                                                          ('price_include', '=', False)],
                                                         limit=1).mapped('id')
        vals['tax_ids'] = [(6, 0, tax_ids)]
        expense_id = self.create(vals)
        self.env['ir.attachment'].search([('res_model', '=', 'hr.expense'),
                                          ('res_id', '=', expense_id.id),
                                          ('res_field', '=', 'attachment')]).write({
            'name': expense_id.name_attachment,
            'description': expense_id.name_attachment,
            'datas_fname': expense_id.name_attachment,
        })
        return expense_id.id if expense_id else False

    @api.model
    def get_representation_product(self, product_code):
        """
        Search for representation products based on the passed code.
        If products do no exist - create them in the system.
        Data is returned in following structure {'product': P, 'account': A}
        :param product_code: default_code for product.product record
        :return: gathered data (dict)
        """
        # Product code must be either R75 or R25!
        if product_code not in ['R75', 'R25']:
            # No reason to translate since this error should only occur in testing phase
            # other code should never be passed
            raise exceptions.ValidationError('Incorrect representation product code!')

        names = {
            'R25': _('Reprezentacinės sąnaudos 50% (neatskaitoma)'),
            'R75': _('Reprezentacinės sąnaudos 50% (atskaitoma)')
        }
        categ_id = self.env.ref('l10n_lt.product_category_16')
        product = self.env['product.product'].search([('default_code', '=', product_code)], limit=1)

        if not product:
            product = self.env['product.product'].create({
                'default_code': product_code,
                'name': names[product_code],
                'categ_id': categ_id.id,
                'type': 'service',
            })
        if product.property_account_expense_id:
            account = product.property_account_expense_id
        elif product.categ_id.property_account_expense_categ_id:
            account = product.categ_id.property_account_expense_categ_id
        else:
            account = self.env['account.account']
        return {'product': product, 'account': account}

    @api.model
    def generate_cheque_invoice_lines(self, invoice_id, expense):

        non_deductible_account_id = invoice_id.sudo().company_id.non_deductible_account_id and invoice_id.sudo().company_id.non_deductible_account_id.id or False
        amount = expense.total_amount
        amount_company = expense.sudo().company_id.currency_id.compute(amount, expense.currency_id)
        product_obj = self.env['product.product']
        tax_obj = self.env['account.tax']
        company_id = expense.company_id

        if expense.representation:
            r75_data = self.get_representation_product('R75')
            r25_data = self.get_representation_product('R25')

            # Gather up the data
            product_r75 = r75_data['product']
            account_r75 = r75_data['account'].id
            product_r25 = r25_data['product']
            account_r25 = r25_data['account'].id

            if (amount_company > 100.0 and not expense.is_fuel) or (expense.is_fuel and amount_company > 150.0):
                account_r25 = non_deductible_account_id
                account_r75 = non_deductible_account_id

            tax1_id = False
            tax2_id = False

            # PVM moketojas?
            invoice_line_tax1_ids = [(4, False)]
            invoice_line_tax2_ids = [(4, False)]

            if expense.tax_ids:
                vat_code = expense.tax_ids.ensure_one().code

                if vat_code:
                    tax2_id = tax_obj.search([('code', '=', vat_code), ('nondeductible', '=', False),
                                              ('type_tax_use', '=', 'purchase'), ('price_include', '=', False)], limit=1)
                    tax1_id = tax_obj.search([('code', '=', vat_code), ('nondeductible', '=', False),
                                              ('type_tax_use', '=', 'purchase'), ('price_include', '=', False)], limit=1)

                if not tax1_id or not tax2_id:
                    raise exceptions.UserError(_('Reprezentacinės sąnaudos galimos tik perkant Lietuvoje.'))

                invoice_line_tax1_ids = [(4, tax1_id.id)]
                invoice_line_tax2_ids = [(4, tax2_id.id)]

            price1 = tools.float_round(expense.unit_amount * 0.5, precision_digits=2)
            price2 = expense.unit_amount - price1

            self.env['account.invoice.line'].create({
                'product_id': product_r75.id,
                'name': expense.name + u' (Reprezentacinės sąnaudos 75%)',
                'quantity': 1.0,
                'price_unit': price1,
                'account_id': account_r75,
                'invoice_line_tax_ids': invoice_line_tax1_ids,
                'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
                'invoice_id': invoice_id.id,
            })
            self.env['account.invoice.line'].create({
                'product_id': product_r25.id,
                'name': expense.name + u' (Reprezentacinės sąnaudos 25%)',
                'quantity': 1.0,
                'price_unit': price2,
                'account_id': account_r25,
                'invoice_line_tax_ids': invoice_line_tax2_ids,
                'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
                'invoice_id': invoice_id.id,
            })
        else:
            # TODO/FIXME: this name check might fail if user lang is not lt_LT
            if expense.product_id.name != 'Kitos komandiruočių sąnaudos (apgyvendinimas, transportas ir kt.)' and (amount_company > 100.0 and not expense.is_fuel) or (expense.is_fuel and amount_company > 150.0):
                account = non_deductible_account_id
            else:
                account = expense.account_id or expense.product_id.property_account_expense_id
                if not account:
                    product_category = expense.product_id.categ_id
                    while product_category and not account:
                        account = product_category.property_account_expense_categ_id
                        product_category = product_category.parent_id
                if account:
                    account = account.id
            if not account:
                if self.env.user.has_group('base.group_system'):
                    raise exceptions.UserError(
                        _('Please define expense account for this product: "%s" (id:%d) - or for its category: "%s".') % \
                        (expense.product_id.name, expense.product_id.id, expense.product_id.categ_id.name))
                else:
                    raise exceptions.UserError(_('Neteisingi produkto nustatymai.'))
            if not expense.tax_ids:
                tax_ids = tax_obj.search([('code', '=', 'PVM100'),
                                          ('nondeductible', '=', False),
                                          ('nondeductible_profit', '=', False),
                                          ('type_tax_use', '=', 'purchase'),
                                          ('price_include', '=', False)], limit=1).mapped('id')
            else:
                tax_ids = expense.tax_ids.mapped('id')
            inv_line_vals = {
                'name': expense.name,
                'origin': 'AVN: ' + expense.name,
                'account_id': account,
                'price_unit': expense.unit_amount,
                'quantity': expense.quantity,
                'uom_id': expense.product_uom_id.id,
                'product_id': expense.product_id.id or False,
                'invoice_line_tax_ids': [(6, 0, tax_ids)],
                'invoice_id': invoice_id.id,
                'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
            }
            line_id = self.env['account.invoice.line'].create(inv_line_vals)

            if expense.sudo().original_vat > 0:
                product_nupvm = product_obj.search([('default_code', '=', 'NUPVM'), ('company_id', '=', company_id.id)],
                                                   limit=1)
                if product_nupvm:
                    self.env['account.invoice.line'].create({
                        'name': product_nupvm.name,
                        'origin': 'AVN: ' + product_nupvm.name,
                        'account_id': account,
                        'quantity': 1.0,
                        'product_id': product_nupvm.id,
                        'price_unit': expense.sudo().original_vat,
                        'invoice_line_tax_ids': [(6, 0, tax_ids)],
                        'invoice_id': invoice_id.id,
                        'account_analytic_id': expense.analytic_account_id.id if expense.analytic_account_id else False,
                    })

                    line_total = line_id.price_subtotal - expense.sudo().original_vat

                    line_id.write({
                        'price_subtotal_make_force_step': True,
                        'price_subtotal_save_force_value': line_total,
                        'price_unit': line_total,
                        'quantity': 1.0,
                    })

        # Necessary to force computation of taxes. In account_invoice, they are triggered
        # by onchanges, which are not triggered when doing a create.
        invoice_id.compute_taxes()

    @api.model
    def generate_cheque_invoice(self, expenses):
        for expense in expenses:
            date_invoice = expense.date or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_invoice_dt = datetime.strptime(date_invoice, tools.DEFAULT_SERVER_DATE_FORMAT)
            passed_deadline = False
            isaf_day = self.env['account.invoice'].get_isaf_report_date(date_invoice)
            fiscal_dates = self.env.user.company_id.compute_fiscalyear_dates(datetime.utcnow() - relativedelta(years=1))
            last_year1 = fiscal_dates['date_from'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            last_year2 = fiscal_dates['date_to'].strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            move_line_obj = self.sudo().env['account.move.line']
            closed_year = move_line_obj.search([('date', '>=', last_year1),
                                                ('date', '<=', last_year2),
                                                '|',
                                                ('account_id.code', '=like', '5%'),
                                                ('account_id.code', '=like', '6%'),
                                                ('journal_id', '=',
                                                 self.sudo().env.user.company_id.period_close_journal_id.id),
                                                ('move_id.state', '=', 'posted')], count=True)
            last_year_records = move_line_obj.search([('date', '>=', last_year1),
                                                      ('date', '<=', last_year2),
                                                      ('move_id.state', '=', 'posted')], limit=1, count=True)
            if ((date_invoice <= last_year2 and not closed_year and last_year_records) or date_invoice > last_year2):
                operacijos_data = date_invoice
            else:
                registration_date_dt = datetime.utcnow()
                if date_invoice_dt < datetime(datetime.utcnow().year, 1, 1):

                    date_deadline = datetime(datetime.utcnow().year, 1, isaf_day)
                    if registration_date_dt > date_deadline and not closed_year and last_year_records:
                        passed_deadline = True

                    if date_invoice_dt < datetime(datetime.utcnow().year - 1, 12, 1):
                        passed_deadline = True

                if passed_deadline:
                    operacijos_data = datetime(registration_date_dt.year - 1, 12, 31).strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT)
                else:
                    date_invoice_d = datetime(date_invoice_dt.year, date_invoice_dt.month, date_invoice_dt.day)
                    operacijos_data = registration_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    registration_date_d = datetime(registration_date_dt.year, registration_date_dt.month,
                                                   registration_date_dt.day)
                    date_invoice_d_1 = date_invoice_d + relativedelta(day=1)
                    registration_date_d_1 = registration_date_d + relativedelta(day=1)
                    if date_invoice_d_1 == registration_date_d_1:
                        operacijos_data = date_invoice
                    elif (date_invoice_d_1 + relativedelta(
                            months=1)) == registration_date_d_1 and registration_date_d.day <= isaf_day:
                        operacijos_data = date_invoice
                    elif (date_invoice_d_1 + relativedelta(
                            months=1)) == registration_date_d_1 and registration_date_d.day > isaf_day:
                        operacijos_data = registration_date_d_1.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    elif (registration_date_d_1 - relativedelta(
                            months=1)) > date_invoice_d_1 and registration_date_d.day <= self.env['account.invoice'].get_isaf_report_date((registration_date_d_1 - relativedelta(months=1)).strftime(
                            tools.DEFAULT_SERVER_DATE_FORMAT)):
                        operacijos_data = (registration_date_d_1 - relativedelta(months=1)).strftime(
                            tools.DEFAULT_SERVER_DATE_FORMAT)
                    elif (registration_date_d_1 - relativedelta(
                            months=1)) > date_invoice_d_1 and registration_date_d.day > self.env['account.invoice'].get_isaf_report_date((registration_date_d_1 - relativedelta(months=1)).strftime(
                            tools.DEFAULT_SERVER_DATE_FORMAT)):
                        operacijos_data = registration_date_d_1.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            invoice_vals = {
                'name': '',
                'origin': expense.name,
                'type': 'in_invoice',
                'account_id': expense.partner_id.property_account_payable_id.id,
                'partner_id': expense.partner_id.id,
                'currency_id': expense.currency_id.id,
                'payment_term_id': False,
                'company_id': expense.company_id.id,
                'user_id': expense.env.user.id,
                'hr_expense_id': expense.id,
                'date_invoice': operacijos_data,
                'operacijos_data': date_invoice,
                'date_due': date_invoice,
                'with_cheque_form': True,
                'with_cheque_picture': True,
                'reference': expense.reference,
                'payment_mode': expense.payment_mode,
                'skip_isaf': True,
            }

            if expense.payment_mode == 'own_account' and expense.state != 'imported':
                invoice_vals['ap_employee_id'] = expense.employee_id.id

            invoice_id = self.env['account.invoice'].with_context(type='in_invoice').create(invoice_vals)
            invoice_id.partner_data_force()
            if expense.original_message:
                if self.sudo().company_id.findir and self.sudo().company_id.findir.partner_id:
                    partner_ids = [self.sudo().company_id.findir.partner_id.id]
                else:
                    partner_ids = []
                msg_params = {
                    'body': expense.original_message,
                    'subject': _('Originali žinutė'),
                    'type': 'email',
                    'subtype': 'comment',
                    'partner_ids': partner_ids,
                }
                invoice_id.message_post(**msg_params)

            self.generate_cheque_invoice_lines(invoice_id, expense)
            expense.write({'invoice_id': invoice_id.id})

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.invoice_id and not self._context.get('deleting_invoice', False):
                rec.invoice_id.with_context({'deleting_cheque': True}).unlink()
        return super(HrExpense, self).unlink()
