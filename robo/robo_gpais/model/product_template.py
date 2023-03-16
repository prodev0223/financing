# -*- coding: utf-8 -*-
import logging
from odoo import _, api, exceptions, fields, models, tools
from .gpais_commons import PRODUCT_TYPES, veiklosBudas_mapping


_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    gpais_product_code = fields.Char(string='GPAIS vidinis prekinio vieneto kodas', readonly=True, sequence=100)
    gpais_use_forced_product_code = fields.Boolean(string='Naudoti priverstinį GPAIS produkto kodą',
                                                   inverse='set_gpais_product_code',
                                                   help='Jei rankiniu būdu susikursite prekinį vienetą GPAIS sistemoje, nurodykite priverstinį kodą. '
                                                          'Visa pakuočių informacija bus imama iš GPAIS sistemoje esančių nustatymų '
                                                          'ir pakeista pakuočių informacija nebus perduota į GPAIS su produktų nustatymais.',
                                                   sequence=100,
                                                   )
    gpais_forced_product_code = fields.Char(string='Priverstinis GPAIS prekinio vieneto kodas',
                                            inverse='set_gpais_product_code',
                                            )
    gpais_product_type = fields.Selection(PRODUCT_TYPES, string='GPAIS produkto tipas')
    gpais_buitine_iranga = fields.Boolean(string='Buitinė įranga', lt_string='Buitinė įranga', default=False,
                                          sequence=100,
                                          )
    gpais_product_origin = fields.Selection([('supplier', 'Importuota (įvežta)'),
                                             ('production', 'Pagaminta'),
                                             ('guess', 'Leisti sistemai nuspręsti'),
                                             ], default='guess', string='Gavimo būdas (GPAIS ataskaitoms)',
                                            lt_string='Gavimo būdas (GPAIS ataskaitoms)')
    klasifikacija = fields.Many2one('gpais.klasifikacija', string='Klasifikacija')
    uzstatine_pakuote_ids = fields.One2many('uzstatine.pakuote', 'product_tmpl_id', string='Užstatinės pakuotės')
    package_update_date = fields.Date(string='Paskutinis pakuočių atnaujinimas', default=fields.Date.today,
                                      track_visibility='onchange', sequence=100)
    battery_update_date = fields.Date(string='Paskutinis baterijų atnaujinimas', default=fields.Date.today,
                                      track_visibility='onchange', sequence=100)
    gpais_info_update_date = fields.Date(string='Paskutinis produktų atnaujinimas', default=fields.Date.today,
                                         track_visibility='onchange', sequence=100,
                                         )
    date_to_market_from = fields.Date(string='Pradėta tiekti rinkai nuo',
                                      default=fields.Date.today,
                                      lt_string='Pradėta tiekti rinkai nuo',
                                      help="Data turi būti vėlesnė nei registracijos data GPAIS sistemoje",
                                      sequence=100,
                                      )
    date_to_market_until = fields.Date(string='Nustota tiekti rinkai nuo', default=False,
                                       lt_string='Nustota tiekti rinkai nuo',
                                       help="Data turi būti vėlesnė nei registracijos data GPAIS sistemoje",
                                       sequence=100,
                                       )
    num_battery_lines = fields.Integer(compute='_compute_num_lines')
    num_deposit_lines = fields.Integer(compute='_compute_num_lines')
    num_package_lines = fields.Integer(compute='_compute_num_lines')

    @api.one
    def _compute_num_lines(self):
        self.num_battery_lines = len(self.product_battery_line_ids)
        self.num_deposit_lines = len(self.uzstatine_pakuote_ids)
        self.num_package_lines = len(self.product_package_default_ids)

    @api.multi
    def write(self, vals):
        if any(val in ['gpais_product_code', 'date_to_market_from', 'date_to_market_until', 'gpais_product_type', 'gpais_product_origin'] for val in vals.keys()):
            vals['gpais_info_update_date'] = fields.Date.today()
        return super(ProductTemplate, self).write(vals)

    @api.multi
    def copy(self, default=None):
        return super(ProductTemplate, self.with_context(on_product_duplicate=True)).copy(default=default)

    @api.model
    def create(self, vals):
        return super(ProductTemplate, self.with_context(on_product_create=True)).create(vals)

    @api.multi
    def set_gpais_product_code(self):
        for rec in self:
            if rec.gpais_product_type:
                if rec.gpais_use_forced_product_code and rec.gpais_forced_product_code:
                    rec.gpais_product_code = rec.gpais_forced_product_code
                elif rec.default_code:
                    rec.gpais_product_code = str(rec.id) + '-' + rec.default_code
                else:
                    rec.gpais_product_code = False
            else:
                rec.gpais_product_code = False

    @api.multi
    def _set_default_code(self):
        res = super(ProductTemplate, self)._set_default_code()
        self.set_gpais_product_code()
        return res

    @api.multi
    @api.constrains('gpais_use_forced_product_code', 'default_code', 'gpais_product_type', 'gpais_forced_product_code')
    def _require_gpais_product_code(self):
        if self._context.get('skip_constraints'):
            return
        for rec in self:
            if rec.gpais_product_type:
                if rec.gpais_use_forced_product_code:
                    if not rec.gpais_forced_product_code:
                        raise exceptions.ValidationError(
                            _('Norint naudotis GPAIS, nurodykite vidinį arba priverstinį prekinio vieneto kodą.'))
                elif not (rec.default_code or rec.gpais_product_code):
                    raise exceptions.ValidationError(
                        _('Norint naudotis GPAIS, nurodykite vidinį arba priverstinį prekinio vieneto kodą.'))
            elif rec.gpais_use_forced_product_code:
                raise exceptions.ValidationError(
                    _('Naudojant priverstinį GPAIS kodą reikia nurodyti GPAIS produkto tipą.'))

    @api.multi
    @api.constrains('weight', 'gpais_product_type', 'gpais_use_forced_product_code')
    def _require_weight_for_gpais(self):
        if self._context.get('on_product_create') or self._context.get('on_product_duplicate'):
            return
        for rec in self:
            if rec.gpais_product_type and not rec.gpais_use_forced_product_code:
                if tools.float_is_zero(rec.weight / 1000, precision_digits=6):
                    raise exceptions.ValidationError(
                        _('Produktui [%s] %s nustatytas GPAIS produkto tipas, tačiau svoris nėra apibrėžtas arba mažesnis '
                          'nei 1 g') % (rec.default_code, rec.name)
                    )

    @api.multi
    @api.constrains('product_battery_line_ids')
    def _constrains_battery_use(self):
        """Check that battery lines using the same battery do not overlap in time"""
        err_msg = _('Negalite turėti tos pačios baterijos viename produkte tuo pačiu metu.')
        for rec in self:
            batteries = rec.mapped('product_battery_line_ids.battery_id')
            for battery in batteries:
                battery_lines = rec.product_battery_line_ids.filtered(lambda b: b.battery_id == battery)
                if len(battery_lines) > 1:
                    for idx, line_to_check in enumerate(battery_lines, 1):
                        date_to = line_to_check.date_to
                        date_from = line_to_check.date_from
                        for line in battery_lines[idx:]:
                            if date_to and not (line.date_from and date_to < line.date_from
                                                or line.date_to and date_to > line.date_to):
                                raise exceptions.ValidationError(err_msg)

                            if date_from and not (line.date_from and date_from < line.date_from
                                                  or line.date_to and date_from > line.date_to):
                                raise exceptions.ValidationError(err_msg)

                            if not date_to and date_from and line.date_from and line.date_from > date_from:
                                raise exceptions.ValidationError(err_msg)

                            if not date_from and date_to and line.date_to and line.date_to < date_to:
                                raise exceptions.ValidationError(err_msg)

                            if not date_from and not date_to and not line.date_from and not line.date_to:
                                raise exceptions.ValidationError(err_msg)

    @api.constrains('product_package_default_ids')
    def _check_product_package_default_package_savom_reikmem(self):
        for rec in self:
            savom_reikmems = rec.mapped('product_package_default_ids.package_id.savom_reikmem')
            if any(savom_reikmems) and not all(savom_reikmems):
                raise exceptions.ValidationError(_('Visos važtaraščio pakuotės turi būti naudojamos savom reikmėm.'))

    # run for existing databases
    @api.model
    def _setup_gpais_product_types(self):
        self.search([('product_electronics_category', '!=', False), ('type', '=', 'product')]).write(
            {'gpais_product_type': 'elektronineIranga'})
        self.search([('product_electronics_category', '=', False), ('type', '=', 'product'),
                     ('product_package_default_ids', '!=', False)]).write(
            {'gpais_product_type': 'apmokestinamasGaminys'})
        self.search([('product_electronics_category', '=', '69')]).write(
            {'klasifikacija': self.env.ref('robo_gpais.gpais_klasifikatorius_13').id})
        self.search([('product_electronics_category', '=', '70')]).write(
            {'klasifikacija': self.env.ref('robo_gpais.gpais_klasifikatorius_18').id})
        self.search([('product_electronics_category', '=', '71')]).write(
            {'klasifikacija': self.env.ref('robo_gpais.gpais_klasifikatorius_20').id})
        self.search([('product_electronics_category', '=', '72')]).write(
            {'klasifikacija': self.env.ref('robo_gpais.gpais_klasifikatorius_24').id})
        self.search([('product_electronics_category', '=', '73')]).write(
            {'klasifikacija': self.env.ref('robo_gpais.gpais_klasifikatorius_28').id})
        self.search([('product_electronics_category', '=', '74')]).write(
            {'klasifikacija': self.env.ref('robo_gpais.gpais_klasifikatorius_32').id})

    @api.multi
    def get_gpais_registracijos_id(self, gpais_product_type=False):
        if not gpais_product_type:
            self.ensure_one()
        gpais_product_type = gpais_product_type or self.gpais_product_type
        if gpais_product_type == 'apmokestinamasGaminys':
            return self.env.user.sudo().company_id.gpais_registras_gaminiai
        elif gpais_product_type == 'alyvosGaminys':
            return self.env.user.sudo().company_id.gpais_registras_alyva
        elif gpais_product_type == 'elektronineIranga':
            return self.env.user.sudo().company_id.gpais_registras_elektra
        elif gpais_product_type == 'transportoPriemone':
            return self.env.user.sudo().company_id.gpais_registras_transportas
        elif gpais_product_type == 'prekinisVienetas':
            return self.env.user.sudo().company_id.gpais_registras_pakuotes
        return False

    @api.multi
    def get_gpais_register_date_from(self, gpais_product_type=False):
        if not gpais_product_type:
            self.ensure_one()
        gpais_product_type = gpais_product_type or self.gpais_product_type
        if gpais_product_type == 'apmokestinamasGaminys':
            return self.env.user.sudo().company_id.gpais_registras_gaminiai_data
        elif gpais_product_type == 'alyvosGaminys':
            return self.env.user.sudo().company_id.gpais_registras_alyva_data
        elif gpais_product_type == 'elektronineIranga':
            return self.env.user.sudo().company_id.gpais_registras_elektra_data
        elif gpais_product_type == 'transportoPriemone':
            return self.env.user.sudo().company_id.gpais_registras_transportas_data
        elif gpais_product_type == 'prekinisVienetas':
            return self.env.user.sudo().company_id.gpais_registras_pakuotes_data
        return False

    def check_veiklos_budas(self, veiklo_budas, skip_activity=False):
        self.ensure_one()

        if self.gpais_product_type == 'prekinisVienetas':
            for package in self.mapped('product_package_default_ids.package_id'):
                if not package.check_veiklos_budas(veiklo_budas):
                    return False
            for package in self.mapped('uzstatine_pakuote_ids'):
                if not package.check_veiklos_budas(veiklo_budas):
                    return False
            return True

        search_domain = [('company_id', '=', self.env.user.company_id.id),
                         ('gpais_product_type', '=', self.gpais_product_type),
                         ('klasifikacija', '=', self.klasifikacija.id),
                         ]

        if veiklosBudas_mapping.get(veiklo_budas) and not skip_activity:
            attr = 'activity_' + veiklosBudas_mapping.get(veiklo_budas)
            search_domain.append((attr, '=', True))

        if self.gpais_product_type == 'elektronineIranga':
            search_domain.append(('buitine_iranga', '=', self.gpais_buitine_iranga))

        if self.env['gpais.registration.line'].search(search_domain, limit=1):
            return True
        return False

    @api.multi
    def action_open_package_deletion_wizard(self):
        self.ensure_one()
        domain = [('product_tmpl_id', '=', self.id)]
        delete_line_ids = self.env.context.get('delete_line_ids')
        if delete_line_ids:
            domain.append(('id', 'in', delete_line_ids))

        package_line_ids = self.env['product.package.default'].search(domain).ids

        return {
                'name': _('Ištrinti pakuočių eilutes'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'package.default.remove.wizard',
                'context': {'default_product_id': self.id,
                            'default_package_line_ids': [(4, line,) for line in package_line_ids]},
                'type': 'ir.actions.act_window',
                'target': 'new'
            }

    @api.multi
    def action_open_deposit_package_deletion_wizard(self):
        self.ensure_one()
        domain = [('product_tmpl_id', '=', self.id)]
        delete_line_ids = self.env.context.get('delete_line_ids')
        if delete_line_ids:
            domain.append(('id', 'in', delete_line_ids))

        uzstatine_pakuote_ids = self.env['uzstatine.pakuote'].search(domain).ids

        return {
                'name': _('Ištrinti užstatinių pakuočių eilutes'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'uzstatine.pakuote.remove.wizard',
                'context': {'default_product_id': self.id,
                            'default_uzstatine_pakuote_ids': [(4, line,) for line in uzstatine_pakuote_ids]},
                'type': 'ir.actions.act_window',
                'target': 'new'
            }

    @api.multi
    def action_open_battery_deletion_wizard(self):
        self.ensure_one()
        domain = [('product_tmpl_id', '=', self.id)]
        delete_line_ids = self.env.context.get('delete_line_ids')
        if delete_line_ids:
            domain.append(('id', 'in', delete_line_ids))

        product_battery_line_ids = self.env['product.battery.line'].search(domain).ids

        return {
                'name': _('Ištrinti baterijų eilutes'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'battery.line.remove.wizard',
                'context': {'default_product_id': self.id,
                            'default_product_battery_line_ids': [(4, line,) for line in product_battery_line_ids]},
                'type': 'ir.actions.act_window',
                'target': 'new'
            }
