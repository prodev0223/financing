# -*- coding: utf-8 -*-
from lxml.builder import E

from odoo import api
from odoo.models import BaseModel


def _get_default_tree_view(self):
    """ Generates a single-field tree view, based on _rec_name.

    :returns: a tree view as an lxml document
    :rtype: etree._Element
    """
    element = E.field(name=self._rec_name_fallback())
    kwargs = {'string': self._description}

    if not self.env.user.is_back_user():
        kwargs.update({'import': "0"})

    return E.tree(element, kwargs)


def _get_default_tree_robo_view(self):
    """ Generates a single-field tree view, based on _rec_name.

    :returns: a tree view as an lxml document
    :rtype: etree._Element
    """
    return _get_default_tree_view(self)


BaseModel._get_default_tree_view = _get_default_tree_view
BaseModel._get_default_tree_robo_view = _get_default_tree_robo_view

fields_view_get = BaseModel.fields_view_get


@api.model
def _fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
    # ROBO: remove non-front view_id for front users

    View = self.env['ir.ui.view']
    if view_id and not self.env.user.is_back_user():
        if not View.browse(view_id).robo_front:
            view_id = None
    result = fields_view_get(self, view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
    return result


BaseModel.fields_view_get = _fields_view_get

# TODO: raise error on simple user _get_default_form_view
