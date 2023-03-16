# -*- coding: utf-8 -*-from
from datetime import datetime
from odoo import models, fields, exceptions, api, _, tools
from odoo.addons.queue_job.job import job, identity_exact


class AmazonSPMarketplace(models.Model):
    _name = 'amazon.sp.marketplace'
    _description = _('Model that holds configuration for Amazon marketplaces')

    @api.model
    def _default_journal(self):
        """Get default invoice journal for the marketplace"""
        return self.env['account.journal'].search([('type', '=', 'sale')], limit=1)

    @api.model
    def _default_location(self):
        """Get default location for the marketplace"""
        return self.env['stock.location'].search([
            ('usage', '=', 'internal')], order='create_date desc', limit=1)

    # Identifier fields
    name = fields.Char(string='Marketplace name', inverse='_set_name')
    code = fields.Char(string='Marketplace code')
    country_code = fields.Char(string='Country code', inverse='_set_country_code')

    # Other fields
    state = fields.Selection([
        ('configured', 'Configured'),
        ('needs_configuration', 'Non-configured')],
        string='State', compute='_compute_state'
    )
    activated = fields.Boolean(string='Activated')
    marketplace_endpoint = fields.Char(required=True)

    # Sync dates
    order_api_sync_date = fields.Datetime(string='Order API Synchronization date')
    inventory_api_sync_date = fields.Datetime(string='Inventory API Synchronization date')

    # Relational fields
    partner_id = fields.Many2one('res.partner', string='Related partner')
    country_id = fields.Many2one('res.country', string='Marketplace country')
    region_id = fields.Many2one('amazon.sp.region', string='Region')

    journal_id = fields.Many2one(
        'account.journal', string='Invoice journal', required=True,
        domain="[('type', '=', 'sale')]", default=_default_journal,
    )
    # Related tax rules
    tax_rule_ids = fields.One2many(
        'amazon.sp.tax.rule', 'marketplace_id', string='Tax rules')

    # Extra fields that are used if robo analytic is installed
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        domain="[('account_type', 'in', ['income', 'profit'])]",
        string='Default analytic account'
    )
    show_analytic_account_id_selection = fields.Boolean(
        compute='_compute_show_analytic_account_id_selection'
    )

    # Extra fields that are used if robo stock is installed
    location_id = fields.Many2one(
        'stock.location', domain="[('usage','=','internal')]",
        default=_default_location, string='Location',
    )
    show_location_id_selection = fields.Boolean(
        compute='_compute_show_location_id_selection'
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _compute_show_analytic_account_id_selection(self):
        """Check whether analytic account ID field should be showed in the form view"""
        robo_analytic_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_analytic'), ('state', 'in', ['installed', 'to upgrade'])])
        for rec in self:
            rec.show_analytic_account_id_selection = robo_analytic_installed

    @api.multi
    def _compute_show_location_id_selection(self):
        """Check whether location ID field should be showed in the form view"""
        configuration = self.env['amazon.sp.api.base'].get_configuration(check_status=False)
        quantitative_integration = configuration.integration_type == 'qty'
        for rec in self:
            rec.show_location_id_selection = quantitative_integration

    @api.multi
    @api.depends('partner_id', 'country_id', 'activated')
    def _compute_state(self):
        """Determine marketplace state (it must have partner, country and be activated)"""
        for rec in self:
            rec.state = 'configured' if rec.partner_id and rec.country_id and rec.activated else 'needs_configuration'

    @api.multi
    def _set_country_code(self):
        """
        Set marketplace code based on the country code
        (Used when creating from the code)
        """
        for rec in self.filtered(lambda x: x.country_code):
            country = self.env['res.country'].search([('code', '=', rec.country_code)], limit=1)
            if not country:
                raise exceptions.UserError(_('Incorrect passed country code [%s]!') % rec.country_code)
            rec.country_id = country

    @api.multi
    def _set_name(self):
        """Create res.partner record based on marketplace name"""
        for rec in self.filtered('name'):
            partner_name = 'Amazon {}'.format(rec.name)
            # Search for the partner and create it if it's not found
            partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)
            if not partner:
                partner_vals = {'name': partner_name, 'kodas': partner_name, 'is_company': True, }
                partner = partner.create(partner_vals)
            rec.partner_id = partner

    # Constraints -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('code')
    def _check_code(self):
        """Ensure that every shop has unique marketplace code"""
        for rec in self:
            if self.search_count([('id', '!=', rec.id), ('code', '=', rec.code)]):
                raise exceptions.UserError(_('You cannot have two marketplaces with the same code!'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def action_open_tax_rules(self):
        """
        Returns action that opens SP-API tax rule tree view,
        filters domain to only include rules for current marketplace.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('amazon_sp_api.action_open_amazon_sp_tax_rule').read()[0]
        action['domain'] = ['|', ('marketplace_id', '=', False), ('marketplace_id', '=', self.id)]
        return action

    @api.multi
    @job
    def fetch_orders(self, threshold_date=None):
        if threshold_date is None:
            configuration = self.get_configuration()
            if not configuration:
                return
            threshold_date = configuration.accounting_threshold_date
        for marketplace in self:
            # Get current API sync date
            sync_date = marketplace.order_api_sync_date or threshold_date
            # Fetch the orders for the marketplace, intermediate creation
            # flag is passed thus orders are created inside of the loop
            api_get_orders_response = self.env['amazon.sp.api.orders'].api_get_orders(
                region=marketplace.region_id, date_from=sync_date,
                marketplaces=marketplace, intermediate_creation=True
            )
            # If whole periods was fetched, update the order sync date
            if api_get_orders_response['period_fetched']:
                # Only update api sync date if all of the orders were fetched in the period
                marketplace.write({
                    'order_api_sync_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                })
