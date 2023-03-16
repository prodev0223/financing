# -*- coding: utf-8 -*-

import logging

from odoo import api, models, tools
from odoo.exceptions import AccessError
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)


class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @api.model
    @tools.ormcache_context('self._uid', 'model', 'mode', 'raise_exception', keys=('lang',))
    def check(self, model, mode='read', raise_exception=True):
        if isinstance(model, models.BaseModel):
            assert model._name == 'ir.model', 'Invalid model object'
            model_name = model.model
        else:
            model_name = model

        if self._uid == 1 or model_name == 'ir.model':
            return super(IrModelAccess, self).check(model, mode, raise_exception)

        overriden = False
        if model_name != 'ir.model.access.override':
            self._cr.execute("""SELECT COUNT(*) 
                                FROM ir_model_access_override o
                                RIGHT JOIN ir_model m ON m.model = %s
                                WHERE o.model_id = m.id AND o.user_id = %s
                                """,
                             (model_name, self._uid,))
            r = self._cr.fetchone()[0]
            overriden = bool(r)

        if not overriden or self._uid == 1:
            return super(IrModelAccess, self).check(model, mode, raise_exception)

        assert mode in ('read', 'write', 'create', 'unlink'), _('Neteisingas prieigos tipas')

        self._cr.execute("""SELECT COUNT(*) 
                            FROM ir_model_access_override o
                            RIGHT JOIN ir_model m ON m.model = %s
                            WHERE o.model_id = m.id AND o.user_id = %s AND o.allow_{mode} = True
                         """.format(mode=mode),
                         (model_name, self._uid))
        r = self._cr.fetchone()[0]
        rule_exists = bool(r)

        if not rule_exists:
            if raise_exception:
                err_access_type_string_mapping = {
                    'read': _("Atsiprašome, tačiau jums neleidžiama pasiekti šio dokumento."),
                    'write': _("Atsiprašome, tačiau jums neleidžiama keisti šio dokumento."),
                    'create': _("Atsiprašome, tačiau jums neleidžiama kurti šio dokumento."),
                    'unlink': _("Atsiprašome, tačiau jums neleidžiama ištrinti šio dokumento."),
                }
                raise AccessError(err_access_type_string_mapping[mode])
            return False

        return True


IrModelAccess()
