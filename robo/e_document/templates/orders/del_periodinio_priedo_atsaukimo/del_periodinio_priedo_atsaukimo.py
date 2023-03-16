# -*- coding: utf-8 -*-
from odoo import models, api


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_periodinio_priedo_atsaukimo_workflow(self):
        self.ensure_one()
        periodic_id = self.env['hr.employee.bonus.periodic'].search(
            [('employee_id', '=', self.employee_id2.id), '|', ('date_stop', '=', False),
             ('date_stop', '>=', self.date_2)])
        if periodic_id:
            periodic_id.write({
                'date_stop': self.date_2,
                'date': False,
            })
            up_front_bonus_records = periodic_id.bonus_ids.filtered(lambda bonus: bonus.payment_date_from > self.date_2)
            if up_front_bonus_records:
                up_front_bonus_records.action_cancel()
                up_front_bonus_records.unlink()


EDocument()
