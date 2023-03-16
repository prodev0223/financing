# -*- coding: utf-8 -*-
from odoo import models, fields


class FrontResGroupsCategory(models.Model):
    _name = 'front.res.groups.category'

    name = fields.Char(string='Grupės pavadinimas', required=True, translate=True)


FrontResGroupsCategory()
