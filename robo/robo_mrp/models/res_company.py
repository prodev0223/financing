# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    politika_gamybos_apskaita = fields.Selection([('off', 'Išjungta'), ('on', 'Įjungta')],
                                                 inverse='_set_politika_gamybos_apskaita',
                                                 string='Gamybos apskaita', default='off')

    mrp_type = fields.Selection([
        ('static', 'Fiksuota gamyba'),
        ('dynamic', 'Kintanti gamyba'),
    ], string='Gamybos tipas', default='dynamic')

    autocreate_lot_number = fields.Boolean(
        string='Automatiškai sugeneruoti gamybos partijos numerį'
    )
    autocreate_serial_number = fields.Boolean(
        string='Automatiškai sugeneruoti gamybos serijos numerį'
    )
    default_mrp_production_location_src_id = fields.Many2one(
        'stock.location', string='Gamybos žaliavų vieta'
    )
    default_mrp_production_location_dest_id = fields.Many2one(
        'stock.location', string='Gamybos gaminių vieta'
    )
    enable_production_surplus = fields.Boolean(
        string='Leisti gamybą su pertekliumi',
        help='Nepavykus užrezervuoti gamybos kurti trūkstamus atsargų judėjimus ir rezervuoti gamybą su pertekliumi'
    )
    enable_production_modification_rules = fields.Boolean(
        string='Įgalinti gamybos modifikavimo taisykles',
        inverse='_set_enable_production_modification_rules'
    )

    enable_recursive_bom_production = fields.Boolean(
        string='Įgalinti sudėtinių komplektacijų gamybą',
        inverse='_set_enable_recursive_bom_production'
    )
    recursive_bom_production_mode = fields.Selection(
        [('explode_all', 'Visada išskleisti sudėtinius komponentus'),
         ('explode_no_stock', 'Išskleisti sudėtinius komponentus trūkstant atsargų'),
         ('explode_none', 'Neskleisti sudėtinių komponentų'),
         ], string='Sudėtiniu komplektacijų gaminimo būdas',
    )

    enable_bom_expiry_dates = fields.Boolean(
        string='Įgalinti komplektacijų galiojimo datas',
        inverse='_set_enable_bom_expiry_dates'
    )

    disable_default_production_locations = fields.Boolean(
        compute='_compute_disable_default_production_locations',
        inverse='_set_disable_default_production_locations',
    )

    @api.multi
    def _compute_disable_default_production_locations(self):
        """Checks if default location disabling is activated"""
        self.ensure_one()
        disabled_loc = self.env['ir.config_parameter'].sudo().get_param(
            'disable_default_production_locations') == 'True'
        self.disable_default_production_locations = disabled_loc

    @api.multi
    def _set_disable_default_production_locations(self):
        """Update config parameter based on company settings value"""
        self.ensure_one()
        self.env['ir.config_parameter'].sudo().set_param(
            'disable_default_production_locations', str(self.disable_default_production_locations)
        )

    @api.multi
    def _set_politika_gamybos_apskaita(self):
        """ Add/remove access to Production menu """
        self.ensure_one()
        robo_mrp = self.env.ref('robo_mrp.group_robo_mrp')
        groups = self.env.ref('mrp.group_mrp_user')
        groups |= self.env.ref('robo_mrp.group_robo_mrp_bom_readonly')
        if self.politika_gamybos_apskaita == 'on':
            groups.sudo().write({'implied_ids': [(4, robo_mrp.id)]})
        else:
            groups.sudo().write({'implied_ids': [(3, robo_mrp.id)]})
            robo_mrp.sudo().write({'users': [(5,)]})

    @api.multi
    def _set_enable_production_modification_rules(self):
        """
        Add production modification group
        to base user on activation
        :return: None
        """
        # Reference needed groups
        modification_group = self.sudo().env.ref('robo_mrp.group_production_modification_rules')
        user_group = self.sudo().env.ref('base.group_user')

        for rec in self:
            if rec.enable_recursive_bom_production:
                user_group.write({'implied_ids': [(4, modification_group.id)]})
            else:
                # On deactivation, remove the inheritance, and clear the users
                user_group.write({'implied_ids': [(3, modification_group.id)]})
                modification_group.write({'users': [(5,)]})

    @api.multi
    def _set_enable_recursive_bom_production(self):
        """
        Add recursive production group
        to base user group on activation
        :return: None
        """

        # Reference needed groups
        recursive_bom_group = self.sudo().env.ref('robo_mrp.group_recursive_bom_production')
        user_group = self.sudo().env.ref('base.group_user')

        for rec in self:
            if rec.enable_recursive_bom_production:
                user_group.write({'implied_ids': [(4, recursive_bom_group.id)]})
            else:
                # On deactivation, remove the inheritance, and clear the users
                user_group.write({'implied_ids': [(3, recursive_bom_group.id)]})
                recursive_bom_group.write({'users': [(5,)]})

    @api.multi
    def _set_enable_bom_expiry_dates(self):
        """
        Add bom expiry date group
        to base user group on activation.
        If
        :return: None
        """
        # Reference needed groups
        expiry_date_group = self.sudo().env.ref('robo_mrp.group_bom_expiry_dates')
        user_group = self.sudo().env.ref('base.group_user')

        for rec in self:
            if rec.enable_bom_expiry_dates:
                user_group.write({'implied_ids': [(4, expiry_date_group.id)]})
            else:
                # On deactivation, remove the inheritance, and clear the users
                user_group.write({'implied_ids': [(3, expiry_date_group.id)]})
                expiry_date_group.write({'users': [(5,)]})
