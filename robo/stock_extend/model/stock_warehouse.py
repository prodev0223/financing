# -*- coding: utf-8 -*-

from odoo import models, api, fields, exceptions
from odoo.tools.translate import _


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    mto_mts_management = fields.Boolean(
        'Use MTO+MTS rules',
        help='If this new route is selected on product form view, a '
             'purchase order will be created only if the virtual stock is '
             'less than 0 else, the product will be taken from stocks',
        inverse='_set_mto_mts_management'
    )
    mts_mto_rule_id = fields.Many2one('procurement.rule', string='MTO+MTS rule')

    @api.multi
    def _set_mto_mts_management(self):
        """
        Inverse //
        When the mto_mts_management is set, always update the routes,
        also if it's being activated and there is no rule - create it
        else if it's being deactivated and rule exists - unlink it.
        :return: None
        """
        for rec in self:
            # Create the rule
            if rec.mto_mts_management and not rec.mts_mto_rule_id:
                mts_mto_pull_vals = self.get_mts_mto_rule_vals()
                mts_mto_rule = self.env['procurement.rule'].create(mts_mto_pull_vals)
                rec.mts_mto_rule_id = mts_mto_rule
                # Update the routes
                rec.with_context(active_test=False)._update_routes()
            # Unlink the rule
            elif not rec.mto_mts_management and rec.mts_mto_rule_id:
                rec.mts_mto_rule_id.unlink()
                # Update the routes
                rec.with_context(active_test=False)._update_routes()

    @api.multi
    def get_mts_mto_rule_vals(self):
        """
        Search for default MTS+MTO route and rules.
        Check base constraints and return formatted
        data structure that can be passed to procurement.rule
        create method.
        :return: data (dict)
        """
        self.ensure_one()
        mts_mto_route = self.env.ref('stock_extend.route_mto_mts')
        # Check whether default route exists
        if not mts_mto_route:
            raise exceptions.ValidationError(_("Can't find any generic MTS+MTO route."))

        # Check whether MTO pull rule is set
        if not self.mto_pull_id:
            raise exceptions.ValidationError(_("Can't find MTO Rule on the warehouse."))

        # Search for MTS rules
        mts_rule = self.env['procurement.rule'].search(
            [('location_src_id', '=', self.lot_stock_id.id),
             ('route_id', '=', self.delivery_route_id.id)], limit=1
        )
        if not mts_rule:
            raise exceptions.ValidationError(_("Can't find MTS Rule on the warehouse."))

        # Return the dict of data/IDs
        return {
            'name': self._format_routename(route_type='mts_mto'),
            'route_id': mts_mto_route.id,
            'action': 'split_procurement',
            'mto_rule_id': self.mto_pull_id.id,
            'mts_rule_id': mts_rule.id,
            'warehouse_id': self.id,
            'location_id': self.mto_pull_id.location_id.id,
            'picking_type_id': self.mto_pull_id.picking_type_id.id,
        }

    def _get_mto_pull_rules_values(self, route_values):
        """
        Extended method //
        Prevent changing standard MTO rules' action from "move"
        :return super of StockWarehouse _get_mto_pull_rules_values
        """
        pull_rules_list = super(StockWarehouse, self)._get_mto_pull_rules_values(route_values)
        for pull_rule in pull_rules_list:
            pull_rule['action'] = 'move'
        return pull_rules_list

    @api.multi
    def _get_push_pull_rules_values(
            self, route_values, values=None, push_values=None, pull_values=None, name_suffix=''):
        """
        Extended method //
        :return super of StockWarehouse _get_push_pull_rules_values
        """
        self.ensure_one()
        res = super(StockWarehouse, self)._get_push_pull_rules_values(
            route_values, values=values, push_values=push_values,
            pull_values=pull_values, name_suffix=name_suffix)

        # Update the push/pull rules if management is activated
        if self.mto_mts_management:
            customer_locations = self._get_partner_locations()
            if customer_locations:
                location_id = customer_locations[0].id
                for pull in res[1]:
                    if pull['location_id'] == location_id:
                        pull_mto_mts = pull.copy()
                        pull_mto_mts_id = self.env['procurement.rule'].create(pull_mto_mts)
                        pull.update({
                            'action': 'split_procurement',
                            'mto_rule_id': pull_mto_mts_id.id,
                            'mts_rule_id': pull_mto_mts_id.id,
                            'sequence': 10
                        })
        return res

    @api.model
    def get_all_routes_for_wh(self):
        """
        Extended method //
        Update the routes with MTS+MTO route if management is activated
        :return super of StockWarehouse get_all_routes_for_wh
        """
        all_routes = super(StockWarehouse, self).get_all_routes_for_wh()
        if self.mto_mts_management and self.mts_mto_rule_id.route_id:
            all_routes |= self.mts_mto_rule_id.route_id
        return all_routes

    @api.multi
    def _update_name_and_code(self, name, code):
        """BACK-PORTED METHOD // Not edited"""
        res = super(StockWarehouse, self)._update_name_and_code(name, code)
        if not name:
            return res
        for warehouse in self.filtered('mts_mto_rule_id'):
            warehouse.mts_mto_rule_id.name = (
                warehouse.mts_mto_rule_id.name.replace(
                    warehouse.name, name, 1,
                )
            )
        return res

    def _get_route_name(self, route_type):
        """BACK-PORTED METHOD // Not edited"""
        names = {'mts_mto': _('MTS+MTO')}
        if route_type in names:
            return names[route_type]
        return super(StockWarehouse, self)._get_route_name(route_type)

    @api.multi
    def _update_routes(self):
        """
        Extended method //
        Update the routes based on mts_mto_rule_id
        :return updated super of StockWarehouse _update_routes
        """
        res = super(StockWarehouse, self)._update_routes()
        for rec in self:
            if rec.delivery_steps and rec.mts_mto_rule_id:
                rec.mts_mto_rule_id.location_id = rec.mto_pull_id.location_id
                mts_rule = self.env['procurement.rule'].search([
                    ('location_src_id', '=', rec.lot_stock_id.id),
                    ('route_id', '=', rec.delivery_route_id.id),
                ], limit=1)
                rec.mts_mto_rule_id.mts_rule_id = mts_rule
        return res


StockWarehouse()
