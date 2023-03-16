# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, models, _, tools, exceptions


class HrPayroll(models.Model):
    _inherit = 'hr.payroll'

    @staticmethod
    def document_has_manual_changes(document, expected_du_input_type, new_minimum_wage):
        """ Check if a document has manual changes - document data differs from what it's supposed to be """
        if document.du_input_type != expected_du_input_type:
            # Salary is going to be changed from GROSS to NET or vice versa
            return True
        # Calculate adjusted document wage
        document_wage = document.float_1
        if document.struct == 'MEN':
            document_wage *= document.etatas_computed if document.show_etatas_computed else document.etatas
        document_wage_more_than_expected = tools.float_compare(document_wage, new_minimum_wage, precision_digits=2) >= 0
        # If the document wage is less than the expected wage then the document has manual changes and the client is
        # changing some other values too
        if not document_wage_more_than_expected:
            return True
        return False

    @staticmethod
    def reload_document(document, confirm=False):
        if document.sudo().running:
            return
        document._compute_name()
        document._view_id()
        document._compute_payroll()
        document._compute_related_employee_ids()
        document._doc_partner_id()
        document.set_final_document()
        if document.state == 'draft' and confirm:
            try:
                document.confirm()
                document.create_pdf()
            except:
                pass

    @api.model
    def find_next_minimum_wage_change_date(self, date_from, maximum_number_of_days_in_the_future):
        """ Finds the next payroll.parameter.history for mma and min_hourly_rate fields based on company setting"""
        company = self.env.user.company_id

        # Specifies how many days after to look. Assumes that the documents for salary changes before this cutoff have
        # already been created. The next minimum wage change is at least cutoff_days from today.
        cutoff_days = 7

        # Compute dates
        if date_from:
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            date_from_dt = datetime.now()

        date_from_dt += relativedelta(days=cutoff_days)
        date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        domain = [
            ('field_name', 'in', ['mma', 'min_hourly_rate', 'npd_max']),
            ('date_from', '>=', date_from),
            ('company_id', '=', company.id)
        ]

        # Check if specified
        if maximum_number_of_days_in_the_future:
            date_to_dt = datetime.now() + relativedelta(days=maximum_number_of_days_in_the_future)
            date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            domain.append(('date_from', '<=', date_to))

        # Find first minimum wage parameter
        next_parameter = self.env['payroll.parameter.history'].search(domain, order='date_from', limit=1)
        return next_parameter.date_from if next_parameter else None

    @api.model
    def prepare_data_for_minimum_wage_salary_adjustment(self, **kwargs):
        company = self.env.user.company_id

        if 'keep_difference' in kwargs:
            keep_difference = kwargs.get('keep_difference', False)
        else:
            keep_difference = company.keep_salary_differences_when_changing_minimum_wage

        if 'minimum_monthly_wage_adjustment' in kwargs:
            minimum_monthly_wage_adjustment = kwargs.get('minimum_monthly_wage_adjustment', 0.0)
        else:
            minimum_monthly_wage_adjustment = company.mma_adjustment_when_creating_salary_change_documents

        if 'minimum_hourly_wage_adjustment' in kwargs:
            minimum_hourly_wage_adjustment = kwargs.get('minimum_hourly_wage_adjustment', 0.0)
        else:
            minimum_hourly_wage_adjustment = company.mmh_adjustment_when_creating_salary_change_documents

        if 'maximum_days_in_the_future' in kwargs:
            maximum_days_in_the_future = kwargs.get('maximum_days_in_the_future')
        else:
            maximum_days_in_the_future = company.minimum_wage_adjustment_document_creation_deadline_days

        auto_confirm = kwargs.get('auto_confirm', False)
        date_from = kwargs.get('date_from', False)
        change_date = self.find_next_minimum_wage_change_date(date_from, maximum_days_in_the_future)
        if not change_date:
            return  # No potential wage changes in the near future

        # Get salary change data
        contract_change_data = self.get_salary_adjustment_data(
            change_date, keep_difference, minimum_monthly_wage_adjustment, minimum_hourly_wage_adjustment
        )
        return {
            'change_date': change_date,
            'contract_change_data': contract_change_data,
            'auto_confirm': auto_confirm
        }

    @api.model
    def create_minimum_wage_salary_adjustment_documents(self, **kwargs):
        document_creation_data = self.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        if not document_creation_data:
            return  # No data provided

        contract_change_data = document_creation_data.get('contract_change_data')
        if not contract_change_data:
            return  # Everyone in the company earns more than the next minimum wage for the next change date

        change_date = document_creation_data['change_date']
        if not change_date:
            return  # No change date provided

        auto_confirm = document_creation_data.get('auto_confirm', False)

        return self._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

    @api.model
    def _create_minimum_wage_salary_adjustment_documents(self, change_date, contract_change_data, auto_confirm=True):
        """
            Creates minimum wage adjustment documents for contracts where the employee earns less than the new minimum
            wage
        """
        # Compute dates
        today = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Find affected contracts
        contracts = self.env['hr.contract'].browse(contract_change_data.keys()).exists()
        if not contracts:
            return

        # Define salary change template
        document_template = self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template')

        # Get existing documents
        existing_documents = self.env['e.document'].search([
            ('template_id', '=', document_template.id),
            ('date_3', '=', change_date),
            ('employee_id2', 'in', contracts.mapped('employee_id').ids),
            ('state', 'in', ['draft', 'confirm'])
        ])

        # Action needed for these appointments. Inform accountant about them later.
        appointments_to_warn_about = self.env['hr.contract.appointment']

        for contract in contracts:
            employee = contract.employee_id

            # Get employee wage data
            # ==========================================================================================================
            current_wage, new_minimum_wage, freeze_net_wage, post = contract_change_data.get(contract.id)
            expected_du_input_type = 'neto' if freeze_net_wage else 'bruto'
            contract_structure_code = contract.struct_id.code
            # ==========================================================================================================

            # Find awaiting salary change documents for the date and adjust them with the new minimum wage if needed
            # ==========================================================================================================
            employee_awaiting_documents = existing_documents.filtered(lambda d: d.employee_id2 == employee)
            if employee_awaiting_documents:
                # Check if there are any salary change documents
                if any(self.document_has_manual_changes(doc, expected_du_input_type, new_minimum_wage) for doc in
                       employee_awaiting_documents):
                    continue
                employee_awaiting_documents = employee_awaiting_documents.filtered(lambda d: not d.sudo().running)
                document_to_adjust = employee_awaiting_documents and employee_awaiting_documents[0]
                if document_to_adjust:
                    self.adjust_existing_salary_change_document(document_to_adjust, new_minimum_wage, post,
                                                                expected_du_input_type, contract_structure_code)
                    continue  # Changes made to existing salary change document, continue to the next contract
            # ==========================================================================================================

            # Find all related appointments
            # ==========================================================================================================
            related_contracts = contract.get_contracts_related_to_work_relation()
            appointments = related_contracts.mapped('appointment_id')
            # ==========================================================================================================

            # Check if there is an appointment that starts on the same date as the change.
            # ==========================================================================================================
            appointment_that_starts_at_change_date = appointments.filtered(lambda a: a.date_start == change_date)
            if appointment_that_starts_at_change_date:
                # Most likely a salary change appointment has already been created in this case
                meets_current_terms = self.check_if_appointment_meets_current_change_terms(
                    appointment_that_starts_at_change_date, new_minimum_wage, post, freeze_net_wage,
                    contract_structure_code
                )
                if not meets_current_terms:
                    appointments_to_warn_about |= appointment_that_starts_at_change_date
                continue
            # ==========================================================================================================

            # Find later appointments that have salary changes and warn about them
            # ==========================================================================================================
            later_appointments = appointments.filtered(lambda a: a.date_start > change_date).sorted(
                key=lambda a: a.date_start
            )
            later_appointment = later_appointments and later_appointments[0]
            if later_appointment:
                meets_current_terms = self.check_if_appointment_meets_current_change_terms(
                    later_appointment, new_minimum_wage, post, freeze_net_wage, contract_structure_code
                )
                if not meets_current_terms:
                    appointments_to_warn_about |= later_appointment
            # ==========================================================================================================

            # Find the appointment for the change date
            # ==========================================================================================================
            appointment_to_change = contract.with_context(date=change_date).appointment_id
            if not appointment_to_change:
                # Should always exist and should always require term changes since contract_change_data should be based
                # on appointments requiring changes.
                continue
            # ==========================================================================================================

            # Get properties and create salary change document
            # ==========================================================================================================
            # Determine disability
            disability = appointment_to_change.invalidumas and appointment_to_change.darbingumas.name

            # Prepare a copy of fixed attendance ids
            schedule_template = appointment_to_change.schedule_template_id
            fixed_attendance_ids = schedule_template.fixed_attendance_ids.filtered(
                lambda a: tools.float_compare(a.hour_from, a.hour_to, precision_digits=2) != 0
            )
            new_fixed_attendance_ids = [(0, 0, {
                'dayofweek': fixed_attendance_id.dayofweek,
                'hour_from': fixed_attendance_id.hour_from,
                'hour_to': fixed_attendance_id.hour_to,
            }) for fixed_attendance_id in fixed_attendance_ids]

            doc = self.env['e.document'].with_context(bypass_weekly_hours_mismatch_schedule=True, recompute=False).create({
                'template_id': document_template.id,
                'document_type': 'isakymas',
                'date_document': today,
                'employee_id2': employee.id,
                'date_3': change_date,
                'date_2': appointment_to_change.trial_date_end,
                'job_id': appointment_to_change.job_id.id,
                'date_6': appointment_to_change.date_end,
                'darbo_rusis': contract.rusis,
                'struct': contract_structure_code,
                'npd_type': 'auto' if appointment_to_change.use_npd else 'manual',
                'contract_priority': appointment_to_change.contract_priority or 'foremost',
                'selection_bool_2': 'false' if not disability else 'true',
                'selection_nedarbingumas': disability,
                'darbo_grafikas': appointment_to_change.schedule_template_id.template_type,
                'fixed_schedule_template': 'custom',
                'work_norm': appointment_to_change.schedule_template_id.work_norm,
                'etatas': appointment_to_change.schedule_template_id.etatas,
                'du_input_type': 'neto' if freeze_net_wage else 'bruto',
                'freeze_net_wage': 'true' if freeze_net_wage else 'false',
                'float_1': new_minimum_wage,
                'fixed_attendance_ids': new_fixed_attendance_ids,
            })
            self.reload_document(doc, confirm=auto_confirm)
            # ==========================================================================================================

        if appointments_to_warn_about:
            self.warn_about_appointments_with_unsuccessful_document_creation(appointments_to_warn_about)

    @api.model
    def adjust_existing_salary_change_document(self, document_to_adjust, new_minimum_wage, post, expected_du_input_type,
                                               contract_structure_code):
        # Find the wage adjusted by the document post
        adjusted_wage = new_minimum_wage
        if contract_structure_code == 'MEN':
            # Adjust minimum wage by doc post
            document_post = document_to_adjust.etatas_computed if \
                document_to_adjust.show_etatas_computed else document_to_adjust.etatas
            adjusted_wage = new_minimum_wage / (post or 1.0) * document_post  # P3:DivOK

        # Find out which values to update on the document
        values_to_update = {}
        if tools.float_compare(adjusted_wage, document_to_adjust.float_1, precision_digits=2) != 0:
            values_to_update['float_1'] = adjusted_wage
        if expected_du_input_type != document_to_adjust.du_input_type:
            values_to_update['du_input_type'] = expected_du_input_type
        if contract_structure_code != document_to_adjust.struct:
            values_to_update['struct'] = contract_structure_code

        # Nothing to update
        if not values_to_update:
            return

        # Write values
        is_confirmed = document_to_adjust.state == 'confirm'
        if is_confirmed:
            document_to_adjust.set_draft()
        document_to_adjust.write(values_to_update)

        # Reload the document, restoring it to confirmed state if needed
        self.reload_document(document_to_adjust, is_confirmed)

    @api.model
    def check_if_appointment_meets_current_change_terms(self, appointment, new_minimum_wage, post, freeze_net_wage,
                                                        contract_structure_code):
        if appointment.contract_id.struct_id.code != contract_structure_code or \
                appointment.freeze_net_wage != freeze_net_wage:
            # Appointment properties have changed so the appointment should be reviewed
            return False
        else:
            wage = appointment.wage
            minimum_wage_adjusted_by_post = new_minimum_wage
            if appointment.struct_id.code == 'MEN':
                # Adjust minimum wage by appointment post
                schedule_template = appointment.schedule_template_id
                minimum_wage_adjusted_by_post = new_minimum_wage / (post or 1.0) * schedule_template.etatas  # P3:DivOK
            if tools.float_compare(wage, minimum_wage_adjusted_by_post, precision_digits=2) < 0:
                # The wage of the existing appointment adjusted by the post is less than the minimum wage for
                # the period adjusted by its post
                return False
        return True

    @api.model
    def warn_about_appointments_with_unsuccessful_document_creation(self, appointments):
        if not appointments:
            return
        appointments_list = ',<br>\n'.join(
            _('({}) {} {}-{}, DU:{}, Etatas: {}').format(
                appointment.id,
                appointment.employee_id.name,
                appointment.date_start,
                appointment.date_end or _('Neterminuotai'),
                appointment.wage,
                appointment.schedule_template_id.etatas
            ) for appointment in appointments
        )
        message = _('''
            Sveiki,<br>\n
            kuriant darbo užmokesčio pakeitimo dokumentus darbuotojams, kuriems nustatytas darbo užmokestis yra 
            mažesnis, nei būsimas minimalus darbo užmokestis, nepavyko automatiškai sukurti darbo užmokesčio pakeitimo 
            įsakymų arba vėliau prasidedantys priedai turi netinkamas darbo sutarties sąlygas. Prašome peržiūrėti darbo 
            sutarties priedus ir užtikrinti, kad sekančiai minimalaus darbo užmokesčio pakeitimo datai šie darbuotojai 
            gautų įstatymus atitinkantį darbo užmokestį. <br>\n<br>\n
            Darbo sutarties priedai:<br>\n
            {}
        ''').format(appointments_list)
        db = self.env.cr.dbname
        subject = _('[{}] Kai kuriems darbuotojams reikia peržiūrėti darbo sutarties priedus').format(db)
        try:
            ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': 'hr.payroll',
                'ticket_record_id': False,
                'name': subject,
                'ticket_user_login': self.env.user.login,
                'ticket_user_name': self.env.user.name,
                'description': message,
                'ticket_type': 'accounting',
                'user_posted': self.env.user.name
            }
            res = ticket_obj.create_ticket(**vals)
            if not res:
                raise exceptions.UserError('The distant method did not create the ticket. Message contents: {}'.format(
                    message)
                )
        except Exception as e:
            message = 'Failed to create ticket for _cron_generate_entries cron job failure\nException: %s' % \
                      (str(e.args))
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': message,
            })