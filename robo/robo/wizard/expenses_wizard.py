# -*- coding: utf-8 -*-


from odoo import api, fields, models


class ExpensesWizard(models.TransientModel):
    _name = 'expenses.wizard'

    employee = fields.Many2one('hr.employee', string='Atskaitingas asmuo')
    payment_mode = fields.Selection(
        [('own_account', 'Asmeninėmis lėšomis'),
         ('company_account', 'Kompanijos lėšomis')],
        string='Kaip apmokėjote?', default='own_account', copy=False)

    @api.onchange('payment_mode')
    def _onchange_payment_mode(self):
        if self.payment_mode == 'own_account':
            allowed_groups = [
                'robo_basic.group_robo_premium_manager',
                'robo.group_menu_kita_analitika',
                'robo.group_robo_see_all_expenses',
            ]
            if not any(self.env.user.has_group(g) for g in allowed_groups):
                if self.env.user.employee_ids:
                    self.employee = self.env.user.employee_ids[0]
                return {'domain': {'employee': [('id', 'in', self.env.user.employee_ids.ids)]}}
            return {'domain': {'employee': []}}

    @api.multi
    def confirm(self):
        self.ensure_one()
        self.env['account.invoice'].browse(self._context['active_id']).update_payment_details(self.payment_mode,
                                                                                              self.employee)