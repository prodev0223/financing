# -*- coding: utf-8 -*-

from odoo import api, fields, models


class HrContractTerminate(models.TransientModel):

    _name = 'hr.contract.terminate'

    def _default_contract_id(self):
        return self._context.get('active_id', False)

    contract_id = fields.Many2one('hr.contract', string='Kontraktas', required=True, default=_default_contract_id,
                                  ondelete="cascade")
    date = fields.Date(string='Nutraukimo data', required=True)

    @api.multi
    def end_contract(self):
        self.ensure_one()
        self.contract_id.end_contract(self.date)


HrContractTerminate()