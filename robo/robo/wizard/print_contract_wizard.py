# -*- coding: utf-8 -*-


from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class PrintContractWizard(models.TransientModel):
    _name = 'print.contract.wizard'

    def _default_contract_date(self):
        return datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    employee_id = fields.Many2one('hr.employee', string='Darbuotojas')
    representative_id = fields.Many2one('hr.employee', string='Representative')
    contracts = fields.Many2one('hr.contract', string='Kontraktas')
    appointments = fields.Many2one('hr.contract.appointment', string='Priedas')
    contract_date = fields.Date(string='Darbo sutarties data', default=_default_contract_date, required=True)
    contract_liabilities = fields.Text(string='Kiti darbuotojo ir darbdavio tarpusavio įsipareigojimai')
    contract_conditions = fields.Text(string='Nustatomos papildomos darbo sutarties sąlygos')
    force_lang = fields.Selection([
        ('lt_LT', 'Lithuanian'),
        ('en_US', 'English'),
    ], string='Report language',)
    choose_representative = fields.Boolean(
        string='Choose representative to show on document',
        help='Chosen representative will be displayed on the contract as the one who signed it'
    )
    print_termination = fields.Boolean(
        string='Print termination attachment',
        help='Checking this box will print the attachment of termination',
    )
    salary_payment_day = fields.Integer(
        string='Salary paid by', default=15,
        help='indicates the day by which the salary is paid',
    )
    show_print_termination = fields.Boolean(compute='_compute_show_print_termination')

    @api.onchange('contracts')
    def change_vals(self):
        if self.contracts:
            self.contract_liabilities = self.contracts.contract_liabilities
            self.contract_conditions = self.contracts.contract_conditions
            self.appointments = self.contracts.appointment_ids.sorted(lambda x: x.date_start, reverse=True)[0] \
                if self.contracts.appointment_ids else False

    @api.onchange('appointments')
    def _compute_show_print_termination(self):
        self.ensure_one()
        self.show_print_termination = True if self.contracts.ends_the_work_relation else False

    @api.multi
    def confirm(self):
        self.ensure_one()
        self.sudo().sent = True

        if self.contract_date > self.appointments.date_start:
            raise exceptions.ValidationError(
                _('Nurodyta darbo sutarties data yra vėlesnė, nei priedo starto data (%s)') %
                self.appointments.date_start)

        # Check salary paid by day value
        if not 1 <= self.salary_payment_day <= 31:
            raise exceptions.ValidationError(
                _('Incorrect value in salary paid by day column. Value must be between 1 and 31')
            )

        manager_name = self.env.user.sudo().company_id.vadovas.name_related
        use_representative = self.choose_representative and self.representative_id
        data = {
            'contract_id': self.contracts.id,
            'appointment_id': self.appointments.id,
            'representative': self.representative_id.name_related if use_representative else manager_name,
            'emp_id': self.employee_id.id,
            'contract_date': self.contract_date,
            'salary_payment_day': self.salary_payment_day,
            'contract_conditions': self.contract_conditions,
            'contract_liabilities': self.contract_liabilities,
            'force_lang': self.force_lang or self.env.user.lang,
        }
        if not self.print_termination:
            return self.env['report'].get_action(self, 'robo.report_employee_contract', data=data)
        else:
            return self.env['report'].get_action(self, 'robo.report_contract_termination_attachment', data=data)
