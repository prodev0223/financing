# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    def __init__(self, pool, cr):
        init_res = super(ResUsers, self).__init__(pool, cr)
        type(self).SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        type(self).SELF_WRITEABLE_FIELDS.extend(['custom_email_footer'])
        type(self).SELF_WRITEABLE_FIELDS = list(set(type(self).SELF_WRITEABLE_FIELDS))
        type(self).SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        type(self).SELF_READABLE_FIELDS.extend(['custom_email_footer'])
        type(self).SELF_READABLE_FIELDS = list(set(type(self).SELF_READABLE_FIELDS))
        return init_res

    def default_email_footer_code(self):
        footer = '<span>' + self.env.user.company_id.name + '</span>'
        if self.env.user.company_id.email:
            footer += '<br><span>' + self.env.user.company_id.email + '</span>'
        return footer

    custom_email_footer = fields.Html(string='El. laiškų parašas', default=default_email_footer_code)


ResUsers()
