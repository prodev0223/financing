# -*- coding: utf-8 -*-
import logging
from six import iteritems

from lxml import etree
from lxml.builder import E

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


@api.model
def _get_default_form_view(self):
    """ Generates a default single-line form view using all fields
    of the current model.

    :returns: a form view as an lxml document
    :rtype: etree._Element
    """
    group = E.group(col="4")
    if self.env.user.is_back_user():
        for fname, field in iteritems(self._fields):
            if field.automatic:
                continue
            elif field.type in ('one2many', 'many2many', 'text', 'html'):
                group.append(E.newline())
                group.append(E.field(name=fname, colspan="4"))
                group.append(E.newline())
            else:
                group.append(E.field(name=fname))
        group.append(E.separator())
    else:
        try:
            group.append(E.field(name=self._rec_name or 'display_name', colspan="4"))
        except KeyError:
            _logger.info('Failed building default from view on model %s', self._name)
            raise
        # group.append(E.text(_('Atsiprašome, jūs neturite teisių pamatyti šį dokumentą')))
    return E.form(E.sheet(group, string=self._description))


models.BaseModel._get_default_form_view = _get_default_form_view


class RoboView(models.Model):
    _inherit = 'ir.ui.view'

    robo_front = fields.Boolean(string='Ar rodyti veiksmą vartotojui?', default=False)
    type = fields.Selection(selection_add=[('calendar_robo', 'Robo Calendar'), ('grid', 'Robo grid')])

    # default view selection
    @api.model
    def default_view(self, model, view_type):
        """ Fetches the default view for the provided (model, view_type) pair:
         primary view with the lowest priority.

        :param str model:
        :param int view_type:
        :return: id of the default view of False if none found
        :rtype: int
        """
        is_robo_back = not self._context.get('robo_front')
        # ROBO: check if front user or not
        if not self.env.user.is_back_user() or not is_robo_back:
            domain = [('model', '=', model), ('type', '=', view_type)]
            if not self.env[model].is_transient():
                domain.append(('robo_front', '=', True))
            view_id = self.search(domain, limit=1).id
            if view_id:
                return view_id
            else:
                if view_type not in ('search',):
                    _logger.info("{ROBO_VIEW_INFO}{Warning} Model "+ model + " view_type " + view_type + " not found in robo_front view list.")
                    if view_type == 'form' and not self.env.user.is_back_user():
                        _logger.info("{ROBO_VIEW_INFO}{Error} Model " + model + " view_type " + view_type + " not found in robo_front view list.")
                        return False

        domain_back = [('model', '=', model), ('type', '=', view_type), ('mode', '=', 'primary'),
                       ('robo_front', '=', False)]
        domain_front = [('model', '=', model), ('type', '=', view_type), ('mode', '=', 'primary'),
                        ('robo_front', '=', True)]
        return self.search(domain_back, limit=1).id or self.search(domain_front, limit=1).id
