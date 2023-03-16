# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models
from .gpais_commons import veiklosBudas_mapping


class UzstatinePakuote(models.Model):
    _name = 'uzstatine.pakuote'


    use_type = fields.Selection([('vienkartine', 'Vienkartinė'),
                                 ('daukartine', 'Daugkartinė')],
                                string='Vienkartinė/Daugkartinė', default='vienkartine', required=True)
    org_code = fields.Char(string='Organizacijos kodas')
    code = fields.Char(string='Pakuotės kodas', required=True)
    qty = fields.Integer(string='Pakuočių skaičius', required=True)
    date_from = fields.Date(string='Pradėta tiekti rinkai nuo', default=False)
    end_date = fields.Date(string='Tiekta iki')
    product_tmpl_id = fields.Many2one('product.template', string='Produktas')
    material_type = fields.Selection([('kita', 'Kita'),
                                      ('kombinuota_kita', 'Kombinuota (kita)'),
                                      ('kombinuota', 'Kombinuota'),
                                      ('medis', 'Medis'),
                                      ('metalas', 'Metalas'),
                                      ('pet', 'PET'),
                                      ('plastikas', 'Plastikas'),
                                      ('popierius', 'Popierius'),
                                      ('stiklas', 'Stiklas'),
                                      ('kombinuota_kita_vyr_stiklas', 'Kombinuota tuščia kita (vyraujanti stiklas)')
                                      ], required=True, string='Medžiaga')

    @api.multi
    def check_veiklos_budas(self, veiklo_budas, skip_activity=False):
        self.ensure_one()

        search_domain = [('company_id', '=', self.env.user.company_id.id),
                         ('gpais_product_type', '=', 'prekinisVienetas'),
                         ('material_type', '=', self.material_type),
                         ('use_type', '=', self.use_type),
                         ('uzstatine', '=', True), ]

        if veiklosBudas_mapping.get(veiklo_budas) and not skip_activity:
            attr = 'activity_' + veiklosBudas_mapping.get(veiklo_budas)
            search_domain.append((attr, '=', True))

        if self.env['gpais.registration.line'].search(search_domain):
            return True
        return False

    @api.multi
    @api.constrains('date_from', 'end_date')
    def _constrain_dates(self):
        for rec in self:
            #todo: add checks for dates related to product, and maybe package registration
            if rec.date_from and rec.end_date and rec.date_from > rec.end_date:
                raise exceptions.ValidationError(_('Data nuo negali būti vėliau, nei data iki.'))

    @api.multi
    def write(self, vals):
        self.filtered('product_tmpl_id').mapped('product_tmpl_id').write({
            'package_update_date': fields.Date.today(),
        })
        res = super(UzstatinePakuote, self).write(vals)
        new_product_tmpl_id = vals.get('product_tmpl_id')
        if new_product_tmpl_id:
            self.env['product.template'].browse(new_product_tmpl_id).write({
                'package_update_date': fields.Date.today(),
            })
        return res

    @api.model
    def create(self, vals):
        if vals.get('product_tmpl_id'):
            self.env['product.template'].browse(vals.get('product_tmpl_id')).write({
                'package_update_date': fields.Date.today(),
            })
        return super(UzstatinePakuote, self).create(vals)

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti įrašo. Kreipkitės į sistemos administratorių.'))
        self.filtered('product_tmpl_id').mapped('product_tmpl_id').write({
            'package_update_date': fields.Date.today(),
        })
        return super(UzstatinePakuote, self).unlink()

    @api.multi
    def button_call_deletion_wizard(self):
        self.ensure_one()
        return self.product_tmpl_id.with_context(delete_line_ids=self.ids).action_open_package_deletion_wizard()
