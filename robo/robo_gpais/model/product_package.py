# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models, tools
from .gpais_commons import MATERIAL_TYPE_CODE_MAPPING, PAKUOTE_RUSIS, veiklosBudas_mapping


class ProductPackage(models.Model):
    _inherit = 'product.package'

    weight = fields.Float(inverse='_round_package_weight')
    tuscia = fields.Boolean(string='Tuščia', compute='_tuscia') #todo:not sure we need to keep
    savom_reikmem = fields.Boolean(string='Savom reikmėm')
    material_type = fields.Selection(selection_add=[('kombinuota_kita', 'Kombinuota (kita)'),
                                                    ('kombinuota_kita_vyr_stiklas', 'Kombinuota tuščia kita (vyraujanti stiklas)')])
    rusis = fields.Selection(PAKUOTE_RUSIS, compute='_compute_rusis', string='Pakuotės rūšis')
    klasifikacija = fields.Many2one('gpais.klasifikacija', string='Klasifikacija', compute='_compute_rusis')

    @api.one
    def _round_package_weight(self):
        if tools.float_compare(self.weight, tools.float_round(self.weight, precision_digits=3, rounding_method='UP'), precision_digits=3,):
            self.write({'weight': tools.float_round(self.weight, precision_digits=3, rounding_method='UP')})

    @api.depends('package_category', 'material_type', 'use_type', 'savom_reikmem')
    def _compute_rusis(self):
        for rec in self.filtered(lambda p: p.package_category and p.material_type):
            package_category = rec.package_category
            material_code = MATERIAL_TYPE_CODE_MAPPING[rec.material_type]
            # TODO: CHECK WITH KOMBINUOTA BEHAVIOUR
            if not package_category:
                rec.rusis = False
            elif package_category == 'nenurodoma' or rec.material_type == 'kombinuota_kita_vyr_stiklas':
                rec.rusis = '0' + MATERIAL_TYPE_CODE_MAPPING[rec.material_type]
            # elif rec.uzstatine: # uzstatine is separate
            #     code_1 = '5'
            elif rec.savom_reikmem and package_category == 'pirmine':
                rec.rusis = '6' + material_code
            elif rec.savom_reikmem and package_category in ['antrine', 'tretine']:
                rec.rusis = '7' + material_code
            elif package_category == 'pirmine' and rec.use_type == 'daukartine':
                rec.rusis = '3' + material_code
            elif package_category in ['antrine', 'tretine'] and rec.use_type == 'daukartine':
                rec.rusis = '4' + material_code
            elif package_category == 'pirmine':
                rec.rusis = '1' + material_code
            elif package_category in ['antrine', 'tretine']:
                rec.rusis = '2' + material_code
            else:
                # should never reach here
                rec.rusis = False
            if rec.rusis:
                rec.klasifikacija = self.env['gpais.klasifikacija'].search(
                    [('code', 'like', 'CL130:' + str(rec.rusis) + ':%')], limit=1)

    @api.multi
    @api.depends('package_category')
    def _tuscia(self):
        for rec in self:
            rec.tuscia = rec.package_category == 'nenurodoma'

    @api.multi
    def _set_material_type(self):
        super(ProductPackage, self)._set_material_type()
        self.filtered(lambda p: p.material_type == 'kombinuota_kita_vyr_stiklas').write({'package_category': 'nenurodoma'})
        self.filtered(lambda p: p.material_type == 'kombinuota_kita').write({'combined_material': 'kita'})
        # self.filtered(lambda p: p.material_type == 'kombinuota').write({'package_category': 'popierus'}) #FIXME: Should we force it ? It seems that GPAIS only consider it as paper based

    @api.multi
    @api.constrains('use_type', 'savom_reikmem')
    def _constrain_reusable_not_for_own_needs(self):
        for rec in self:
            if rec.savom_reikmem and rec.use_type == 'daukartine':
                raise exceptions.ValidationError(_('Daugkartinės pakuotės negali būti naudojamos savom reikmėm.'))

    @api.constrains('savom_reikmem')
    def _check_savom_reikmem(self):
        package_defaults = self.env['product.package.default'].search([('package_id', 'in', self.ids)])
        product_templates = package_defaults.mapped('product_tmpl_id')
        product_templates._check_product_package_default_package_savom_reikmem()

    @api.onchange('use_type')
    def _onchange_use_type(self):
        if self.use_type == 'daukartine':
            self.savom_reikmem = False

    @api.onchange('savom_reikmem')
    def _onchange_savom_reikmem(self):
        if self.savom_reikmem:
            self.use_type = 'vienkartine'

    @api.multi
    def check_veiklos_budas(self, veiklo_budas, skip_activity=False):
        self.ensure_one()

        search_domain = [('company_id', '=', self.env.user.company_id.id),
                         ('gpais_product_type', '=', 'prekinisVienetas'),
                         ('material_type', '=', self.material_type),
                         ('use_type', '=', self.use_type),
                         ('uzstatine', '=', False),]

        if veiklosBudas_mapping.get(veiklo_budas) and not skip_activity:
            attr = 'activity_' + veiklosBudas_mapping.get(veiklo_budas)
            search_domain.append((attr, '=', True))

        if self.env['gpais.registration.line'].search(search_domain):
            return True
        return False
