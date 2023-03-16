# -*- coding: utf-8 -*-

from odoo import models, api, fields
from odoo.tools.translate import _


class HrEmployee(models.Model):

    _inherit = 'hr.employee'

    nesiusti = fields.Boolean(string='Nesiųsti atsiskaitymo lapelių', default=False)


HrEmployee()


class HrPayslip(models.Model):

    _inherit = 'hr.payslip'

    issiustas_email = fields.Boolean(string='Išsiųsta el. paštu', default=False, required=False, readonly=True)

    @api.multi
    def siusti_emaila(self):
        patvirtinti_ids = []
        for slip in self:
            if slip.state in ['draft', 'cancel']:
                continue
            if not slip.employee_id.active or slip.employee_id.nesiusti:
                continue
            # mtp = self.env['mail.template']
            mtp = self.env.ref('l10n_lt_payroll.algalapio_israso_email_template')
            mtp.send_mail(slip.id, force_send=True)
            if slip.id not in patvirtinti_ids:
                patvirtinti_ids.append(slip.id)
        self.env['hr.payslip'].browse(patvirtinti_ids).write({'state': 'done', 'issiustas_email': True})
        return True


HrPayslip()


class HrPayslipRun(models.Model):

    _inherit = 'hr.payslip.run'

    @api.multi
    def siusti_emailus(self):
        patvirtinti_ids = []
        for run in self:
            for slip in run.slip_ids:
                if slip.state in ['draft', 'cancel']:
                    continue
                if not slip.employee_id.active or slip.employee_id.nesiusti:
                    continue
                # mtp = self.env['mail.template']
                mtp = self.env.ref('l10n_lt_payroll.algalapio_israso_email_template')
                mtp.send_mail(slip.id, force_send=True)
                if slip.id not in patvirtinti_ids:
                    patvirtinti_ids.append(slip.id)
        self.env['hr.payslip'].browse(patvirtinti_ids).write({'state': 'done', 'issiustas_email': True})
        return True


HrPayslipRun()
