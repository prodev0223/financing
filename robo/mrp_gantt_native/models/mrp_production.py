# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
from lxml import etree

import datetime
from dateutil import tz
import pytz
import time
from string import Template
from datetime import datetime, timedelta
from odoo.exceptions import  Warning
from pdb import set_trace as bp

from itertools import groupby
from operator import itemgetter

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__) # Need for message in console.


class MrpProduction(models.Model):
    _name = "mrp.production"
    _inherit = ['mrp.production']

    #Sorting
    sorting_seq = fields.Integer(string='Sorting Seq.')
    sorting_level = fields.Integer('Sorting Level', default=0)
    sorting_level_seq = fields.Integer('Sorting Level Seq.', default=0)


    #Gantt
    is_milestone = fields.Boolean("Mark as Milestone", default=False)
    on_gantt = fields.Boolean("Task name on gantt", default=False)

    #MRP
    date_planned_deadline = fields.Datetime(
        'Deadline Gantt', copy=False, default=fields.Datetime.now,
        index=True,
        states={'confirmed': [('readonly', False)]})



    @api.model
    def childs_get(self, ids_field_name, ids, fields):

        test = "OK"
        return test



