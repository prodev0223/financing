# -*- coding: utf-8 -*-
from odoo import models, api, fields, exceptions, tools, _
from datetime import datetime


class StockMove(models.Model):
    _name = 'stock.move'
    _inherit = ['stock.move', 'barcodes.barcode_events_mixin']

    let_modify = fields.Boolean(compute='_compute_let_modify')
    production_type = fields.Selection([
        ('dynamic', 'Kintantis'),
        ('static', 'Fiksuotas')], string='Gamybos tipas', compute='_compute_production_type')

    cancel_production_id = fields.Many2one('mrp.production', string='Atšaukta gamyba')
    surplus_production_id = fields.Many2one('mrp.production', string='Perteklinė gamyba')
    cancel_raw_material_production_id = fields.Many2one('mrp.production', string='Komponentų suvartojimo atšaukimas')
    is_consumable = fields.Boolean(string='Ar suvartojama paslauga?', compute='_compute_is_consumable')

    # Scanning fields
    scan_status_text = fields.Char(string='Skenavimo statusas', groups='stock.group_production_lot', store=False)
    scan_status = fields.Integer(string='Indikatorius', groups='stock.group_production_lot', store=False)
    barcode = fields.Char(string='Barkodas', groups='stock.group_production_lot', store=False)

    production_modification_rule_id = fields.Many2one('mrp.production.modification.rule')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('product_id.type')
    def _compute_is_consumable(self):
        """Compute whether product is consumable"""
        for rec in self:
            rec.is_consumable = rec.product_id.type == 'consu'

    @api.multi
    @api.depends('raw_material_production_id.production_type', 'product_uom_qty')
    def _compute_production_type(self):
        """Get production type from related manufacturing"""
        for rec in self:
            rec.production_type = rec.raw_material_production_id.production_type

    @api.multi
    def _compute_let_modify(self):
        """
        Check whether stock moves can be
        edited in the form view based on the
        mrp type in company settings
        :return: None
        """
        company = self.sudo().env.user.company_id
        for rec in self:
            rec.let_modify = company.mrp_type == 'dynamic'

    @api.multi
    def _calculate_total_cost(self):
        """
        Calculates total inventory value
        for the passed move record-set
        :return: None
        """
        total_cost = 0
        for consumed_move in self:
            total_cost += sum(x.inventory_value for x in consumed_move.quant_ids if x.qty > 0)
        return total_cost

    @api.onchange('product_id')
    def _onchange_product_id_set_location(self):
        if self.env.context.get('manufacturing_move_line') or self.raw_material_production_id:
            src_location = self.product_id.product_tmpl_id.production_location_id
            if src_location:
                self.location_id = src_location
            self.location_dest_id = self.product_id.property_stock_production.id

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def action_done(self):
        """
        Force accounting dates on stock moves that have
        related production and are passed in one batch
        :return: super of action_done
        """
        manufacturing_order = self.mapped('raw_material_production_id') | self.mapped('production_id')
        if len(manufacturing_order) > 1:
            raise exceptions.UserError(_('Negali būti susijęs daugiau nei vienas gamybos užsakymas.'))
        if manufacturing_order and manufacturing_order[0].force_accounting_date:
            force_date = manufacturing_order[0].accounting_date
            force_date_localized = manufacturing_order[0].localized_accounting_date
            for rec in self:
                rec.date_expected = force_date
                rec.date = force_date
            super(StockMove, self.with_context(force_period_date=force_date_localized)).action_done()
            for rec in self:
                rec.date = force_date
                if rec.location_id.usage == 'production' and rec.location_dest_id.usage == 'internal':
                    rec.quant_ids.sudo().write({'in_date': force_date})
        else:
            super(StockMove, self).action_done()
        for rec in self.filtered(lambda x: x.product_id.type != 'consu'):
            total_qty = sum(rec.quant_ids.mapped('qty'))
            # Do no check small precision differences (Check that is meant to break and help us find another bug)
            if tools.float_compare(rec.product_uom_qty, total_qty, precision_digits=0):
                raise exceptions.ValidationError(
                    _('Nepavyko patvirtinti sandėlio judėjimo, nesutampa originalus ir perduodamas kiekis')
                )

    @api.multi
    def _auto_create_lot_numbers(self):
        """
        If current stock move has tracking,
        set barcode codes on it
        :return: None
        """
        for rec in self:
            if rec.product_id.tracking == 'lot':
                code = self.env['ir.sequence'].next_by_code('stock.production.lot.number')
                rec.on_barcode_scanned(code)
            if rec.product_id.tracking == 'serial':
                for i in range(int(rec.product_uom_qty - rec.quantity_done)):
                    code = self.env['ir.sequence'].next_by_code('stock.production.serial.number')
                    rec.on_barcode_scanned(code)

    @api.multi
    def save(self):
        for rec in self:
            if not rec.active_move_lot_ids:
                continue
            precision = {'precision_rounding': rec.product_id.uom_id.rounding or 0.01}
            if any(not (l.lot_id or tools.float_is_zero(l.quantity_done, **precision)) for l in
                   rec.active_move_lot_ids):
                raise exceptions.ValidationError(_('Jums reikia nurodyti naudojamą serijinį numerį'))
        return super(StockMove, self).save()

    @api.multi
    def _get_accounting_data_for_valuation(self):
        journal_id, acc_src, acc_dest, acc_valuation = super(StockMove, self)._get_accounting_data_for_valuation()
        if self.surplus_production_id:
            surplus_account = self.product_id.stock_surplus_account_id
            if not surplus_account:
                category = self.product_id.categ_id
                while category.parent_id and not category.stock_surplus_account_categ_id:
                    category = category.parent_id
                surplus_account = category.stock_surplus_account_categ_id or \
                                  self.env.user.sudo().company_id.default_stock_surplus_account_id
            if not surplus_account:
                raise exceptions.UserError(
                    _('Nenustatyta atsargų pertekliaus sąskaita produktui %s') % self.product_id.name)
            acc_src = surplus_account.id
        return journal_id, acc_src, acc_dest, acc_valuation

    # Scanning methods ------------------------------------------------------------------------------------------------

    @api.onchange('barcode')
    def onchange_barcode(self):
        if self.barcode:
            self.on_barcode_scanned(self.barcode)
            self.barcode = ''

    @api.one
    def on_barcode_scanned(self, barcode):
        if not barcode:
            return
        if not self.env.user.has_group('stock.group_production_lot'):
            return
        if self.production_id.state == 'done':
            return
        barcode = barcode.strip()
        product_serial = self.env['stock.production.lot'].search([('name', '=', barcode),
                                                                  ('product_id', '=', self.product_id.id)
                                                                  ], limit=1)
        if product_serial:
            serial_id = product_serial.id
            if 'default_picking_id' in self._context and serial_id in self.env['stock.picking'].browse(
                    self._context['default_picking_id']).pack_operation_pack_ids.filtered(
                lambda r: r.processed_boolean).mapped('package_id.quant_ids.lot_id.id'):
                self.scan_status_text = _('Nuskenuotas <%s> SN jau pridėtas pakuotėje.') % barcode
                self.scan_status = 0
                return
            elif 'default_picking_id' in self._context and serial_id in self.env['stock.picking'].browse(
                    self._context['default_picking_id']).pack_operation_product_ids.mapped('pack_lot_ids').filtered(
                lambda r: r.qty > 0).mapped('lot_id.id'):
                # FIXME: should use ^ float_compare (with what precision?) ?
                self.scan_status_text = _('Nuskenuotas <%s> SN jau pridėtas.') % barcode
                self.scan_status = 0
                return
            for line in self.active_move_lot_ids:
                if line.lot_id.id == serial_id:
                    if line.quantity_done >= line.quantity:
                        self.scan_status_text = _('SN <%s> jau nuskenuotas.') % product_serial.name
                        self.scan_status = 0
                        return
                    else:
                        line.quantity_done += 1
                        self.scan_status_text = _('Sėkmingai pridėtas <%s> SN numeris.') % product_serial.name
                        self.scan_status = 1
                        return
            quants = self.env['stock.quant'].search([('lot_id', '=', serial_id)])
            if quants:
                lot = quants.filtered(lambda r: r.product_id.id == self.product_id.id)
                if not lot:
                    self.scan_status_text = (_('Skenuotas <%s> SN priklauso kitam produktui (%s).')
                                             % (barcode, quants[0].product_id.name))
                    self.scan_status = 0
                    return
                lot = quants.filtered(lambda r: r.location_id.id == self.location_id.id)
                if not lot and self.location_id:
                    self.scan_status_text = (_('Skenuotas <%s> SN yra kitoje lokacijoje (%s).')
                                             % (barcode, quants[0].location_id.display_name))
                    if self.env.user.is_accountant():
                        self.scan_status_text += '\n%s (ID: %s) != %s (ID: %s)' % (quants[0].location_id.display_name,
                                                                                   quants[0].location_id.id,
                                                                                   self.location_id.display_name,
                                                                                   self.location_id.id)
                    self.scan_status = 0
                    return
                # TODO: handle quantities on lot / serial tracking. Also related to the found quants already ?
                vals = {'lot_id': product_serial.id,
                        'quantity': 1,
                        'quantity_done': 1,
                        'done_wo': True}
                self.active_move_lot_ids |= self.active_move_lot_ids.new(vals)
                self.scan_status_text = _('Pridėtas naujas SN <%s>.') % product_serial.name
                self.scan_status = 2
                return
            else:
                if product_serial.product_id.id != self.product_id.id:
                    self.scan_status_text = (_('Skenuotas SN <%s> priskirtas kitam produktui (%s).')
                                             % (barcode, product_serial.product_id.name))
                    self.scan_status = 0
                    return
                product_serial._update_expiry_dates()
                qty = self.product_uom_qty - self.quantity_done \
                    if self.product_id.product_tmpl_id.tracking == 'lot' else 1
                vals = {'lot_id': product_serial.id,
                        'quantity': qty,
                        'quantity_done': qty,
                        'done_wo': True}
                self.active_move_lot_ids |= self.active_move_lot_ids.new(vals)
                self.scan_status_text = _('Pridėtas naujas SN <%s>.') % product_serial.name
                self.scan_status = 2
                return
        else:
            products = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
            if products:
                self.scan_status_text = (_('Nuskenuotas produkto barkodas <%s>, turėtumėte nuskenuoti SN.') % barcode)
                self.scan_status = 0
                return
            if not self.env.user.company_id.scan_new_serial:
                self.scan_status_text = _('Nuskenuotas SN <%s> nerastas.') % barcode
                self.scan_status = 0
                return
            if self._context.get('no_create', False):
                return
            cdate = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            self.sudo()._cr.execute(
                u'''INSERT INTO stock_production_lot (create_date, write_date, create_uid, write_uid, name, product_id) VALUES ('%s', '%s', %s, %s, '%s', %s)''' %
                (cdate, cdate, self._uid, self._uid, barcode, self.product_id.id))
            new_serial = self.env['stock.production.lot'].search([('name', '=', barcode),
                                                                  ('product_id', '=', self.product_id.id)
                                                                  ], limit=1)
            new_serial._post_manual_create()
            qty = self.product_uom_qty - self.quantity_done if self.product_id.product_tmpl_id.tracking == 'lot' else 1
            vals = {'lot_id': new_serial.id,
                    'quantity': qty,
                    'quantity_done': qty,
                    'done_wo': True}
            self.active_move_lot_ids |= self.active_move_lot_ids.new(vals)
            self.scan_status_text = _('Naujas SN <%s> pridėtas.') % new_serial.name
            self.scan_status = 2
