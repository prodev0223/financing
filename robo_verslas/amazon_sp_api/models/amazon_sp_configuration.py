# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, tools, _
from dateutil.relativedelta import relativedelta
from .. import amazon_sp_api_tools as at
from datetime import datetime


class AmazonSPConfiguration(models.Model):
    _name = 'amazon.sp.configuration'
    _description = _('Model that stores SP API configuration data')

    # Application credentials
    application_arn = fields.Char(string='Application ARN', groups='base.group_system')
    application_key = fields.Char(string='Application identifier', groups='base.group_system')
    # LWA credentials
    lwa_client_id = fields.Char(string='LWA ID', groups='base.group_system')
    lwa_client_secret = fields.Char(string='LWA Secret', groups='base.group_system')
    # IAM credentials
    access_key_id = fields.Char(string='AWS Access key ID', groups='base.group_system')
    secret_key = fields.Char(string='AWS Secret key', groups='base.group_system')

    # Configuration fields
    strict_batch_creation = fields.Boolean(
        string='Only create the invoice if all batch orders pass the validation',
        default=True,
    )
    accounting_threshold_date = fields.Date(string='Accounting threshold date')
    order_creation_interval = fields.Selection(
        [('monthly', 'Monthly'), ('weekly', 'Weekly'), ('daily', 'Daily')],
        string='Order creation interval', default='weekly'
    )
    create_individual_order_invoices = fields.Boolean(
        string='Create separate invoice for each Amazon order', default=True,
        help='If checked, separate invoice will be created for each order and order ID will be used as invoice number'
    )
    next_order_creation_date = fields.Date(string='Next order creation date')
    integration_type = fields.Selection(
        [('sum', 'Summable'), ('qty', 'Quantitative')],
        string='Integration type', default='sum',
        inverse='_set_integration_type'
    )
    order_date_to_use = fields.Selection([
        ('purchase_date', 'Purchase date'), ('shipment_date', 'Shipment date'), ('latest_date', 'Latest date')],
        string='Order date to use', help='Date that is used in the invoice creation', default='purchase_date'
    )

    # Optional inclusion fields
    include_order_commission_fees = fields.Boolean(
        string='Include order commission fees into invoices')
    include_order_shipping_fees = fields.Boolean(
        string='Include order shipping fees into invoices')
    include_order_gift_wrap_fees = fields.Boolean(
        string='Include order gift wrap fees into invoices')
    include_order_promotion_discounts = fields.Boolean(
        string='Include order discounts into invoices'
    )
    include_order_tax = fields.Boolean(
        string='Include Amazon passed taxes into invoices'
    )

    # Other API fields
    api_state = fields.Selection([
        ('not_initiated', 'API is disabled'),
        ('failed', 'Failed to configure the API'),
        ('partially_working', 'Some of the region keys are expired/failed'),
        ('working', 'API is working'),
    ], string='State', compute='_compute_api_state')

    region_ids = fields.One2many(
        'amazon.sp.region', 'configuration_id', string='Amazon regions',
    )

    order_fulfillment_channels = fields.Selection([
        ('MFN', 'Fulfilled by seller'),
        ('AFN', 'Fulfilled by Amazon'),
        ('all_channels', 'Fulfilled by any channel'),
    ], string='Order fulfillment type', default='all_channels')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('integration_type')
    def _check_integration_type(self):
        """Ensure that quantitative integration cannot be activated if robo_stock module is not installed"""
        robo_stock_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])])
        for rec in self:
            if rec.integration_type == 'quantitative' and not robo_stock_installed:
                raise exceptions.ValidationError(
                    _('Quantitative integration cannot be enabled - '
                      'stock module is not installed in the system. Contact your accountant')
                )

    @api.multi
    def _set_integration_type(self):
        """
        Modify default system product and category
        based on Amazon integration type.
        """
        sum_category = self.env.ref('l10n_lt.product_category_30')
        qty_category = self.env.ref('l10n_lt.product_category_2')

        product = self.env['product.product'].with_context(lang='lt_LT').search(
            [('name', '=', at.STATIC_SUM_SYSTEM_PRODUCT_NAME)]
        )

        account_2040 = self.env.ref('l10n_lt.1_account_195').id
        account_6000 = self.env.ref('l10n_lt.1_account_438').id

        # Get the groups to set
        qty_integration = self.sudo().env.ref('amazon_sp_api.group_amazon_sp_api_quantitative_integration')
        manager_group = self.sudo().env.ref('robo_basic.group_robo_premium_manager')

        # Assign the values based on type
        for rec in self:
            if rec.integration_type == 'sum':
                sum_category.write({'property_account_expense_categ_id': account_2040})
                product.write({'acc_product_type': 'product', 'categ_id': sum_category.id})
                # On sum activation, remove the inheritance, and clear the users from qty group
                manager_group.write({'implied_ids': [(3, qty_integration.id)]})
                qty_integration.write({'users': [(5,)]})
            else:
                manager_group.write({'implied_ids': [(4, qty_integration.id)]})
                sum_category.write({'property_account_expense_categ_id': account_6000})
                product.write({'acc_product_type': 'service', 'categ_id': qty_category.id})
                # Create additional objects
                self.env['amazon.sp.inventory.act.type'].init_create_inventory_act_types()

    @api.multi
    def _compute_api_state(self):
        """Compute API state based on region states"""
        for rec in self:
            api_state = 'not_initiated'
            if rec.region_ids:
                # Get all of the different states in a set
                states = set(rec.region_ids.mapped('api_state'))
                if 'failed' in states or 'expired' in states:
                    # If failed and expired is in states, check whether there's
                    # any working region, if not, whole configuration is failed
                    # otherwise it's partially working
                    api_state = 'partially_working' if 'working' in states else 'failed'
                elif 'working' in states:
                    api_state = 'working'
            rec.api_state = api_state

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def action_open_regions(self):
        """
        Returns action that opens SP-API region tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('amazon_sp_api.action_open_amazon_sp_region').read()[0]
        return action

    @api.multi
    def action_open_marketplaces(self):
        """
        Returns action that opens SP-API marketplace tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('amazon_sp_api.action_open_amazon_sp_marketplace').read()[0]
        return action

    @api.multi
    def action_open_tax_rules(self):
        """
        Returns action that opens SP-API tax rule tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('amazon_sp_api.action_open_amazon_sp_tax_rule').read()[0]
        return action

    @api.multi
    def name_get(self):
        """Returns static string as name get for all of the records"""
        return [(x.id, _('Amazon SP-API configuration')) for x in self]

    @api.multi
    def check_configuration(self, ignore_api_state=False):
        """
        Checks whether Amazon configuration is properly configured
        :return: True/False
        """
        self.ensure_one()
        configuration_initiated = self.sudo().application_arn and self.sudo().application_key and \
            self.sudo().lwa_client_id and self.sudo().lwa_client_secret and self.sudo().access_key_id and \
            self.sudo().secret_key and self.accounting_threshold_date and self.integration_type
        if not ignore_api_state:
            configuration_initiated = configuration_initiated and self.api_state in ['working', 'partially_working']
        return configuration_initiated

    @api.model
    def get_redirect_url(self):
        """Returns base redirect URL for Amazon operations"""
        base_redirect_url = self.sudo().env['ir.config_parameter'].get_param('amazon_sp_api_redirect_url')
        if not base_redirect_url:
            raise exceptions.ValidationError(
                _('Amazon SP-API settings are not configured. Contact administrators')
            )
        return '{}/amazon_sp_api_auth'.format(base_redirect_url)

    @api.model
    def get_oauth_exchange_url(self):
        """Returns base oauth token exchange URL for Amazon operations"""
        exchange_url = self.sudo().env['ir.config_parameter'].get_param('amazon_oauth_exchange_endpoint')
        if not exchange_url:
            raise exceptions.ValidationError(
                _('Amazon SP-API settings are not configured. Contact administrators')
            )
        return exchange_url

    @api.multi
    def check_order_creation_date(self):
        """
        Check order creation day - if creation day is earlier or equal to current day
        creation is allowed.
        :return: True if creation should be allowed, otherwise False
        """
        self.ensure_one()
        next_date = self.next_order_creation_date
        # Do not create the orders if date is not set
        if next_date:
            current_date_dt = datetime.utcnow()
            next_date_dt = datetime.strptime(next_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            if next_date_dt <= current_date_dt:
                return True
        return False

    @api.multi
    def set_order_creation_date(self):
        """
        Sets next order creation date based on the interval
        that is set in Amazon configuration
        :return: None
        """
        self.ensure_one()
        next_date = self.next_order_creation_date
        interval = self.order_creation_interval
        next_date_dt = datetime.strptime(next_date, tools.DEFAULT_SERVER_DATE_FORMAT) if next_date \
            else datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Determine next order creation date
        if interval == 'monthly':
            next_date_dt = next_date_dt + relativedelta(months=1)
        else:
            days_to_add = 7 if interval == 'weekly' else 1
            next_date_dt = next_date_dt + relativedelta(days=days_to_add)

        # Write next order creation date to the settings
        self.write({
            'next_order_creation_date': next_date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
        })

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def create(self, vals):
        """
        Ensure that only one SP-API configuration exists in the system
        :param vals: record values (dict)
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('You cannot create several Amazon SP-API configuration records!'))
        return super(AmazonSPConfiguration, self).create(vals)

