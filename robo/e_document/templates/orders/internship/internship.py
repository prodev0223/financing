# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import _, models, api, fields, tools, exceptions

from .... model import e_document_tools


TEMPLATE = 'e_document.internship_order_template'
MAX_VOLUNTARY_INTERNSHIP_DURATION = 2  # Maximum number of months a voluntary internship can last


class EDocument(models.Model):
    _inherit = 'e.document'

    internship_type = fields.Selection([
        ('voluntary_internship', 'Voluntary internship'),
        ('educational_internship', 'Educational institution internship')],
        default='voluntary_internship', inverse='set_final_document', readonly=True,
        states={'draft': [('readonly', False)]})

    @api.model
    def default_get(self, fields):
        res = super(EDocument, self).default_get(fields)
        template = self.env.ref('e_document.internship_order_template', False)
        if template and res.get('template_id') == template.id:
            res['text_3'] = self.env.user.company_id.street
        return res

    @api.multi
    def confirm(self):
        name_mapper = {
            'voluntary_internship': 'Savanoriškos praktikos įsakymas',
            'educational_internship': 'Švietimo įstaigos praktika',
        }
        for rec in self.filtered(
                lambda document: document.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False)):
            rec.write({'name': name_mapper.get(rec.internship_type) or _('Internship order')})
        return super(EDocument, self).confirm()

    @api.onchange('employee_id2')
    def _onchange_intern_id(self):
        if self.template_id != self.env.ref(TEMPLATE, raise_if_not_found=False):
            return
        employee = self.employee_id2
        self.text_1 = employee.identification_id
        self.text_2 = employee.street

    @api.multi
    def internship_order_workflow(self):
        self.ensure_one()

        struct = self.env['hr.payroll.structure'].search([('code', 'like', 'MEN')], limit=1)

        line_ids = []
        for line in self.fixed_attendance_ids:
            new_line = self.env['fix.attendance.line'].create({
                'dayofweek': line.dayofweek,
                'hour_from': line.hour_from,
                'hour_to': line.hour_to,
            })
            line_ids.append(new_line.id)

        weekly_hours = self.etatas_computed * 40 * 1.0
        five_day_default = [round(weekly_hours / 5.0, 2) for i in range(0, 5)] + [0, 0]  # P3:DivOK
        six_day_default = [round(weekly_hours / 6.0, 2) for i in range(0, 6)] + [0]  # P3:DivOK

        weekday_times = []
        for weekday in range(0, 7):
            weekday_lines = self.fixed_attendance_ids.filtered(lambda l: l.dayofweek == str(weekday))
            weekday_times.append(
                sum([round(abs(weekday_line.hour_to - weekday_line.hour_from), 2) for weekday_line in weekday_lines]))

        if weekday_times == five_day_default or not self.fixed_attendance_ids:
            work_week_type = 'five_day'
        elif weekday_times == six_day_default:
            work_week_type = 'six_day'
        else:
            work_week_type = 'based_on_template'

        schedule_template = self.env['schedule.template'].create({
            'template_type': 'fixed',
            'etatas_stored': self.etatas_computed,
            'work_norm': 1.0,
            'wage_calculated_in_days': True,
            'shorter_before_holidays': True,
            'fixed_attendance_ids': [(6, 0, line_ids)],
            'work_week_type': work_week_type
        })
        educational_institution_code = self.text_6 if self.internship_type == 'educational_internship' else False
        contract_id = self.env['hr.contract.create'].create({
            'employee_id': self.employee_id2.id,
            'job_id': self.employee_id2.job_id.id,
            'department_id': self.employee_id2.department_id.id,
            'struct_id': struct.id if struct else False,
            'date_start': self.date_from,
            'date_end': self.date_to,
            'wage': 0.0,
            'rusis': self.internship_type,
            'sodra_papildomai': False,
            'sodra_papildomai_type': 'exponential',
            'trial_date_end': False,
            'use_npd': True,
            'invalidumas': False,
            'darbingumas': False,
            'schedule_template_id': schedule_template.id,
            'avansu_politika': False,
            'avansu_politika_suma': 0.0,
            'order_date': self.date_document,
            'educational_institution_company_code': educational_institution_code,
        }).with_context(no_action=True).create_contract()
        self.inform_about_creation(contract_id)
        self.send_ticket_informing_about_signed_internship_document()
        self.write({'record_model': 'hr.contract', 'record_id': contract_id.id})

    @api.multi
    def execute_confirm_workflow_check_values(self):
        res = super(EDocument, self).execute_confirm_workflow_check_values()
        for rec in self.filtered(
                lambda r: r.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False) and
                          not r.sudo().skip_constraints_confirm):
            internship_type = rec.internship_type
            if internship_type == 'educational_internship' and rec.text_6 and not rec.text_6.isdigit():
                raise exceptions.UserError(_('Company code is invalid - it must consist of numbers only.'))
            date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from_dt > date_to_dt:
                raise exceptions.UserError(_('Praktika turi prasidėti prieš praktikos pabaigą'))

            max_date_to_dt = date_from_dt + relativedelta(months=MAX_VOLUNTARY_INTERNSHIP_DURATION)
            if date_to_dt > max_date_to_dt and internship_type == 'voluntary_internship':
                max_date_to = max_date_to_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                raise exceptions.UserError(_('Savanoriška praktika turi baigtis ne vėliau, nei {}, nes savanoriška '
                                             'praktika negali trukti ilgiau nei {} '
                                             'mėnesius').format(max_date_to, MAX_VOLUNTARY_INTERNSHIP_DURATION))

            if rec.int_1 < 1:
                raise exceptions.UserError(_('Neteisingai nurodyta, kiek dienų prieš sutarties nutraukimą reikia '
                                             'informuoti kitą šalį. Laukelio reikšmė privalo būti skaičius didesnis už ' 
                                             'arba lygus 1'))

            if rec.employee_id1 == rec.employee_id2:
                raise exceptions.UserError(_('Praktikantas negali būti praktikos vadovu'))

            if not rec.fixed_attendance_ids:
                raise exceptions.UserError(_('Būtina užpildyti praktikos grafiką'))

            age = e_document_tools.get_age_from_identification(self.text_1)
            if not age:
                raise exceptions.ValidationError(_('Provided personal code is incorrect.\n'))
            if internship_type == 'voluntary_internship' and age and age > 29:
                raise exceptions.ValidationError(_('The person indicated in the document is older than 29 years, '
                                                   'therefore, in accordance with Paragraph 1 of Article 10 of the '
                                                   'Law on Employment of the Republic of Lithuania, he / she has no '
                                                   'right to enter into a voluntary internship agreement.\n'))

        return res

    @api.multi
    def check_workflow_constraints(self):
        body = super(EDocument, self).check_workflow_constraints()
        template = self.env.ref('e_document.internship_order_template', False)
        for rec in self.filtered(lambda t: t.template_id == template):
            employee = rec.employee_id2
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', rec.date_to)
            ])
            if rec.internship_type == 'educational_internship' and rec.text_6 and not rec.text_6.isdigit():
                body += _('Company code is invalid - it must consist of numbers only.')
            if contract:
                # Either the employee did an internship already or had already worked for the company. By law a person
                # can not do an internship for the same company twice and it does not make sense for someone to do an
                # internship after that person has already worked for that company for some time thus this check should
                # be good enough to check both cases - simply checks if any contract exists.
                body += _('Sistemoje egzistuoja darbuotojo darbo sutartis, todėl darbuotojas negali būti priimtas '
                          'praktikai.\n')
                existing_period_line = self.env['ziniarastis.period.line'].search_count([
                    ('contract_id', '=', contract.id),
                    ('state', '=', 'done'),
                ])
                if existing_period_line and contract.rusis in dict(self._fields['internship_type'].selection).keys():
                    body += _('The employee\'s internship under this contract has already been recorded in accounting, '
                              'therefore the contract could not be cancelled. Please contact the accountant')

            contracts = self.env['hr.contract'].search([
                ('date_start', '<=', rec.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', rec.date_from)
            ])
            number_of_employees = len(contracts.mapped('employee_id.id'))
            if number_of_employees >= 10:
                number_of_voluntary_internships = len(contracts.filtered(lambda c: c.rusis == 'voluntary_internship'))
                including_this_one = number_of_voluntary_internships + 1
                percentage_of_voluntary = including_this_one / float(number_of_employees) * 100  # P3:DivOK
                if tools.float_compare(percentage_of_voluntary, 10, precision_digits=2) > 0:
                    body += _('Praktikos sutartis negali būti sudaryta, nes asmenų atliekančių savanorišką praktiką '
                              'skaičius viršytų 10% visų įmonės darbuotojų.\n')
            else:
                if any(contract.rusis == 'voluntary_internship' for contract in contracts):
                    body += _('Praktikos periode aktyvių darbuotojų skaičius nesiekia 10 darbuotojų bei egzistuoja '
                              'kita savanoriškos praktikos sutartis, todėl dar viena savanoriška praktika šiam '
                              'laikotarpiui negali būti skelbiama.\n')
            age = e_document_tools.get_age_from_identification(self.text_1)
            if not age:
                body += _('Provided personal code is incorrect.\n')
            if rec.internship_type == 'voluntary_internship' and age and age > 29:
                body += (_('The person indicated in the document is older than 29 years, '
                           'therefore, in accordance with Paragraph 1 of Article 10 of the '
                           'Law on Employment of the Republic of Lithuania, he / she has no '
                           'right to enter into a voluntary internship agreement.\n'))

        return body

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        if self.cancel_id and self.cancel_id.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False):
            self.cancel_id._cancel_internship_contract()
        else:
            super(EDocument, self).execute_cancel_workflow()

    @api.multi
    def _cancel_internship_contract(self):
        self.ensure_one()
        database = self._cr.dbname
        if not self.template_id == self.env.ref(TEMPLATE, raise_if_not_found=False):
            return

        internship_type_list = dict(self._fields['internship_type'].selection).keys()

        contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('date_start', '=', self.date_from),
            ('date_end', '=', self.date_to),
            ('rusis', 'in', internship_type_list)
        ], limit=1)
        if not self.sudo().skip_constraints:
            if not contract:
                subject = _('[%s] Internship contract could not be found').format(database)
                body = _('Internship contract could not be found while cancelling internship order #{}').format(
                    self.document_number)
                try:
                    self.create_internal_ticket(subject, body)
                except Exception as e:
                    self._create_cancel_workflow_failed_ticket_creation_bug(self.id, e)
        try:
            contract.mapped('appointment_ids').unlink()
            contract.unlink()
        except:
            subject = 'Praktikos sutartis buvo atšaukta [%s]' % database
            try:
                body = 'Praktikos sutartis buvo atšaukta. Reikia atlikti pakeitimus sutarčiai rankiniu būdu, ' \
                       'kad būtų atstatyta buvusi būsena.'
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)

    @api.multi
    def cancel_internship(self):
        if not (self.env.user.has_group('robo_basic.group_robo_edocument_manager') or
                self.env.user.has_group('robo_basic.group_robo_premium_manager')):
            raise exceptions.AccessError(_('You do not have sufficient rights to cancel internship orders'))
        for rec in self:
            rec.sudo()._cancel_internship_contract()
            msg_values = {
                'body': _('Sutartis atšaukta.'),
                'priority': 'high',
                'front_message': True,
                'rec_model': 'e.document',
                'rec_id': rec.id,
                'view_id': rec.view_id.id or False,
            }
            rec.robo_message_post(**msg_values)
        self.sudo().write({'state': 'cancel', 'cancel_uid': self.env.uid})

    @api.multi
    def send_ticket_informing_about_signed_internship_document(self):
        for rec in self:
            employee_info = _('{}, internship period: {} - {}.').format(
                rec.employee_id2.name_related, rec.date_from, rec.date_to
            )
            subject = _('An internship order has been signed for some employees')
            body = _('Order for internship has been signed for the following employees:\n{}\n'
                     'Please make sure to submit the required information to SoDra if needed.').format(employee_info)
            try:
                rec.create_internal_ticket(subject, body)
            except Exception as exc:
                message = 'Failed to create a ticket informing that an order for internship was signed.' \
                          '\nError: {}'.format(str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })


EDocument()
