# -*- coding: utf-8 -*-
import ast

from odoo import _, api, fields, models


class StartEmployeeInternship(models.TransientModel):
    _name = 'start.employee.internship'

    internship_type = fields.Selection([
        # ('student_internship', 'Studento praktika'),  TODO
        # ('pupil_internship', 'Moksleivio praktika'),  TODO
        ('voluntary_internship', 'Savanoriška praktika'),
        ('educational_internship', 'Švietimo įstaigos praktika'),
    ], string='Praktikos tipas', required=True, default='voluntary_internship')

    internship_description = fields.Char(string='Praktikos aprašymas', compute='_compute_internship_description')
    employee_id = fields.Many2one('hr.employee', required=True)

    @api.one
    @api.depends('internship_type')
    def _compute_internship_description(self):
        if self.internship_type in ['student_internship', 'educational_internship']:
            self.internship_description = _('Praktika asmenims, studijuojantiems aukštosiose mokyklose pagal studijų '
                                            'programą arba doktorantūroje.')
        elif self.internship_type == 'pupil_internship':
            self.internship_description = _('Praktika asmenims, kurie mokosi pagal profesinio mokymo programas.')
        elif self.internship_type == 'voluntary_internship':
            self.internship_description = _('Nemokama savanoriška praktika asmenims iki 29 metų.')
        else:
            self.internship_description = ''

    @api.onchange('internship_type')
    def _onchange_internship_type(self):
        self._compute_internship_description()

    @api.multi
    def create_internship_contract(self):
        self.ensure_one()
        if self.internship_type in ['voluntary_internship', 'educational_internship']:
            action = self.env.ref('e_document.internship_order_action').read()[0]
            context = ast.literal_eval(action['context'])
            context.update({
                'default_employee_id2': self.employee_id.id,
                'default_text_1': self.employee_id.identification_id,
                'default_text_2': self.employee_id.street,
                'default_text_5': self.env.user.company_id.street,
                'default_internship_type': self.internship_type,
            })
            action['context'] = context
            return action
        else:
            return True  # TODO


StartEmployeeInternship()
