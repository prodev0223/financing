# -*- coding: utf-8 -*-

from six import iteritems
from odoo import _, api, fields, models


class HrContract(models.Model):
    _inherit = 'hr.contract'

    contract_conditions = fields.Text(string='Nustatomos papildomos darbo sutarties sąlygos')
    contract_liabilities = fields.Text(string='Kiti darbuotojo ir darbdavio tarpusavio įsipareigojimai')

    @api.multi
    def name_get(self):
        names = dict(super(HrContract, self).name_get())
        for contract in self:
            name = names.get(contract.id)
            other_contracts_with_same_name = contract.employee_id.contract_ids.filtered(lambda c: c.name == name)
            if len(other_contracts_with_same_name) > 1:
                name += _(' (nuo {})').format(contract.date_start)
                names.update({contract.id: name})
        return list(iteritems(names))

    # @api.multi #This is handled by the cron job
    # def set_as_close(self):
    #     date_now = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
    #     contracts = self.search([('date_start', '<=', date_now), '|',
    #                              ('date_end', '>', date_now), ('date_end', '=', False)], count=True)
    #     if contracts and self.employee_id.active:
    #         self.sudo().employee_id.toggle_active()
    #     return self.write({'state': 'close'})
