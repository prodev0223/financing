# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models

class ProductBatteryLine(models.Model):
    _inherit = 'product.battery.line'

    @api.multi
    def write(self, vals):
        self.filtered('product_tmpl_id').mapped('product_tmpl_id').write({
            'package_update_date': fields.Date.today(),
        })
        res = super(ProductBatteryLine, self).write(vals)
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
        return super(ProductBatteryLine, self).create(vals)

    @api.multi
    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise exceptions.UserError(_('Negalima ištrinti įrašo. Kreipkitės į sistemos administratorių.'))
        self.filtered('product_tmpl_id').mapped('product_tmpl_id').write({
            'package_update_date': fields.Date.today(),
        })
        return super(ProductBatteryLine, self).unlink()

    @api.multi
    def button_call_deletion_wizard(self):
        self.ensure_one()
        return self.product_tmpl_id.with_context(delete_line_ids=self.ids).action_open_package_deletion_wizard()
