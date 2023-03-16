# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import _, api, exceptions, fields, models, tools


class PrintContractWizard(models.TransientModel):
    _inherit = 'print.contract.wizard'

    def _get_possible_representatives(self):
        date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        representatives = self.env.user.sudo().company_id.vadovas
        representatives |= self.env.ref('robo_basic.group_robo_hr_manager').users.mapped('employee_ids')
        representatives |= self.env.ref('robo_basic.group_robo_premium_manager').users.mapped('employee_ids')
        representatives |= self.env['e.document.delegate'].sudo().search([
            ('date_start', '<', date),
            ('date_stop', '>', date),
        ]).mapped('employee_id')
        if self and self.employee_id:
            if self.env.user.is_region_manager_at_date(self.employee_id.department_id.id, fields.Date.context_today(self)):
                representatives |= self.env.user.employee_ids
        return representatives

    def _get_representative_id_domain(self):
        """
        Get a search domain to find hr.employee records of ones that are able to sign work contracts.
        Considered representatives of the company, these employees can be chosen to appear on the work contract
        instead of the CEO.
        @return: search domain to find representatives
        """
        representatives = self._get_possible_representatives()
        return [('id', 'in', representatives.ids)]

    representative_id = fields.Many2one(domain=[])

    @api.multi
    def confirm(self):
        self.ensure_one()
        if self.choose_representative:
            if self.representative_id not in self._get_possible_representatives():
                raise exceptions.AccessError(_('You do not have sufficient rights to perform this action'))
        if self.env.user.is_region_manager_at_date(self.employee_id.department_id.id):
            return super(PrintContractWizard, self.sudo().with_context(uid=1)).confirm()
        elif self.env.user.is_region_manager():
            raise exceptions.AccessError(_('You do not have sufficient rights to perform this action'))
        else:
            return super(PrintContractWizard, self).confirm()

    @api.onchange('choose_representative', 'employee_id')
    def _onchange_responsible_options(self):
        possible_representatives = self._get_possible_representatives()
        if self.env.user.employee_ids and self.env.user.employee_ids[0] in possible_representatives:
            self.representative_id = self.env.user.employee_ids[0]
        return {'domain': {'representative_id': [('id', 'in', possible_representatives.ids)]}}
