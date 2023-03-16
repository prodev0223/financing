# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class EbayConfiguration(models.Model):
    _name = 'ebay.configuration'
    _description = _('Model that stores Ebay configuration data')

    # Configuration file can be extended in the future if
    # any API integration will be implemented.
    # Only sum integration is available at the moment
    integration_type = fields.Selection(
        [('sum', 'Summable'), ('qty', 'Quantitative')],
        string='Integration type', default='sum',
    )
    default_origin_country_id = fields.Many2one(
        'res.country', string='Default origin country',
    )
    default_journal_id = fields.Many2one(
        'account.journal', string='Default journal',
    )

    # Optional inclusion fields
    include_order_shipping_fees = fields.Boolean(
        string='Include order shipping fees into invoices',
        default=True,
    )
    include_order_collected_taxes = fields.Boolean(
        string='Include eBay passed taxes into invoices',
        default=True,
    )
    configured = fields.Boolean(compute='_compute_configured')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    def _compute_configured(self):
        """Check whether current configuration is set up"""
        for rec in self:
            rec.configured = rec.default_origin_country_id and rec.default_journal_id

    @api.multi
    @api.constrains('integration_type')
    def _check_integration_type(self):
        """Ensure that quantitative integration cannot be activated if robo_stock module is not installed"""
        robo_stock_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_stock'), ('state', 'in', ['installed', 'to upgrade'])])
        for rec in self:
            if rec.integration_type == 'qty' and not robo_stock_installed:
                raise exceptions.ValidationError(
                    _('Quantitative integration cannot be enabled - '
                      'stock module is not installed in the system. Contact your accountant')
                )

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def get_configuration(self):
        """Returns configuration record"""
        configuration = self.search([])
        if not configuration or not configuration.configured:
            raise exceptions.ValidationError(
                _('Configuration record does not exist, or mandatory fields are not set')
            )
        return configuration

    @api.multi
    def action_open_tax_rules(self):
        """
        Returns action that opens Ebay tax rule tree view.
        :return: JS action (dict)
        """
        self.ensure_one()
        action = self.env.ref('ebay.action_open_ebay_tax_rule').read()[0]
        return action

    @api.multi
    def name_get(self):
        """Returns static string as name get for all the records"""
        return [(x.id, _('Ebay configuration')) for x in self]

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def create(self, vals):
        """
        Ensure that only one Ebay configuration exists in the system
        :param vals: dict: record values
        :return: super of create method
        """
        if self.search_count([]):
            raise exceptions.ValidationError(_('You cannot create several eBay configuration records!'))
        return super(EbayConfiguration, self).create(vals)
