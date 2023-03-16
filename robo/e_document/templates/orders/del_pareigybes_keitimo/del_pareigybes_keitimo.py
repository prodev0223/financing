# -*- coding: utf-8 -*-
from odoo import models, api, _, exceptions


TEMPLATE = 'e_document.isakymas_del_pareigybes_keitimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_pareigybes_keitimo_workflow(self):
        self.ensure_one()
        contract = self.env['hr.contract'].search(
            [('employee_id', '=', self.employee_id2.id), ('date_start', '<=', self.date_3), '|',
             ('date_end', '=', False),
             ('date_end', '>=', self.date_3)],
            order='date_start desc', limit=1)
        new_appointment_created = False
        if contract:
            new_record = contract.update_terms(self.date_3, job_id=self.job_id4.id)
            if new_record:
                self.inform_about_creation(new_record)
                self.set_link_to_record(new_record)
                new_appointment_created = True
        else:
            raise exceptions.ValidationError(_('Negalite keisti pareigų, darbuotojas %s neturi aktyvaus kontrakto. '
                                               'Naudokite įsakymą dėl priėmimo į darbą') % self.employee_id2.name)
        self.write({'new_appointment_created': new_appointment_created})

    @api.multi
    def get_required_form_fields(self):
        """Overridden method, returns required fields for this template form view"""
        self.ensure_one()
        res = super(EDocument, self).get_required_form_fields()

        if self.template_id == self.env.ref(TEMPLATE):
            res.update({
                'employee_id2': _('Darbuotojo(-s) Vardas Pavardė'),
                'job_id4': _('Pareigos į kurias darbuotojas norėtų pakeisti savąsias'),
                'date_3': _('Įsigaliojimo data'),
            })
        return res


EDocument()
