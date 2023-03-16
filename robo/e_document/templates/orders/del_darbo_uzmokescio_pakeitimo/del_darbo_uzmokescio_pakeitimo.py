# -*- coding: utf-8 -*-

from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, models, tools, fields
TEMPLATE = 'e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    struct_computed = fields.Selection([('MEN', 'Mėnesinis'), ('VAL', 'Valandinis')], string='Atlyginimo struktūra',
                                       compute='_compute_struct_computed')

    @api.multi
    def isakymas_del_darbo_uzmokescio_pakeitimo_workflow(self):
        self.ensure_one()
        date_5_dt = datetime.strptime(self.date_5, tools.DEFAULT_SERVER_DATE_FORMAT)
        day_before = (date_5_dt - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('date_start', '<=', self.date_5),
            '|',
            ('date_end', '=', False),
            '|',
            ('date_end', '=', day_before),
            ('date_end', '>=', self.date_5)
        ], order='date_start desc', limit=1)

        avansu_politika = 'fixed_sum' if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else False
        avansu_politika_suma = self.advance_amount if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else 0.00

        if contract:
            new_record = contract.update_terms(self.date_5, wage=self.wage_bruto, avansu_politika=avansu_politika,
                                               avansu_politika_suma=avansu_politika_suma,
                                               freeze_net_wage=self.freeze_net_wage == 'true')
            if new_record:
                self.inform_about_creation(new_record)
                self.set_link_to_record(new_record)

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, False)
        if self.cancel_id and self.cancel_id.template_id == template:
            findir_email = self.sudo().env.user.company_id.findir.partner_id.email
            database = self._cr.dbname
            subject = 'Įsakymas dėl darbo užmokesčio pakeitimo buvo atšauktas [%s]' % database
            doc_url = self.cancel_id._get_document_url()
            doc_name = '<a href=%s>%s</a>' % (doc_url, self.cancel_id.name) if doc_url else self.cancel_id.name
            message = 'Dokumentas %s buvo atšauktas. Reikia atstatyti sutarties pakeitimus rankiniu būdu. Turėjo būti sukurtas ticketas.' % doc_name
            if findir_email:
                self.env['script'].send_email(emails_to=[findir_email],
                                              subject=subject,
                                              body=message)
            try:
                body = """
                    Įsakymas dėl darbo užmokesčio pakeitimo buvo atšauktas. Reikia atlikti pakeitimus sutarčiai 
                    rankiniu būdu, kad būtų atstatyta buvusi būsena. Darbuotojas(-a) - {}.
                """.format(self.employee_id2.display_name)
                self.cancel_id.create_internal_ticket(subject, body)
            except Exception as exc:
                self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)
        else:
            super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def is_darbo_uzmokescio_mokejimo_template(self):
        self.ensure_one()
        return self.template_id == self.env.ref(TEMPLATE)

    @api.onchange('template_id', 'employee_id2')
    def default_contract_vals(self):
        if self.template_id.id == self.env.ref(TEMPLATE).id:
            if self.employee_id2:
                current_day = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                contract_id = self.env['hr.contract'].search([('employee_id', '=', self.employee_id2.id),
                                                              ('date_start', '<', current_day), '|',
                                                              ('date_end', '=', False),
                                                              ('date_end', '>=', current_day)])
                if contract_id:
                    appointment_id = contract_id.get_active_appointment()
                    if appointment_id:
                        self.darbo_rusis = contract_id.rusis
                        self.struct = appointment_id.struct_id.code
                        self.npd_type = 'auto' if appointment_id.use_npd else 'manual'
                        self.selection_bool_1 = 'true' if appointment_id.sodra_papildomai else 'false'
                        self.freeze_net_wage = 'true' if appointment_id.freeze_net_wage else 'false'

    @api.one
    @api.depends('float_1', 'current_salary')
    def set_salary_diff(self):
        if self.template_id.id == self.env.ref(TEMPLATE).id and self.current_salary and self.float_1:
            self.salary_diff = round(self.float_1 - self.current_salary, 2)
        else:
            self.salary_diff = 0.0

    @api.one
    @api.depends('template_id', 'date_5', 'employee_id2', 'selection_bool_1')
    def _compute_bool_1(self):
        du_pakeitimo_template_id = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if self.template_id == du_pakeitimo_template_id:
            if self.compute_bool_1_stored:
                self.selection_bool_1 = self.compute_bool_1_stored
                self.compute_bool_1 = self.selection_bool_1
            else:
                self.compute_bool_1 = self.selection_bool_1

    @api.one
    @api.depends('template_id', 'date_5', 'employee_id2', 'sodra_papildomai_type')
    def _compute_sodra_papildomai_type(self):
        du_pakeitimo_template_id = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if self.template_id == du_pakeitimo_template_id:
            if self.sodra_papildomai_type_stored:
                self.sodra_papildomai_type = self.sodra_papildomai_type_stored
                self.compute_sodra_papildomai_type = self.sodra_papildomai_type
            else:
                self.compute_sodra_papildomai_type = self.sodra_papildomai_type

    @api.one
    @api.depends('struct')
    def _compute_struct_computed(self):
        """
        Making 'struct' field read-only in form view resets its default value when saving the form
        :return: None
        """
        self.struct_computed = self.struct

    @api.onchange('employee_id2')
    def onch_employee_du_keitimas(self):
        if self.template_id == self.env.ref(TEMPLATE) and self.employee_id2:
            last_appointment = self.env['hr.contract.appointment'].search([('employee_id', '=', self.employee_id2.id)],
                                                                          order='date_start desc', limit=1)
            date = self.date_5 if self.date_5 else datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.selection_bool_1 = 'true' if last_appointment.sodra_papildomai else 'false'
            if date >= '2019-01-01' and self.selection_bool_1 == 'true':
                self.sodra_papildomai_type = 'full' if last_appointment.sodra_papildomai_type == 'full' else 'exponential'
            self.selection_bool_2 = 'true' if last_appointment.invalidumas else 'false'
            if self.selection_bool_2 == 'true':
                self.selection_nedarbingumas = '0_25' if last_appointment.darbingumas.name == '0_25' else '30_55'
            self.npd_type = 'auto' if last_appointment.use_npd else 'manual'
            self.etatas = last_appointment.schedule_template_id.etatas
            self.work_norm = last_appointment.schedule_template_id.work_norm if last_appointment else 1.0


EDocument()
