# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrEmployeeBonus(models.Model):
    _inherit = 'hr.employee.bonus'

    related_document = fields.Many2one('e.document', string='Susijęs dokumentas', inverse='set_relation',
                                       states={'confirm': [('readonly', True)]})

    @api.multi
    def set_relation(self):
        for rec in self:
            if rec.related_document:
                msg = {'body': 'Priedas | Įsakymo nr: %s' % str(rec.related_document.document_number)}
                rec.message_post(**msg)


HrEmployeeBonus()
