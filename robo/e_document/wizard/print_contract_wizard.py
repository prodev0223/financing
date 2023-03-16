# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import api, fields, models, tools


class PrintContractWizard(models.TransientModel):
    _inherit = 'print.contract.wizard'

    def _get_representative_id_domain(self):
        """
        Get a search domain to find hr.employee records of ones that are able to sign work contracts.
        Considered representatives of the company, these employees can be chosen to appear on the work contract
        instead of the CEO.
        @return: search domain to find representatives
        """
        date = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        representatives = self.env.user.sudo().company_id.vadovas
        representatives |= self.env.ref('robo_basic.group_robo_hr_manager').users.mapped('employee_ids')
        representatives |= self.env.ref('robo_basic.group_robo_premium_manager').users.mapped('employee_ids')
        representatives |= self.env['e.document.delegate'].sudo().search([
            ('date_start', '<', date),
            ('date_stop', '>', date),
        ]).mapped('employee_id')
        return [('id', 'in', representatives.ids)]

    representative_id = fields.Many2one(domain=lambda self: self._get_representative_id_domain(), )

    @api.onchange('choose_representative')
    def _onchange_choose_representative(self):
        """
        Get the default value for representative as person who signed the last e document for work contract.
        """
        template = self.env.ref('e_document.isakymas_del_priemimo_i_darba_template')
        signed_user = self.env['e.document'].sudo().search([
            ('template_id', '=', template.id),
            ('employee_id2', '=', self.employee_id.id),
            ('record_model', '=', 'hr.contract'),
        ], order='date_document desc', limit=1).mapped('signed_user_id')
        manager = self.env.user.sudo().company_id.vadovas
        representative = signed_user.employee_ids[0] if signed_user.employee_ids else manager
        self.representative_id = representative.id
