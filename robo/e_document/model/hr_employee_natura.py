# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployeeNatura(models.Model):
    _inherit = 'hr.employee.natura'

    e_document_id = fields.Many2one('e.document', 'Related Document')


HrEmployeeNatura()
