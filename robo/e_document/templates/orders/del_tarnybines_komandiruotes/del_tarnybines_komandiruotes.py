# -*- coding: utf-8 -*-
from __future__ import division
import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta
from pytz import timezone

from odoo import models, fields, api, _, exceptions, tools
from odoo.addons.robo.models.linksnis import kas_to_ko, kas_to_kam

_logger = logging.getLogger(__name__)


class EDocument(models.Model):
    _inherit = 'e.document'

    raise_business_trip_travel_time_warning = fields.Boolean(compute='_compute_raise_business_trip_travel_time_warning')
    raise_business_trip_payment_warning = fields.Boolean(compute='_compute_raise_business_trip_payment_warning')
    business_trip_employee_text = fields.Char(compute='_compute_business_trip_employee_text')
    business_trip_employee_table = fields.Char(compute='_compute_business_trip_employee_table')
    business_trip_employee_journey_text = fields.Char(compute='_compute_business_trip_employee_journey_text')
    business_trip_allowance_text = fields.Char(compute='_compute_business_trip_allowance_text')
    business_trip_request_work_time_text = fields.Char(compute='_compute_business_trip_request_work_time_text')
    different_journey_time_employee_table = fields.Char(compute='_compute_different_journey_time_employee_table')
    allow_choose_extra_work_days = fields.Boolean(compute='_compute_allow_choose_extra_work_days')
    show_business_trip_annotation = fields.Boolean(readonly=True, compute='_compute_show_annotation')
    business_trip_request_extra_worked_day_ids = fields.One2many(
        'e.document.business.trip.request.extra.worked.days',
        'e_document_id',
        string='Poilsio dienos, kuriomis bus dirbama',
        compute='_compute_business_trip_request_extra_worked_day_ids',
        inverse='set_final_document',
        store=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
    )

    business_trip_employee_line_ids = fields.One2many('e.document.business.trip.employee.line', 'e_document_id',
                                                      string='Komandiruojami darbuotojai',
                                                      inverse='set_final_document', readonly=True,
                                                      states={'draft': [('readonly', False)]}, copy=True)
    business_trip_request_wish_to_work_extra_days = fields.Selection(
        [('true', _('Taip')), ('false', _('Ne'))],
        default='false',
        string='Darbas poilsio dienomis',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    business_trip_request_overtime_compensation = fields.Selection(
        [
            ('paid', _('Apmokamas')),
            ('holidays', _('Kompensuojamas laiką pridedant prie kasmetinių atostogų trukmės'))
        ],
        string='Darbas poilsio dienomis',
        required=True,
        default='paid',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    business_trip_request_journey_compensation = fields.Selection(
        [
            ('holidays', _('Apmokamas ir pridedamas prie kasmetinių atostogų trukmės')),
            ('free_time', _('Apmokamas ir suteikiamas tokios pačios trukmės poilsis iškart grįžus'))
        ],
        string='Kelionės laikas nepatenkantis į darbuotojo darbo laiką',
        required=True,
        default='holidays',
        inverse='set_final_document',
        readonly=True,
        states={'draft': [('readonly', False)]},
    )
    business_trip_document = fields.Boolean(compute='_business_trip_document', store=True)
    allowance_payout = fields.Selection([
            ('after_signing', _('Pasirašius dokumentą')),
            ('with_salary_payment', _('Su darbo užmokesčio mokėjimu')),
            ('dont_create', _('Kol kas nemokėti'))
        ], string='Dienpinigių išmokėjimas', help='Pasirinkite, kada norite išmokėti darbuotojams dienpinigius',
        readonly=True, states={'draft': [('readonly', False)]}, default='after_signing'
    )

    @api.multi
    def isakymas_del_tarnybines_komandiruotes_workflow(self):
        def calc_date(date, hour):
            local, utc = datetime.now(), datetime.utcnow()
            diff = utc - local
            hour, minute = divmod(hour * 60, 60)
            local_time = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=int(hour),
                                                                                                   minute=int(minute))
            utc_time = local_time + diff
            return utc_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        self.ensure_one()
        date_from_calculated = calc_date(self.date_from, 8)
        date_to_calculated = calc_date(self.date_to, 16)
        next_day_after = (
                datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        employee_lines = self.business_trip_employee_line_ids
        business_trip_holiday_status = self.env.ref('hr_holidays.holiday_status_K').id
        holiday_status_id = self.env['hr.holidays.status'].search([('kodas', '=', 'A')], limit=1).id
        work_schedule_installed = bool(
            self.env['ir.module.module'].search([('name', '=', 'work_schedule'), ('state', '=', 'installed')],
                                                count=True))
        country_allowance = self.country_allowance_id.id
        isakymo_nr = self.document_number
        move_lines = self.env['account.move.line']
        for employee_line in employee_lines:
            employee_id = employee_line.employee_id
            hol_id = self.env['hr.holidays'].create({
                'name': 'Tarnybinės komandiruotės',
                'data': self.date_document,
                'employee_id': employee_id.id,
                'holiday_status_id': business_trip_holiday_status,
                'date_from': date_from_calculated,
                'date_to': date_to_calculated,
                'type': 'remove',
                'numeris': isakymo_nr,
                'country_allowance_id': country_allowance,
                'amount_business_trip': employee_line.allowance_amount,
                'business_trip_worked_on_weekends': False,
                'allowance_payout': self.allowance_payout
            })
            hol_id.action_approve()
            self.inform_about_creation(hol_id)
            if employee_line.journey_has_to_be_compensated:
                time_to_compensate = employee_line.journey_amount_to_be_compensated
                appointment = employee_id.contract_id.with_context(date=next_day_after).appointment_id
                avg_hours_per_day = appointment.schedule_template_id.avg_hours_per_day if appointment else 8.0
                if not appointment:
                    raise exceptions.ValidationError(_('Negalima kompensuoti komandiruotės kelionės laiko poilsio '
                                                       'dienomis darbuotojui %s, nes nerastas galiojantis '
                                                       'darbuotojo priedas komandiruotės pabaigos datai') % employee_id.name)
                if employee_line.journey_compensation == 'holidays':
                    days_to_compensate = time_to_compensate / float(avg_hours_per_day)  # P3:DivOK
                    self.env['hr.holidays.fix'].adjust_fix_days(employee_id, next_day_after, days_to_compensate,
                                                                adjustment_in_work_days=True)
                else:
                    date_dt = datetime.strptime(next_day_after, tools.DEFAULT_SERVER_DATE_FORMAT)
                    to_compensate = time_to_compensate
                    while tools.float_compare(to_compensate, 0.0, precision_digits=2) > 0:
                        date_strf = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                        appointment = employee_id.contract_id.with_context(date=date_strf).appointment_id
                        if not appointment:
                            break
                        if tools.float_is_zero(sum(l.hour_to - l.hour_from for l in
                                                   appointment.schedule_template_id.fixed_attendance_ids),
                                               precision_digits=2):
                            regular_day_hours = appointment.schedule_template_id.avg_hours_per_day
                        else:
                            regular_day_hours = appointment.schedule_template_id.get_regular_hours(date_strf)

                        possible_compensation = min(regular_day_hours, to_compensate)
                        to_compensate -= possible_compensation

                        if not tools.float_is_zero(possible_compensation, precision_digits=2):
                            compensate_from_date = calc_date(date_strf, 8)
                            compensate_to_date = calc_date(date_strf, 8 + possible_compensation)
                            new_hol_id = self.env['hr.holidays'].create({
                                'name': 'Poilsio dienos už komandiruotėje dirbtas poilsio dienas',
                                'data': self.date_document,
                                'employee_id': employee_id.id,
                                'holiday_status_id': self.env.ref('hr_holidays.holiday_status_V').id,
                                'date_from': compensate_from_date,
                                'date_to': compensate_to_date,
                                'type': 'remove',
                                'numeris': isakymo_nr,
                            })
                            new_hol_id.action_approve()
                            self.inform_about_creation(new_hol_id)

                        date_dt += relativedelta(days=1)

            if not work_schedule_installed and employee_line.overtime_compensation == 'holidays':
                days_to_compensate = len(employee_line.extra_worked_day_ids.filtered(lambda l: l.worked and l.id))
                self.env['hr.holidays.fix'].adjust_fix_days(employee_id, next_day_after, days_to_compensate,
                                                            adjustment_in_work_days=True)

            if self.allowance_payout == 'after_signing' and not employee_id.pay_salary_in_cash:
                acc_move_lines = hol_id.payment_id.mapped('account_move_ids.line_ids')
                if acc_move_lines:
                    move_lines |= acc_move_lines
                else:
                    move_lines |= hol_id.payment_id.account_move_id.line_ids

        self.inform_about_employees_without_contract_receiving_allowance()

        if move_lines and self.env.user.company_id.form_business_trip_payments_immediately_after_signing:
            wizard_data = move_lines.call_multiple_invoice_export_wizard()
            wizard_id = wizard_data.get('res_id', False)
            if wizard_id:
                wizard = self.env['account.invoice.export.wizard'].browse(wizard_id)
                wizard.write({'journal_id': self.env.ref('base.main_company').payroll_bank_journal_id.id})
                bank_statement_data = wizard.create_bank_statement()
                bank_statement_id = bank_statement_data.get('res_id', False)
                if bank_statement_id:
                    bank_statement = self.env['account.bank.statement'].browse(bank_statement_id)
                    bank_statement.write({
                        'name': _('Dienpinigiai - {0}, {1} - {2}').format(self.country_allowance_id.name, self.date_from, self.date_to)
                    })
                    bank_statement.show_front()
                    integration_type = self.env['bank.export.base'].get_integration_types(wizard.journal_id.api_bank_type)
                    if self.env.user.company_id.automatically_send_business_trip_allowance_payments_to_bank and integration_type:
                        bank_statement.send_to_bank()

        self.write({'record_model': 'hr.holidays'})

    @api.multi
    def inform_about_employees_without_contract_receiving_allowance(self):
        self.ensure_one()
        employees = []
        for employee_line in self.business_trip_employee_line_ids:
            is_paid = tools.float_compare(employee_line.allowance_amount, 0.0, precision_digits=2) > 0
            if is_paid and not employee_line.employee_id.with_context(date=self.date_to).contract_id and not \
                    employee_line.employee_id.type == 'mb_narys':
                employees.append(employee_line.employee_id.display_name)
        if employees:
            try:
                subject = _('Business trip employees without a contract')
                body = _("""
                There are people appointed to the business trip who are getting an allowance,
                but do not have an existing work contract for the period of said business travel ({} - {}).\nEmployees:
                """).format(self.date_from, self.date_to)
                body += '\n'.join(employees)
                self.create_internal_ticket(subject, body)
            except Exception as exc:
                message = """
                Failed to create ticket about business trip employees without contract getting allowance for EDoc ID %s
                \nException: %s
                """ % (self.id, str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def is_business_trip_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template',
                                    raise_if_not_found=False)
        return doc_to_check and self.sudo().template_id.id == doc_to_check.id

    @api.one
    @api.depends('date_from', 'date_to', 'business_trip_employee_line_ids',
                 'business_trip_employee_line_ids.employee_id', 'business_trip_employee_line_ids.extra_worked_day_ids')
    def _compute_raise_business_trip_travel_time_warning(self):
        warn = False
        user = self.env.user
        if user.is_hr_manager() or user.is_premium_manager() or user.is_free_manager() \
                or user.has_group('e_document.group_robo_business_trip_signer'):
            if self.date_from and self.date_to:
                journey_during_holidays = self.env['sistema.iseigines'].search_count([
                    ('date', 'in', [self.date_from, self.date_to])
                ])

                lines = self.business_trip_employee_line_ids.filtered(lambda l: l.employee_id and
                                                                                l.journey_time == 'during_work_hours')
                appointments = self.env['hr.contract.appointment'].sudo().search([
                    ('employee_id', 'in', lines.mapped('employee_id.id')),
                    ('schedule_template_id.template_type', 'in', ['fixed', 'suskaidytos']),
                    '|',
                    '&',
                    ('date_start', '<=', self.date_to),
                    '|',
                    ('date_end', '>=', self.date_to),
                    ('date_end', '=', False),
                    '&',
                    ('date_start', '<=', self.date_from),
                    '|',
                    ('date_end', '>=', self.date_from),
                    ('date_end', '=', False)
                ])

                date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                start_weekday = str(date_from_dt.weekday())
                end_weekday = str(date_to_dt.weekday())

                for line in lines:
                    employee_appointments = appointments.filtered(lambda a: a.employee_id.id == line.employee_id.id).sorted(
                        key=lambda r: r.date_start)
                    if not employee_appointments:
                        continue
                    appointment_at_business_trip_start = employee_appointments.filtered(
                        lambda a: a.date_start <= self.date_from and
                                  (not a.date_end or a.date_end >= self.date_from))
                    worked_line_at_start_of_business_trip = line.extra_worked_day_ids.filtered(lambda day:
                                                                                               day.date == self.date_from and
                                                                                               day.worked)
                    if appointment_at_business_trip_start:
                        fixed_attendance_ids = appointment_at_business_trip_start.mapped(
                            'schedule_template_id.fixed_attendance_ids').filtered(lambda l: l.dayofweek == start_weekday)
                        if (not fixed_attendance_ids or journey_during_holidays) and line.journey_time != 'other' and \
                                not worked_line_at_start_of_business_trip:
                            warn = True
                            break
                    appointment_at_business_trip_end = employee_appointments.filtered(
                        lambda a: a.date_start <= self.date_to and
                                  (not a.date_end or a.date_end >= self.date_to))
                    worked_line_at_end_of_business_trip = line.extra_worked_day_ids.filtered(lambda day:
                                                                                             day.date == self.date_to and
                                                                                             day.worked)
                    if appointment_at_business_trip_end:
                        fixed_attendance_ids = appointment_at_business_trip_end.mapped(
                            'schedule_template_id.fixed_attendance_ids').filtered(lambda l: l.dayofweek == end_weekday)
                        if (not fixed_attendance_ids or journey_during_holidays) and line.journey_time != 'other' and \
                                not worked_line_at_end_of_business_trip:
                            warn = True
                            break
        self.raise_business_trip_travel_time_warning = warn

    @api.depends('business_trip_employee_line_ids.employee_id', 'allowance_payout')
    def _compute_raise_business_trip_payment_warning(self):
        user = self.env.user
        if user.is_hr_manager() or user.is_premium_manager():
            for rec in self.filtered(lambda d: d.allowance_payout == 'after_signing'):
                if any(e.employee_id.pay_salary_in_cash for e in rec.business_trip_employee_line_ids):
                    rec.raise_business_trip_payment_warning = True

    @api.one
    @api.depends('template_id')
    def _business_trip_document(self):
        if self.template_id.id in [self.env.ref('e_document.isakymas_del_komandiruotes_template').id,
                                   self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template').id,
                                   self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template').id]:
            self.business_trip_document = True
        else:
            self.business_trip_document = False

    @api.one
    @api.depends('business_trip_employee_line_ids')
    def _compute_business_trip_employee_text(self):
        text = ''
        if self.is_business_trip_doc():
            if len(self.business_trip_employee_line_ids) == 1:
                line = self.business_trip_employee_line_ids
                employee_id = line.employee_id
                job_name_adj = self.linksnis(employee_id.job_id.name, 'ka').lower() if employee_id.job_id else str()
                empl_name_adj = self.linksnis(employee_id.name, 'ka').title()
                text = job_name_adj + ' <span style="font-weight: bold;">' + empl_name_adj + '</span> '
            else:
                text = _('darbuotojų grupę')
        self.business_trip_employee_text = text

    @api.one
    @api.depends('business_trip_employee_line_ids',
                 'business_trip_employee_line_ids.allowance_amount')
    def _compute_business_trip_employee_table(self):
        if not self.is_business_trip_doc() or len(self.business_trip_employee_line_ids) == 1:
            text = ''
        else:
            text = '<br/>Siunčiami darbuotojai:<br/>'
            text += '''
            <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                <tr style="border:1px solid black;">
                    <td style="border:1px solid black; padding:5px;"><b>Vardas pavardė</b></td>
                    <td style="border:1px solid black; padding:5px;"><b>Dienpinigių suma, EUR</b></td>
                </tr>'''
            good_lines = self.env['e.document.business.trip.employee.line']
            empl_ids = self.business_trip_employee_line_ids.mapped('employee_id')
            for empl in empl_ids:
                empl_lines = self.business_trip_employee_line_ids.filtered(lambda l: l.employee_id.id == empl.id)
                line_to_add = empl_lines.filtered(lambda l: l.id)
                if not line_to_add:
                    line_to_add = empl_lines
                good_lines |= line_to_add
            for line in good_lines.sorted(key=lambda l: l.employee_id.name):
                amount = '%.2f' % line.allowance_amount
                amount = amount.replace('.', ',')
                text += '''
                 <tr style="border:1px solid black;">
                     <td style="border:1px solid black;">%(name)s</td>
                     <td style="border:1px solid black;">%(amount)s</td>
                 </tr>''' % {'name': line.employee_id.name, 'amount': amount}
            text += """</table><br/>"""
        self.business_trip_employee_table = text

    @api.one
    @api.depends('business_trip_employee_line_ids')
    def _compute_business_trip_employee_journey_text(self):
        def convert_to_local_tz(date):
            tzone = self._context.get('tz') or self.env.user.tz
            value = date
            try:
                diff = round((datetime.now(timezone(tzone)).replace(tzinfo=None) - datetime.utcnow()).total_seconds(),
                             3)
                value_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(seconds=diff)
                value = value_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except:
                pass
            return value

        text = ''
        if self.is_business_trip_doc():
            lines = self.business_trip_employee_line_ids
            if len(lines) == 1:
                line = lines
                text = '''N u s t a t a u kelionės į komandiruotę '''
                if line.journey_time == 'other':
                    text += '''laiką: %s - %s; kelionės iš komandiruotės laiką: %s - %s.<br/>''' % \
                            (convert_to_local_tz(line.departure_journey_start),
                             convert_to_local_tz(line.departure_journey_end),
                             convert_to_local_tz(line.return_journey_start),
                             convert_to_local_tz(line.return_journey_end)
                             )
                else:
                    text += 'laiku laikyti darbuotojo darbo laiką, pagal jam nustatytą grafiką ir papildomai šio ' \
                            'laiko nekompensuoti.<br/>'
            elif not any(line.journey_time == 'other' for line in lines):
                text = 'N u s t a t a u kelionės į komandiruotę laiku laikyti darbuotojų darbo laiką, pagal jiems ' \
                       'nustatytą grafiką ir papildomai šio laiko nekompensuoti <br/>'
        self.business_trip_employee_journey_text = text

    @api.one
    @api.depends('business_trip_employee_line_ids',
                 'business_trip_employee_line_ids.allowance_amount',
                 'business_trip_employee_line_ids.allowance_percentage')
    def _compute_business_trip_allowance_text(self):
        if not self.is_business_trip_doc() or len(self.business_trip_employee_line_ids) > 1:
            text = ''
        else:
            line = self.business_trip_employee_line_ids
            text = 'N u s t a t a u ' + str(line.allowance_amount) + ' Eur'
            if line.allowance_percentage != 100:
                text += ' (' + str(line.allowance_percentage) + '% dienpinigių normos)'
            text += ' dydžio dienpinigių sumą<br/>'
        self.business_trip_allowance_text = text

    @api.one
    @api.depends('business_trip_request_wish_to_work_extra_days',
                 'business_trip_request_extra_worked_day_ids',
                 'business_trip_request_overtime_compensation',
                 'business_trip_request_journey_compensation')
    def _compute_business_trip_request_work_time_text(self):
        text = ''
        if self.is_business_trip_request_doc() and self.business_trip_request_wish_to_work_extra_days and self.business_trip_request_extra_worked_day_ids.filtered(lambda d: d.worked):
            text += _('Prašau man leisti dirbti šiomis poilsio dienomis: ')
            index = 0
            for day in self.business_trip_request_extra_worked_day_ids.filtered(lambda d: d.worked).sorted('date'):
                if index != 0:
                    text += ', '
                text += str(day.date)
                index += 1
            text += '. '
            if self.business_trip_request_overtime_compensation == 'paid':
                text += 'Prašau šį papildomai dirbtą laiką apmokėti kartu su mano darbo užmokesčiu. '
            else:
                text += 'Prašau šį papildomai dirbtą laiką kompensuoti pridedant prie mano sukauptų kasmetinių ' \
                        'atostogų laiko. '
        text += 'Esant kelionės laikui, nepatenkančiam į mano darbo laiką, prašau šį laiką kompensuoti apmokėjimu, ' \
                'atitinkamai prilygstančiu mano darbo užmokesčiui ir '
        if self.business_trip_request_journey_compensation == 'holidays':
            text += 'atitinkamos trukmės laiką pridėti prie mano sukauptų kasmetinių atostogų laiko. '
        else:
            text += 'suteikti tokios pat trukmės poilsį iškart grįžus. '
        self.business_trip_request_work_time_text = text

    @api.one
    @api.depends('business_trip_employee_line_ids')
    def _compute_different_journey_time_employee_table(self):
        def convert_to_local_tz(date):
            tzone = self._context.get('tz') or self.env.user.tz
            value = date
            try:
                diff = round((datetime.now(timezone(tzone)).replace(tzinfo=None) - datetime.utcnow()).total_seconds(),
                             3)
                value_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(seconds=diff)
                value = value_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except:
                pass
            return value

        lines_with_diff_times = self.business_trip_employee_line_ids.filtered(
            lambda l: l.journey_time != 'during_work_hours' and l.id)
        text = ''
        if self.is_business_trip_doc() and len(lines_with_diff_times) > 0 and len(self.business_trip_employee_line_ids) > 1:
            text = '<br/>N u s t a t a u darbuotojų kelionės laiką:<br/>'
            text += '''
                <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                    <tr style="border:1px solid black;">
                        <td style="border:1px solid black; padding:5px;"><b>Darbuotojas</b></td>
                        <td style="border:1px solid black; padding:5px;"><b>Kelionės į komandiruotę pradžia</b></td>
                        <td style="border:1px solid black; padding:5px;"><b>Kelionės į komandiruotę pabaiga</b></td>
                        <td style="border:1px solid black; padding:5px;"><b>Kelionės iš komandiruotės pradžia</b></td>
                        <td style="border:1px solid black; padding:5px;"><b>Kelionės iš komandiruotės pabaiga</b></td>
                    </tr>'''
            for line in lines_with_diff_times.sorted(key=lambda l: l.employee_id.name):
                text += '''
                         <tr style="border:1px solid black;">
                             <td style="border:1px solid black;">%(name)s</td>
                             <td style="border:1px solid black;">%(departure_journey_start)s</td>
                             <td style="border:1px solid black;"> %(departure_journey_end)s</td>
                             <td style="border:1px solid black;">%(return_journey_start)s</td>
                             <td style="border:1px solid black;">%(return_journey_end)s</td>
                         </tr>''' % {
                                        'name': line.employee_id.name,
                                        'departure_journey_start': convert_to_local_tz(line.departure_journey_start),
                                        'departure_journey_end': convert_to_local_tz(line.departure_journey_end),
                                        'return_journey_start': convert_to_local_tz(line.return_journey_start),
                                        'return_journey_end': convert_to_local_tz(line.return_journey_end),
                                     }
            text += """</table>"""
            if len(lines_with_diff_times) != len(self.business_trip_employee_line_ids):
                text += 'Kitų darbuotojų kelionės laikas patenka į jų darbo laiką, todėl nebus kompensuojamas ' \
                        'papildomai.<br/>'
            text += '<br/>'
        self.different_journey_time_employee_table = text

    @api.one
    @api.depends('business_trip_request_extra_worked_day_ids')
    def _compute_allow_choose_extra_work_days(self):
        self.allow_choose_extra_work_days = True if self.is_business_trip_request_doc() and len(self.business_trip_request_extra_worked_day_ids) > 0 else False

    @api.one
    @api.depends('business_trip_employee_line_ids')
    def _compute_show_annotation(self):
        employees = self.business_trip_employee_line_ids.mapped('employee_id.id') if self.is_business_trip_doc() else []
        self.show_business_trip_annotation = self.env.user.company_id.vadovas.id in employees

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_business_trip_request_extra_worked_day_ids(self):
        doc_to_check = self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template',
                                    raise_if_not_found=False)
        if doc_to_check and self.template_id.id == doc_to_check.id and self.date_from and self.date_to and \
                self.date_from <= self.date_to:
            appointments = self.env['hr.contract.appointment'].sudo().search([
                ('employee_id', '=', self.employee_id1.id),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)
            ])
            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

            iteration = date_from_dt
            loop_end = date_to_dt
            business_trip_dates = []
            while iteration <= loop_end:
                business_trip_dates.append(iteration.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
                iteration += relativedelta(days=1)

            national_holidays = self.env['sistema.iseigines'].search([('date', '<=', self.date_to),
                                                                      ('date', '>=', self.date_from)]).mapped('date')

            line_commands = [(5,)]
            for date in business_trip_dates:
                date_app = appointments.filtered(
                    lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date))
                include_in_dates = True if date in national_holidays and date_app else False
                if not include_in_dates:
                    weekends = [5, 6]
                    if date_app:
                        weekends = date_app.schedule_template_id.off_days()
                    if datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday() in weekends:
                        include_in_dates = True
                if not include_in_dates:
                    continue
                date_worked = True if self.business_trip_request_extra_worked_day_ids.filtered(
                    lambda d: d.date == date and d.worked) else False
                line_commands.append((0, 0, {'e_document_id': self.id, 'date': date, 'worked': date_worked}))
            self.business_trip_request_extra_worked_day_ids = line_commands

    @api.multi
    def confirm(self):
        doc_to_check = self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template',
                                    raise_if_not_found=False)
        docs = self.filtered(lambda d: d.state == 'draft')
        if doc_to_check:
            if any(not doc.business_trip_request_extra_worked_day_ids.filtered(lambda d: d.worked) for doc in
                   docs.filtered(lambda d: d.template_id.id == doc_to_check.id and d.business_trip_request_wish_to_work_extra_days == 'true')):
                raise exceptions.ValidationError(_('Nurodžius, kad norite dirbti poilsio dienomis, būtina nurodyti '
                                                   'dienas, kuomet norite dirbti'))
        return super(EDocument, self).confirm()

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_business_trip_dates(self):
        for rec in self:
            if not rec.date_from or not rec.date_to or not rec.is_business_trip_doc():
                continue
            for line in rec.business_trip_employee_line_ids.filtered(
                    lambda l: l.id and l.journey_time != 'during_work_hours'):
                if line.return_journey_end and rec.date_to < line.return_journey_end[:10]:
                    raise exceptions.UserError(
                        _('Darbuotojo %s kelionės iš komandiruotės data turi patekti į komandiruotės laiką') %
                        line.employee_id.name)
                elif line.departure_journey_start and rec.date_from > line.departure_journey_start[:10]:
                    raise exceptions.UserError(
                        _('Darbuotojo %s kelionės į komandiruotę data turi patekti į komandiruotės laiką')
                        % line.employee_id.name
                    )

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.is_business_trip_doc() and rec.date_from and rec.date_to:
                date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                if (date_to_dt - date_from_dt).days < 0:
                    raise exceptions.ValidationError(_('Komandiruotė turi prasidėti prieš pabaigą'))

    @api.multi
    def execute_confirm_check_holiday_intersect(self):
        res = super(EDocument, self).execute_confirm_check_holiday_intersect()
        poilsio_type = self.env.ref('hr_holidays.holiday_status_P', raise_if_not_found=False)
        poilsio_type_id = poilsio_type and poilsio_type.id or False
        for rec in self.filtered(lambda r: r.is_business_trip_doc()):
            if rec.sudo().skip_constraints_confirm:
                _logger.info('Holiday overlap check was skipped for document %s: %s' % (rec.id, rec.name))
                continue

            employees = rec.business_trip_employee_line_ids.mapped('employee_id')

            holidays = self.env['hr.holidays'].search(
                [('employee_id', 'in', employees.ids),
                 ('holiday_status_id', '!=', poilsio_type_id),
                 ('state', 'not in', ['cancel', 'refuse']),
                 ('date_from_date_format', '<=', rec.date_to),
                 ('date_to_date_format', '>=', rec.date_from)])
            other_day_holidays = holidays.filtered(
                lambda r: r['date_from_date_format'] != rec.date_from or r['date_to_date_format'] != rec.date_to)

            overlapping_employees = other_day_holidays.mapped('employee_id')
            overlapping_employees |= self.check_employees_who_have_taken_unpaid_time_off(
                employees, rec.date_from, rec.date_to
            )

            if overlapping_employees:
                employee_list = ',\n'.join(kas_to_kam(empl_name) for empl_name in overlapping_employees.mapped('name'))
                msg = _('Negalima turėti persidengiančių atostogų. '
                        'Neatvykimai persidengia šiems darbuotojams: \n{}').format(employee_list)
                raise exceptions.Warning(msg)
        return res

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        res = super(EDocument, self).execute_cancel_workflow()
        document = self.cancel_id
        if document and document.is_business_trip_doc():
            hol_status = self.env.ref('hr_holidays.holiday_status_K')
            komandiruote_from = document.date_from
            komandiruote_to = document.date_to
            date_to_dt = datetime.strptime(document.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day_after = (date_to_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            document_number = document.document_number
            for line in document.business_trip_employee_line_ids:
                holidays = self.env['hr.holidays'].search([
                    ('employee_id', '=', line.employee_id.id),
                    ('date_from_date_format', '=', komandiruote_from),
                    ('date_to_date_format', '=', komandiruote_to),
                    ('holiday_status_id', '=', hol_status.id),
                    ('numeris', '=', document_number)
                ])
                if holidays and holidays.date_from:
                    if holidays.state == 'validate':
                        period_line_ids = self.env['ziniarastis.period.line'].search([
                            ('employee_id', '=', holidays.employee_id.id),
                            ('date_from', '<=', holidays.date_from),
                            ('date_to', '>=', holidays.date_from)], limit=1)
                        if period_line_ids and period_line_ids[0].period_state == 'done':
                            raise exceptions.UserError(_('Įsakymo patvirtinti negalima, nes atlyginimai '
                                                         'jau buvo paskaičiuoti. Informuokite buhalterį '
                                                         'parašydami žinutę dokumento apačioje.'))
                        holidays.action_refuse()
                    holidays.action_draft()
                    holidays.unlink()

                if line.any_extra_days_worked:
                    extra_days_worked = list(set(line.extra_worked_day_ids.filtered(lambda d: d.worked).mapped('date')))
                    if line.overtime_compensation == 'paid':
                        period_line_ids = self.env['ziniarastis.period.line'].search([
                            ('employee_id', '=', line.employee_id.id),
                            ('date_from', '<=', max(extra_days_worked)),
                            ('date_to', '>=', min(extra_days_worked)),
                            ('state', '=', 'done')], limit=1)
                        if period_line_ids:
                            raise exceptions.UserError(
                                _('Įsakymo patvirtinti negalima, nes darbuotojo %s atlyginimas jau buvo '
                                  'paskaičiuotas. Informuokite buhalterį '
                                  'parašydami žinutę dokumento apačioje.') % line.employee_id.name)
                    else:
                        days_to_compensate = len(extra_days_worked) * -2
                        self.env['hr.holidays.fix'].adjust_fix_days(line.employee_id, next_day_after,
                                                                    days_to_compensate, adjustment_in_work_days=True)

                if line.journey_has_to_be_compensated:
                    had_to_compensate = line.journey_amount_to_be_compensated
                    if line.journey_compensation == 'holidays':
                        fix_date_app = self.env['hr.contract.appointment'].search([
                            ('employee_id', '=', line.employee_id.id),
                            ('date_start', '<=', next_day_after),
                            '|',
                            ('date_end', '>=', next_day_after),
                            ('date_end', '=', False)
                        ])
                        avg_daily_hrs = fix_date_app.schedule_template_id.avg_hours_per_day if fix_date_app else 8.0
                        days_compensated = had_to_compensate / avg_daily_hrs  # P3:DivOK
                        self.env['hr.holidays.fix'].adjust_fix_days(line.employee_id, next_day_after,
                                                                    -days_compensated, adjustment_in_work_days=True)
                    else:
                        related_free_days_after_business_trip = self.env['hr.holidays'].search(
                            [('numeris', '=', self.cancel_id.document_number),
                             ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_V').id)])
                        for free_day in related_free_days_after_business_trip:
                            if free_day.state == 'validate' and free_day.date_from:
                                period_line_ids = self.env['ziniarastis.period.line'].search([
                                    ('employee_id', '=', free_day.employee_id.id),
                                    ('date_from', '<=', free_day.date_from),
                                    ('date_to', '>=', free_day.date_from)], limit=1)
                            if period_line_ids and period_line_ids[0].period_state == 'done':
                                raise exceptions.Warning(
                                    _('Įsakymo patvirtinti negalima, nes darbuotojo %s atlyginimas '
                                      'jau buvo paskaičiuotas. Informuokite buhalterį '
                                      'parašydami žinutę dokumento apačioje.') % line.employee_id.name)
                                free_day.action_refuse()
                                free_day.action_draft()
                                free_day.unlink()
                            elif free_day.state != 'validate' and free_day.date_from:
                                free_day.action_draft()
                                free_day.unlink()

        return res

    @api.multi
    def is_business_trip_request_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template',
                                    raise_if_not_found=False)
        return True if doc_to_check and self.sudo().template_id.id == doc_to_check.id else False

    @api.multi
    def check_workflow_constraints(self):
        body = super(EDocument, self).check_workflow_constraints()
        nestumo_doc = self.env.ref('e_document.isakymas_del_nestumo_ir_gimdymo_atostogu_template').id
        for rec in self:
            is_nestumo_doc = rec.template_id.id == nestumo_doc
            if (rec.is_business_trip_doc() or is_nestumo_doc) and rec.date_from and rec.date_to:
                for line in self.business_trip_employee_line_ids:
                    employee_id = line.employee_id.id
                    date_from = rec.date_from
                    date_to = rec.date_from if is_nestumo_doc else rec.date_to
                    contract = self.env['hr.contract'].search([
                        ('employee_id', '=', employee_id),
                        ('date_start', '<=', date_from),
                        '|',
                        ('date_end', '=', False),
                        ('date_end', '>=', date_to)
                    ])
                    if line.employee_id.type != 'mb_narys' and not contract:
                        body += _('Darbuotojas %s neturi darbo sutarties nurodytam komandiruotės periodui\n') % line.employee_id.name_related
            if rec.is_business_trip_doc() and rec.date_to and rec.date_to >= '2020-01-01':
                starts_before = rec.date_from and rec.date_from < '2020-01-01'
                for line in self.business_trip_employee_line_ids:
                    if line.allowance_percentage > 100:
                        body += _('Nuo 2020 metų Sausio 1 dienos nebegalima išmokėti daugiau nei 100% dienpinigių dydį.')
                        if starts_before:
                            body += _('Norėdami už komandiruotės dalį (iki Sausio 1 d.) išmokėti 200% dienpinigių '
                                      'dydį - kurkite 2 įsakymus dėl komandiruotės.\n')
                        else:
                            body += '\n'
                        break
            if rec.is_business_trip_doc() and rec.raise_business_trip_travel_time_warning:
                body += _('Kai kurių darbuotojų kelionės laikas nesutampa su šių darbuotojų darbo laiku. Prašome '
                          'tikslingai nustatyti kelionės laiką.')
            if rec.is_business_trip_doc() and rec.allowance_payout == 'after_signing':
                employees = self.business_trip_employee_line_ids.mapped('employee_id')
                employees = employees.filtered(lambda e: not e.pay_salary_in_cash)
                for employee in employees:
                    if not employee.bank_account_id:
                        employee_business_trip_lines = self.business_trip_employee_line_ids.filtered(
                            lambda employee_line: employee_line.employee_id == employee
                        )
                        employee_business_trip_amount = sum(employee_business_trip_lines.mapped('allowance_amount'))
                        if not tools.float_is_zero(employee_business_trip_amount, precision_digits=2):
                            body += _('Negalima suformuoti pavedimo, nenurodyta %s banko sąskaita.\n') % \
                                    kas_to_ko(employee.name)
            if rec.is_business_trip_doc():
                poilsio_type = self.env.ref('hr_holidays.holiday_status_P', raise_if_not_found=False)
                poilsio_type_id = poilsio_type and poilsio_type.id or False
                holidays = self.env['hr.holidays'].search(
                    [('employee_id', 'in', rec.business_trip_employee_line_ids.mapped('employee_id.id')),
                     ('holiday_status_id', '!=', poilsio_type_id),
                     ('state', 'not in', ['cancel', 'refuse']),
                     ('date_from_date_format', '<=', rec.date_to),
                     ('date_to_date_format', '>=', rec.date_from)])
                other_day_holidays = holidays.filtered(
                    lambda r: r['date_from_date_format'] != rec.date_from or r['date_to_date_format'] != rec.date_to)
                if other_day_holidays:
                    employee_names = other_day_holidays.mapped('employee_id.name')
                    employee_list = ',\n'.join(kas_to_kam(empl_name) for empl_name in employee_names)
                    msg = _('Negalima turėti persidengiančių atostogų. '
                            'Neatvykimai persidengia šiems darbuotojams: \n{}').format(employee_list)
                    raise exceptions.Warning(msg)
        return body

    @api.multi
    @api.constrains('business_trip_employee_line_ids')
    def _check_employee_lines_exist(self):
        for rec in self:
            if rec.is_business_trip_doc() and not rec.business_trip_employee_line_ids:
                raise exceptions.ValidationError(_('Nenustatyti komandiruojami darbuotojai'))

    @api.multi
    @api.constrains('business_trip_employee_line_ids')
    def _check_single_employee(self):
        for rec in self:
            if rec.is_business_trip_doc():
                line_employee_ids = rec.mapped('business_trip_employee_line_ids.employee_id.id')
                if len(line_employee_ids) != len(set(line_employee_ids)):
                    raise exceptions.ValidationError(
                        _('Kaikurie darbuotojai įvesti daugiau nei vieną kartą. Patikrinkite komandiruojamų darbuotojų sąrašą'))

    @api.onchange('country_allowance_id', 'date_from', 'date_to')
    def _onchange_country_allowance_id(self):
        if self.is_business_trip_doc():
            for line in self.business_trip_employee_line_ids:
                line._onchange_allowance_percentage_or_employee_id()


EDocument()


class EDocumentBusinessTripWorkSchedule(models.Model):
    _name = 'e.document.business.trip.employee.line'

    e_document_id = fields.Many2one(
        'e.document',
        string='Susijęs dokumentas',
        required=True,
        ondelete='cascade',
        inverse='set_final_document'
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Darbuotojas',
        required=True,
        ondelete='cascade',
        inverse='set_final_document'
    )

    extra_worked_day_ids = fields.One2many(
        'e.document.business.trip.extra.worked.days',
        'business_trip_schedule_id',
        string='Pažymėkite švenčių ir poilsio dienas, kuriomis buvo dirbta'
    )

    journey_time = fields.Selection(
        [
            ('during_work_hours', 'Taip'),
            ('other', 'Ne'),
        ],
        string='Ar kelionės laikas patenka į darbuotojo darbo laiką?',
        required=True,
        default='during_work_hours'
    )
    departure_journey_start = fields.Datetime(string='Kelionės į komandiruotę pradžia', inverse='set_final_document')
    departure_journey_end = fields.Datetime(string='Kelionės į komandiruotę pabaiga', inverse='set_final_document')
    return_journey_start = fields.Datetime(string='Kelionės iš komandiruotės pradžia', inverse='set_final_document')
    return_journey_end = fields.Datetime(string='Kelionės iš komandiruotės pabaiga', inverse='set_final_document')
    journey_amount_to_be_compensated = fields.Float(
        string='Kompensuojamas kelionės laikas (valandomis)',
        compute='_compute_journey_compensation'
    )

    journey_has_to_be_compensated = fields.Boolean(
        string='Ar privaloma kompensuoti komandiruotės kelionės laiką',
        compute='_compute_journey_compensation'
    )

    allowance_amount = fields.Float(string='Dienpinigių dydis', required=True, inverse='set_final_document')
    allowance_percentage = fields.Integer(
        string='Dienpinigiu procentas',
        default=100, required=True,
        inverse='set_final_document'
    )

    any_extra_days_worked = fields.Boolean(compute='_compute_any_extra_days_worked')

    overtime_compensation = fields.Selection(
        [
            ('paid', _('Apmokamas')),
            ('holidays', _('Kompensuojamas laiką pridedant prie kasmetinių atostogų trukmės'))
        ],
        string='Darbas poilsio dienomis',
        default='paid',
        inverse='set_final_document'
    )

    journey_compensation = fields.Selection(
        [
            ('holidays', _('Apmokamas ir pridedamas prie kasmetinių atostogų trukmės')),
            ('free_time', _('Apmokamas ir suteikiamas tokios pačios trukmės poilsis iškart grįžus'))
        ],
        string='Kelionės laikas nepatenkantis į darbuotojo darbo laiką',
        default='holidays',
        inverse='set_final_document'
    )
    line_is_editable = fields.Boolean(compute='_compute_line_is_editable')

    @api.multi
    @api.constrains('e_document_id', 'employee_id', 'extra_worked_day_ids', 'journey_time', 'departure_journey_start',
                    'departure_journey_end', 'return_journey_start', 'return_journey_end',
                    'allowance_amount', 'allowance_percentage', 'overtime_compensation', 'journey_compensation')
    def _check_state_draft(self):
        admin_user = self.env.user.has_group('base.group_system')
        for rec in self:
            if rec.e_document_id and rec.e_document_id.state != 'draft' and not \
                    admin_user and not rec.sudo().e_document_id.skip_constraints:
                raise exceptions.ValidationError(_(
                    'Dokumentas, kurio eilutė keičiama nėra juodraščio būsenoje, todėl negalima keisti darbuotojo komandiruotės eilutės nustatymų.'))

    @api.multi
    def set_final_document(self):
        self.ensure_one()
        e_doc = self.e_document_id
        if e_doc:
            e_doc._compute_different_journey_time_employee_table()
            e_doc._compute_business_trip_allowance_text()
            e_doc._compute_business_trip_employee_table()
            e_doc._compute_business_trip_employee_text()
            e_doc.set_final_document()

    @api.one
    @api.depends('extra_worked_day_ids')
    def _compute_any_extra_days_worked(self):
        self.any_extra_days_worked = bool(self.extra_worked_day_ids.filtered(lambda d: d.worked))

    @api.one
    @api.depends('e_document_id')
    def _compute_line_is_editable(self):
        self.line_is_editable = False if self.e_document_id and self.e_document_id.state != 'draft' else True

    @api.multi
    @api.constrains('departure_journey_start', 'departure_journey_end', 'return_journey_start',
                    'return_journey_end', 'journey_time', 'e_document_id')
    def _check_journey_times_in_business_trip_period(self):
        for rec in self:
            if rec.journey_time == 'during_work_hours':
                continue
            if not rec.e_document_id.date_to or not rec.e_document_id.date_from:
                raise exceptions.ValidationError(_('Prašome nustatykite komandiruotės trukmę'))
            if not rec.e_document_id:
                raise exceptions.ValidationError(_('Nenurodytas dokumentas'))
            date_from_dt = datetime.strptime(rec.e_document_id.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.e_document_id.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + \
                         relativedelta(days=1)  # Date to is always the end of the date, or midnight of next day
            user_tz = timezone(self._context.get('tz') or self.env.user.tz)
            if rec.return_journey_end:
                return_journey_end_dt = datetime.strptime(
                    rec.return_journey_end, tools.DEFAULT_SERVER_DATETIME_FORMAT
                )
                offset = int(user_tz.localize(return_journey_end_dt).strftime('%z')[1:3])
                localised_return_journey_end_dt = return_journey_end_dt + relativedelta(hours=offset)
                if date_to_dt <= localised_return_journey_end_dt:
                    raise exceptions.UserError(_('Darbuotojo %s kelionės iš komandiruotės data turi patekti į '
                                                 'komandiruotės laiką') % rec.employee_id.name)
            if rec.departure_journey_start:
                departure_journey_start_dt = datetime.strptime(
                    rec.departure_journey_start, tools.DEFAULT_SERVER_DATETIME_FORMAT
                )
                offset = int(user_tz.localize(departure_journey_start_dt).strftime('%z')[1:3])
                localised_departure_journey_start_dt = departure_journey_start_dt + relativedelta(hours=offset)
                if date_from_dt > localised_departure_journey_start_dt:
                    raise exceptions.UserError(_('Darbuotojo %s kelionės į komandiruotę data turi patekti į '
                                                 'komandiruotės laiką') % rec.employee_id.name)

    @api.multi
    @api.constrains('departure_journey_start', 'departure_journey_end', 'return_journey_start',
                    'return_journey_end', 'journey_time')
    def _check_journey_times_set(self):
        for rec in self:
            if rec.journey_time == 'during_work_hours':
                continue
            ds = rec.departure_journey_start
            de = rec.departure_journey_end
            rs = rec.return_journey_start
            re = rec.return_journey_end
            journey_vals = [ds, de, rs, re]
            not_set = len([True for val in journey_vals if not val])
            e_doc = rec.e_document_id
            if not_set > 0 and not_set != 4:
                raise exceptions.UserError(_(
                    'Nustačius skirtingą komandiruotės kelionės trukmę darbuotojui %s privaloma nustatyti visus kelionės laukelius'
                ) % rec.employee_id.name)
            elif not_set == 4 and e_doc:
                rec.write({
                    'departure_journey_start': e_doc.business_trip_departure_journey_start,
                    'departure_journey_end': e_doc.business_trip_departure_journey_end,
                    'return_journey_start': e_doc.business_trip_return_journey_start,
                    'return_journey_end': e_doc.business_trip_return_journey_end,
                })

    def create(self, vals):
        e_doc = self.env['e.document'].browse(vals.get('e_document_id'))
        employee_id = self.env['hr.employee'].browse(vals.get('employee_id'))
        employee_name = employee_id.name
        if employee_id.id in e_doc.business_trip_employee_line_ids.mapped('employee_id.id'):
            raise exceptions.UserError(_('Darbuotojas %s jau pridėtas prie komandiruojamų darbuotojų') % employee_name)

        business_trip_date_to = e_doc.date_to
        business_trip_date_from = e_doc.date_from

        if vals.get('journey_time', False) == 'other':
            ds = vals.get('departure_journey_start', False)
            de = vals.get('departure_journey_end', False)
            rs = vals.get('return_journey_start', False)
            re = vals.get('return_journey_end', False)
            journey_vals = [ds, de, rs, re]
            not_set = len([True for val in journey_vals if not val])
            if not_set > 0:
                raise exceptions.UserError(_('Nustatyti ne visi darbuotojo %s kelionių parametrai') % employee_name)

        return super(EDocumentBusinessTripWorkSchedule, self).create(vals)

    @api.onchange('allowance_percentage', 'employee_id')
    def _onchange_allowance_percentage_or_employee_id(self):
        allow_zero = self.sudo().env.user.company_id.allow_zero_allowance_business_trip
        self.e_document_id._num_calendar_days()
        lt_country_id = self.env.ref('l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False)
        is_country_lt = lt_country_id and self.e_document_id.country_allowance_id.id == lt_country_id.id
        is_company_manager = self.employee_id.id == self.env.user.company_id.vadovas.id
        constrain_no_more_than_hundred = self.e_document_id.date_from and self.e_document_id.date_from >= '2020-01-01'
        allowance_percentage = self.allowance_percentage
        if allow_zero:
            if self.allowance_percentage < 50:
                allowance_percentage = 0
            elif 200 >= allowance_percentage > 100:
                if not is_company_manager:
                    allowance_percentage = 100
            elif allowance_percentage > 200:
                allowance_percentage = 100 if is_company_manager else 200
            if constrain_no_more_than_hundred and allowance_percentage > 100:
                allowance_percentage = 100
            norma = allowance_percentage / 100.0  # P3:DivOK
        else:
            if self.allowance_percentage < 50:
                if self.e_document_id.num_calendar_days == 1 and is_country_lt:
                    allowance_percentage = 0
                else:
                    allowance_percentage = 50
            elif 200 >= allowance_percentage > 100:
                if not is_company_manager:
                    allowance_percentage = 100
            elif allowance_percentage > 200:
                allowance_percentage = 100 if is_company_manager else 200
            if constrain_no_more_than_hundred and allowance_percentage > 100:
                allowance_percentage = 100
            norma = allowance_percentage / 100.0  # P3:DivOK
            if self.e_document_id.with_context(employee=self.employee_id).num_calendar_days != 1 or not is_country_lt:
                if tools.float_compare(norma, 0.5, precision_digits=2) == -1:
                    norma = 1.0
                    allowance_percentage = 100
        if self.allowance_percentage != allowance_percentage:
            self.allowance_percentage = allowance_percentage
        date_from = self.e_document_id.date_from
        date_to = self.e_document_id.date_to
        amount = 0.0
        if date_from and date_to:
            dont_pay_allowance_for = len(self.extra_worked_day_ids.filtered(lambda l: not l.pay_allowance))
            date_to = (datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) -
                       relativedelta(days=dont_pay_allowance_for))
            date_to = date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_to < date_from:
                date_to = date_from
            amount = self.e_document_id.country_allowance_id.get_amount(date_from, date_to)
        self.allowance_amount = tools.float_round(amount * norma, precision_digits=2)

    @api.onchange('allowance_amount')
    def _onchange_allowance_amount(self):
        if self.e_document_id and self.e_document_id.country_allowance_id and self._context.get(
                'norm', False):  # prevent endless onchange triggering
            country_allowance_amount = self.e_document_id.country_allowance_id.get_amount(self.e_document_id.date_from,
                                                                                           self.e_document_id.date_to)
            mid_norm = tools.float_round(country_allowance_amount, precision_digits=2)
            min_norm = tools.float_round(country_allowance_amount * 0.5, precision_digits=2)
            max_norm = tools.float_round(country_allowance_amount * 2, precision_digits=2)
            constrain_no_more_than_hundred = self.e_document_id.date_from and self.e_document_id.date_from >= '2020-01-01'
            if constrain_no_more_than_hundred:
                max_norm = tools.float_round(country_allowance_amount * 1, precision_digits=2)
            self.e_document_id._num_calendar_days()
            is_ceo = self.employee_id.id == self.env.user.company_id.vadovas.id
            lt_country_id = self.env.ref('l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False)
            is_country_lt = lt_country_id and self.e_document_id.country_allowance_id.id == lt_country_id.id
            max_possible = 200 if is_ceo and not constrain_no_more_than_hundred else 100
            min_possible = 0 if self.e_document_id.num_calendar_days == 1 and is_country_lt else 50
            try:
                per_percent = mid_norm // 100  # P3:DivOK
                percentage = self.allowance_amount // per_percent  # P3:DivOK

                if (self.allowance_amount >= max_norm and is_ceo) or (self.allowance_amount > mid_norm and not is_ceo):
                    self.allowance_percentage = max_possible
                elif self.allowance_amount <= min_norm:
                    self.allowance_percentage = min_possible
                else:
                    self.allowance_percentage = int(tools.float_round(percentage, precision_digits=3))
                self._onchange_allowance_percentage_or_employee_id()

            except ZeroDivisionError:
                self.allowance_percentage = 0
                self.allowance_amount = 0
                self._onchange_allowance_percentage_or_employee_id()

    @api.onchange('e_document_id', 'journey_time')
    def _onchange_set_start_and_end_dates(self):
        if self.journey_time == 'other' and self.e_document_id:
            start_time = datetime.strptime(self.e_document_id.date_from,
                                           tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=5)
            end_time = datetime.strptime(self.e_document_id.date_to,
                                         tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=15)
            self.departure_journey_start = start_time
            self.departure_journey_end = start_time
            self.return_journey_start = end_time
            self.return_journey_end = end_time

    @api.one
    @api.depends('departure_journey_start', 'departure_journey_end', 'return_journey_start', 'return_journey_end',
                 'journey_time')
    def _compute_journey_compensation(self):
        if self.journey_time == 'during_work_hours':
            self.journey_amount_to_be_compensated = 0.0
            self.journey_has_to_be_compensated = False
        else:
            if self.departure_journey_start and self.departure_journey_end and self.return_journey_start and self.return_journey_end:
                departure_journey_after_hours_amount = self.get_business_trip_travel_after_work_hours_amount(
                    self.employee_id,
                    self.departure_journey_start,
                    self.departure_journey_end)

                return_journey_after_hours_amount = self.get_business_trip_travel_after_work_hours_amount(
                    self.employee_id,
                    self.return_journey_start,
                    self.return_journey_end)

                total_amount_after_hours = 0.0
                if not self.env.context.get('skip_departure_journey', False):
                    total_amount_after_hours += departure_journey_after_hours_amount
                if not self.env.context.get('skip_return_journey', False):
                    total_amount_after_hours += return_journey_after_hours_amount
            else:
                total_amount_after_hours = 0.0
            self.journey_amount_to_be_compensated = total_amount_after_hours
            self.journey_has_to_be_compensated = not tools.float_is_zero(total_amount_after_hours, precision_digits=2)

    @api.multi
    @api.constrains('departure_journey_start',
                    'departure_journey_end',
                    'return_journey_start',
                    'return_journey_end',
                    'journey_time')
    def _check_business_trip_journey_times(self):
        for rec in self:
            if rec.journey_time != 'during_work_hours':
                e_name = rec.employee_id.display_name
                if rec.departure_journey_start >= rec.departure_journey_end:
                    raise exceptions.ValidationError(_(
                        'Darbuotojo %s kelionės į komandiruotę pradžia turi prasidėti prieš kelionės pabaigą') % e_name)
                if rec.return_journey_start >= rec.return_journey_end:
                    raise exceptions.ValidationError(_(
                        'Darbuotojo %s kelionės iš komandiruotės pradžia turi prasidėti prieš kelionės pabaigą') % e_name)
                if rec.departure_journey_end > rec.return_journey_start:
                    raise exceptions.ValidationError(_(
                        'Darbuotojo %s kelionė į komandiruotę privalo baigtis prieš kelionę iš komandiruotės') % e_name)

    @api.model
    def get_business_trip_travel_after_work_hours_amount(self, employee_id, trip_start, trip_end):
        def convert_to_local_tz(date_to_convert):
            tzone = self._context.get('tz') or self.env.user.tz
            value = date_to_convert
            try:
                diff = round((datetime.now(timezone(tzone)).replace(tzinfo=None) - datetime.utcnow()).total_seconds(),
                             3)
                value_dt = datetime.strptime(date_to_convert, tools.DEFAULT_SERVER_DATETIME_FORMAT) + relativedelta(seconds=diff)
                value = value_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            except:
                pass
            return value

        if not (employee_id and trip_start and trip_end):
            return 0

        if trip_start > trip_end:
            raise exceptions.ValidationError(
                _('Skaičiuojant komandiruotės kelionės trukmę, data nuo turėtų būti mažesnė už datą iki'))

        date_from = trip_start[:10]
        date_to = trip_end[:10]

        appointments = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', employee_id.id),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '>=', date_from),
            ('date_end', '=', False)
        ])

        trip_start = datetime.strptime(convert_to_local_tz(trip_start), tools.DEFAULT_SERVER_DATETIME_FORMAT)
        trip_end = datetime.strptime(convert_to_local_tz(trip_end), tools.DEFAULT_SERVER_DATETIME_FORMAT)

        loop_date = trip_start + relativedelta(hour=0, minute=0, second=0)
        loop_date_to = trip_end + relativedelta(hour=0, minute=0, second=0)
        dates = []
        while loop_date <= loop_date_to:
            datetime_strf = loop_date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            date = datetime_strf[:10]
            dates.append(date)
            loop_date += relativedelta(days=1)
        dates = list(set(dates))
        total_time_after_hours = 0.0
        for date in dates:
            date_appointment = appointments.filtered(
                lambda app: app.date_start <= date and (not app.date_end or app.date_end >= date))
            if not date_appointment:
                continue
            working_ranges = date_appointment.schedule_template_id.get_working_ranges([date])
            working_ranges = working_ranges.get(str(date), [])
            date_day_start = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=0, minute=0,
                                                                                                       second=0)
            date_day_end = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1,
                                                                                                     hour=0,
                                                                                                     minute=0,
                                                                                                     second=0)
            date_trip_start = max(date_day_start, trip_start)
            date_trip_end = min(date_day_end, trip_end)
            start_time = date_trip_start.hour + date_trip_start.minute / 60.0  # P3:DivOK
            end_time = date_trip_end.hour + date_trip_end.minute / 60.0  # P3:DivOK
            if tools.float_is_zero(end_time, 2):
                end_time = 24.0
            date_time_after_hours = end_time - start_time
            for working_range in working_ranges:
                range_time_from = working_range[0]
                range_time_to = working_range[1]
                if end_time <= range_time_to and start_time >= range_time_from:
                    date_time_after_hours = 0.0
                    break
                elif end_time >= range_time_to and start_time <= range_time_from:
                    date_time_after_hours -= range_time_to - range_time_from
                elif range_time_from <= start_time < range_time_to:
                    date_time_after_hours -= range_time_to - start_time
                elif range_time_from < end_time <= range_time_to:
                    date_time_after_hours -= end_time - range_time_from
            date_time_after_hours = max(date_time_after_hours, 0.0)
            total_time_after_hours += date_time_after_hours
        return total_time_after_hours

    @api.multi
    def get_not_pay_allowance_days(self):
        """
        Method to be overridden
        :return: List of dates
        """
        self.ensure_one()

        pay_allowance_by_default = self.env['ir.config_parameter'].sudo().get_param(
            'pay_allowance_by_default', default='do'
        ) == 'do'

        date_from = self.e_document_id.date_from
        date_to = self.e_document_id.date_to

        if pay_allowance_by_default or not date_from or not date_to:
            return self.extra_worked_day_ids.filtered(lambda l: not l.pay_allowance).mapped('date')

        date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

        days_with_paid_allowance = self.extra_worked_day_ids.filtered(lambda l: l.pay_allowance).mapped('date')
        days_not_to_pay_allowance_on = list()

        while date_dt <= date_to_dt:
            date = date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if date not in days_with_paid_allowance:
                days_not_to_pay_allowance_on.append(date)
            date_dt += relativedelta(days=1)

        return days_not_to_pay_allowance_on

    @api.multi
    def set_settings(self):
        self.ensure_one()

        doc = self.e_document_id
        if not doc.is_business_trip_doc():
            return

        if doc.state == 'draft':
            not_pay_allowance_dates = self.get_not_pay_allowance_days()
            worked_dates = self.extra_worked_day_ids.filtered(lambda l: l.worked).mapped('date')

            date_from_dt = datetime.strptime(doc.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(doc.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

            iteration = date_from_dt
            loop_end = date_to_dt
            business_trip_dates = []
            while iteration <= loop_end:
                business_trip_dates.append(iteration.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
                iteration += relativedelta(days=1)

            appointments = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', self.employee_id.id),
                ('date_start', '<=', doc.date_to),
                '|',
                ('date_end', '>=', doc.date_from),
                ('date_end', '=', False)
            ])

            national_holidays = self.env['sistema.iseigines'].search([('date', '<=', doc.date_to),
                                                                      ('date', '>=', doc.date_from)]).mapped('date')

            line_commands = [(5,)]
            for date in business_trip_dates:
                date_app = appointments.filtered(lambda app: app.date_start <= date and
                                                             (not app.date_end or app.date_end >= date))
                include_in_dates = date in national_holidays and date_app
                if not include_in_dates:
                    weekends = [5, 6]
                    if date_app:
                        weekends = date_app.schedule_template_id.off_days()
                    if datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT).weekday() in weekends:
                        include_in_dates = True
                if not include_in_dates:
                    continue
                # TODO Don't overwrite on each open
                line_commands.append(
                    (0, 0, {'business_trip_schedule_id': self.id, 'date': date, 'worked': date in worked_dates,
                            'pay_allowance': date not in not_pay_allowance_dates}))
            self.write({'extra_worked_day_ids': line_commands})

        return {
            'name': _('Darbuotojo komandiruotės nustatymai'),
            'view_mode': 'form',
            'res_model': 'e.document.business.trip.employee.line',
            'res_id': self.id,
            'view_id': self.env.ref('e_document.employee_business_trip_line_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'view_type': 'form',
            'flags': {'initial_mode': 'readonly' if not self.line_is_editable else 'edit',
                      'mode': 'readonly' if not self.line_is_editable else 'edit'},
        }


EDocumentBusinessTripWorkSchedule()


class EDocumentBusinessTripExtraWorkedDays(models.Model):
    _name = 'e.document.business.trip.extra.worked.days'

    def _pay_allowance_by_default(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'pay_allowance_by_default', default='do'
        ) == 'do'

    business_trip_schedule_id = fields.Many2one('e.document.business.trip.employee.line',
                                                string='Komandiruotės darbuotojo darbo laiko grafikas', required=True,
                                                ondelete='cascade', readonly=True)
    date = fields.Date(string='Data', required=True, readonly=True)
    worked = fields.Boolean(string='Dirbta', default=False)
    pay_allowance = fields.Boolean(string='Mokėti dienpinigius', default=_pay_allowance_by_default,
                                   inverse='_inverse_set_employee_allowance')

    @api.multi
    def _inverse_set_employee_allowance(self):
        for rec in self:
            rec.business_trip_schedule_id.with_context(dont_recreate_worked_days=True)._onchange_allowance_percentage_or_employee_id()


EDocumentBusinessTripExtraWorkedDays()


class EDocumentBusinessTripRequestExtraWorkedDays(models.Model):
    _name = 'e.document.business.trip.request.extra.worked.days'

    e_document_id = fields.Many2one(
        'e.document',
        string='Susijęs dokumentas',
        required=True,
        ondelete='cascade'
    )
    date = fields.Date(string='Data', required=True, readonly=True)
    worked = fields.Boolean(string='Noriu dirbti', default=False)


EDocumentBusinessTripRequestExtraWorkedDays()
