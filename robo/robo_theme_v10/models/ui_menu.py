# -*- coding: utf-8 -*-
from odoo import fields, models, api, tools, _
import operator
from odoo.tools import xml_import as baseXmlImport


# TAGS

def _tag_menuitem(fn):
    def new(self, rec, data_node=None, mode=None):
        res = fn(self, rec, data_node=data_node, mode=mode)
        rec_id = rec.get("id", '').encode('ascii')

        values = {
            'robo_front': True if rec.get('robo_front') else False,
            'robo_extended': True if rec.get('robo_extended') else False,
            'searchable': True if rec.get('searchable') else False
        }

        if rec.get('tags'):
            values['tags'] = rec.get('tags')

        if rec.get('force_web_icon'):
            values['web_icon'] = rec.get('force_web_icon')

        self.env['ir.model.data']._update('ir.ui.menu', self.module, values, rec_id,
                                                noupdate=self.isnoupdate(data_node), mode=self.mode,
                                                res_id=res and res[0] or False)
        return res

    return new


baseXmlImport._tag_menuitem = _tag_menuitem(baseXmlImport._tag_menuitem)


class ResUsers(models.Model):

    _inherit = 'res.users'

    @api.multi
    def is_back_user(self):
        self.ensure_one()
        if not self.is_accountant() and self.is_user():
            return False
        else:
            return True


ResUsers()


class IrUiMenu(models.Model):

    _inherit = 'ir.ui.menu'

    tags = fields.Char(string='Žyma', copy=False, translate=True)
    description = fields.Char(string='Aprašymas', copy=False)
    searchable = fields.Boolean(string='Rodomas paieškoje', default=False, copy=False)
    robo_extended = fields.Boolean(string='Turi iškylantį meniu dešinėje', default=False, copy=False)
    robo_front = fields.Boolean(default=False, copy=False)
    robo_main_menu = fields.Boolean(default=False)

    # @api.one
    # def _compute_is_robo_start_app(self):
    #     self.is_robo_start_app = (self.id and (self.id == self.env.ref('robo.menu_start').id))

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if not self.env.user.is_back_user():
            args = args or []
            args.append(('robo_front', '=', True))

        return super(IrUiMenu, self).search(args, offset=offset, limit=limit, order=order, count=count)


IrUiMenu()


