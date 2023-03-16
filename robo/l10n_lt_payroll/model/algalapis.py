# -*- encoding: utf-8 -*-
from odoo import fields, models, api, _, exceptions


class HrPayslipWorkedDays(models.Model):

    _inherit = 'hr.payslip.worked_days'

    def _get_default_contract(self):
        return self._context.get('contract_id', False)

    contract_id = fields.Many2one('hr.contract', default=_get_default_contract)
    number_of_work_days = fields.Float(string='Darbo dienų skaičius', default=0.0)
    is_paid_for = fields.Boolean(default=True)

    @api.model
    def create(self, vals):
        res = super(HrPayslipWorkedDays, self).create(vals)
        payslip = vals.get('payslip_id', False)
        appointment = vals.get('appointment_id', False)
        if payslip and appointment:
            info_lines_with_appointment = self.env['hr.payslip.appointment.info.line'].search([
                ('payslip','=',payslip),
                ('appointment_id','=',appointment),
            ])
            if not info_lines_with_appointment:
                self.env['hr.payslip.appointment.info.line'].create({
                    'payslip': payslip,
                    'appointment_id': appointment,
                })
        return res

    @api.multi
    def unlink(self):
        for rec in self:
            appointment = rec.appointment_id.id
            line_appointments = self.filtered(lambda r: r['id'] != rec.id).mapped('appointment_id.id')
            if not line_appointments or appointment not in line_appointments:
                rec.payslip_id.appointment_info_lines.filtered(lambda r: r['appointment_id']['id'] == appointment).unlink()
        return super(HrPayslipWorkedDays, self).unlink()

HrPayslipWorkedDays()


class HrPayslipInput(models.Model):

    _inherit = 'hr.payslip.input'

    def _get_default_contract(self):
        return self._context.get('contract_id', False)

    contract_id = fields.Many2one('hr.contract', default=_get_default_contract)
    manual = fields.Boolean(string='Eilutė keista rankiniu būdu', default=False)

    @api.onchange('code', 'name', 'amount', 'contract_id')
    def onchange_set_manual(self):
        self.manual = True

    @api.constrains('code', 'payslip_id', 'contract_id')
    def constrain_unique_code(self):
        for rec in self:
            if self.env['hr.payslip.input'].search_count([('id', '!=', rec.id),
                                                          ('payslip_id', '=', rec.payslip_id.id),
                                                          ('contract_id', '=', rec.contract_id.id),
                                                          ('code', '=', rec.code)]):
                raise exceptions.ValidationError(_('Algalapis gali turėti tik viena eilutę su nurodytu kodu.'))

    @api.multi
    def get_input_vals(self):
        return [{'name': rec.name,
                 'code': rec.code,
                 'amount': rec.amount,
                 'contract_id': rec.contract_id.id,
                 'manual': rec.manual} for rec in self]


HrPayslipInput()
