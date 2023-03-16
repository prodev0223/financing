# -*- encoding: utf-8 -*-
from odoo import models, api, fields


class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    # MTO + MTS fields
    mts_mto_procurement_id = fields.Many2one(
        'procurement.order',
        string='MTO+MTS Procurement',
        copy=False, index=True
    )
    mts_mto_procurement_ids = fields.One2many(
        'procurement.order',
        'mts_mto_procurement_id',
        string='Procurements'
    )

    @api.multi
    def get_mto_qty_to_order(self):
        """
        Calculates and returns MTO quantity
        for current rule stock location.
        :return: product QTY (float)
        """
        self.ensure_one()
        stock_location = self.rule_id.mts_rule_id.location_src_id.id
        proc_warehouse = self.with_context(location=stock_location)
        virtual_available = proc_warehouse.product_id.virtual_available
        qty_available = self.product_id.uom_id._compute_quantity(
            virtual_available, self.product_uom)

        if qty_available > 0:
            if qty_available >= self.product_qty:
                return 0.0
            else:
                return self.product_qty - qty_available
        return self.product_qty

    @api.multi
    def _check(self):
        """
        Extended method //
        If action is split procurement, execute
        extra checks on mts_mto procurements.
        :return: super of ProcurementOrder _check
        """
        self.ensure_one()
        if self.rule_id and self.rule_id.action == 'split_procurement':
            if all(x.state == 'cancel' for x in self.mts_mto_procurement_ids):
                self.write({'state': 'cancel'})
            elif all(x.state in ['done', 'cancel'] for x in self.mts_mto_procurement_ids):
                return True
        return super(ProcurementOrder, self)._check()

    @api.multi
    def check(self, autocommit=False):
        """
        Extended method //
        Execute recursive procurement checks if it contains
        mto_mts procurement ID.
        :param autocommit:
        :return: super of ProcurementOrder check
        """
        res = super(ProcurementOrder, self).check(autocommit=autocommit)
        for procurement in self:
            if procurement.mts_mto_procurement_id:
                procurement.mts_mto_procurement_id.check(autocommit=autocommit)
        return res

    @api.multi
    def get_mts_mto_procurement(self, rule, qty):
        """BACK-PORTED METHOD // Not edited"""
        self.ensure_one()
        origin = (self.group_id and (self.group_id.name + ":") or "") + \
                 (self.rule_id and self.rule_id.name or self.origin or "/")
        return {
            'name': self.name,
            'origin': origin,
            'product_qty': qty,
            'rule_id': rule.id,
            'mts_mto_procurement_id': self.id,
        }

    @api.multi
    def _run(self):
        """
        Extended method //
        :return: super of ProcurementOrder _run
        """
        self.ensure_one()
        if self.rule_id and self.rule_id.action == 'split_procurement':
            # If current record contains MTO+MTS
            # continue with unaltered execution
            if self.mts_mto_procurement_ids:
                return super(ProcurementOrder, self)._run()
            needed_qty = self.get_mto_qty_to_order()

            # Execute either MTS or MTO processes
            # Based on the quantity
            if needed_qty == 0.0:
                # Execute MTS process
                self.execute_mts_mto_process(self.rule_id.mts_rule_id, self.product_qty)
            elif needed_qty == self.product_qty:
                # Execute MTO process
                self.execute_mts_mto_process(self.rule_id.mto_rule_id, self.product_qty)
            else:
                mts_qty = self.product_qty - needed_qty
                self.execute_mts_mto_process(self.rule_id.mts_rule_id, mts_qty)
                self.execute_mts_mto_process(self.rule_id.mto_rule_id, needed_qty)

        # Continue with super
        return super(ProcurementOrder, self)._run()

    @api.multi
    def execute_mts_mto_process(self, mts_mto_rule, quantity):
        """
        Get the procurement vals, copy current record with
        new values and execute MTS or MTO process.
        :param mts_mto_rule: procurement.rule (record)
        :param quantity: quantity (float)
        :return: None
        """
        self.ensure_one()
        mts_mto_vals = self.get_mts_mto_procurement(mts_mto_rule, quantity)
        mts_mto_proc = self.copy(mts_mto_vals)
        mts_mto_proc.run()

    @api.multi
    def run(self, autocommit=False):
        if self._context.get('auto_set_done_procurements'):
            return self.write({'state': 'done'})
        else:
            return super(ProcurementOrder, self).run(autocommit=autocommit)

    def _prepare_purchase_order_line(self, po, supplier):
        res = super(ProcurementOrder, self)._prepare_purchase_order_line(po, supplier)
        if self.warehouse_id:
            res.update({
                'location_dest_id': self.warehouse_id.lot_stock_id.id
            })
        return res

    @api.multi
    def _prepare_purchase_order(self, partner):
        res = super(ProcurementOrder, self)._prepare_purchase_order(partner)
        if self.warehouse_id:
            res.update({
                'location_dest_id': self.warehouse_id.lot_stock_id.id
            })
        return res


ProcurementOrder()