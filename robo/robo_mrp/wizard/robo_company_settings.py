# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class RoboCompanySettings(models.TransientModel):
    _inherit = 'robo.company.settings'

    politika_gamybos_apskaita = fields.Selection(
        [('off', 'Išjungta'), ('on', 'Įjungta')], string='Gamybos apskaita')

    mrp_type = fields.Selection([
        ('static', 'Fiksuota gamyba'),
        ('dynamic', 'Kintanti gamyba'),
    ], string='Gamybos tipas', default='dynamic')

    # Recursive production fields
    enable_recursive_bom_production = fields.Boolean(
        string='Įgalinti sudėtinių komplektacijų gamybą'
    )
    enable_production_modification_rules = fields.Boolean(
        string='Įgalinti gamybos modifikavimo taisykles',
    )
    enable_bom_expiry_dates = fields.Boolean(
        string='Įgalinti komplektacijų galiojimo datas'
    )
    recursive_bom_production_mode = fields.Selection(
        [('explode_none', 'Neskleisti sudėtinių komponentų'),
         ('explode_all', 'Visada išskleisti sudėtinius komponentus'),
         ('explode_no_stock', 'Išskleisti sudėtinius komponentus trūkstant atsargų'),
         ], string='Sudėtiniu komplektacijų gaminimo būdas',
        default='explode_none'
    )

    autocreate_lot_number = fields.Boolean(
        string='Gamybos metu automatiškai sukurti partijos numerį', default=False,
        help='Naujai sukurtiems produktams, kurie sekami partijos numeriais, '
             'automatiškai kurti partijos numerius gamybos metu.'
    )
    autocreate_serial_number = fields.Boolean(
        string='Gamybos metu automatiškai sukurti SN numerį', default=False,
        help='Naujai sukurtiems produktams, kurie sekami SN numeriais, '
             'automatiškai kurti SN numerius gamybos metu.'
    )

    production_lot_series = fields.Char(required=True)
    production_lot_number = fields.Integer(required=True)
    production_lot_length = fields.Integer(required=True)
    production_lot_actual_number = fields.Char(compute='_compute_lot_actual_number')  # TODO

    serial_num_series = fields.Char(required=True)
    serial_num_number = fields.Integer(required=True)
    serial_num_length = fields.Integer(required=True)
    serial_num_actual_number = fields.Char(compute='_compute_serial_actual_number')  # TODO

    default_mrp_production_location_src_id = fields.Many2one(
        'stock.location', string='Gamybos žaliavų vieta'
    )
    default_mrp_production_location_dest_id = fields.Many2one('stock.location', string='Gamybos gaminių vieta')

    enable_production_surplus = fields.Boolean(
        string='Leisti gamybą su pertekliumi',
        help='Nepavykus užrezervuoti gamybos kurti trūkstamus '
             'atsargų judėjimus ir rezervuoti gamybą su pertekliumi',
        groups='robo_basic.group_robo_premium_accountant'
    )
    disable_default_production_locations = fields.Boolean(string='Disable default production locations')

    @api.one
    @api.depends('production_lot_series', 'production_lot_number', 'production_lot_number')
    def _compute_lot_actual_number(self):
        self.production_lot_actual_number = str(self.production_lot_series or '') + str(
            self.production_lot_number or 1).zfill(
            self.production_lot_length)

    @api.one
    @api.depends('serial_num_series', 'serial_num_number', 'serial_num_number')
    def _compute_serial_actual_number(self):
        self.serial_num_actual_number = str(self.serial_num_series or '') + str(self.serial_num_number or 1).zfill(
            self.serial_num_length)

    @api.model
    def default_get(self, field_list):
        res = super(RoboCompanySettings, self).default_get(field_list)
        company = self.env.user.sudo().company_id
        if self.env.user.is_accountant():
            res['politika_gamybos_apskaita'] = company.politika_gamybos_apskaita
            res['enable_production_surplus'] = self.env.user.sudo().company_id.enable_production_surplus
        if self.env.user.is_manager():
            res.update({
                'mrp_type': company.mrp_type,
                'autocreate_lot_number': company.autocreate_lot_number,
                'autocreate_serial_number': company.autocreate_serial_number,
                'default_mrp_production_location_src_id': company.default_mrp_production_location_src_id.id,
                'default_mrp_production_location_dest_id': company.default_mrp_production_location_dest_id.id,
                'enable_recursive_bom_production': company.enable_recursive_bom_production,
                'enable_production_modification_rules': company.enable_production_modification_rules,
                'recursive_bom_production_mode': company.recursive_bom_production_mode,
                'enable_bom_expiry_dates': company.enable_bom_expiry_dates,
                'disable_default_production_locations': company.disable_default_production_locations,
            })
            res.update(self.get_lot_number_data())
        return res

    @api.model
    def get_lot_number_data(self):
        res = {}
        serial_number_sequence_code = 'stock.production.serial.number'
        serial_number_sequence = self.env['ir.sequence'].search([('code', '=', serial_number_sequence_code)], limit=1)
        if serial_number_sequence:
            series, length, number = serial_number_sequence.get_prefix_size_number()
            res.update({'serial_num_series': series,
                        'serial_num_length': length,
                        'serial_num_number': number,
                        })
        lot_number_sequence_code = 'stock.production.lot.number'
        lot_number_sequence = self.env['ir.sequence'].search([('code', '=', lot_number_sequence_code)], limit=1)
        if lot_number_sequence:
            series, length, number = lot_number_sequence.get_prefix_size_number()
            res.update({'production_lot_series': series,
                        'production_lot_length': length,
                        'production_lot_number': number,
                        })
        return res

    @api.model
    def _get_company_policy_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_policy_field_list()
        res.extend((
            'politika_gamybos_apskaita',
            'enable_production_surplus',
            'disable_default_production_locations',
        ))
        return res

    @api.model
    def _get_company_info_field_list(self):
        res = super(RoboCompanySettings, self)._get_company_info_field_list()
        res.extend((
            'mrp_type',
            'enable_recursive_bom_production',
            'enable_production_modification_rules',
            'recursive_bom_production_mode',
            'enable_bom_expiry_dates',
            'autocreate_lot_number',
            'autocreate_serial_number',
            'default_mrp_production_location_src_id',
            'default_mrp_production_location_dest_id',
        ))
        return res

    @api.multi
    def save_numberings(self):
        super(RoboCompanySettings, self).save_numberings()
        if self._context.get('production_lot'):
            self.set_production_number()
        if self._context.get('production_serial'):
            self.set_production_serial_number()

    @api.multi
    def set_production_number(self):
        self.ensure_one()
        sequence_code = 'stock.production.lot.number'
        sequence_id = self.env['ir.sequence'].sudo().search([('code', '=', sequence_code)])
        if sequence_id:
            example_number = str(self.production_lot_series or '') + str(self.production_lot_number or 1).zfill(
                self.production_lot_length)
            if self.sudo().env['stock.production.lot'].search_count([('name', '=', example_number)]):
                raise exceptions.UserError(_('Toks partijos numeris jau egzistuoja.'))
            sequence_id.write({
                'prefix': self.production_lot_series,
                'padding': self.production_lot_length,
                'number_next_actual': self.production_lot_number
            })

    @api.multi
    def set_production_serial_number(self):
        self.ensure_one()
        sequence_code = 'stock.production.serial.number'
        sequence_id = self.env['ir.sequence'].sudo().search([('code', '=', sequence_code)])
        if sequence_id:
            example_number = str(self.serial_num_series or '') + str(self.serial_num_number or 1).zfill(
                self.serial_num_length)
            if self.sudo().env['stock.production.lot'].search_count([('name', '=', example_number)]):
                raise exceptions.UserError(_('Toks SN numeris jau egzistuoja.'))
            sequence_id.write({
                'prefix': self.serial_num_series,
                'padding': self.serial_num_length,
                'number_next_actual': self.serial_num_number
            })
