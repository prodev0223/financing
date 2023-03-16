# -*- coding: utf-8 -*-

from odoo import _, api, exceptions, fields, models


class HrPayslipWorkedDays(models.Model):

    _inherit = 'hr.payslip.worked_days'

    appointment_id = fields.Many2one('hr.contract.appointment', string='Appointment')
    compensated_time_before_holidays = fields.Boolean(string='Line is time before holidays',
                                                      help='Line marks time that the employee does not work but still '
                                                           'gets paid for before holidays. Usually one hour before '
                                                           'each national holiday date')

    @api.onchange('contract_id')
    def onchange_contract(self):
        if self.contract_id:
            appointment = self.contract_id.get_active_appointment()
            if appointment:
                self.appointment_id = appointment.id
                return
        self.appointment_id = False

    @api.constrains('contract_id', 'appointment_id')
    def _constrain_appointment_contract(self):
        for rec in self:
            if rec.appointment_id and rec.appointment_id.contract_id.id != rec.contract_id.id:
                raise exceptions.ValidationError(_('Sutarties priedas turi būti susijęs su sutartimi.'))


HrPayslipWorkedDays()