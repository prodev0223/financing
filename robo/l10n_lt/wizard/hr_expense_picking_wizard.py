# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions
from datetime import datetime


class HrExpensePickingWizard(models.TransientModel):
    _name = 'hr.expense.picking.wizard'

    def _delivery_date(self):
        if self._context.get('expense_id', False):
            expense = self.env['hr.expense'].browse(self._context.get('expense_id', False))
            return expense.date
        return datetime.utcnow()

    def _expense_id(self):
        if self._context.get('expense_id', False):
            return self._context['expense_id']

    warehouse_id = fields.Many2one('stock.warehouse', string='Destination Warehouse', required=True)
    delivery_date = fields.Date(string='Delivery Date', default=_delivery_date, required=True)
    expense_id = fields.Many2one('hr.expense', string='Expense', default=_expense_id)

    @api.multi
    def create_delivery(self):
        if not self.expense_id:
            raise exceptions.UserError(_('Nepavyko rasti susijusių išlaidų'))
        if self.expense_id.product_id.type != 'product':
            raise exceptions.UserError(_('Jūs negalite kurti važtaraščio.'))
        pick_type_id = self.warehouse_id.in_type_id
        vals = {
            'picking_type_id': pick_type_id.id,
            'partner_id': self.expense_id.partner_id.id,
            'date': self.delivery_date,
            'origin': u'Expense: ' + self.expense_id.name,
            'location_dest_id': pick_type_id.default_location_dest_id.id,
            'location_id': self.expense_id.partner_id.property_stock_supplier.id,
            'company_id': self.expense_id.company_id.id,
            'move_lines': [(0, 0, {
                'product_id': self.expense_id.product_id.id,
                'date': self.delivery_date,
                'date_expected': self.delivery_date,
                'product_uom': self.expense_id.product_uom_id.id,
                'product_uom_qty': self.expense_id.quantity,
                'location_id': self.expense_id.partner_id.property_stock_supplier.id,
                'location_dest_id': pick_type_id.default_location_dest_id.id,
                'name': self.expense_id.product_id.name,
                'price_unit': self.expense_id.currency_id.with_context(date=self.delivery_date).compute(
                    self.expense_id.unit_amount, self.expense_id.company_id.currency_id, round=False),
            })]
        }
        picking = self.env['stock.picking'].create(vals)
        self.expense_id.picking_id = picking.id
        return {'type': 'ir.actions.act_window_close'}
