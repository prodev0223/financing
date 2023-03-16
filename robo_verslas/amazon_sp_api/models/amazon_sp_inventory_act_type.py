# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from .. import amazon_sp_api_tools as at


class AmazonSPInventoryActType(models.Model):
    _name = 'amazon.sp.inventory.act.type'
    _description = _('Model that is used to hold data about Amazon SP inventory act types')

    @api.model
    def _default_alignment_committee_id(self):
        """Returns default inventory alignment committee"""
        committee = self.env['alignment.committee'].sudo().search([
            ('state', '=', 'valid'), ('type', '=', 'inventory')],
            order='date DESC', limit=1
        )
        return committee

    name = fields.Char(string='Name', compute='_compute_name')
    write_off_reason = fields.Selection(
        at.INVENTORY_WRITE_OFF_REASONS,
        string='Write-off reason', required=True
    )

    stock_reason_line_id = fields.Many2one(
        'stock.reason.line', string='Stock reason line',
        inverse='_set_stock_reason_line_id'
    )
    stock_reason_account_id = fields.Many2one(
        'account.account', string='Stock reason account',
    )
    alignment_committee_id = fields.Many2one(
        'alignment.committee', string='Inventory alignment committee',
        default=_default_alignment_committee_id,
    )

    @api.multi
    def _compute_name(self):
        """Computes the display name for inventory act type"""
        for rec in self:
            rec.name = _('Inventory type: {}').format(rec.write_off_reason)

    @api.multi
    def _set_stock_reason_line_id(self):
        """Set default account ID when stock reason line is set"""
        for rec in self.filtered(lambda x: x.stock_reason_line_id and not x.stock_reason_account_id):
            rec.stock_reason_account_id = rec.stock_reason_line_id.account_id

    @api.multi
    @api.constrains('write_off_reason')
    def _check_write_off_reason(self):
        """Ensure that write-off reason for act type is unique"""
        for rec in self:
            if self.search_count([('write_off_reason', '=', rec.write_off_reason)]) > 1:
                raise exceptions.ValidationError(
                    _('You cant have two Amazon inventory act types with the same reason')
                )

    @api.model
    def init_create_inventory_act_types(self):
        """
        Creates inventory act types when the quantitative
        integration is enabled in the Amazon settings.
        :return: None
        """
        mapping = at.DEFAULT_INVENTORY_REASON_TO_STOCK_REASON_MAPPING
        for write_off_reason, name in at.INVENTORY_WRITE_OFF_REASONS:
            if self.search_count([('write_off_reason', '=', write_off_reason)]):
                continue
            # Form stock reason external ID
            stock_reason_ext_id = 'robo_stock.{}'.format(mapping.get(write_off_reason))
            stock_reason = self.env.ref(stock_reason_ext_id)

            self.create({
                'write_off_reason': write_off_reason,
                'stock_reason_line_id': stock_reason.id,
            })
