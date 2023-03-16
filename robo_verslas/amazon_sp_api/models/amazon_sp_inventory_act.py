# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _


class AmazonSPInventoryAct(models.Model):
    _name = 'amazon.sp.inventory.act'
    _description = _('Model that is used to hold data about Amazon SP inventory acts')
    _inherit = ['mail.thread']

    name = fields.Char(string='Inventory name', compute='_compute_name')
    write_off_reason = fields.Selection([
        ('customerDamagedQuantity', 'Quantity damaged by customer'),
        ('warehouseDamagedQuantity', 'Quantity damaged in warehouse'),
        ('distributorDamagedQuantity', 'Quantity damaged by distributor'),
        ('carrierDamagedQuantity', 'Quantity damaged by carrier'),
        ('defectiveQuantity', 'Defective quantity'),
        ('expiredQuantity', 'Expired quantity'),
    ], string='Write-off reason', required=True, inverse='_set_write_off_reason')

    total_write_off_quantity = fields.Float(
        string='Total write-off quantity',
        compute='_compute_total_write_off_quantity',
    )
    state = fields.Selection([
        ('imported', 'Inventory act imported'),
        ('failed', 'Failed to create the act'),
        ('created', 'System inventory record created')],
        string='State', default='imported',
    )

    # Dates
    period_start_date = fields.Datetime(string='Period start', required=True)
    period_end_date = fields.Datetime(string='Period end', required=True)

    # Relational fields
    stock_inventory_id = fields.Many2one('stock.inventory', string='Related stock inventory')
    marketplace_id = fields.Many2one('amazon.sp.marketplace', string='Amazon marketplace', required=True)
    amazon_inventory_type_id = fields.Many2one('amazon.sp.inventory.act.type', string='Inventory act type')
    amazon_inventory_line_ids = fields.One2many(
        'amazon.sp.inventory.act.line',
        'amazon_inventory_id',
        string='Inventory lines',
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('amazon_inventory_line_ids', 'amazon_inventory_line_ids')
    def _compute_total_write_off_quantity(self):
        """Calculate total write-off quantity based on the lines"""
        for rec in self:
            rec.total_write_off_quantity = sum(rec.write_off_quantity for rec in rec.amazon_inventory_line_ids)

    @api.multi
    def _compute_name(self):
        """Compose a name for inventory act"""
        for rec in self:
            rec.name = _('SP Inventory - [{}] / [{}] - [{}]').format(
                rec.period_start_date, rec.period_end_date, rec.marketplace_id.code
            )

    @api.multi
    def _set_write_off_reason(self):
        """Get related inventory type based on the write off reason"""
        for rec in self:
            act_type = self.env['amazon.sp.inventory.act.type'].search(
                [('write_off_reason', '=', rec.write_off_reason)], limit=1
            )
            rec.amazon_inventory_type_id = act_type

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('period_end_date', 'marketplace_id', 'write_off_reason')
    def _check_inventory_act_integrity(self):
        """Ensure intersecting act for the same marketplace and reason will not be created"""
        for rec in self:
            intersection_domain = [
                ('id', '!=', rec.id),
                ('marketplace_id', '=', rec.marketplace_id.id),
                ('write_off_reason', '=', rec.write_off_reason),
                '|', '&',
                ('period_start_date', '<=', rec.period_start_date),
                ('period_end_date', '>=', rec.period_start_date),
                '&',
                ('period_start_date', '<=', rec.period_end_date),
                ('period_start_date', '>=', rec.period_start_date),
            ]
            if self.search_count(intersection_domain):
                raise exceptions.ValidationError(
                    _('Intersecting inventory act was found for period - {} / {}. Marketplace - [{}]').format(
                        rec.period_start_date, rec.period_end_date, rec.marketplace_id.code)
                )

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def create_inventory_write_off_prep(self):
        """
        Prepare Amazon inventory act objects for stock inventory creation.
        Records are validated and filtered out before creation.
        :return: None
        """

        # Get the configuration and check whether integration type is quantitative
        configuration = self.env['amazon.sp.api.base'].sudo().get_configuration()
        if not configuration or configuration.integration_type != 'qty':
            return

        # Filter out inventories before validation
        inventories = self.filtered(
            lambda x: x.state in ['imported', 'failed'] and not x.stock_inventory_id
        )
        # Check constraints, validate records and create stock inventory records
        validated_records = inventories.check_inventory_write_off_creation_constraints()
        for inventory in validated_records:
            inventory.create_inventory_write_off()

    @api.multi
    def check_inventory_write_off_creation_constraints(self):
        """
        Validate current Amazon inventory act record
        and ensure that all needed values are set
        before passing it to stock inventory creation
        :return: Validated Amazon inventories (recordset)
        """
        validated_records = self.env['amazon.sp.inventory.act']

        for rec in self:
            # Validate the parent fields
            error_template = str()
            if not rec.marketplace_id.activated:
                error_template += _('Related marketplace is not activated')
            if not rec.marketplace_id.location_id:
                error_template += _('Location is not set on related marketplace')

            inv_type = rec.amazon_inventory_type_id
            if not inv_type:
                error_template += _('Amazon inventory type is not defined or set')
            if not inv_type.stock_reason_line_id:
                error_template += _('Amazon inventory type stock reason line is not set')
            if not inv_type.alignment_committee_id:
                error_template += _('Amazon inventory type alignment committee is not set')

            # Validate the lines
            for line in rec.amazon_inventory_line_ids:
                if not line.amazon_product_id.product_id:
                    error_template += _(
                        'Line with ASIN {} does not have systemic product defined or set\n'
                    ).format(line.asin_product_code)

            # Post the message if there's any validation errors, otherwise append record to validated list
            if error_template:
                error_template = _('Failed to create stock inventory record, errors: \n\n') + error_template
                rec.post_message(error_template, state='failed')
            else:
                validated_records |= rec
        return validated_records

    @api.multi
    def create_inventory_write_off(self):
        """
        Creates stock inventory records from current Amazon
        SP inventory act data.
        :return: None
        """
        self.ensure_one()

        # Get the default values
        inventory_type = self.amazon_inventory_type_id
        inventory_location = self.marketplace_id.location_id
        stock_reason = inventory_type.stock_reason_line_id
        stock_reason_account = inventory_type.stock_reason_account_id or stock_reason.account_id
        alignment_committee = inventory_type.alignment_committee_id

        # Check if robo analytics is installed in the system
        analytic_account = None
        if self.marketplace_id.show_analytic_account_id_selection:
            analytic_account = self.marketplace_id.analytic_account_id

        # Prepare the name for the inventory
        name = _('Amazon Inventory [{}] / [{}]').format(
            self.marketplace_id.code, self.period_end_date
        )
        # Prepare inventory values
        inventory_lines = []
        inventory_values = {
            'name': name,
            'filter': 'partial',
            'komisija': alignment_committee.id,
            'reason_line': stock_reason.id,
            'account_id': stock_reason_account.id,
            'location_id': inventory_location.id,
            'date': self.period_end_date,
            'accounting_date': self.period_end_date,
            'line_ids': inventory_lines,
        }
        # Update the main values if account is set / analytics is installed
        if analytic_account:
            inventory_values.update({'account_analytic_id': analytic_account.id})

        # Prepare stock inventory lines based on sales
        for line in self.amazon_inventory_line_ids:
            product = line.amazon_product_id.product_id
            line_values = {
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'location_id': inventory_location.id,
                'consumed_qty': line.write_off_quantity * -1,
            }
            # Update the line if account is set / analytics is installed
            if analytic_account:
                line_values.update({'account_analytic_id': analytic_account.id})
            inventory_lines.append((0, 0, line_values))

        # Create inventory record
        try:
            inventory = self.env['stock.inventory'].create(inventory_values)
            # Try to confirm the inventory
            inventory.prepare_inventory()
            inventory.action_done()
            inventory.mark_validated()
        except Exception as e:
            # Rollback everything
            self.env.cr.rollback()
            self.env.all.todo = {}
            self.env.clear()
            # Compose the message and post it to inventory and commit the post
            body = _('Failed to create the stock inventory act due to following errors: {}').format(e.args[0])
            self.post_message(body, state='failed')
            if not tools.config.get('test_enable'):
                self.env.cr.commit()
            return

        self.write({'state': 'created', 'stock_inventory_id': inventory.id})
        if not tools.config.get('test_enable'):
            self.env.cr.commit()

    @api.model
    def post_message(self, body, state):
        """
        Post message to Amazon SP inventory act records
        :param body: message to-be posted (str)
        :param state: object state (str)
        :return: None
        """
        self.write({'state': state})
        for inventory in self:
            msg = {
                'body': body, 'front_message': True,
                'priority': 'low', 'message_type': 'notification',
            }
            # Use robo message post so front user can see the messages
            inventory.robo_message_post(**msg)
