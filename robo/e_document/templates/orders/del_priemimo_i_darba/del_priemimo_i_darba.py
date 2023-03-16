# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime, timedelta

from odoo import _, api, exceptions, models, tools, fields

TEMPLATE = 'e_document.isakymas_del_priemimo_i_darba_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    show_wage_less_than_mma_warning = fields.Boolean(compute='_compute_show_wage_less_than_mma_warning')
    show_request_date_after_order_date_warning = fields.Boolean(
        compute='_compute_show_request_date_after_order_date_warning')

    @api.multi
    @api.depends('float_1', 'date_from', 'template_id', 'struct', 'du_input_type')
    def _compute_show_wage_less_than_mma_warning(self):
        doc_template = self.env.ref(TEMPLATE)
        documents = self.filtered(lambda doc: doc.template_id == doc_template and
                                              doc.state in ['draft', 'confirm'] and
                                              doc.struct and doc.struct.upper() == 'MEN')
        for doc in documents:
            mma = self.env['hr.contract'].with_context(date=doc.date_from).get_payroll_tax_rates(
                ['mma'])['mma']
            if doc.du_input_type == 'neto':
                wage = doc.wage_bruto
            else:
                wage = doc.float_1
            if tools.float_compare(mma, wage, precision_digits=2) > 0:
                doc.show_wage_less_than_mma_warning = True

    @api.multi
    @api.depends('date_2', 'date_document')
    def _compute_show_request_date_after_order_date_warning(self):
        doc_template = self.env.ref(TEMPLATE)
        for rec in self.filtered(lambda doc: doc.template_id == doc_template):
            rec.show_request_date_after_order_date_warning = rec.date_2 and rec.date_document and \
                                                             rec.date_2 > rec.date_document

    @api.model
    def default_get(self, fields_list):
        res = super(EDocument, self).default_get(fields_list)
        doc_template = self.env.ref(TEMPLATE)
        if res.get('template_id') == doc_template.id:
            mma = self.env['hr.contract'].sudo().get_payroll_tax_rates(['mma'])['mma']
            res['float_1'] = mma
            employee = self.env['hr.employee'].browse(res.get('employee_id2')).exists()
            if employee:
                res['bool_1'] = employee.is_foreign_resident
                if res['bool_1']:
                    res['country_id'] = employee.nationality_id.id
        return res

    @api.onchange('bool_1')
    def _onchange_is_foreigner(self):
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE)):
            if rec.bool_1:
                rec.npd_type = 'manual'

    @api.onchange('employee_id2')
    def _onchange_employee_id(self):
        for rec in self.filtered(lambda t: t.template_id == self.env.ref(TEMPLATE)):
            rec.bool_1 = rec.employee_id2.is_foreign_resident

    @api.onchange('job_id2')
    def _onchange_job_id2(self):
        if self.template_id == self.env.ref(TEMPLATE) and self.job_id2.department_id:
            self.department_id2 = self.job_id2.department_id.id

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """
        Call super workflow value checking, then execute
        date checks for this template on confirm action
        :return: None
        """
        super(EDocument, self).execute_confirm_workflow_check_values()

        # Ref current template
        doc_template = self.env.ref(TEMPLATE)
        past_forming = self.sudo().env.user.company_id.e_documents_allow_historic_signing_spec
        for rec in self.filtered(
                lambda x: not x.sudo().skip_constraints_confirm and x.sudo().template_id == doc_template):
            # Throw an exception on outdated contract type
            if self.darbo_rusis == 'nenustatytos_apimties':
                raise exceptions.ValidationError(_('Employment contract type is outdated. Choose a different type.'))
            # Check order and request dates
            order_date_dt = datetime.strptime(rec.date_document, tools.DEFAULT_SERVER_DATE_FORMAT)
            request_date_dt = datetime.strptime(rec.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)
            now_dt = datetime.utcnow()
            now = now_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if now > rec.date_document and not past_forming:
                raise exceptions.ValidationError(
                    _('Įsakymo data negali būti anksčiau nei pasirašymo data! Pakoreguokite laukelį "Dokumento data"')
                )
            if request_date_dt > order_date_dt:
                raise exceptions.ValidationError(_('Prašymo data negali būti vėlesnė negu įsakymo data!'))

            # Check order and first work day dates
            first_work_day_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            warning_template = _('Įsakymo data turi būti ne vėlesnė kaip 2 d.d. prieš įdarbinimo dieną.')
            if order_date_dt > first_work_day_dt:
                raise exceptions.ValidationError(warning_template)
            else:
                related_national_holidays = self.env['sistema.iseigines'].search(
                    [('date', '<=', rec.date_from), ('date', '>=', rec.date_document)]).mapped('date')
                num_days = 0
                while order_date_dt <= first_work_day_dt:
                    if order_date_dt.weekday() not in (5, 6) and order_date_dt.strftime(
                            tools.DEFAULT_SERVER_DATE_FORMAT) not in related_national_holidays:
                        num_days += 1
                    order_date_dt += timedelta(days=1)
                if num_days <= 2:
                    raise exceptions.ValidationError(warning_template)

    # Main Method // --------------------------------------------------------------------------------------------------

    @api.multi
    def isakymas_del_priemimo_i_darba_workflow(self):
        self.ensure_one()
        # Throw an exception on outdated contract type
        if self.darbo_rusis == 'nenustatytos_apimties':
            raise exceptions.ValidationError(_('Employment contract type is outdated. Choose a different type.'))

        # Determine disability values
        invalidumas = self.selection_bool_2 == 'true'
        darbingumas = False
        if invalidumas:
            if self.selection_nedarbingumas == '0_25':
                darbingumas = self.env.ref('l10n_lt_payroll.0_25').id
            elif self.selection_nedarbingumas == '30_55':
                darbingumas = self.env.ref('l10n_lt_payroll.30_55').id

        # Determine the salary structure
        struct_id = self.env['hr.payroll.structure'].search([('code', 'like', self.struct.upper())], limit=1)
        struct_id = struct_id.id if struct_id else False

        line_ids = []
        for line in self.fixed_attendance_ids:
            new_line = self.env['fix.attendance.line'].create({
                'dayofweek': line.dayofweek,
                'hour_from': line.hour_from,
                'hour_to': line.hour_to,
            })
            line_ids.append(new_line.id)

        wage_calculated_in_days = False
        if self.darbo_grafikas in ['fixed', 'suskaidytos'] and self.struct == 'MEN':
            wage_calculated_in_days = True

        weekly_hours = self.etatas_computed * 40 * self.work_norm
        five_day_default = [round(weekly_hours / 5.0, 2) for i in range(0, 5)] + [0, 0]  # P3:DivOK
        six_day_default = [round(weekly_hours / 6.0, 2) for i in range(0, 6)] + [0]  # P3:DivOK

        weekday_times = []
        for weekday in range(0, 7):
            weekday_lines = self.fixed_attendance_ids.filtered(lambda l: l.dayofweek == str(weekday))
            weekday_times.append(sum([round(abs(weekday_line.hour_to - weekday_line.hour_from), 2) for weekday_line in weekday_lines]))

        if weekday_times == five_day_default or not self.fixed_attendance_ids:
            work_week_type = 'five_day'
        elif weekday_times == six_day_default:
            work_week_type = 'six_day'
        else:
            work_week_type = 'based_on_template'

        schedule_template = self.env['schedule.template'].create({
            'template_type': self.darbo_grafikas,
            'etatas_stored': self.etatas_computed,
            'work_norm': self.work_norm,
            'wage_calculated_in_days': wage_calculated_in_days,
            'shorter_before_holidays': False if self.work_norm < 1.0 else True,
            'fixed_attendance_ids': [(6, 0, line_ids)],
            'work_week_type': work_week_type
        })

        contract_id = self.env['hr.contract.create'].create({
            'employee_id': self.employee_id2.id,
            'job_id': self.job_id2 and self.job_id2.id or False,
            'department_id': self.department_id2.id or False,
            'struct_id': struct_id,
            'date_start': self.date_from,
            'date_end': self.date_6,
            'wage': self.wage_bruto,
            'rusis': self.darbo_rusis,
            'sodra_papildomai': True if self.selection_bool_1 == 'true' else False,
            'sodra_papildomai_type': self.sodra_papildomai_type,
            'trial_date_end': self.date_1,
            'use_npd': self.npd_type == 'auto',
            'contract_priority': self.contract_priority or 'foremost',
            'invalidumas': invalidumas,
            'darbingumas': darbingumas,
            'schedule_template_id': schedule_template.id,
            'avansu_politika': 'fixed_sum' if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else False,
            'avansu_politika_suma': self.advance_amount if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else 0.00,
            'freeze_net_wage': self.freeze_net_wage == 'true',
            'order_date': self.date_document,
        }).with_context(no_action=True).create_contract()
        # Use different taxes if employee is foreigner
        if self.bool_1:
            tax_keys = ['employee_tax_fund_foreigner_with_visa_pct', 'employer_sodra_foreigner_with_visa_pct', ]
            foreigner_tax_percentages = contract_id.get_payroll_tax_rates(tax_keys)
            if any(tax_key not in foreigner_tax_percentages.keys() for tax_key in tax_keys):
                raise exceptions.ValidationError(
                    _('Tax rates for employee tax fund and / or employer sodra for foreigner with visa were not found. '
                      'Please contact the system administrator.'))
            contract_id.write({
                'darbuotojo_pensijos_proc': foreigner_tax_percentages['employee_tax_fund_foreigner_with_visa_pct'],
                'darbdavio_sodra_proc': foreigner_tax_percentages['employer_sodra_foreigner_with_visa_pct'],
                'darbuotojo_sveikatos_proc': 0.0,
                'use_darbuotojo_pensijos': True,
                'use_darbuotojo_sveikatos': True,
                'use_darbdavio_sodra': True,
                'override_taxes': True,
            })
            self.employee_id2.sudo().write({'is_non_resident': True})

        appointment = contract_id.with_context(date=self.date_from).appointment_id
        if self.du_input_type == 'neto':
            dif = tools.float_compare(appointment.neto_monthly, self.float_1, precision_digits=2)
            counter = 10
            while dif and counter:
                appointment.wage -= 0.01 * dif
                dif = tools.float_compare(appointment.neto_monthly, self.float_1, precision_digits=2)
                counter -= 1

            if dif != 0:
                subject = 'Nurodytas neteisingas NETO naujam kontraktui'
                body = ''' 
                        Nepavyko perskaičiuoti. NETO alga įsakyme priimti į darbą buvo nustatyta %s, 
                        o reikšmė prie darbuotojo sutarties yra %s.
                        ''' % (appointment.neto_monthly, self.float_1)
                try:
                    self.create_internal_ticket(subject, body)
                except:
                    findir_email = self.sudo().env.user.company_id.findir.partner_id.email
                    if findir_email:
                        self.env['script'].sudo().send_email(emails_to=[findir_email],
                                                             subject=subject,
                                                             body=body)
                    else:
                        self.env['robo.bug'].sudo().create({
                            'user_id': self.env.user.id,
                            'error_message': body + '\nDocument ID: %s' % self.id,
                            'subject': subject,
                        })

        self.inform_about_creation(contract_id)
        if self.bool_1 and self.country_id:
            self.inform_about_foreigner_recruited()

        # Create a ticket for accountant if contract start date is a prior month
        year_month_contract_start = '-'.join(self.date_from.split('-')[0:2])
        year_month_contract_sign = '-'.join(datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT).split('-')[0:2])
        is_payslip_closed = self.env['hr.payslip.run'].search_count([
            ('date_end', '>=', self.date_from),
            ('date_start', '<=', self.date_from),
            ('state', '=', 'close'),
        ])
        if year_month_contract_sign > year_month_contract_start and is_payslip_closed:
            try:
                subject = _('[{}] Pasirašytas įsakymas dėl priėmimo į darbą atgaline data ({})').format(self._cr.dbname, self.id)
                body = _("""Pasirašytas įsakymas ({}) dėl priėmimo į darbą atgaline data ({}). 
                Gali reikėti atlikti veiksmus rankiniu būdu.""").format(self.id, self.date_from)
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                message = _("""
                Failed to create a ticket for signing a work contract for a past date: {}
                \nError: {}
                """).format(self.id, str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

        create_request_document = self.env.user.company_id.sudo().enable_employment_requests_on_order_sign

        if create_request_document:
            request_template = self.env.ref('e_document.prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_template')
            related_request_document = self.search([
                ('template_id', '=', request_template.id),
                ('employee_id1', '=', self.employee_id2.id),
                ('date_1', '=', self.date_from),
            ])

            if not related_request_document:
                self.create({
                    'template_id': request_template.id,
                    'employee_id1': self.employee_id2.id,
                    'date_document': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'date_1': self.date_from,
                    'document_type': 'prasymas',
                    'text_4': self.employee_id2.bank_account_id.acc_number or False,
                    'selection_bool_1': self.selection_bool_1,
                    'sodra_papildomai_type': self.sodra_papildomai_type,
                    'selection_bool_3': 'true' if self.npd_type == 'auto' else 'false'
                })

        self.write({'record_model': 'hr.contract', 'record_id': contract_id.id})

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, False)
        document = self.cancel_id
        if document and document.template_id == template:
            if document.record_id and document.record_model == 'hr.contract':
                contract = self.env['hr.contract'].browse(document.record_id).exists()
                if contract:
                    payslips = self.env['hr.payslip'].search([('contract_id', '=', contract.id)], limit=1)
                    if not payslips:
                        contract.appointment_ids.unlink()
                        contract.unlink()
        else:
            return super(EDocument, self).execute_cancel_workflow()

    @api.one
    @api.depends('employee_id2')
    def _show_warning(self):
        self.show_warning = False
        if self.template_id == self.env.ref('e_document.isakymas_del_priemimo_i_darba_template',
                                            raise_if_not_found=False) and self.employee_id2 and not self.employee_id2.identification_id:
            self.show_warning = True

    @api.multi
    def inform_about_foreigner_recruited(self):
        """
        Ticket and email informing accountant that an order of employment was signed
        for an employee who is not a citizen of Lithuania
        """
        self.ensure_one()
        subject = _('[{}] Priimtas darbuotojas nėra LT pilietis'.format(self.env.cr.dbname))
        body = _('Priimtas darbuotojas {} nėra LT pilietis, galimai reikia pateikti LDU pranešimą.').format(
            self.employee_id2.name_related)
        try:
            self.create_internal_ticket(subject, body)
        except Exception as exc:
            message = 'Failed to create a ticket informing that recruited employee is not a lithuanian citizen.' \
                      '\nError: {}'.format(str(exc.args))
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': message,
            })
        accountants_email = self.env.user.company_id.findir.partner_id.email
        self.env['script'].send_email(
            emails_to=[accountants_email],
            subject=subject,
            body=body,
        )


EDocument()
