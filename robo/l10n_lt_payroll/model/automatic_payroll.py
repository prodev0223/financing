# -*- coding: utf-8 -*-
import logging
import urllib2
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, _, api, exceptions, fields, models, tools
from .hr_payroll import PAYROLL_EXECUTION_STAGES

_logger = logging.getLogger(__name__)


def _strf(date):
    return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)


def _payroll_executor_default_date_ranges(year=False, month=False):
    year = year or datetime.utcnow().year
    month = month or datetime.utcnow().month
    period_start = datetime(year, month, 1)
    month_start = _strf(period_start)
    month_end = _strf(period_start + relativedelta(day=31))
    return month_start, month_end, year, month


class AutomaticPayrollExecutionHistory(models.Model):
    _name = 'automatic.payroll.execution.history'
    _order = 'create_date DESC'

    year = fields.Integer('DU Skaičiavimo metai', required=True, readonly=True)
    month = fields.Integer('DU Skaičiavimo mėnuo', required=True, readonly=True)
    employee_history = fields.One2many('automatic.payroll.execution.employee.history', 'history_obj_id',
                                       string='Darbuotojų tvirtinimo istorija', readonly=True)
    success = fields.Boolean('Sėkmingai įvykdyta', compute='_compute_success', store=True)

    @api.multi
    def name_get(self):
        names = []
        for rec in self:
            exec_date = _strf(datetime.strptime(rec.create_date, tools.DEFAULT_SERVER_DATETIME_FORMAT))
            names.append((
                rec.id, _('Skaičiavimas už %s-%s (%s)') % (str(rec.year), str(rec.month), exec_date)
            ))
        return names

    @api.one
    @api.depends('employee_history.success')
    def _compute_success(self):
        self.success = not any(not eh.success for eh in self.employee_history)


AutomaticPayrollExecutionHistory()


class AutomaticPayrollExecutionEmployeeHistory(models.Model):
    _name = 'automatic.payroll.execution.employee.history'

    history_obj_id = fields.Many2one('automatic.payroll.execution.history', string='Istorijos objektas',
                                     help='Automatinio atlyginimo skaičiavimo istorijos objektas', required=True,
                                     readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True, readonly=True)
    message = fields.Char('Klaidos/Įsivykdymo pranešimas', readonly=True)
    stage = fields.Selection(PAYROLL_EXECUTION_STAGES,
                             'Etapas', readonly=True)
    success = fields.Boolean('Sėkmingai įvykdyta', required=True, readonly=True)


AutomaticPayrollExecutionEmployeeHistory()


