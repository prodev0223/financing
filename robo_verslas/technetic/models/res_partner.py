# -*- coding: utf-8 -*-
import re
import unicodedata
from odoo import api, fields, models

def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(re.sub('[^\w\s-]', '', value).strip())
    value = unicode(re.sub('[-\s]+', '_', value))
    return value


class ResPartner(models.Model):
    _inherit = 'res.partner'

    slugified_name = fields.Char(compute='_compute_slugified_name')

    @api.depends('sanitized_name')
    def _compute_slugified_name(self):
        for rec in self:
            rec.slugified_name = slugify(rec.sanitized_name)
