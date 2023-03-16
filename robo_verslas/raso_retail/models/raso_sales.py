# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api, tools, exceptions, _
from six import iteritems
from .. import rr_tools as rt

allowed_calc_error = 0.02
vat_code_mapper = {
    1: 21,
    2: 5,
    3: 0
}


class RasoSales(models.Model):
    _name = 'raso.sales'
    _inherit = ['mail.thread', 'raso.line.base']

    shop_no = fields.Char(required=True, string='Parduotuvės numeris', inverse='get_shop_pos')
    pos_no = fields.Char(string='Kasos numeris', inverse='get_shop_pos')
    last_z = fields.Char(string='Z Numeris')

    sale_date = fields.Datetime(required=True, string='Pardavimo data')
    sale_day = fields.Date(compute='get_sale_day')
    code = fields.Char(required=True, string='Produkto barkodas')
    name = fields.Char(required=True, string='Produkto pavadinimas')

    qty = fields.Float(string='Kiekis')
    qty_man = fields.Float(string='Kiekis (RN)')

    amount = fields.Float(string='Kaina su PVM', digits=(12, 3))
    amount_man = fields.Float(string='Kaina su PVM (RN)', digits=(12, 3))

    vat_sum = fields.Float(string='PVM suma', digits=(12, 3))
    vat_sum_man = fields.Float(string='PMV suma (RN)', digits=(12, 3))

    price_unit = fields.Float(compute='compute_price_unit')
    price_unit_man = fields.Float(compute='compute_price_unit_man')

    discount = fields.Float(string='Nuolaida', digits=(12, 3))
    has_man = fields.Boolean(compute='get_has_man')

    payment_id = fields.Many2one('raso.payments', string='Susijęs mokėjimas')
    shop_id = fields.Many2one('raso.shoplist', string='Susieta Parduotuvė', readonly=True)
    pos_id = fields.Many2one('raso.shoplist.registers', string='Susieta Kasa', readonly=True)
    product_id = fields.Many2one('product.product', compute='get_product_id', store=True, readonly=True, string='Produktas')
    state = fields.Selection([
        ('imported', 'Pardavimo eilutė importuota'),
        ('created', 'Sąskaita sukurta sistemoje'),
        ('failed', 'Klaida kuriant sąskaitą'),
        ('warning', 'Pardavimo eilutė importuota su įspėjimais'),
        ('created_inventory', 'Nurašymas sukurtas sistemoje'),
        ('failed_inventory', 'Klaida kuriant nurašymą')],
        string='Būsena', default='imported', track_visibility='onchange',
    )
    tax_id = fields.Many2one('account.tax', compute='_compute_tax_id', store=True, string='Mokesčiai', readonly=True)
    force_taxes = fields.Boolean(default=False)
    man_tax_id = fields.Many2one('account.tax', compute='_compute_man_tax_id', string='Mokesčiai', store=True, readonly=True)
    invoice_id = fields.Many2one('account.invoice', compute='get_invoice', string='Sisteminė sąskaita')
    invoice_line_id = fields.Many2one('account.invoice.line')

    data_type = fields.Selection([('0', 'Pardavimai'),
                                  ('3', 'Grąžinimai'),
                                  ('2', 'Tara')], string='Duomenų Tipas')

    line_type = fields.Char(compute='get_line_type', store=True)

    # Fields for zero amount sales
    zero_amount_sale = fields.Boolean(
        compute='_compute_zero_amount_sale',
        store=True, string='Nulinis pardavimas'
    )
    zero_manual_amount_sale = fields.Boolean(
        compute='_compute_zero_manual_amount_sale',
        store=True, string='Nulinis pardavimas (rankinės nuolaidos)'
    )
    split_sale_line_id = fields.Many2one('raso.sales', string='Išskaidytas pardavimas')
    inventory_id = fields.Many2one('stock.inventory', string='Atsargų nurašymas')

    @api.multi
    @api.depends('amount')
    def _compute_zero_amount_sale(self):
        """Computes whether current sale is zero amount sale"""
        for rec in self:
            if tools.float_is_zero(rec.amount, precision_digits=2) \
                    and not tools.float_is_zero(rec.qty, precision_digits=2):
                rec.zero_amount_sale = True

    @api.multi
    @api.depends('amount_man')
    def _compute_zero_manual_amount_sale(self):
        """Computes whether current sale is zero manual amount sale"""
        for rec in self:
            if tools.float_is_zero(rec.amount_man, precision_digits=2) \
                    and not tools.float_is_zero(rec.qty_man, precision_digits=2):
                rec.zero_manual_amount_sale = True

    @api.multi
    def recompute_fields(self):
        self.compute_price_unit()
        self.get_has_man()
        self.get_invoice()
        self.get_product_id()
        self.get_shop_pos()
        # Inherited methods, see - raso.line.base
        self._compute_tax_id()
        self._compute_man_tax_id()

    @api.one
    @api.depends('sale_date')
    def get_sale_day(self):
        if self.sale_date:
            self.sale_day = self.sale_date[:10]

    @api.one
    @api.depends('amount', 'qty')
    def compute_price_unit(self):
        self.price_unit = self.amount / self.qty if self.qty else 0

    @api.one
    @api.depends('qty_man', 'amount_man')
    def compute_price_unit_man(self):
        self.price_unit_man = self.amount_man / self.qty_man if self.qty_man else 0

    @api.one
    @api.depends('qty_man', 'amount_man')
    def get_has_man(self):
        if self.qty_man and self.amount_man:
            self.has_man = True
        else:
            self.has_man = False

    @api.one
    @api.depends('invoice_line_id')
    def get_invoice(self):
        if self.invoice_line_id:
            self.invoice_id = self.invoice_line_id.invoice_id

    @api.one
    @api.depends('code')
    def get_product_id(self):
        if self.code:
            self.product_id = self.env['product.product'].search([('barcode', '=', self.code)])

    @api.one
    @api.depends('data_type', 'qty')
    def get_line_type(self):
        if self.data_type == '3':
            self.line_type = 'out_refund'
        else:
            if self.qty < 0:
                self.line_type = 'out_refund'
            else:
                self.line_type = 'out_invoice'

    @api.multi
    def validator(self, invoice_mode=True):
        """
        Check constraints and validate Raso Retail sale records,
        so they meet all criteria for account.invoice/stock.inventory creation.
        Records that have errors are filtered out
        :return: Validated raso.sales recordset
        """

        # Initialize dict with different fail reasons
        data = {k: self.env['raso.sales'] for k in rt.VALIDATION_FAIL_MESSAGE_MAPPER.keys()}
        self.recompute_fields()
        # Determine failed state based on the validation mode
        failed_state = 'failed' if invoice_mode else 'failed_inventory'
        # Validate the sales
        for rec in self:
            if invoice_mode and ((not tools.float_is_zero(rec.qty, precision_digits=2) and not rec.tax_id) or (
                    not tools.float_is_zero(rec.qty_man, precision_digits=2) and not rec.man_tax_id)):
                data['tax'] |= rec
            elif not rec.product_id:
                data['product'] |= rec
            elif not rec.shop_id.location_id:
                data['shop'] |= rec
            elif invoice_mode and (not rec.pos_id.journal_id or not rec.pos_id.partner_id):
                data['pos'] |= rec
            else:
                data['validated'] |= rec

        # Post different messages to corresponding failed sales
        for fail_key, sales in data.items():
            fail_message = rt.VALIDATION_FAIL_MESSAGE_MAPPER.get(fail_key)
            if fail_message and sales:
                self.post_message(sales, fail_message, failed_state)

        return data['validated']

    @api.multi
    def get_related_sales(self):
        return self.search([
            ('shop_id', 'in', self.mapped('shop_id').ids),
            ('pos_id', 'in', self.mapped('pos_id').ids),
            ('line_type', 'in', self.mapped('line_type')),
        ]).filtered(lambda s: s.sale_day in self.mapped('sale_day'))

    @api.model
    def prepare_invoice_values(self, lines):
        """ Prepares invoice values based on Raso sales """
        RasoSales = self.env['raso.sales']

        # Group lines by shop, pos, sale day and line type
        lines_grouped_by_key = defaultdict(lambda: RasoSales)
        for line in lines:
            key = (line.shop_id, line.pos_id, line.sale_day, line.line_type)
            lines_grouped_by_key[key] |= line

        AccountAccount = self.env['account.account'].sudo()

        sale_account = AccountAccount.search([('code', '=', '2410')])
        invoice_values = list()

        base_invoice_values = {
            'account_id': sale_account.id,
            'external_invoice': True,
            'price_include_selection': 'inc',
            'imported_api': True,
            'force_dates': True,
        }

        for (shop, pos, sale_day, line_type), filtered_lines_type in iteritems(lines_grouped_by_key):
            invoice_lines = []
            inv_values = base_invoice_values.copy()
            inv_values.update({
                'journal_id': pos.journal_id.id,
                'partner_id': pos.partner_id.id,
                'date_invoice': sale_day,
                'operacijos_data': sale_day,
                'type': line_type,
                'invoice_line_ids': invoice_lines,
                'raso_amount_to_add': 0.0,
                'raso_sales': RasoSales,
                'raso_invoice_shop': shop
            })

            for sale_line in filtered_lines_type:
                product_account = sale_line.product_id.get_product_income_account(return_default=True)
                tax_to_use = sale_line.tax_id if sale_line.tax_id else sale_line.man_tax_id
                qty_wo_discount = sale_line.qty
                qty_w_discount = sale_line.qty_man
                amount_to_add = sale_line.amount + sale_line.amount_man
                inv_values['raso_amount_to_add'] += abs(amount_to_add)
                inv_values['raso_sales'] |= sale_line

                base_invoice_line_values = {
                    'product_id': sale_line.product_id.id,
                    'name': sale_line.product_id.name or sale_line.product_id.default_code,
                    'uom_id': sale_line.product_id.product_tmpl_id.uom_id.id,
                    'account_id': product_account.id,
                    'invoice_line_tax_ids': [(6, 0, tax_to_use.ids)],
                    'raso_sale_line_id': sale_line.id
                }

                if qty_wo_discount:
                    line = base_invoice_line_values.copy()
                    line.update({
                        'quantity': abs(qty_wo_discount),
                        'price_unit': abs(sale_line.price_unit),
                    })
                    invoice_lines.append((0, 0, line))

                if qty_w_discount:
                    line = base_invoice_line_values.copy()
                    line.update({
                        'quantity': abs(qty_w_discount),
                        'price_unit': abs(sale_line.price_unit_man),
                    })
                    invoice_lines.append((0, 0, line))
            invoice_values.append(inv_values)

        return invoice_values

    @api.multi
    def create_invoices(self):
        """
        Create account.invoice records from Raso Retail sale records.
        Two types of creation can be done - normal operation and refund operation
        :return: None
        """
        # Filter out the lines that should not be invoiced
        lines = self.filtered(
            lambda s_line: not s_line.invoice_id and not s_line.invoice_line_id
            and not s_line.zero_manual_amount_sale and not s_line.zero_amount_sale
        )
        # Validate and sort the lines
        lines = lines.validator().sorted(key=lambda r: r.sale_date, reverse=True)

        AccountInvoice = self.env['account.invoice'].sudo()
        InvoiceDeliveryWizard = self.env['invoice.delivery.wizard'].sudo()
        RasoSales = self.env['raso.sales']

        invoice_values = self.prepare_invoice_values(lines)  # Get invoice values from RASO sales
        for inv_values in invoice_values:
            amount_total = inv_values.pop('raso_amount_to_add', 0.0)
            raso_invoice_shop = inv_values.pop('raso_invoice_shop', self.env['raso.shoplist'])
            raso_sales = inv_values.pop('raso_sales', RasoSales)
            try:
                invoice = AccountInvoice.create(inv_values)
                if tools.float_compare(amount_total, abs(invoice.amount_total), precision_digits=2):
                    diff = abs(invoice.amount_total - amount_total)
                    if tools.float_compare(diff, allowed_calc_error, precision_digits=2) > 0:
                        raise exceptions.ValidationError(
                            _('RASO sąskaitos galutinė suma nesutampa su paskaičiuota suma (%s != %s).') % (
                                amount_total, invoice.amount_total
                            ))
                raso_sales.write({'state': 'created'})
            except Exception as e:
                error_message = _('Nepavyko sukurti sąskaitos, sisteminė klaida %s') % e
                self.post_message(raso_sales, error_message, 'failed')
                continue

            try:
                invoice.partner_data_force()
                invoice.action_invoice_open()
                wizard = InvoiceDeliveryWizard.with_context(invoice_id=invoice.id).create({
                    'location_id': raso_invoice_shop.location_id.id
                })
                wizard.create_delivery()
                invoice.picking_id.confirm_delivery()
            except Exception as e:
                error_message = _('Nepavyko patvirtinti sąskaitos, sisteminė klaida %s') % e
                self.post_message(raso_sales, error_message, 'failed')

    @api.model
    def create_invoice_action_raso(self):
        action = self.env.ref('raso_retail.create_invoices_action_raso')
        if action:
            action.create_action()

    @api.one
    def get_shop_pos(self):
        if not self.shop_no:
            return
        shop = self.env['raso.shoplist'].search([('shop_no', '=', self.shop_no)])
        if not shop:
            shop = self.env['raso.shoplist'].create({
                'shop_no': self.shop_no,
                'location_id': False,
            })
        self.shop_id = shop
        if self.pos_no:
            pos = self.env['raso.shoplist.registers'].search([('shop_id', '=', shop.id),
                                                              ('pos_no', '=', self.pos_no)])
            if len(pos) > 1:
                raise exceptions.ValidationError(_('Konfigūracijos klaida: '
                                                   'rasti keli kasos aparatai %s parduotuvėje %s')
                                                 % (self.pos_no, self.shop_no))
            if not pos:
                pos = self.env['raso.shoplist.registers'].create({
                    'pos_no': self.pos_no,
                    'shop_id': self.shop_id.id
                })
            self.pos_id = pos
        else:
            pos = self.shop_id.generic_pos
            if not pos:
                pos = self.env['raso.shoplist.registers'].search([('pos_no', '=', 'Generic')])
            if not pos:
                self.shop_id.create_generic_pos()
                pos = self.shop_id.generic_pos
            if not pos:
                raise exceptions.ValidationError(_('Konfigūracijos klaida: Nerastas kasos '
                                                   'aparatas parduotuvei %s') % self.shop_no)
            self.pos_id = pos

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalite ištrinti įrašų!'))
        if any(rec.invoice_line_id or rec.invoice_id for rec in self):
            raise exceptions.UserError(_('Negalite ištrinti eilutės kuri turi sisteminę sąskaitą!'))
        return super(RasoSales, self).unlink()

    def post_message(self, lines, body, state):
        send = {
            'body': body,
        }
        for line in lines:
            line.message_post(**send)
            lines.write({'state': state})

    # Zero Amount Sale Handlers ---------------------------------------------------------------------------------------

    @api.multi
    def split_zero_amount_sale(self):
        """
        Splits sales that have both manual/normal quantities
        with one of the amounts being zero, into two separate records
        :return: None
        """

        # Recompute the fields before splitting
        self._compute_zero_amount_sale()
        self._compute_zero_manual_amount_sale()

        for sale in self:
            # Check whether sale should be split or not
            splitting_needs = sale.zero_amount_sale and not tools.float_is_zero(
                sale.amount_man, precision_digits=2) or sale.zero_manual_amount_sale and not tools.float_is_zero(
                sale.amount, precision_digits=2,
            )
            if splitting_needs and not sale.invoice_line_id and not sale.inventory_id and not sale.split_sale_line_id:
                split_sale = sale.copy()
                # Reset all normal amounts on the copy, and all of the manual amounts on the original sale
                split_sale.write({
                    'qty': 0.0, 'amount': 0.0, 'vat_sum': 0.0, 'split_sale_line_id': sale.id,
                })
                sale.write({
                    'qty_man': 0.0, 'amount_man': 0.0, 'vat_sum_man': 0.0, 'split_sale_line_id': split_sale.id,
                })
                self.env.cr.commit()

    @api.multi
    def create_inventory_write_off_prep(self):
        """
        Prepare Raso sale line objects for stock inventory creation.
        Sales that contain zero prices amounts are used in this action.
        Records are validated and filtered out before creation.
        :return: None
        """
        # Filter out sales before validation
        sales = self.filtered(
            lambda x: x.state in ['imported', 'failed', 'warning', 'failed_inventory']
            and not x.inventory_id and (x.zero_amount_sale or x.zero_manual_amount_sale)
        )
        sales.split_zero_amount_sale()
        # Check constraints and validate records
        validated_records = sales.validator(invoice_mode=False)
        if validated_records:
            grouped_lines = {}
            for line in validated_records:
                # Loop through lines and build dict of dicts with following mapping
                pos = line.pos_id
                s_date = line.sale_date
                l_type = line.line_type

                grouped_lines.setdefault(pos, {})
                grouped_lines[pos].setdefault(s_date, {})
                grouped_lines[pos][s_date].setdefault(l_type, self.env['raso.sales'])
                grouped_lines[pos][s_date][l_type] |= line

            # Loop through grouped lines and create inventory write-offs for each batch
            for pos, by_pos in grouped_lines.items():
                for sale_date, by_sale_date in by_pos.items():
                    for line_type, sale_lines in by_sale_date.items():
                        sale_lines.create_inventory_write_off()

    @api.multi
    def create_inventory_write_off(self):
        """
        Creates stock inventory records from grouped Raso Retail sales.
        :return: None
        """
        # Check for active alignment committee
        committee = self.env['alignment.committee'].sudo().search([
            ('state', '=', 'valid'), ('type', '=', 'inventory')],
            order='date DESC', limit=1
        )
        if not committee:
            self.custom_rollback(
                _('Nerasta aktyvi atsargų nurašymo komisija'), action_type='inventory_creation')
            return

        default_obj = self.sorted(lambda r: r.sale_date, reverse=True)[0]
        default_location = default_obj.pos_id.location_id
        stock_reason = self.env.ref('robo_stock.reason_line_1')
        # Prepare the name for the inventory
        name = _('Nemokamų pardavimų nurašymas {} [{}]').format(
            default_obj.sale_date, default_obj.pos_id.name
        )
        # Prepare inventory values
        inventory_lines = []
        inventory_values = {
            'name': name,
            'filter': 'partial',
            'komisija': committee.id,
            'date': default_obj.sale_date,
            'reason_line': stock_reason.id,
            'location_id': default_location.id,
            'accounting_date': default_obj.sale_date,
            'account_id': stock_reason.account_id.id,
            'line_ids': inventory_lines,
        }
        # Prepare stock inventory lines based on sales
        for line in self:
            # Either qty or qty manual is used
            consumed_qty = line.qty if tools.float_is_zero(line.qty_man, precision_digits=2) else line.qty_man
            line_values = {
                'product_id': line.product_id.id,
                'product_uom_id': line.product_id.uom_id.id,
                'location_id': default_location.id,
                'consumed_qty': consumed_qty * -1,
            }
            inventory_lines.append((0, 0, line_values))
        # Create inventory record
        try:
            inventory = self.env['stock.inventory'].create(inventory_values)
            # Try to confirm the inventory
            inventory.prepare_inventory()
            inventory.action_done()
            inventory.mark_validated()
        except Exception as e:
            self.custom_rollback(e.args[0], action_type='inventory_creation')
            return

        self.write({'state': 'created_inventory', 'inventory_id': inventory.id})
        self.env.cr.commit()

    @api.multi
    def custom_rollback(self, msg, action_type='invoice_creation'):
        """
        Rollback current transaction,
        post message to the object and commit
        :return: None
        """
        self.env.cr.rollback()
        self.env.all.todo = {}
        self.env.cache.clear()
        if action_type == 'inventory_creation':
            body = _('Nepavyko sukurti nurašymo, sisteminė klaida: {}').format(msg)
            self.post_message(self, body, state='failed_inventory')
        self.env.cr.commit()
