# -*- coding: utf-8 -*-

import models
import controllers

from odoo import SUPERUSER_ID

MODULE = '_backend_debranding'


def uninstall_hook(cr, registry):
    registry['ir.model.data']._module_data_uninstall(cr, SUPERUSER_ID, [MODULE])