class HrPayroll(models.Model):
    _inherit = 'hr.payroll'

    @api.model
    def execute_automatic_payroll(self, month=False, year=False, update_ziniarastis=True, show_bank_statements=False,
                                  auto_confirm_all_planned_schedule_lines=False):
        if not self.env.user.is_accountant():
            raise exceptions.ValidationError(_('Neturite pakankamai teisių automatiškai paskaičiuoti atlyginimus'))

        month_start, month_end, year, month = _payroll_executor_default_date_ranges(year=year, month=month)

        history_obj = self.env['automatic.payroll.execution.history'].create({'year': year, 'month': month})
        self = self.sudo().with_context(lang='lt_LT')

        response = {'sam_url': False, 'status': 'fail', 'details': []}

        good_employee_ids = self.env['hr.contract'].search([
            ('date_start', '<=', month_end),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', month_start)
        ]).mapped('employee_id.id')

        if not good_employee_ids:
            response['status'] = 'no-employees-fail'
            return response

        def check_payslip_run_done_status():
            du_closed = bool(self.env['hr.payslip.run'].search(
                [('date_start', '=', month_start), ('state', '=', 'close')], count=True))
            return du_closed

        def update_response_and_employee_continuation(msg, stage, employees_to_add, status='fail'):
            details = []
            stages_dict = {}
            for payroll_execution_stage in PAYROLL_EXECUTION_STAGES:
                stages_dict[payroll_execution_stage[0]] = payroll_execution_stage[1]

            empl_history_base = {
                'history_obj_id': history_obj.id,
                'message': msg,
                'stage': stage,
                'success': False if status == 'fail' else True,
            }

            for empl in employees_to_add:
                empl_history_vals = empl_history_base.copy()
                empl_history_vals.update({
                    'employee_id': empl
                })
                self.env['automatic.payroll.execution.employee.history'].create(empl_history_vals)
                details.append({
                    'employee_name': self.env['hr.employee'].browse(empl).display_name,
                    'employee_id': empl,
                    'msg': msg,
                    'stage': stages_dict.get(stage, stages_dict.get('undefined')),
                    'status': status
                })
            response['details'] += details
            to_remove = list(employees_to_add)
            for el in to_remove:
                if el in good_employee_ids:
                    good_employee_ids.remove(el)

        def close_payslip_run():
            payslip_runs = self.env['hr.payslip.run'].search(
                [('ziniarastis_period_id', '=', ziniarastis_period.id), ('state', '=', 'draft')])
            for payslip_run in payslip_runs:
                try:
                    slips = payslip_run.slip_ids.filtered(lambda x: not x.pre_paid)
                    slips.write({'pre_paid': True, 'closed': True})
                    employees_paid_by_cash = slips.filtered(lambda r: r.employee_id.pay_salary_in_cash).mapped(
                        'employee_id')
                    if employees_paid_by_cash:
                        empl_list = ', '.join(employees_paid_by_cash.mapped('name'))
                        payslip_run.write({'last_confirm_warning_message': _(
                            'Šiems darbuotojams nebuvo sukurti mokėjimai, nes jiems darbo užmokestis yra mokamas grynais: %s') % str(
                            empl_list)})
                    else:
                        payslip_run.write({'last_confirm_warning_message': False})
                    payslip_run.with_context(slips=slips, closed=True).create_bank_statements()
                    payslip_run.with_context(slips=slips)._create_holiday_fix()
                    payslip_run.create_atostoginiu_kaupiniu_irasas()
                    payslip_runs.recompute_later_holiday_reserve()
                    if show_bank_statements and payslip_run.show_invite_sign:
                        payslip_run.invite_sign()
                    payslip_run.write({'state': 'close'})
                except Exception as exc:
                    payslip_runs.write({'last_confirm_fail_message': _('Algalapio užvėrimas nepavyko, klaidos pranešimas: %s') % str(exc.args[0])})
                    update_response_and_employee_continuation(
                        msg=_('Suvestinės nepavyko užverti dėl kitos priežasties. Klaidos pranešimas: %s') % str(exc.args[0]),
                        stage='payslip_run',
                        employees_to_add=payslip_run.mapped('slip_ids.employee_id.id'))

        def close_ziniarastis():
            try:
                ziniarastis_period.button_done()
            except:
                ziniarastis_employees = ziniarastis_period.mapped('related_ziniarasciai_lines.employee_id.id')
                update_response_and_employee_continuation(
                    msg='Nepavyko užverti žiniaraščio',
                    stage='ziniarastis_validation',
                    employees_to_add=ziniarastis_employees)

        def perform_payslip_checks(slips_for_slip_checks):
            def is_draft(obj): return obj.state == 'draft'

            def no_neto_diff(obj): return tools.float_is_zero(obj.neto_skirtumas, precision_digits=2)

            def no_unconfirmed_employee_payments(obj): return not obj.unconfirmed_employee_payments_exist

            def no_holidays_that_need_recomputing(obj): return not obj.has_need_action_holidays

            def no_negative_holidays(obj): return not obj.has_negative_holidays

            def no_external_calculation_mismatch(obj):
                return not obj.warn_about_possible_incorrect_calculations

            def no_possible_parenthood_holidays_npd_issue(obj):
                return not obj.warn_about_possible_parenthood_holidays_npd_issue

            def check_failed(method_to_check_against):
                return [obj.employee_id.id for obj in slips_for_slip_checks if not method_to_check_against(obj)]

            # Type (err_msg_if_fails, empls_failed)
            checks_to_perform = [
                ('Algalapis nėra juodraščio būsenos', check_failed(is_draft)),
                # ('Skiriasi NETO atlyginimas', check_failed(no_neto_diff)),
                ('Yra nepatvirtintų išmokų už periodą', check_failed(no_unconfirmed_employee_payments)),
                ('Reikia perskaičiuoti atostogas', check_failed(no_holidays_that_need_recomputing)),
                ('Atostogų likutis yra neigiamas', check_failed(no_negative_holidays)),
                ('Nesutampa paskaičiuota NETO suma su išoriniais paskaičiavimais', check_failed(no_external_calculation_mismatch)),
                ('Baigiasi ar prasideda tėvystės atostogos viduryje mėnesio, todėl galimi neaiškumai dėl NPD taikymo',
                 check_failed(no_possible_parenthood_holidays_npd_issue)),
            ]
            for check in [check for check in checks_to_perform if check[1]]:
                update_response_and_employee_continuation(
                    msg=check[0],
                    stage='payslip',
                    employees_to_add=check[1])

        def check_payslips():
            payslip_runs = self.env['hr.payslip.run'].search([('ziniarastis_period_id', '=', ziniarastis_period.id)])
            slip_ids = payslip_runs.mapped('slip_ids').filtered(lambda p: p.employee_id.id in good_employee_ids)
            payslip_not_created_employee_ids = []
            for employee_id in good_employee_ids:
                empl_payslip = slip_ids.filtered(lambda p: p.employee_id.id == employee_id)
                if not empl_payslip:
                    payslip_not_created_employee_ids.append(employee_id)
            if payslip_not_created_employee_ids:
                update_response_and_employee_continuation(
                    msg='Nepavyko sukurti algalapio dėl nežinomų priežasčių',
                    stage='payslip',
                    employees_to_add=payslip_not_created_employee_ids)

            slip_ids.filtered(lambda s: s.state == 'draft').refresh_and_recompute()
            perform_payslip_checks(slip_ids.filtered(lambda s: s.state != 'done'))

            slip_ids = slip_ids.filtered(lambda s: s.employee_id.id in good_employee_ids)

            bad_payslip_employee_ids = []
            slip_holidays = self.env['hr.holidays'].search([('employee_id', 'in', slip_ids.mapped('employee_id.id')),
                                                       ('date_from_date_format', '<=', month_end),
                                                       ('date_to_date_format', '>=', month_start),
                                                       ('holiday_status_id.kodas', '=', 'A')])
            slip_holidays.recalculate_holiday_payment_amounts()
            for payment in slip_holidays.mapped('payment_id').filtered(lambda p: p.state != 'done'):
                payment.atlikti()
            for slip in slip_ids.filtered(lambda p: p.state == 'draft'):
                try:
                    slip_empl_hols = slip_holidays.filtered(lambda h: h.employee_id.id == slip.employee_id.id)
                    if slip_empl_hols:
                        slip.compute_sheet()
                    slip.with_context(automatic_payroll=True).action_payslip_done()
                except:
                    bad_payslip_employee_ids.append(slip.employee_id.id)

            if bad_payslip_employee_ids:
                update_response_and_employee_continuation(
                    msg='Algalapio nepavyko patvirtinti dėl nežinomos priežasties',
                    stage='payslip',
                    employees_to_add=bad_payslip_employee_ids)

            return slip_ids.filtered(lambda p: p.state == 'done')

        def confirm_ziniarastis_lines():
            successful_ziniarastis_lines = ziniarastis_period.mapped('related_ziniarasciai_lines').filtered(
                lambda l: l.employee_id.id in good_employee_ids and l.state == 'draft')
            unsuccessful_ziniarastis_line_confirm_ids = []
            for line in successful_ziniarastis_lines:
                try:
                    line.button_single_done()
                except:
                    unsuccessful_ziniarastis_line_confirm_ids.append(line.employee_id.id)
            if unsuccessful_ziniarastis_line_confirm_ids:
                update_response_and_employee_continuation(
                    msg='Nepavyko patvirtinti žiniaraščio eilutės dėl nežinomų priežasčių',
                    stage='ziniarastis_line_validation',
                    employees_to_add=unsuccessful_ziniarastis_line_confirm_ids)

        def confirm_schedule():
            payroll_schedule_module = self.env['ir.module.module'].search([
                ('name', '=', 'payroll_schedule')
            ], limit=1)
            work_schedule_module = self.env['ir.module.module'].search([
                ('name', '=', 'work_schedule')
            ], limit=1)

            payroll_schedule_exists = payroll_schedule_module.state == 'installed' if payroll_schedule_module else False
            work_schedule_exists = work_schedule_module.state == 'installed' if work_schedule_module else False
            is_schedule_installed = True if payroll_schedule_exists or work_schedule_exists else False

            bad_employee_ids = []
            if payroll_schedule_exists:
                days = self.env['hr.schedule.day'].search([
                    ('date', '<=', month_end),
                    ('date', '>=', month_start),
                    ('employee_id', 'in', good_employee_ids)
                ])
                day_lines = days.filtered(lambda d: d.state == 'validate_2').mapped('schedule_day_lines')
                if len(day_lines) > 0:
                    day_lines.action_done()
                done_days = days.filtered(lambda d: d.state == 'done')
                bad_employee_ids = days.filtered(lambda d: d.id not in done_days.mapped('id')).mapped('employee_id.id')
            elif work_schedule_exists and self.env.user.company_id.with_context(date=month_end).extended_schedule:
                work_schedule_lines = self.env['work.schedule.line'].search([
                    ('year', '=', year),
                    ('month', '=', month),
                    ('employee_id', 'in', good_employee_ids)
                ])
                factual_schedule_lines = work_schedule_lines.filtered(
                    lambda l: l.work_schedule_id.schedule_type == 'factual')
                planned_schedule_lines = work_schedule_lines.filtered(
                    lambda l: l.work_schedule_id.schedule_type == 'planned')
                if auto_confirm_all_planned_schedule_lines and planned_schedule_lines and factual_schedule_lines:
                    planned_schedule_lines.with_context(automatic_payroll=True).action_set_all_as_used_or_not(True)
                if factual_schedule_lines:
                    confirmed_lines = factual_schedule_lines.filtered(lambda l: l.state == 'confirmed')
                    bad_employee_ids += factual_schedule_lines.filtered(lambda l: l.id not in confirmed_lines.ids and l.state != 'done').mapped('employee_id.id')
                    for line in confirmed_lines:
                        try:
                            line.with_context(automatic_payroll=True).action_done()
                        except Exception as e:
                            bad_employee_ids.append(line.employee_id.id)
                if not bad_employee_ids:
                    validated_lines = factual_schedule_lines.filtered(lambda l: l.state == 'done')
                    bad_employee_ids = factual_schedule_lines.filtered(
                        lambda l: l.id not in validated_lines.mapped('id')).mapped('employee_id.id')
            if bad_employee_ids:
                update_response_and_employee_continuation(
                    msg='Nepavyko patvirtinti grafiko',
                    stage='schedule',
                    employees_to_add=bad_employee_ids)
            return is_schedule_installed

        def update_ziniarasciai():
            ziniarastis = self.env['ziniarastis.period'].search([
                ('date_from', '=', month_start),
                ('date_to', '=', month_end)
            ], limit=1)
            if not ziniarastis:
                ziniarastis = self.env['ziniarastis.period'].create({
                    'date_from': month_start,
                    'date_to': month_end
                })
                ziniarastis.generate_ziniarasciai()
            if update_ziniarastis:
                period_lines = ziniarastis.related_ziniarasciai_lines.filtered(
                    lambda
                        l: l.employee_id.id in good_employee_ids and l.state == 'draft' and l.date_from == month_start and l.date_to == month_end)
                if schedule_installed:
                    period_lines.auto_fill_period_line()
                else:
                    lines_to_update = []
                    for employee in good_employee_ids:
                        period_line = period_lines.filtered(lambda l: l.employee_id.id == employee)
                        if any(not day.holidays_match for day in period_line.mapped('ziniarastis_day_ids')):
                            lines_to_update.append(period_line.id)
                    period_lines.filtered(lambda l: l.id in lines_to_update).auto_fill_period_line()
                    period_lines._compute_time_worked()
            return ziniarastis

        def check_ziniarastis_problems():
            e_doc_problem_ids = []
            holiday_mismatch_ids = []
            hours_mismatch_problem_ids = []
            for line in ziniarastis_period.mapped('related_ziniarasciai_lines').filtered(
                    lambda l: l.employee_id.id in good_employee_ids and l.state == 'draft'):
                if line.show_warning:
                    e_doc_problem_ids.append(line.employee_id.id)

                if not tools.float_compare(line.hours_worked, line.num_regular_work_hours_without_holidays,
                                           precision_digits=2) == 0:
                    hours_mismatch_problem_ids.append(line.employee_id.id)

                if any(not day.holidays_match for day in line.mapped('ziniarastis_day_ids')):
                    holiday_mismatch_ids.append(line.employee_id.id)

            if e_doc_problem_ids:
                update_response_and_employee_continuation(
                    msg='Egzistuoja nepasirašyti dokumentai',
                    stage='ziniarastis_checks',
                    employees_to_add=e_doc_problem_ids)

            if holiday_mismatch_ids:
                update_response_and_employee_continuation(
                    msg='Egzistuoja neatitikimai tarp atostogų ir žiniaraščio dienų',
                    stage='ziniarastis_checks',
                    employees_to_add=holiday_mismatch_ids)

            if hours_mismatch_problem_ids:
                update_response_and_employee_continuation(
                    msg='Egzistuoja neatitikimai tarp dirbto laiko ir darbo normos',
                    stage='ziniarastis_checks',
                    employees_to_add=hours_mismatch_problem_ids)

            failed_workflow_documents = self.env['e.document'].search([
                ('failed_workflow', '=', True),
                ('date_from_display', '<=', ziniarastis_period.date_to),
                ('date_to_display', '>=', ziniarastis_period.date_from)
            ])

            failed_doc_employees = failed_workflow_documents.mapped('related_employee_ids.id')

            failed_doc_employee_ids = ziniarastis_period.mapped('related_ziniarasciai_lines').filtered(
                lambda
                    l: l.employee_id.id in good_employee_ids and l.state == 'draft' and l.employee_id.id in failed_doc_employees).mapped(
                'employee_id.id')

            if failed_doc_employee_ids:
                update_response_and_employee_continuation(
                    msg='Egizstuoja dokumentai, kuriem neįvykdyta dokumento darbo eiga',
                    stage='ziniarastis_checks',
                    employees_to_add=failed_doc_employee_ids)

        def show_front_statements():
            statements = payslips.mapped('payment_ids.bank_statement')
            bad_empl_ids = []
            for statement in statements:
                try:
                    statement.show_front()
                except Exception as exc:
                    _logger.info('Front bank statement exception: %s' % str(exc.args))
                    bad_empl_ids.append(statement.mapped('line_ids.partner_id.employee_ids.id'))

            bad_empl_ids = list(set(bad_empl_ids))
            if bad_empl_ids:
                update_response_and_employee_continuation(
                    msg='Nepavyko rodyti pavedimo vadovui',
                    stage='transactions',
                    employees_to_add=bad_empl_ids)

        if not check_payslip_run_done_status():
            schedule_installed = confirm_schedule()
            if not good_employee_ids:
                return response
            ziniarastis_period = update_ziniarasciai()
            check_ziniarastis_problems()
            if not good_employee_ids:
                return response
            confirm_ziniarastis_lines()
            if not good_employee_ids:
                return response
            payslips = check_payslips()
            if not good_employee_ids:
                return response
            elif len(response['details']) > 0:
                response['status'] = 'partial'
                update_response_and_employee_continuation(
                    msg='Algalapiai užverti',
                    stage='payslip',
                    employees_to_add=good_employee_ids,
                    status='success')
                return response
            close_ziniarastis()
            if not good_employee_ids:
                return response
            close_payslip_run()
            if not good_employee_ids:
                return response
            if show_bank_statements:
                show_front_statements()
            if not good_employee_ids:
                return response
            elif len(response['details']) > 0:
                response['status'] = 'partial'
                update_response_and_employee_continuation(
                    msg='Pavyko rodyti pavedimą vadovui',
                    stage='transactions',
                    employees_to_add=good_employee_ids,
                    status='success')
                return response
        # else:
        #     response['status'] = 'success'
        #     update_response_and_employee_continuation(
        #         msg='Visi veiksmai sėkmingai atlikti',
        #         stage='done',
        #         employees_to_add=good_employee_ids,
        #         status='success')
        gpm_exported = self.env['vmi.document.export'].search_count([('doc_name', '=', 'GPM313.ffdata'),
                                                             ('state', '=', 'confirmed'),
                                                             ('file_type', '=', 'ffdata'),
                                                             ('document_date', '>=', month_start),
                                                             ('document_date', '<=', month_end)]) > 0
        if not gpm_exported:
            if self.env.user.id == SUPERUSER_ID:
                accountant = self.env.user.company_id.findir
            else:
                accountant = self.env.user
            gpm_313 = self.sudo(accountant.id).generate_gpm313(month, year)
            success = gpm_313.get('status') == 'success'
            if not success:
                update_response_and_employee_continuation(
                    msg='Nepavyko suformuoti GPM313 dėl nežinomos priežasties',
                    stage='gpm',
                    employees_to_add=good_employee_ids)
                response['status'] = 'fail'
        if not good_employee_ids:
            return response
        sam_exported = self.env['sodra.document.export'].search_count([('doc_name', '=', 'SAM'),
                                                          ('state', '=', 'confirmed'),
                                                          ('document_date', '>=', month_start),
                                                          ('document_date', '<=', month_end)]) > 0
        if not sam_exported:
            sam_url = self.payroll_executor_send_sam(month=month, year=year)
            date_from = datetime(year, month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.env['hr.payroll.dashboard'].search([
                ('date_from', '=', date_from)
            ]).write({'sam_url': sam_url})

            if not isinstance(sam_url, bool):
                response['status'] = 'success'
                update_response_and_employee_continuation(
                    msg='Visi veiksmai sėkmingai atlikti',
                    stage='done',
                    employees_to_add=good_employee_ids,
                    status='success')
                response['sam_url'] = sam_url
            else:
                response['status'] = 'fail'
                update_response_and_employee_continuation(
                    msg='Nepavyko išsiųsti SAM pranešimo',
                    stage='sam',
                    employees_to_add=good_employee_ids)
        else:
            response['status'] = 'success'
        return response

    @api.model
    def generate_gpm313(self, month, year):
        month_start = datetime(year, month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        month_end = (datetime(year, month, 1)+relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        try:
            company_id = self.sudo().env.user.company_id.id
            self.env.cr.execute("""
                                SELECT MAX(F.date_done) as "date"
                                FROM account_bank_statement F
                                INNER JOIN account_journal J ON (J.id = F.journal_id)                                                            
                                WHERE F.company_id = %s
                                  AND F.state = 'confirm'
                                  AND F.date_done IS NOT NULL
                                  AND F.sepa_imported = TRUE
                                  AND J.show_on_dashboard = TRUE
                                  AND J.currency_id IS NULL
                                GROUP BY journal_id
                                """, (company_id,))
            update_date = self.env.cr.dictfetchall()
            if update_date and update_date[0].get('date'):
                deadline = datetime(year, month, 1) + relativedelta(months=1, day=31)
                if datetime.utcnow() <= deadline:
                    main_accountant = self.env['res.users'].search([('main_accountant', '=', True)], limit=1)
                    gpm = self.sudo(user=main_accountant).env['e.vmi.gpm313'].create({
                        'data_nuo': month_start,
                        'data_iki': month_end,
                    })
                    try:
                        gpm313_data = gpm.with_context(eds=True, check_report_matches_payslips=True).form_gpm313()
                        return {
                            'status': 'success',
                            'data': gpm313_data
                        }
                    except:
                        return {'status': 'fail'}
                else:
                    return {'status': 'fail'}
        except Exception as exc:
            return {'status': 'fail'}

    @api.model
    def payroll_executor_send_sam(self, month=False, year=False):
        if not self.env.user.has_group('robo_basic.group_robo_premium_accountant'):
            return False
        main_accountant = self.env['res.users'].search([('main_accountant', '=', True)], limit=1)

        def send(user_id):
            month_start, month_end, new_year, new_month = _payroll_executor_default_date_ranges(year, month)
            sam = self.sudo(user=user_id).env['e.sodra.sam'].create({
                'data_nuo': month_start,
                'data_iki': month_end,
            })
            res = sam.send()
            urls = res['context'].get('urls', False)
            if urls:
                urls = urllib2.quote(urls[0])
            return urls

        try:
            return send(main_accountant)
        except:
            try:
                return send(self.env.user)
            except:
                pass
        return False

HrPayroll()
