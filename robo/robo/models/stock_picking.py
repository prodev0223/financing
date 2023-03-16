# -*- coding: utf-8 -*-


from odoo import api, models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    backorder_id = fields.Many2one(sequence=100)
    carrier_id = fields.Many2one(sequence=100)
    carrier_tracking_ref = fields.Char(sequence=100)
    company_id = fields.Many2one(sequence=100)
    date = fields.Datetime(sequence=100)
    group_id = fields.Many2one(sequence=100)
    delivery_type = fields.Selection(sequence=100)
    launch_pack_operations = fields.Boolean(sequence=100)
    max_date = fields.Datetime(sequence=100)
    message_is_follower = fields.Boolean(sequence=100)
    message_follower_ids = fields.One2many(sequence=100)
    message_partner_ids = fields.Many2many(sequence=100)
    message_channel_ids = fields.Many2many(sequence=100)
    message_last_post = fields.Datetime(sequence=100)
    min_date = fields.Datetime(sequence=100)
    move_lines = fields.One2many(sequence=100, copy=True)
    note = fields.Text(sequence=100)
    pack_operation_ids = fields.One2many(sequence=100)
    pack_operation_pack_ids = fields.One2many(sequence=100)
    pack_operation_product_ids = fields.One2many(sequence=100)
    picking_type_entire_packs = fields.Boolean(sequence=100)
    printed = fields.Boolean(sequence=100)
    purchase_id = fields.Many2one(sequence=100)
    recompute_pack_op = fields.Boolean(sequence=100)
    sale_id = fields.Many2one(sequence=100)
    weight_uom_id = fields.Many2one(sequence=100)
    message_needaction = fields.Boolean(sequence=100)
    move_type = fields.Selection(sequence=100)

    @api.multi
    def do_transfer(self):
        res = super(StockPicking, self).do_transfer()
        for rec in self.filtered(lambda x: not x.error):
            rec.force_picking_aml_analytics_prep()
        for rec in self.filtered(lambda x: x.error):
            rec.force_reverse_analytics_prep()
        return res

    @api.multi
    def force_picking_aml_analytics_prep(self):
        """
        Force analytics to picking move lines from the related invoice lines.
        Match related move lines by reference (picking name)
        :return: None
        """
        self.ensure_one()
        invoice_lines = self.mapped('invoice_ids.invoice_line_ids')
        if not invoice_lines:
            invoice_lines = self.sale_id.mapped('order_line.invoice_lines')

        # Apply extra filtering with a field introduced in this module
        invoice_lines = invoice_lines.filtered(
            lambda x: not x.product_id.product_tmpl_id.skip_analytic)

        # Different mapping is used here
        used_lines = self.env['account.move.line']
        move_lines = used_lines.sudo().search([('ref', '=', self.name)])
        for line in invoice_lines:
            used_lines |= line.force_picking_aml_analytics(move_lines, used_lines)

    def force_reverse_analytics_prep(self):
        """
        Force analytics to picking move lines from the related picking move lines.
        Match related move lines by reference (picking name)
        :return: None
        """

        self.ensure_one()
        MoveLine = self.env['account.move.line']

        active_id = self._context.get('active_id', False)
        if not active_id:
            return
        picking_to_reverse = self.env['stock.picking'].browse(active_id).exists()

        move_lines = MoveLine.sudo().search([('ref', '=', picking_to_reverse.name),
                                             ('analytic_account_id', '!=', False)])
        move_lines_to_apply = MoveLine.sudo().search([('ref', '=', self.name),
                                                      ('product_id.product_tmpl_id.skip_analytic', '=', False)])
        used_lines = MoveLine
        for line in move_lines_to_apply:
            used_lines |= line.force_reverse_analytics(move_lines, used_lines)
