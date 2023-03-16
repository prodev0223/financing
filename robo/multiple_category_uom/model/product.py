# -*- encoding: utf-8 -*-

from odoo import models, fields, _, api, exceptions, tools


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    product_uom_lines = fields.One2many('product.uom.line', 'product_tmpl_id', string='Antriniai matavimo vienetai',
                                        groups='stock_extend.group_robo_stock')

    @api.multi
    def convert_from_secondary_uom(self, qty, secondary_uom, to_uom):
        self.ensure_one()
        uom_line = self.product_uom_lines.filtered(lambda r: r.uom_id == secondary_uom)
        if uom_line:
            main_uom = self.uom_id
            qty_main_uom = qty * uom_line[0].factor
            return main_uom._compute_quantity(qty_main_uom, to_uom, round=False)
        elif secondary_uom.category_id == to_uom.category_id:
            return secondary_uom._compute_quantity(qty, to_uom, round=False)
        else:
            raise exceptions.UserError(_('Matavimo vienetas %s nenurodytas prie produkto %s antrinių matavimo vienetų')
                                       % (secondary_uom.name, self.display_name))

    @api.multi
    def convert_to_secondary_uom(self, qty, from_uom, secondary_uom):
        """ raises UserError or ZeroDivisionError if failed """
        self.ensure_one()
        main_uom_id = self.uom_id
        qty_main = from_uom._compute_quantity(qty, main_uom_id, round=False)
        uom_line = self.product_uom_lines.filtered(lambda r: r.uom_id == secondary_uom)
        if uom_line:
            factor = uom_line[0].factor
            return qty_main / factor
        elif secondary_uom.category_id == from_uom.category_id:
            return main_uom_id._compute_quantity(qty_main, secondary_uom, round=False)
        else:
            raise exceptions.UserError(_('Matavimo vienetas %s nenurodytas prie produkto %s antrinių matavimo vienetų')
                                       % (secondary_uom.name, self.display_name))

    @api.multi
    def compute_price_from_secondary_uom(self, price, secondary_uom, to_uom):
        self.ensure_one()
        if not self or not price or not to_uom or secondary_uom == to_uom:
            return price
        uom_line = self.product_uom_lines.filtered(lambda r: r.uom_id == secondary_uom)
        if uom_line:
            main_uom = self.uom_id
            factor = uom_line[0].factor
            if not tools.float_is_zero(factor, precision_digits=3):
                price_main_uom = price / uom_line[0].factor
            else:
                price_main_uom = price
            return main_uom._compute_price(price_main_uom, to_uom)
        elif secondary_uom.category_id == to_uom.category_id:
            return secondary_uom._compute_price(price, to_uom)
        else:
            raise exceptions.UserError(_('Matavimo vienetas %s nenurodytas prie produkto %s antrinių matavimo vienetų')
                                       % (secondary_uom.name, self.display_name))


ProductTemplate()


class ProductUomLine(models.Model):
    _name = 'product.uom.line'

    _sql_constraints = [('product_tmpl_uom_unique',
                         'unique (product_tmpl_id, uom_id)',
                         _('Negalima kartoti antrinių produkto matavimo vienetų'))]

    product_tmpl_id = fields.Many2one('product.template', string='Produktas', required=True)
    uom_id = fields.Many2one('product.uom', string='Matavimo vienetas', required=True)
    factor = fields.Float(string='Santykis',
                          help='Kiek vienas matavimo vienetas atitinka produkto matavimo vienetų')


ProductUomLine()
