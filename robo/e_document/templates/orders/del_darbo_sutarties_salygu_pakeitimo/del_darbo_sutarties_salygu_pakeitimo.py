# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools, exceptions
from odoo.tools.translate import _


TEMPLATE = 'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    wage_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    job_id_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    department_id2_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    struct_id_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    etatas_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    work_norm_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    darbingumas_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    schedule_type_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    schedule_times_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    contract_end_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    contract_type_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    npd_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    advance_amount_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')
    selection_1_being_changed = fields.Boolean(compute='_compute_change_contract_terms_values_changed')

    @api.multi
    def isakymas_del_darbo_sutarties_salygu_pakeitimo_workflow(self):
        self.ensure_one()
        date_before = (datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('date_start', '<=', self.date_3),
            '|',
            ('date_end', '=', False),
            '|',
            ('date_end', '>=', self.date_3),
            ('date_end', '=', date_before)
        ], order='date_start desc', limit=1)

        line_ids = []
        for line in self.fixed_attendance_ids:
            new_line = self.env['fix.attendance.line'].create({
                'dayofweek': line.dayofweek,
                'hour_from': line.hour_from,
                'hour_to': line.hour_to,
            })
            line_ids.append(new_line.id)
        etatas = self.etatas_computed
        avansu_politika = 'fixed_sum' if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else False
        avansu_politika_suma = self.advance_amount if self.selection_1 == 'twice_per_month' and self.enable_advance_setup else 0.00

        schedule_template = self.env['schedule.template'].create({
            'template_type': self.darbo_grafikas,
            'wage_calculated_in_days': self.darbo_grafikas in ['fixed', 'suskaidytos'] and self.struct == 'MEN',
            'shorter_before_holidays': False if self.work_norm < 1.0 else True,
            'fixed_attendance_ids': [(6, 0, line_ids)],
            'etatas_stored': etatas,
            'work_norm': self.work_norm,
        })
        contract_date_end_diff = False
        if contract:
            struct = self.struct
            struct_id = self.env['hr.payroll.structure'].search([('code', '=', struct)], limit=1)
            use_npd = self.npd_type == 'auto'
            invalidumas = self.selection_bool_2 == 'true'
            darbingumas = False
            if invalidumas:
                if self.selection_nedarbingumas == '0_25':
                    darbingumas = self.env.ref('l10n_lt_payroll.0_25').id
                elif self.selection_nedarbingumas == '30_55':
                    darbingumas = self.env.ref('l10n_lt_payroll.30_55').id

            contract_type_is_being_changed = contract.rusis != self.darbo_rusis
            if self.darbo_rusis in ['terminuota', 'laikina_terminuota', 'pameistrystes', 'projektinio_darbo']:
                contract_end = self.date_6
            else:
                if contract_type_is_being_changed:
                    contract_end = False
                else:
                    # Important - contract_end_date can already be set even if contract is not terminated
                    contract_end = contract.date_end

            need_new_contract = False
            if contract_type_is_being_changed:
                need_new_contract = True
            if contract.struct_id.code != struct:
                need_new_contract = True
            end_old_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
            end_old = end_old_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            appointment = contract.with_context(date=end_old).appointment_id
            sodra_papildomai = True if appointment and appointment.sodra_papildomai else False
            sodra_papildomai_type = appointment.sodra_papildomai_type if appointment else 'full'

            if self.darbo_rusis in ['terminuota', 'laikina_terminuota', 'pameistrystes',
                                    'projektinio_darbo'] and self.date_6 != contract.date_end:
                contract_date_end_diff = True

            if need_new_contract:
                contract.end_contract(end_old)
                vals = {
                    'name': contract.name,
                    'date_start': self.date_3,
                    'date_end': contract_end,
                    'wage': self.wage_bruto,
                    'struct_id': struct_id.id,
                    'invalidumas': invalidumas,
                    'darbingumas': darbingumas,
                    'employee_id': contract.employee_id.id,
                    'job_id': self.job_id.id or False,
                    'rusis': self.darbo_rusis,
                    'sodra_papildomai': sodra_papildomai,
                    'sodra_papildomai_type': sodra_papildomai_type,
                    'use_npd': use_npd,
                    'schedule_template_id': schedule_template.id,
                    'avansu_politika': avansu_politika,
                    'avansu_politika_suma': avansu_politika_suma,
                    'freeze_net_wage': self.freeze_net_wage == 'true',
                    'order_date': self.date_3,
                    'trial_date_end': contract.trial_date_end,
                    'contract_priority': self.contract_priority or 'foremost',
                }
                if self.department_id2:
                    vals['department_id'] = self.department_id2.id

                contract_id = self.env['hr.contract.create'].create(vals).with_context(no_action=True).create_contract()
                if contract_id:
                    self.inform_about_creation(contract_id)
                    self.set_link_to_record(contract_id)
            else:
                if self.darbo_grafikas in ('sumine', 'lankstus', 'suskaidytos', 'individualus'):
                    leaves_accumulation_type = 'calendar_days'
                else:
                    leaves_accumulation_type = 'work_days'
                terms_date_end = contract.date_end if contract.date_end and contract.date_end != contract_end else False
                if terms_date_end and appointment.contract_terms_date_end != terms_date_end:
                    appointment.write({'contract_terms_date_end': terms_date_end})
                if contract.date_end != contract_end:
                    contract.write({'date_end': contract_end})
                usable = contract.date_end if contract.date_end else self.date_6
                etatas = self.etatas_computed if self.show_etatas_computed else self.etatas
                vals = {
                    'wage': self.wage_bruto,
                    'date_end': usable,
                    'struct_id': struct_id.id,
                    'contract_terms_date_end': usable,
                    'leaves_accumulation_type': leaves_accumulation_type,
                    'invalidumas': invalidumas,
                    'darbingumas': darbingumas,
                    'use_npd': use_npd,
                    'darbo_rusis': self.darbo_rusis,
                    'schedule_template_id': schedule_template.id,
                    'sodra_papildomai': sodra_papildomai,
                    'sodra_papildomai_type': sodra_papildomai_type,
                    'work_norm': self.work_norm,
                    'etatas': etatas,
                    'job_id': self.job_id.id,
                    'avansu_politika': avansu_politika,
                    'avansu_politika_suma': avansu_politika_suma,
                    'freeze_net_wage': self.freeze_net_wage == 'true',
                    'contract_priority': self.contract_priority or 'foremost',
                }
                if self.department_id2:
                    vals['department_id'] = self.department_id2.id

                new_record = contract.update_terms(self.date_3, **vals)

                if new_record:
                    self.inform_about_creation(new_record)
                    self.set_link_to_record(new_record)

            # Ticket to inform accountant about potential need for manual fixes and double payslips;
            if need_new_contract and datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT).day != 1:
                try:
                    subject = '[{}] Darbo sutarties sąlygų pakeitimo dokumentas buvo pasirašytas'.format(
                        self._cr.dbname)
                    body = '''Buvo pasirašytas darbo sutarties sąlygų pakeitimo dokumentas. 
                    Primename, kad šiam mėnesiui yra sukurti du algalapiai ir gali prireikti rankinių taisymų susijusių su NPD.
                    '''
                    self.create_internal_ticket(subject, body)
                except Exception:
                    message = '[{}] Failed to create a ticket informing about potential need for manual fixes'.format(self._cr.dbname)
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'error_message': message,
                    })

        # Check if the document takes effect in the past and inform accountant if it does
        year_month_contract_start = '-'.join(self.date_3.split('-')[0:2])
        year_month_contract_sign = '-'.join(datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT).split('-')[0:2])
        payslip_of_contract_start_month = self.env['hr.payslip.run'].search_count([
            ('date_end', '>=', self.date_from),
            ('date_start', '<=', self.date_from),
            ('state', '=', 'close'),
        ])
        if year_month_contract_sign > year_month_contract_start and payslip_of_contract_start_month:
            try:
                subject = _('[{}] Pasirašytas įsakymas dėl darbo sąlygų keitimo atgaline data ({})').format(self._cr.dbname, self.id)
                body = _("""Pasirašytas įsakymas ({}) dėl darbo salygų keitimo atgaline data ({}). 
                Gali reikėti atlikti veiksmus rankiniu būdu.""").format(self.id, self.date_from)
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                message = _("""
                [{}] Failed to create a ticket for change of work terms for a past date: {} 
                \nError: {}
                """).format(self._cr.dbname, self.id, str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

        self.write({
            'new_appointment_created': True,
            'date_end_change': contract_date_end_diff
        })

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        if not template:
            return res
        for rec in self.filtered(lambda doc: doc.template_id == template and not doc.sudo().skip_constraints_confirm):
            existing_documents = self.search_count([
                ('template_id', '=', template.id),
                ('employee_id2', '=', rec.employee_id2.id),
                ('state', '=', 'e_signed'),
                ('rejected', '=', False),
                ('date_3', '=', rec.date_3)
            ])
            if existing_documents:
                raise exceptions.ValidationError(_('A document for that employee with that date already exists.'))
        return res

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, False)
        if self.cancel_id and self.cancel_id.template_id == template and self.cancel_id.employee_data_is_accessible():
            findir_email = self.sudo().env.user.company_id.findir.partner_id.email
            database = self._cr.dbname
            subject = 'Įsakymas dėl darbo sutarties sąlygų pakeitimo buvo atšauktas [%s]' % database
            doc_url = self.cancel_id._get_document_url()
            doc_name = '<a href=%s>%s</a>' % (doc_url, self.cancel_id.name) if doc_url else self.cancel_id.name
            message = 'Dokumentas %s buvo atšauktas. Reikia rankiniu būdu atstatyti sutarties pakeitimus. Turėjo būti sukurtas ticketas.' % doc_name
            if findir_email:
                self.env['script'].send_email(emails_to=[findir_email],
                                              subject=subject,
                                              body=message)
            try:
                body = """
                Įsakymas dėl darbo sutarties sąlygų pakeitimo buvo atšauktas. Reikia atlikti pakeitimus sutarčiai rankiniu būdu, kad būtų atstatyta buvusi būsena.
                """
                self.cancel_id.create_internal_ticket(subject, body)
            except Exception as exc:
                self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)
        else:
            super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def is_isakymas_del_darbo_sutarties_salygu_pakeitimo_template(self):
        self.ensure_one()
        return self.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)

    @api.one
    @api.depends('employee_id2', 'date_3', 'appointment_id_computed', 'template_id', 'float_1', 'job_id',
                 'struct', 'etatas_computed', 'work_norm', 'selection_bool_2', 'selection_nedarbingumas',
                 'darbo_grafikas', 'fixed_attendance_ids', 'darbo_rusis', 'date_6', 'npd_type', 'advance_amount')
    def _compute_change_contract_terms_values_changed(self):
        if self.new_appointment_created and self.employee_data_is_accessible():
            date_to_get = (datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(
                days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            appointment_id = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', self.employee_id2.id),
                ('date_start', '<=', date_to_get),
                '|',
                ('date_end', '>=', date_to_get),
                ('date_end', '=', False)
            ])
        else:
            appointment_id = self.appointment_id_computed
        if self.is_isakymas_del_darbo_sutarties_salygu_pakeitimo_template() and appointment_id:
            self.wage_being_changed = self.float_1 != appointment_id.wage
            self.job_id_being_changed = self.job_id.id != appointment_id.job_id.id
            current_department = appointment_id.department_id or self.employee_id2.department_id
            self.department_id2_being_changed = self.department_id2 and self.department_id2.id != current_department.id
            self.struct_id_being_changed = self.struct != appointment_id.struct_id.code
            self.etatas_being_changed = self.etatas_computed != appointment_id.schedule_template_id.etatas
            self.work_norm_being_changed = self.work_norm != appointment_id.schedule_template_id.work_norm
            appointment_darbingumas = 'true' if appointment_id.invalidumas else 'false'
            self.darbingumas_being_changed = True if appointment_darbingumas != self.selection_bool_2 or (
                    appointment_darbingumas == 'true' and self.selection_nedarbingumas != appointment_id.darbingumas.name) else False
            self.schedule_type_being_changed = self.darbo_grafikas != appointment_id.schedule_template_id.template_type
            self.advance_amount_being_changed = self.enable_advance_setup and self.advance_amount != appointment_id.avansu_politika_suma and self.selection_1 == 'twice_per_month'
            self.selection_1_being_changed = self.enable_advance_setup and (
                    (self.selection_1 == 'twice_per_month' and appointment_id.avansu_politika == False) or (
                    self.selection_1 == 'once_per_month' and appointment_id.avansu_politika == 'fixed_sum'))
            e_doc_lines = self.fixed_attendance_ids
            sched_lines = appointment_id.schedule_template_id.fixed_attendance_ids
            match = True
            if len(e_doc_lines) != len(sched_lines):
                match = False
            if match:
                for line in e_doc_lines:
                    matching_line = sched_lines.filtered(lambda
                                                             l: l.dayofweek == line.dayofweek and l.hour_from == line.hour_from and l.hour_to == line.hour_to)
                    if not matching_line:
                        match = False
                        break
            if not e_doc_lines or self.darbo_grafikas == 'individualus':
                match = True
            self.schedule_times_being_changed = not match
            match_doc_npd_type = 'auto' if appointment_id.use_npd else 'manual'
            self.npd_being_changed = self.npd_type != match_doc_npd_type
            self.date_6 = False if self.darbo_rusis not in ['terminuota', 'laikina_terminuota', 'pameistrystes',
                                                            'projektinio_darbo'] else self.date_6
            self.contract_end_being_changed = self.date_6 != appointment_id.contract_id.date_end and self.darbo_rusis in [
                'terminuota', 'laikina_terminuota', 'pameistrystes', 'projektinio_darbo']
            if self.new_appointment_created and self.date_end_change:
                self.contract_end_being_changed = True
            self.contract_type_being_changed = self.darbo_rusis != appointment_id.contract_id.rusis

    @api.onchange('darbo_rusis')
    def _onchange_darbo_rusis_set_date_6(self):
        if self.is_isakymas_del_darbo_sutarties_salygu_pakeitimo_template():
            app = self.appointment_id_computed
            if app and app.contract_id.date_end:
                self.date_6 = app.contract_id.date_end

    @api.onchange('job_id')
    def _onchange_job_id(self):
        if self.is_isakymas_del_darbo_sutarties_salygu_pakeitimo_template() and self.job_id.department_id:
            self.department_id2 = self.job_id.department_id.id

    @api.onchange('employee_id2', 'date_3')
    def _set_appointment_values(self):
        is_salygu_pakeitimo_doc = self.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)
        app = self.appointment_id_computed
        if app and is_salygu_pakeitimo_doc and self.employee_data_is_accessible():
            ids = []
            app = app.sudo()
            for line in app.schedule_template_id.fixed_attendance_ids:
                # lines |= EDocFixAttendanceLine.create({
                #     'hour_from': line.hour_from,
                #     'hour_to': line.hour_to,
                #     'dayofweek': line.dayofweek,
                #     'e_document': self.id,
                # })
                vals = {
                    'hour_from': line.hour_from,
                    'hour_to': line.hour_to,
                    'dayofweek': line.dayofweek
                }
                ids.append((0, 0, vals))
            self.fixed_attendance_ids = [(5,)] + ids

            self.float_1 = app.wage
            self.job_id = app.job_id.id
            self.department_id2 = app.job_id.department_id.id or app.department_id.id or \
                                  self.employee_id2.department_id.id
            self.date_2 = app.trial_date_end
            self.struct = app.struct_id.code
            self.freeze_net_wage = 'true' if app.freeze_net_wage else 'false'
            self.npd_type = 'auto' if app.use_npd else 'manual'
            self.work_norm = app.schedule_template_id.work_norm
            self.selection_bool_2 = 'true' if app.invalidumas else 'false'
            self.selection_nedarbingumas = '0_25' if app.darbingumas.name == '0_25' else '30_55'
            self.darbo_grafikas = app.schedule_template_id.template_type
            # self.fixed_attendance_ids = [(6, 0, lines.mapped('id'))]
            self.date_6 = app.contract_id.date_end
            self.darbo_rusis = app.contract_id.rusis
            self.etatas = app.schedule_template_id.etatas
            self.contract_priority = app.contract_priority or 'foremost'


EDocument()
