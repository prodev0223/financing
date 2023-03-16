# -*- coding: utf-8 -*-

from odoo import models, api

rum_cat_fields_start_with = 'rum_cat_'


class FrontResGroupsCategory(models.Model):
    _inherit = 'front.res.groups.category'

    @api.multi
    def get_field_name(self):
        self.ensure_one()
        return rum_cat_fields_start_with + str(self.id)

    @api.multi
    def get_invisible_field_name(self):
        self.ensure_one()
        return self.get_field_name() + '_is_invisible'

    @api.multi
    def get_readonly_field_name(self):
        self.ensure_one()
        return self.get_field_name() + '_is_readonly'

    @api.model
    def is_rum_group_field(self, field_name):
        return field_name.startswith(rum_cat_fields_start_with)

    @api.model
    def get_category_id_from_field_name(self, field_name):
        if not self.is_rum_group_field(field_name):
            return False
        try:
            return int(field_name.split(rum_cat_fields_start_with)[1].split('_')[0])
        except ValueError:
            return False


FrontResGroupsCategory()
