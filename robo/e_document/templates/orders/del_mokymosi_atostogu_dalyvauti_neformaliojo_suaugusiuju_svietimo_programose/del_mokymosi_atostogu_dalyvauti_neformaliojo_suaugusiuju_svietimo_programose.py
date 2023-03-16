# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_mokymosi_atostogu_dalyvauti_neformaliojo_suaugusiuju_svietimo_programose_workflow(self):
        self.ensure_one()
        hol_id = self.env['hr.holidays'].create({
            'name': 'Mokymosi atostogos',
            'data': self.date_document,
            'employee_id': self.employee_id2.id,
            'holiday_status_id': self.env.ref('hr_holidays.holiday_status_MA').id,
            'date_from': self.calc_date_from(self.date_from),
            'date_to': self.calc_date_to(self.date_to),
            'type': 'remove',
            'numeris': self.document_number,
        })
        hol_id.action_approve()
        self.inform_about_creation(hol_id)
        self.write({
            'record_model': 'hr.holidays',
            'record_id': hol_id.id,
        })


EDocument()
