# -*- coding: utf-8 -*-
from __future__ import division
import babel

from odoo import models, fields, api, tools, exceptions, registry, SUPERUSER_ID
from odoo.tools.translate import _
from odoo.api import Environment
import odoo
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import calendar
from hr_contract_appointment import get_days_intersection, night_shift_start, night_shift_end
import threading
import logging
import time
from odoo.addons.l10n_lt_payroll.model.payroll_codes import PAYROLL_CODES
from six import iteritems


_logger = logging.getLogger(__name__)

NEATVYKIMAI_BE_K = ['V', 'M', 'MP', 'NLL', 'D', 'L', 'N', 'NS', 'A', 'MA', 'NA', 'KA', 'G', 'ID', 'PV',
                    'MD', 'SŽ', 'KV', 'KVN', 'VV', 'KT', 'KM', 'PK', 'PN', 'PB', 'ND', 'NP', 'KR',
                    'NN', 'ST']

def multiple_create(self, table_name, values):
    """Creates and executes an insert query into a table
        Returns the list of ids created
    """
    id_seq_string = 'nextval(\'%s_id_seq\')' % table_name

    # Safety checks
    self.check_access_rule('create')
    if not table_name or not values:
        return list()
    val_length = False
    for val in values:
        # Values not equal length check
        if not val_length:
            val_length = len(val)
        elif val_length != len(val) or len(val) == 0:
            raise exceptions.Warning(
                _('Nenumatyta sistemos klaida sukuriant duomenis. Kreipkitės į sistemos administratorių.'))

    query = 'INSERT INTO \"%s\" ("id", "create_date", "write_date", "create_uid", "write_uid", \"%s\") VALUES '
    field_names = list(values[0].keys())
    query = query % (table_name, "\",\"".join(field_names))

    values_list = list()
    id_seq_start_string = "(%s, (now() at time zone \'UTC\'), (now() at time zone \'UTC\'), %s, %s, " % (
    id_seq_string, self.env.user.id, self.env.user.id)
    i = 0
    for val_dict in values:
        query += id_seq_start_string
        for j in range(0, len(val_dict)):
            query += '%s'
            values_list.append(val_dict[field_names[j]])
            if j != (len(val_dict) - 1):
                query += ', '
        query += ')'
        if i != (len(values) - 1):
            query += ', '
        i += 1
    query += " RETURNING id;"
    self.env.cr.execute(query, values_list)
    ids_fetch = self.env.cr.dictfetchall()
    return [single_id['id'] for single_id in ids_fetch]


class ZiniarastisPeriod(models.Model):

    _name = 'ziniarastis.period'

    _order = 'date_from desc'

    _sql_constraints = [('date_from_date_to_unique', 'unique(date_from, date_to)',
                         _('There cannot be two žiniarastis periods with same date_from and date_to'))]

    def default_date_from(self):
        current_date = datetime.utcnow()
        return datetime(year=current_date.year, month=current_date.month, day=1)

    def default_date_to(self):
        current_date = datetime.utcnow()
        return datetime(year=current_date.year, month=current_date.month, day=1) + relativedelta(day=31)

    def _default_company(self):
        return self.env.user.company_id

    employee_id = fields.Many2one('hr.employee', store=False)  # Used for search in custom ziniarastis view

    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=_default_company)
    date_from = fields.Date(string='Data nuo', default=default_date_from, required=True, inverse='search_for_lines')
    date_to = fields.Date(string='Data iki', default=default_date_to, required=True, inverse='search_for_lines')
    state = fields.Selection([('draft', 'Preliminary'), ('done', 'Done')], required=True,
                             default='draft', readonly=True, copy=False)
    related_ziniarasciai_lines = fields.One2many('ziniarastis.period.line', 'ziniarastis_period_id')
    related_ziniarastis_days = fields.One2many('ziniarastis.day', 'ziniarastis_period_id')
    name = fields.Char(compute='get_name', store=True)

    hours_worked = fields.Float(string='Dirbta valandų', compute='_hours_worked', store=False)
    hours_night = fields.Float(string='Dirbta naktį', compute='_hours_night', store=False)
    hours_overtime = fields.Float(string='Dirbta viršvalandžių', compute='_hours_overtime', store=False)
    hours_not_regular = fields.Float(string='Dirbta nukrypus nuo normalių darbo sąlygų',
                                     compute='_hours_not_regular', store=False)
    hours_watch_home = fields.Float(string='Budėjimas namuose', compute='_hours_watch_home', store=False)
    hours_watch_work = fields.Float(string='Budėjimas darbe', compute='_hours_watch_work', store=False)
    hours_weekends = fields.Float(string='Poilsio dienomis', compute='_hours_weekends', store=False)
    hours_holidays = fields.Float(string='Švenčių dienomis', compute='_hours_holidays', store=False)
    num_lines = fields.Integer(string='Number of lines', compute='_num_lines')
    num_days = fields.Integer(string='Number of days', compute='_num_days')
    num_payslip_batches = fields.Integer(string='Num of payslip batches', compute='_num_payslip_batches')
    busy = fields.Boolean(string='Skaičiuojama', compute='_compute_busy')
    last_confirm_fail_message = fields.Char(string='Klaidos pranešimas')
    payroll_id = fields.Many2one('hr.payroll', compute='_compute_payroll_id')

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_busy(self):
        self.busy = self.payroll_id.busy

    @api.one
    @api.depends('date_from', 'date_to')
    def _compute_payroll_id(self):
        dt_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        HrPayroll = self.env['hr.payroll']
        payroll_id = HrPayroll.search([
            ('year', '=', dt_from.year),
            ('month', '=', dt_from.month),
        ], limit=1)
        if not payroll_id:
            payroll_id = HrPayroll.create({
                'year': dt_from.year,
                'month': dt_from.month
            })
        self.payroll_id = payroll_id

    @api.multi
    def get_button_statuses(self):
        # Gets button statuses for dynamic ziniarastis header (custom view)
        self.ensure_one()
        is_draft = self.state == 'draft'
        is_done = self.state == 'done'
        is_busy = self.busy
        draft_and_not_busy = is_draft and not is_busy
        done_and_not_busy = is_done and not is_busy
        slips_not_done = bool(self.mapped('related_ziniarasciai_lines').filtered(
            lambda l: 'done' not in l.mapped('payslip_ids.state'))
        )
        return {
            'button_done_threaded': draft_and_not_busy,
            'button_done_selected': draft_and_not_busy,
            'button_cancel': not is_done and not is_busy and slips_not_done,
            'button_draft': done_and_not_busy,
            'add_non_existing_contracts': draft_and_not_busy,
            'update_ziniarasciai': draft_and_not_busy,
            'export_excel': True,
            'export_excel_multiple': True,
            'open_payslip_batches': self.num_payslip_batches != 0,
            'button_switch_table_container': True,
            'ziniarastis_arrow_group': True,
            'button_check': True,
        }

    @api.model
    def get_back_end_empl_view(self, empl_id):
        action = self.env.ref('hr.open_view_employee_list_my')
        view = self.env.ref('hr.view_employee_form').id
        res = action.read()[0]
        res['res_id'] = int(empl_id)
        res['view_type'] = 'form'
        res['views'] = [[view, 'form']]
        res['view_id'] = view
        return res

    @api.multi
    def button_draft(self):
        self.write({'state': 'draft'})

    @api.one
    def _num_payslip_batches(self):
        self.num_payslip_batches = self.env['hr.payslip.run'].search_count([('ziniarastis_period_id', '=', self.id)])

    @api.multi
    @api.depends('related_ziniarasciai_lines')
    def _num_lines(self):
        for rec in self:
            rec.num_lines = len(rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarastis_days')
    def _num_days(self):
        for rec in self:
            rec.num_days = len(rec.related_ziniarastis_days)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_worked')
    def _hours_worked(self):
        for rec in self:
            rec.hours_worked = sum(l.hours_worked for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_night')
    def _hours_night(self):
        for rec in self:
            rec.hours_night = sum(l.hours_night for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_overtime')
    def _hours_overtime(self):
        for rec in self:
            rec.hours_overtime = sum(l.hours_overtime for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_not_regular')
    def _hours_not_regular(self):
        for rec in self:
            rec.hours_not_regular = sum(l.hours_not_regular for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_watch_home')
    def _hours_watch_home(self):
        for rec in self:
            rec.hours_watch_home = sum(l.hours_watch_home for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_watch_work')
    def _hours_watch_work(self):
        for rec in self:
            rec.hours_watch_work = sum(l.hours_watch_work for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_weekends')
    def _hours_weekends(self):
        for rec in self:
            rec.hours_weekends = sum(l.hours_weekends for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('related_ziniarasciai_lines.hours_holidays')
    def _hours_holidays(self):
        for rec in self:
            rec.hours_holidays = sum(l.hours_holidays for l in rec.related_ziniarasciai_lines)

    @api.multi
    @api.depends('date_from', 'date_to')
    def get_name(self):
        for rec in self:
            rec.name = '%s - %s' % (rec.date_from, rec.date_to)

    @api.multi
    def add_non_existing_contracts(self):
        self.ensure_one()
        contract_ids = self.env['hr.contract.appointment'].search([
            ('date_start', '<=', self.date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', self.date_from)]
        ).mapped('contract_id')
        existing_contract_ids = self.related_ziniarasciai_lines.mapped('contract_id')
        to_be_added_ids = [contract.id for contract in contract_ids if contract.id not in existing_contract_ids.mapped('id')]
        to_be_added_contracts = self.env['hr.contract'].browse(to_be_added_ids)
        self.generate_ziniarasciai(to_be_added_contracts)

    @api.multi
    def generate_ziniarasciai(self, contract_ids=None):
        self.ensure_one()
        self.check_availability()
        if not contract_ids:
            contract_ids = self.env['hr.contract.appointment'].search([
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)]
            ).mapped('contract_id')
        self.env['ziniarastis.period'].generate_contract_ziniarasciai(self.date_from, self.date_to, contract_ids, update_only_created=False)
        self.remove_nonexisting_contracts()


    @api.multi
    def generate_ziniarasciai_threaded(self):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            period_obj = env['ziniarastis.period']
            period_id = period_obj.browse(self.id)
            try:
                contract_ids = env['hr.contract'].search([('date_start', '<=', period_id.date_to),
                                                           '|',
                                                           ('date_end', '=', False),
                                                           ('date_end', '>=', period_id.date_from)]).mapped('id')
                period_obj.generate_contract_ziniarasciai(period_id.date_from, period_id.date_to, contract_ids,
                                                          update_only_created=True)
            except:
                new_cr.rollback()
                period_id.payroll_id.write({
                    'busy': False,
                    'partial_calculations_running': False,
                    'stage': False,
                })
            finally:
                period_id.payroll_id.write({
                    'busy': False,
                    'partial_calculations_running': False,
                    'stage': False,
                })
                new_cr.commit()
                new_cr.close()

    @api.multi
    def generate_ziniarasciai_background(self):
        self.ensure_one()
        self.payroll_id.write({
            'busy': True,
            'partial_calculations_running': True,
            'stage': 'ziniarastis_validation',
        })
        self.env.cr.commit()
        threaded_calculation = threading.Thread(target=self.generate_ziniarasciai_threaded)
        threaded_calculation.start()

    @api.model
    def refresh_line(self, date_from, date_to, contract_id):
        if not (date_from and date_to and contract_id):
            return
        line_to_refresh = self.env['ziniarastis.period.line'].search([('date_from', '=', date_from),
                                                                      ('date_to', '=', date_to),
                                                                      ('contract_id', '=', contract_id),
                                                                      ('state', '=', 'draft')], limit=1)
        line_to_refresh.auto_fill_period_line()

    @api.model
    def cancel_done_line(self, date_from, date_to, contract_id):
        if not (date_from and date_to and contract_id):
            return
        line_to_refresh = self.env['ziniarastis.period.line'].search([('date_from', '=', date_from),
                                                                      ('date_to', '=', date_to),
                                                                      ('contract_id', '=', contract_id),
                                                                      ('state', '=', 'done')], limit=1)
        line_to_refresh.button_cancel()

    @api.model
    def call_button_single_done(self, date_from, date_to, contract_id):
        if not (date_from and date_to and contract_id):
            return
        line_to_refresh = self.env['ziniarastis.period.line'].search([('date_from', '=', date_from),
                                                                      ('date_to', '=', date_to),
                                                                      ('contract_id', '=', contract_id),
                                                                      ('state', '=', 'draft')], limit=1)
        if not line_to_refresh:
            return
        line_to_refresh.button_single_done()

    @api.multi
    def update_ziniarasciai(self):
        self.ensure_one()
        self.check_availability()
        contract_ids = self.env['hr.contract'].search([
            ('date_start', '<=', self.date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', self.date_from)
        ])
        # Only generate for contracts that have appointments in the period
        contracts_to_generate_for = contract_ids.filtered(
            lambda contract: any(app.date_start <= self.date_to and (not app.date_end or app.date_end >= self.date_from)
                                 for app in contract.appointment_ids)
        )
        self.env['ziniarastis.period'].generate_contract_ziniarasciai(self.date_from, self.date_to,
                                                                      contracts_to_generate_for,
                                                                      update_only_created=False)
        self.remove_nonexisting_contracts()

    @api.multi
    def remove_nonexisting_contracts(self):
        for rec in self:
            valid_contracts_for_period = self.env['hr.contract.appointment'].search([
                ('date_start', '<=', rec.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', rec.date_from)
            ]).mapped('contract_id').filtered(lambda contract: not contract.is_internship_contract)
            rec.mapped('related_ziniarasciai_lines').filtered(
                lambda l: l.contract_id not in valid_contracts_for_period
            ).unlink()

    @api.model
    def generate_contract_ziniarasciai(self, date_from, date_to, contracts, update_only_created=True):
        # Create the timesheet period if it does not exist
        timesheet_period = self.env['ziniarastis.period'].search([
            ('date_from', '=', date_from), ('date_to', '=', date_to)
        ], limit=1)
        if not timesheet_period:
            timesheet_period = self.env['ziniarastis.period'].create({'date_from': date_from, 'date_to': date_to})

        timesheet_period_lines = self.env['ziniarastis.period.line'].search([
            ('contract_id', 'in', contracts.ids),
            '|',
                '&',
                    ('date_from', '<=', date_to),
                    ('date_from', '>=', date_from),
                '&',
                    ('date_from', '<=', date_from),
                    ('date_to', '>=', date_from),
        ])
        newly_created_period_lines = self.env['ziniarastis.period.line']
        for contract in contracts:
            # Check if the existing line period matches
            existing_timesheet_line = timesheet_period_lines.filtered(lambda l: l.contract_id == contract)
            if existing_timesheet_line:
                if existing_timesheet_line.date_from != date_from or existing_timesheet_line.date_to != date_to:
                    raise exceptions.Warning(_('This would intersect with existing ziniarastis for %(employee_id)s and '
                                               'contract %(contract_id)s') % {
                        'employee_id': contract.employee_id.name,
                        'contract_id': contract.name,
                    })
            else:
                newly_created_period_lines |= self.env['ziniarastis.period.line'].with_context(
                    dont_auto_fill_on_ziniarastis_period_create=True
                ).create({
                    'ziniarastis_period_id': timesheet_period.id,
                    'employee_id': contract.employee_id.id,
                    'contract_id': contract.id,
                    'date_from': timesheet_period.date_from,
                    'date_to': timesheet_period.date_to,
                    'working_schedule_number': contract.working_schedule_number
                })

        # If only auto fill newly created lines unless otherwise specified (by update_only_created)
        timesheet_lines_to_auto_fill = newly_created_period_lines
        if not update_only_created:
            timesheet_lines_to_auto_fill |= timesheet_period_lines
        timesheet_lines_to_auto_fill.filtered(lambda r: r.state == 'draft').auto_fill_period_line()

    @api.multi
    @api.constrains('date_from', 'date_to')
    def constrain_datos(self):
        for rec in self:
            date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from_dt.day != 1 or date_from_dt + relativedelta(day=31) != date_to_dt:
                raise exceptions.ValidationError(_('Periodo pradžia ir pabaiga turi sutapti su mėnesio pradžios ir '
                                                   'pabaigos datomis'))

    @api.one
    def search_for_lines(self):
        potential_lines = self.env['ziniarastis.period.line'].search([('date_from', '=', self.date_from),
                                                                      ('date_to', '=', self.date_to),
                                                                      ('ziniarastis_period_id', '!=', self.id)])
        for line in potential_lines:
            line._ziniarastis_period_id()

    @api.multi
    def button_done_threaded(self):
        self.ensure_one()
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('This action can only be performed by accountants!'))
        threaded_calculation = threading.Thread(target=self.thread_calc, args=(self.id,))
        threaded_calculation.start()

    def thread_calc(self, ziniarastis_id, filtered_line_ids=None):
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})
            ziniarastis_period = env['ziniarastis.period'].browse(ziniarastis_id)

            date_from_dt = datetime.strptime(ziniarastis_period.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            year, month = date_from_dt.year, date_from_dt.month

            last_confirm_fail_message = None

            history_obj = env['automatic.payroll.execution.history'].create({
                'year': year,
                'month': month
            })

            payroll = ziniarastis_period.payroll_id
            payroll.write({'busy': True, 'partial_calculations_running': True, 'stage': 'ziniarastis_validation'})
            new_cr.commit()

            try:
                line_cr = self.pool.cursor()
                line_env = api.Environment(line_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})

                lines = ziniarastis_period.related_ziniarasciai_lines.filtered(lambda r: r.state == 'draft')
                if filtered_line_ids:
                    lines = lines.filtered(lambda l: l.id in filtered_line_ids)
                lines = line_env['ziniarastis.period.line'].browse(lines.ids)
                number_of_tries = 3  # Try to confirm line 3 times. This is needed due to frequent serialization errors
                for line in lines:
                    if line.state == 'done':
                        continue
                    exception_message = None
                    continue_trying = True
                    for attempt in range(1, number_of_tries+1):
                        try:
                            if line.state == 'done':
                                break
                            line.button_single_done()
                            continue_trying = False
                        except Exception as e:
                            exception_message = e.args[0] if e.args else e.message
                            line_cr.rollback()
                        finally:
                            if not continue_trying or attempt == number_of_tries:
                                line_env['automatic.payroll.execution.employee.history'].create({
                                    'history_obj_id': history_obj.id,
                                    'message': exception_message if exception_message else '',
                                    'stage': 'ziniarastis_line_validation',
                                    'employee_id': line.employee_id.id,
                                    'success': not bool(exception_message),
                                })
                            line_cr.commit()
                        if not continue_trying:
                            break
                lines = env['ziniarastis.period.line'].browse(lines.ids)
                line_cr.close()

                new_cr.commit()
                lines.with_context(thread_calc=False).compute_stored_fields()
                new_cr.commit()
            except Exception as e:
                last_confirm_fail_message = _('Employee time sheet confirmation failed. Exception message: {}').format(
                    e.args[0] if e.args else e.message
                )
                new_cr.rollback()
            finally:
                payroll.write({'busy': False, 'partial_calculations_running': False, 'stage': False})
                ziniarastis_period_values = {'last_confirm_fail_message': last_confirm_fail_message}
                if all(l.state == 'done' for l in ziniarastis_period.mapped('related_ziniarasciai_lines')):
                    ziniarastis_period_values.update({'state': 'done'})
                ziniarastis_period.write(ziniarastis_period_values)
                new_cr.commit()
            new_cr.close()

    @api.one
    def check_availability(self):
        if self.busy:
            raise exceptions.Warning(_('Negalite modifikuoti žiniaraščio kuris yra tvirtinamas!'))

    @api.multi
    def button_done(self):
        self.ensure_one()
        lines = self.related_ziniarasciai_lines.filtered(lambda r: r.state == 'draft')
        for line in lines:
            line.button_single_done()
        if self._context.get('thread_calc', False):
            self.env.cr.commit()
            lines.button_done()
            slips = self.env['hr.payslip'].search([
                ('ziniarastis_period_line_id', 'in', lines.mapped('id')),
                ('state', '=', 'draft')
            ])
            for slip in slips:
                slip.refresh_and_recompute()
        self.state = 'done'

    @api.multi
    def button_cancel(self):
        for rec in self:
            rec.check_availability()
            payslip_batches = self.env['hr.payslip.run'].search([('ziniarastis_period_id', '=', rec.id)])
            for payslip_batch in payslip_batches:
                batch_slips = payslip_batch.slip_ids
                if payslip_batch.state != 'draft':
                    raise exceptions.UserError(_('Algalapiai jau patvirtinti. Pirmiau atšaukite juos.'))
                batch_slips = batch_slips.filtered(lambda s: s.state != 'done')
                batch_slips.atsaukti()
                batch_slips.with_context(ziniarastis_period_line_is_being_cancelled=True).unlink()
            rec.related_ziniarasciai_lines.filtered(lambda l: 'done' not in l.mapped('payslip_ids.state')).button_cancel()

    @api.multi
    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti patvirtinto žiniaraščio.'))
        return super(ZiniarastisPeriod, self).unlink()

    @api.multi
    def open_payslip_batches(self):
        self.ensure_one()
        batch_ids = self.env['hr.payslip.run'].search([('ziniarastis_period_id', '=', self.id)]).ids
        action = self.env.ref('hr_payroll.action_hr_payslip_run_tree')
        action_vals = {
            'id': action.id,
            'name': action.name,
            'view_id': False,
            'res_model': 'hr.payslip.run',
            'type': 'ir.actions.act_window',
            'context': {},
            'view_mode': 'form',
        }
        if len(batch_ids) == 1:
            view_id = self.env.ref('hr_payroll.hr_payslip_run_form').id
            action_vals.update({
                'view_type': 'form',
                'target': 'current',
                'res_id': batch_ids[0],
                'view_id': view_id,
                'views': [[view_id, 'form']]
            })
        else:  # should not happen
            view_id = self.env.ref('hr_payroll.hr_payslip_run_tree').id
            action_vals.update({
                'view_type': 'tree',
                'domain': [('id', 'in', batch_ids)],
                'view_id': view_id,
                'views': [[view_id, 'tree']]
            })
        return action_vals

    @api.model
    def cron_generate_ziniarasciai(self):
        current_date = datetime.utcnow()
        month_to_generate_date_from = current_date + relativedelta(months=1, day=1)
        month_to_generate_date_to = month_to_generate_date_from + relativedelta(day=31)
        date_from = month_to_generate_date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = month_to_generate_date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        ziniarastis = self.env['ziniarastis.period'].search_count([
            ('date_from', '=', date_from),
            ('date_to', '=', date_to)
        ])
        if not ziniarastis:
            ziniarastis = self.env['ziniarastis.period'].create({'date_from': date_from,
                                                                 'date_to': date_to})
            ziniarastis.generate_ziniarasciai()

    @api.model
    def get_data_for_view(self, ziniarastis_period_id, year, month, extra_domain, offset=0, limit=20):
        def _strp(date):
            return datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)

        def _strf(date):
            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        res = {
            'header_data': list(),
            'main_data': list(),
            'button_data': list(),
            'ziniarastis_period_id': False,
            'year': False,
            'month': False,
            'ziniarastis_state': False
        }

        if not ziniarastis_period_id and (not year and not month):
            return res

        if ziniarastis_period_id:
            ziniarastis_period = self.env['ziniarastis.period'].browse(ziniarastis_period_id)
        else:
            date_from = _strf(datetime(year, month, 1))
            ziniarastis_period = self.env['ziniarastis.period'].search([
                ('date_from', '>=', date_from),
            ], order='date_from asc', limit=1)
            if not ziniarastis_period:
                ziniarastis_period = self.env['ziniarastis.period'].search([
                    ('date_from', '<=', date_from),
                ], order='date_from desc', limit=1)
        if not ziniarastis_period:
            return res
        else:
            date_from = ziniarastis_period.date_from
            year, month = _strp(date_from).year, _strp(date_from).month
        date_from = ziniarastis_period.date_from
        date_to = ziniarastis_period.date_to
        date_from_dt = _strp(date_from)
        date_to_dt = _strp(date_to)
        num_of_days_in_month = date_to_dt.day

        national_holidays = self.env['sistema.iseigines'].search([
            ('date', '<=', date_to),
            ('date', '>=', date_from)
        ]).mapped('date')

        date_data = []
        date_of_day = date_from_dt
        weekends = [5, 6]
        today = _strf(datetime.utcnow())
        locale = self.env.context.get('lang') or 'lt_LT'
        while date_of_day <= date_to_dt:
            date_of_day_strf = _strf(date_of_day)
            ttyme = datetime.fromtimestamp(time.mktime(time.strptime(date_of_day_strf, "%Y-%m-%d")))
            day_string = tools.ustr(babel.dates.format_date(date=ttyme, format='EE', locale=locale))
            date_data.append({
                'date': date_of_day_strf,
                'is_national_holiday': date_of_day_strf in national_holidays,
                'is_weekend': date_of_day.weekday() in weekends,
                'is_today': date_of_day_strf == today,
                'print_str': str(date_of_day.day).zfill(2) + ', ' + day_string.capitalize() + '.'
            })
            date_of_day += relativedelta(days=1)

        ttyme = datetime.fromtimestamp(time.mktime(time.strptime(date_from, "%Y-%m-%d")))
        month_name = tools.ustr(babel.dates.format_date(date=ttyme, format='MMMM', locale=locale)).capitalize()

        header_data = {
            'number_of_days': num_of_days_in_month,
            'date_data': date_data,
            'month_name': month_name,
            'year': date_from_dt.year,
        }

        main_data, total_number_of_lines = self.env['ziniarastis.period'].get_all_data(ziniarastis_period, extra_domain, offset, limit)
        context_lang = self._context.get('lang', 'lt_LT')
        new_context = self._context.copy()
        new_context.update({'lang': context_lang})
        self = self.with_context(new_context)
        return {
            'header_data': header_data,
            'main_data': main_data,
            'button_data': ziniarastis_period.get_button_statuses(),
            'ziniarastis_period_id': ziniarastis_period.id,
            'year': year,
            'month': month,
            'ziniarastis_state': ziniarastis_period.state,
            'ziniarastis_state_title': dict(ziniarastis_period._fields['state']._description_selection(self.env)).get(ziniarastis_period.state),
            'busy': ziniarastis_period.busy,
            'line_ids': [l['id'] for l in main_data],
            'last_confirm_fail_message': ziniarastis_period.last_confirm_fail_message,
            'total_number_of_lines': total_number_of_lines,
        }

    @api.model
    def get_all_data(self, ziniarastis_period, extra_domain, offset, limit):
        if not self.env.user.is_premium_manager():
            raise exceptions.UserError(_('Neturite pakankamai teisių'))
        data = []
        if not ziniarastis_period:
            return data, 0
        domain = [('ziniarastis_period_id', '=', ziniarastis_period.id)]
        parsed_extra_domain = []
        # HACK: Parse domain to use on ziniarastis.period.line where initially this domain is on ziniarastis.period.
        # HACK: Shouldn't cause issues if custom search is disabled.
        if extra_domain and isinstance(extra_domain, list):
            for domain_el in extra_domain:
                if isinstance(domain_el, list):
                    extra_extra_domain_el = []
                    for domain_el_el in domain_el:
                        extra_extra_domain_el.append(domain_el_el.replace('related_ziniarasciai_lines.', ''))
                    if extra_extra_domain_el:
                        parsed_extra_domain.append(extra_extra_domain_el)
                else:
                    parsed_extra_domain.append(domain_el)
            domain += parsed_extra_domain
        period_lines = self.env['ziniarastis.period.line'].sudo().search(domain)
        if not period_lines:
            return data, 0
        total_number_of_lines = len(period_lines)
        period_lines = period_lines.sorted(lambda l: l.employee_id.name)[offset:offset+limit]
        date_from = ziniarastis_period.date_from
        date_to = ziniarastis_period.date_to

        self._cr.execute('''
                    SELECT
                        day.id AS id,
                        day.ziniarastis_period_line_id AS ziniarastis_period_line_id,
                        day.date AS date,
                        day.holidays_match AS holidays_match,
                        day.name AS name,
                        day.shorter_before_holidays_special as shorter_before_holidays_special
                    FROM
                        ziniarastis_day AS day
                    WHERE
                        day.ziniarastis_period_line_id IN %s
                ''', (tuple(period_lines.ids),))
        day_data = self._cr.dictfetchall()

        data_keys = [
            'id', 'days_not_worked', 'days_set', 'contract_id', 'employee_id', 'days_total', 'hours_holidays',
            'hours_night', 'hours_not_regular', 'hours_not_worked', 'hours_overtime', 'hours_watch_home',
            'hours_watch_work', 'hours_weekends', 'hours_worked', 'num_regular_work_days_contract_only',
            'num_regular_work_hours_without_holidays', 'show_warning', 'state', 'tabelio_numeris', 'name'
        ]

        period_data = {
            'date_from': date_from,
            'date_to': date_to,
            'period_state': ziniarastis_period.state
        }

        data = period_lines.read(data_keys)
        for line_data in data:
            line_data.update(period_data)
            days_data = [x for x in day_data if x['ziniarastis_period_line_id'] == line_data['id']]
            line_data['days'] = sorted(days_data, key=lambda k: k['date'])

        data = sorted(data, key=lambda k: k['employee_id'][1])
        return data, total_number_of_lines


ZiniarastisPeriod()


class ZiniarastisPeriodLine(models.Model):

    _name = 'ziniarastis.period.line'

    _sql_constraints = [('ziniarastis_period_line_period_contract_unique', 'unique(date_from, date_to, contract_id)',
                         _('Ziniarastis period cannot have more than one line for the same contract'))]

    _order = 'date_from desc, tabelio_numeris asc'

    state = fields.Selection([('draft', 'Preliminary'), ('done', 'Done')], required=True,
                             default='draft', readonly=True, copy=False)
    ziniarastis_period_id = fields.Many2one('ziniarastis.period', string='Žiniaraštis',
                                            compute='_ziniarastis_period_id', store=True)
    period_state = fields.Selection([('draft', 'Preliminary'), ('done', 'Done')], related='ziniarastis_period_id.state',
                                    readonly=True, string='Periodo būsena')
    ziniarastis_day_ids = fields.One2many('ziniarastis.day', 'ziniarastis_period_line_id', string='Dienos')
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True)
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', required=True,
                                  domain="[('employee_id', '=', employee_id)]")
    date_from = fields.Date(string='Data nuo', required=True)
    date_to = fields.Date(string='Data iki', required=True)
    job_id = fields.Many2one('hr.job', string='Pareigos', related='contract_id.job_id', store=True, readonly=True,
                             compute_sudo=True)
    tabelio_numeris = fields.Char(string='Tabelio numeris', related='employee_id.tabelio_numeris', store=True, readonly=True)
    days_total = fields.Integer(string='Dirbta dienų', compute='_compute_time_worked', store=True)
    days_set = fields.Integer(string='Dirbta dienų', compute='_compute_days_set', readonly=True, store=True)
    normal_hours_work_in_month = fields.Float(string='Nustatytas darbo valandų skaičius per mėnesį', compute='set_normal_hours_work_in_month', store=False)
    hours_worked = fields.Float(string='Dirbta valandų', compute='_compute_time_worked', store=True)
    hours_night = fields.Float(string='Dirbta naktį', compute='_compute_time_worked', store=True)
    hours_overtime = fields.Float(string='Dirbta viršvalandžių', compute='_compute_time_worked', store=True)
    hours_not_regular = fields.Float(string='Dirbta nukrypus nuo normalių darbo sąlygų',
                                     compute='_compute_time_worked', store=True)
    hours_watch_home = fields.Float(string='Budėjimas namuose', compute='_compute_time_worked', store=True)
    hours_watch_work = fields.Float(string='Budėjimas darbe', compute='_compute_time_worked', store=True)
    hours_qualification_training = fields.Float(string='Kvalifikacijos kėlimas', compute='_compute_time_worked', store=True)
    hours_weekends = fields.Float(string='Poilsio dienomis', compute='_compute_time_worked', store=True)
    hours_holidays = fields.Float(string='Švenčių dienomis', compute='_compute_time_worked', store=True)
    hours_not_worked = fields.Float(string='Neatvykimas į darbą dienų', compute='_compute_time_worked', store=True)
    days_not_worked = fields.Float(string='Neatvykimas į darbą valandų', compute='_compute_time_worked', store=True)

    time_worked_hours = fields.Integer(string='Dirbta valandų', compute='_compute_time_worked', store=False)
    time_worked_minutes = fields.Integer(string='Dirbta Minučių', compute='_compute_time_worked', store=False)
    time_night_hours = fields.Integer(string='Dirbta naktį valandų', compute='_compute_time_worked', store=False)
    time_night_minutes = fields.Integer(string='Dirbta naktį minučių', compute='_compute_time_worked', store=False)
    time_overtime_hours = fields.Integer(string='Dirbta viršvalandžių valandų', compute='_compute_time_worked',
                                         store=False)
    time_overtime_minutes = fields.Integer(string='Dirbta viršvalandžių minučių', compute='_compute_time_worked',
                                           store=False)
    time_not_regular_hours = fields.Integer(string='Dirbta nukrypus nuo normalių darbo sąlygų valandų',
                                            compute='_compute_time_worked', store=False)
    time_not_regular_minutes = fields.Integer(string='Dirbta nukrypus nuo normalių darbo sąlygų minučių',
                                              compute='_compute_time_worked', store=False)
    time_watch_home_hours = fields.Integer(string='Budėjimas namuose valandų', compute='_compute_time_worked',
                                           store=False)
    time_watch_home_minutes = fields.Integer(string='Budėjimas namuose valandų minučių',
                                             compute='_compute_time_worked', store=False)
    time_watch_work_hours = fields.Integer(string='Budėjimas darbe valandų', compute='_compute_time_worked',
                                           store=False)
    time_watch_work_minutes = fields.Integer(string='Budėjimas darbe minučių', compute='_compute_time_worked',
                                             store=False)
    time_qualification_training_hours = fields.Integer(string='Kvalifikacijos kėlimo valandų', compute='_compute_time_worked',
                                           store=False)
    time_qualification_training_minutes = fields.Integer(string='Kvalifikacijos kėlimo minučių', compute='_compute_time_worked',
                                             store=False)
    time_weekends_hours = fields.Integer(string='Poilsio dienomis valandų', compute='_compute_time_worked',
                                         store=False)
    time_weekends_minutes = fields.Integer(string='Poilsio dienomis minučių', compute='_compute_time_worked',
                                           store=False)
    time_holidays_hours = fields.Integer(string='Poilsio dienomis valandų', compute='_compute_time_worked',
                                         store=False)
    time_holidays_minutes = fields.Integer(string='Poilsio dienomis minučių', compute='_compute_time_worked',
                                           store=False)
    time_not_worked_hours = fields.Integer(string='Neatvykimas į darbą valandų', compute='_compute_time_worked', store=False)
    time_not_worked_minutes = fields.Integer(string='Neatvykimas į darbą minučių', compute='_compute_time_worked', store=False)

    name = fields.Char(string='Name', compute='get_name', store=True)
    num_regular_work_days = fields.Integer(string='Darbo dienų',
                                           help='Kiek būtų darbo dienų neatsižvelgiant į atostogas',
                                           compute='_num_regular_work_days')
    num_regular_work_hours = fields.Float(string='Darbo valandų',
                                           help='Kiek yra darbo valandų mėnesyje',
                                           compute='_num_regular_work_hours')
    num_regular_work_days_contract_only = fields.Integer(string='Darbo dienų',
                                           help='Kiek būtų darbo dienų neatsižvelgiant į atostogas, kai egzistuoja kontraktas',
                                           compute='_num_regular_work_days_contract_only', store=True)
    num_regular_work_days_by_accounting_month = fields.Integer(string='Darbo dienų',
                                                               help='Kiek būtų darbo dienų pagal buhalterio kalendorių',
                                                               compute='_num_regular_work_days_by_accounting_month')
    working_schedule_number = fields.Integer(string='Darbo grafiko numeris')
    show_warning = fields.Boolean(string='Rodyti įspėjimą', help='Ar yra nepasirašytų dokumentų už laikotarpį',
                                  compute='_show_warning')
    num_regular_work_hours_without_holidays = fields.Float(string='Darbo valandų neįskaičiavus atostogas', compute='_compute_num_regular_work_hours_without_holidays', store=True)
    payslip_ids = fields.One2many('hr.payslip', 'ziniarastis_period_line_id', string='Algalapiai')

    @api.one
    def compute_stored_fields(self):
        # Fields that are triggered in threaded calc
        self._compute_num_regular_work_hours_without_holidays()
        self._num_regular_work_days_contract_only()

    @api.one
    @api.depends('ziniarastis_day_ids.worked_time_hours', 'ziniarastis_day_ids.worked_time_minutes')
    def _compute_num_regular_work_hours_without_holidays(self):
        if self._context.get('thread_calc', False):
            return  # Skip computation in the middle of the thread, and do it afterwards
        calc_date_from = self._context.get('date_from', False) or self.date_from
        calc_date_to = self._context.get('date_to', False) or self.date_to
        appointment = self.env['hr.contract.appointment'].browse(
            self._context.get('appointment_id')) if self._context.get('appointment_id', False) else False
        contract = self.contract_id
        work_norm = self.env['hr.employee'].employee_work_norm(
            calc_date_from=calc_date_from,
            calc_date_to=calc_date_to,
            contract=contract,
            appointment=appointment,
            skip_leaves=True)
        self.num_regular_work_hours_without_holidays = work_norm['hours']

    @api.depends('ziniarastis_day_ids', 'ziniarastis_day_ids.ziniarastis_day_lines')
    def _compute_days_set(self):
        for rec in self:
            rec.days_set = len(set(rec.ziniarastis_day_ids.mapped('ziniarastis_day_lines').filtered(lambda r: r['worked_time_hours'] > 0 or r['worked_time_minutes'] > 0).mapped('date')))

    @api.multi
    def _show_warning(self):
        pass  # to be overriden

    @api.model
    def num_days_by_accounting_month(self, date_from, date_to, contract_id):
        date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        iseigines = list(self.env['sistema.iseigines'].search([('date', '>=', date_from), ('date', '<=', date_to)]).mapped('date'))
        contract_appointments = self.env['hr.contract.appointment'].search([
            ('contract_id', '=', contract_id.id),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from)
        ])
        not_included_dates = []
        # For calculating SODRA grindys, we need to skip holidays. There should be a better way to do this, but for now its ok. TODO Improve me
        if self._context.get('without_holidays', False):
            ziniarastis_period_days = self.env['ziniarastis.day'].search([
                ('contract_id', '=', contract_id.id),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('date', '>=', contract_id.date_start)
            ])
            CODES_NOT_INCLUDED = ['A', 'G', 'KA', 'KR', 'M', 'MP', 'NLL', 'MA', 'N', 'NA', 'ND', 'PV', 'TA', 'V', 'D', 'KM', 'KT', 'L', 'NN', 'NP', 'NS', 'PB', 'PK', 'PN', 'ST', 'VV']
            not_included_dates = ziniarastis_period_days.mapped('ziniarastis_day_lines').filtered(lambda l: l.code in CODES_NOT_INCLUDED).mapped('ziniarastis_id.date')
        num_days = 0
        while date_from_dt <= date_to_dt:
            appointment = contract_appointments.filtered(
                lambda r: r['date_start'] <= date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT) and (
                            not r['date_end'] or r['date_end'] >= date_from_dt.strftime(
                        tools.DEFAULT_SERVER_DATE_FORMAT)))
            weekends = [5] if appointment and appointment.schedule_template_id.six_day_work_week else [5, 6]
            the_date = date_from_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if the_date not in iseigines and date_from_dt.weekday() not in weekends and the_date not in not_included_dates:
                num_days += 1
            date_from_dt += relativedelta(days=1)
        return num_days

    @api.one
    def _num_regular_work_days_by_accounting_month(self):
        self.num_regular_work_days_by_accounting_month = self.num_days_by_accounting_month(self.date_from, self.date_to, self.contract_id)

    @api.one
    @api.depends('contract_id.date_start', 'contract_id.date_end')
    def _num_regular_work_days_contract_only(self):
        # self.num_regular_work_days_contract_only = self.env['ziniarastis.day'].search_count(
        #     [('ziniarastis_period_line_id', '=', self.id),
        #      ('not_by_schedule', '=', False),
        #      ('contract_id','!=', False)])
        if self._context.get('thread_calc', False):
            return  # Skip computation in the middle of the thread, and do it afterwards
        calc_date_from = max(self.contract_id.date_start, self.date_from)
        calc_date_to = min(self.contract_id.date_end, self.date_to) if self.contract_id.date_end else self.date_to
        contract = self.contract_id
        work_norm = self.env['hr.employee'].employee_work_norm(calc_date_from=calc_date_from, calc_date_to=calc_date_to,
                                                               contract=contract)
        self.num_regular_work_days_contract_only = work_norm['days']

    @api.one
    def _num_regular_work_days(self):
        self.num_regular_work_days = self.env['ziniarastis.day'].search_count(
            [('ziniarastis_period_line_id', '=', self.id),
             ('not_by_schedule', '=', False)])

    @api.one
    def _num_regular_work_hours(self):
        calc_date_from = self._context.get('date_from', False) or self.date_from
        calc_date_to = self._context.get('date_stop', False) or self.date_to
        appointment = self.env['hr.contract.appointment'].browse(self._context.get('appointment_id')) if self._context.get('appointment_id', False) else False
        contract = self.contract_id
        work_norm = self.env['hr.employee'].employee_work_norm(calc_date_from=calc_date_from, calc_date_to=calc_date_to, contract=contract, appointment=appointment)
        self.num_regular_work_hours = work_norm['hours']

    @api.one
    @api.depends('contract_id.name', 'date_from', 'date_to')
    def get_name(self):
        self.name = '%s žiniaraštis %s - %s' % (self.contract_id.name, self.date_from, self.date_to)

    @api.onchange('employee_id')
    def change_contract(self):
        cur_date = datetime.utcnow()
        date_from = self.date_from or (cur_date + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = self.date_to or (cur_date + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        contract = self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id),
                                                   ('date_start', '<=', date_to),
                                                   '|',
                                                       ('date_end', '>=', date_from),
                                                       ('date_end', '=', False)
                                                   ], limit=1)
        if not contract:
            contract = self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id)], limit=1)
        self.contract_id = contract.id

    @api.one
    @api.depends('date_from', 'date_to')
    def _ziniarastis_period_id(self):
        ziniarastis_period = self.env['ziniarastis.period'].search([('date_from', '=', self.date_from),
                                                                   ('date_to', '=', self.date_to)], limit=1)
        self.ziniarastis_period_id = ziniarastis_period.id or False

    @api.multi
    @api.depends('ziniarastis_day_ids.time_worked_hours', 'ziniarastis_day_ids.time_worked_minutes',
                 'ziniarastis_day_ids.time_not_worked_hours', 'ziniarastis_day_ids.time_not_worked_minutes',
                 'ziniarastis_day_ids.time_night_hours', 'ziniarastis_day_ids.time_night_minutes',
                 'ziniarastis_day_ids.time_overtime_hours', 'ziniarastis_day_ids.time_overtime_minutes',
                 'ziniarastis_day_ids.time_not_regular_hours', 'ziniarastis_day_ids.time_not_regular_minutes',
                 'ziniarastis_day_ids.time_watch_home_hours', 'ziniarastis_day_ids.time_watch_home_minutes',
                 'ziniarastis_day_ids.time_watch_work_hours', 'ziniarastis_day_ids.time_watch_work_minutes',
                 'ziniarastis_day_ids.time_qualification_training_hours',
                 'ziniarastis_day_ids.time_qualification_training_minutes',
                 'ziniarastis_day_ids.time_weekends_hours', 'ziniarastis_day_ids.time_weekends_minutes',
                 'ziniarastis_day_ids.time_holidays_hours', 'ziniarastis_day_ids.time_holidays_minutes',
                 'ziniarastis_day_ids.worked_time_hours', 'ziniarastis_day_ids.worked_time_minutes')
    def _compute_time_worked(self):
        for rec in self:
            days = rec.ziniarastis_day_ids
            time_fields = [
                'worked',
                'not_worked',
                'night',
                'overtime',
                'not_regular',
                'watch_home',
                'watch_work',
                'weekends',
                'holidays',
                'qualification_training'
            ]

            prefix = 'time_'
            hours_str = '_hours'
            minutes_str = '_minutes'

            data = {}

            for field in time_fields:
                field_formatted_str = prefix+field
                hour_field_name = field_formatted_str+hours_str
                minute_field_name = field_formatted_str+minutes_str
                worked_total = sum(d[hour_field_name] * 60 + d[minute_field_name] for d in days)
                worked_hours, worked_minutes = divmod(worked_total, 60)
                total_worked = worked_hours + float(worked_minutes) / 60.0  # P3:DivOK
                data.update({
                    hour_field_name: round(worked_hours, 2),
                    minute_field_name: round(worked_minutes, 2),
                    'hours_'+field: round(total_worked, 2)
                })

            for key, val in iteritems(data):
                rec[key] = val  # TODO maybe possible to execute singular write?

            rec.days_not_worked = len(days.filtered(lambda r: r.time_not_worked_hours or r.time_not_worked_minutes))
            rec.days_total = len(days.filtered(lambda d: not tools.float_is_zero(
                d.worked_time_hours + d.worked_time_minutes + d.time_night_hours + d.time_night_minutes +
                d.time_weekends_hours + d.time_weekends_minutes + d.time_overtime_hours + d.time_overtime_minutes +
                d.time_holidays_minutes + d.time_holidays_hours,
                precision_digits=2
            )))

    @api.multi
    def fill_with_days(self, dates=None):

        """ @dates: optional parameter to provide exactly whitch dates to create. If not provided, all days are created """

        # Creates days but does not compute their values
        dates = dates or []
        for rec in self:
            date = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            national_holidays = self.env['sistema.iseigines'].search(
                [('date', '<=', rec.date_to), ('date', '>=', rec.date_from)]).mapped('date')
            appointments = self.env['hr.contract.appointment'].search([('contract_id', '=', self.contract_id.id),
                                                                       ('date_start', '<=', date_to.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                                                                       '|',
                                                                       ('date_end', '=', False),
                                                                       ('date_end', '>=', date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))])
            business_trips = self.env['hr.holidays'].search([
                ('state', '=', 'validate'),
                ('date_from_date_format', '<=', rec.date_to),
                ('date_to_date_format', '>=', rec.date_from),
                ('holiday_status_id.kodas', '=', 'K'),
                ('employee_id', '=', rec.employee_id.id)
            ])
            all_existing_days = self.env['ziniarastis.day'].search([
                ('date', '<=', rec.date_to),
                ('date', '>=', rec.date_from),
                ('ziniarastis_period_line_id', '=', rec.id)
            ])
            day_to_create_vals = []
            while date <= date_to:
                date_str = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                if not dates or date_str in dates:
                    holidays = bool(date_str in national_holidays)
                    appointment = appointments.filtered(lambda r: r['date_start'] <= date_str and (not r['date_end'] or r['date_end'] >= date_str))
                    appointment = appointment[0] if len(appointment) > 1 else appointment
                    if not appointment:  # todo šitas naudojamas apskaičiuoti darbo dienų mėnesyje skaičių, todėl jį kažkaip reikia užpildyti
                        not_by_schedule = False
                        if appointments:
                            appointment_to_use = appointments[0] if len(appointments) > 1 else appointments
                            if appointment_to_use.schedule_template_id.fixed_attendance_ids and len(list(set(appointment_to_use.schedule_template_id.fixed_attendance_ids.mapped('dayofweek')))) > 0:
                                if holidays or str(date.weekday()) not in list(set(appointment_to_use.schedule_template_id.fixed_attendance_ids.mapped('dayofweek'))):
                                    not_by_schedule = True
                            else:
                                if holidays or date.weekday() in (5, 6):
                                    not_by_schedule = True
                        else:
                            if holidays or date.weekday() in (5, 6):
                                not_by_schedule = True
                    else:
                        not_by_schedule = not appointment.schedule_template_id.is_work_day(date_str)
                    normal_hours_work_in_day = appointment.schedule_template_id.get_regular_hours(date_str) if appointment.schedule_template_id else 0
                    business_trip = business_trips.filtered(lambda r: r['date_from_date_format'] <= date_str <= r['date_to_date_format'])
                    vals = {
                        'holiday': holidays,
                        'not_by_schedule': not_by_schedule,
                        'normal_hours_work_in_day': normal_hours_work_in_day,
                        'business_trip': bool(business_trip),
                    }
                    existing_day = all_existing_days.filtered(lambda d: d.date == date_str)
                    if not existing_day:
                        vals.update({
                            'date': date_str,
                            'ziniarastis_period_line_id': rec.id,
                            'employee_id': rec.employee_id.id,
                            'contract_id': appointment.contract_id.id if appointment else None
                        })
                        day_to_create_vals.append(vals)
                        # self.env['ziniarastis.day'].create(vals)
                    else:
                        existing_day.write(vals)
                date += timedelta(days=1)
            ids = multiple_create(self, 'ziniarastis_day', day_to_create_vals)
            day_ids = self.env['ziniarastis.day'].browse(ids)
            day_ids._compute_shorter_before_holidays_special()

    @api.multi
    def button_auto_fill_period_line(self):
        self.auto_fill_period_line()

    @api.multi
    def _get_auto_fill_data(self, dates):
        self.ensure_one()
        appointments = self.env['hr.contract.appointment'].search([('contract_id', '=', self.contract_id.id),
                                                                   ('date_start', '<=', self.date_to),
                                                                   '|',
                                                                   ('date_end', '=', False),
                                                                   ('date_end', '>=', self.date_from)])
        dates_with_appointment = set()
        full_data_hours_by_date = {}
        full_data_different_days = []
        for appointment in appointments:
            date_from, date_to = get_days_intersection((self.date_from, self.date_to),
                                                       (appointment.date_start, appointment.date_end))
            date_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            different_dates = []
            while date_dt <= date_to_dt:
                if not dates or date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT) in dates:
                    different_dates.append(date_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
                date_dt += timedelta(days=1)
            dates_with_appointment = dates_with_appointment.union(set(different_dates))
            hours_by_day = appointment.get_hours(different_dates)
            full_data_hours_by_date.update(hours_by_day)
            full_data_different_days.extend(different_dates)
        return full_data_hours_by_date, full_data_different_days, dates_with_appointment

    @api.multi
    def auto_fill_period_line(self, dates=None):
        """
            @dates: optional parameter to provide exactly which dates to create. If not provided, all days are created
        """
        if self.env.user.has_group('hr.group_hr_manager'):
            self = self.sudo()
        if not dates:
            dates = list()

        business_trip_time_marking_id = self.env.ref('l10n_lt_payroll.tabelio_zymejimas_K').id

        all_days_to_set_null = self.env['ziniarastis.day']
        lines_to_unlink = self.env['ziniarastis.day.line']
        line_values_to_create = list()

        for rec in self:
            # Determine if the line should exist
            contract = rec.contract_id
            contract_has_ended = contract.date_end and contract.date_end < rec.date_from
            contract_has_not_yet_started = contract.date_start > rec.date_to
            work_time_is_not_tracked = contract.employee_id.type in ['intern', 'mb_narys'] or \
                                       contract.is_internship_contract
            if contract_has_ended or contract_has_not_yet_started or work_time_is_not_tracked:
                rec.unlink()
                continue

            # Create day records
            rec._ziniarastis_period_id()
            rec.fill_with_days(dates=dates)

            # Get data
            full_data_hours_by_date, full_data_different_days, dates_with_appointment = rec._get_auto_fill_data(dates)

            # Get days to update
            time_register_days = rec.ziniarastis_day_ids.filtered(lambda day: day.date in full_data_different_days)

            # Add the period line days to days that should not have any day lines
            days = rec.ziniarastis_day_ids.filtered(lambda day: day.date not in list(dates_with_appointment))
            if dates:
                days = days.filtered(lambda day: day.date in dates)
            all_days_to_set_null |= days

            for day in time_register_days:
                if day.id in days.ids:
                    # Day values will be set to null
                    continue
                date = day.date

                day_lines = day.ziniarastis_day_lines

                time_marking_data_for_date = full_data_hours_by_date.get(date, dict())
                time_marking_ids_for_date = time_marking_data_for_date.keys()

                # Unlink all lines that are not in full_data_hours_by_date
                lines_to_unlink |= day_lines.filtered(lambda l: l.tabelio_zymejimas_id.id not in time_marking_ids_for_date)

                # Set business trip
                if not day.business_trip:  # Can be set from elsewhere
                    day.business_trip = business_trip_time_marking_id in time_marking_ids_for_date

                for time_marking_id in time_marking_ids_for_date:
                    hours, minutes = time_marking_data_for_date.get(time_marking_id)
                    existing_lines = day.ziniarastis_day_lines
                    existing_line = existing_lines.filtered(lambda l: l.tabelio_zymejimas_id.id == time_marking_id and
                                                                      l.id not in lines_to_unlink.ids)
                    # If an existing line exists - just update the values, otherwise - save values to create later
                    if existing_line:
                        existing_line = existing_line[0]
                        # Only write if the current values do not match new values. Saves a lot of time.
                        if tools.float_compare(existing_line.worked_time_hours, hours, precision_digits=2) != 0 or \
                            tools.float_compare(existing_line.worked_time_minutes, minutes, precision_digits=2) != 0:
                            existing_line.write({
                                'worked_time_hours': hours,
                                'worked_time_minutes': minutes
                            })
                    else:
                        line_values_to_create.append({
                            'ziniarastis_id': day.id,
                            'tabelio_zymejimas_id': time_marking_id,
                            'worked_time_hours': hours,
                            'worked_time_minutes': minutes,
                        })

            # Force update work norm
            rec._compute_num_regular_work_hours_without_holidays()

        for values in line_values_to_create:
            self.env['ziniarastis.day.line'].create(values)
        lines_to_unlink.unlink()
        all_days_to_set_null.mapped('ziniarastis_day_lines').unlink()

    @api.multi
    def check_lock_dates(self):
        bypass_lock_check = self._context.get('bypass_payroll_lock_dates') and self.env.user.id == SUPERUSER_ID
        if not bypass_lock_check:
            company = self.env.user.company_id
            lock_date = company.get_user_accounting_lock_date()
            if any(date <= lock_date for date in self.mapped('date_to')):
                raise exceptions.UserError(_('Negalima keisti būsenos žiniaraščiams, iki apskaitos užrakinimo datos '
                                             '{}').format(lock_date))

    @api.multi
    def button_done(self):
        self.check_lock_dates()
        self.write({'state': 'done'})

    @api.multi
    def confirm_selected_lines(self, ids=None):
        if not self and not ids:
            raise exceptions.UserError(_('Nepasirinkti įrašai'))
        if not self:
            self = self.browse(ids)

        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('This action can only be performed by accountants!'))
        lines = self.filtered(lambda s: s.state == 'draft')
        for ziniarastis_period in lines.mapped('ziniarastis_period_id'):
            ziniarastis_period_lines = lines.filtered(lambda l: l.ziniarastis_period_id == ziniarastis_period)
            threaded_calculation = threading.Thread(target=ziniarastis_period.thread_calc,
                                                    args=(ziniarastis_period.id, ziniarastis_period_lines.ids,))
            threaded_calculation.start()

    @api.multi
    def check_dk_constraints(self, ids=False, raise_if_successfull=True):
        if not self and not ids:
            raise exceptions.UserError(_('Nepasirinkti įrašai'))
        if not self:
            self = self.browse(ids)

        def _dt(date_obj):
            return datetime.strptime(date_obj, tools.DEFAULT_SERVER_DATE_FORMAT)

        def _strf(datetime_obj):
            return datetime_obj.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        def float_to_hrs_and_mins(total_time):
            hours, minutes = divmod(total_time * 60, 60)
            if tools.float_compare(int(round(minutes)), 60, precision_digits=3) == 0:
                minutes = 0
                hours += 1
            hours = int(hours)
            minutes = int(minutes)
            hours_minutes_formatted = ''
            if not tools.float_is_zero(hours, precision_digits=2):
                hours_minutes_formatted += str(hours) + _(' val.')
            if not tools.float_is_zero(minutes, precision_digits=2):
                hours_minutes_formatted += str(minutes) + _(' min.')
            return hours_minutes_formatted

        def format_error_tuple_to_string():
            msg = ''
            if errors:
                employees = self.env['hr.employee'].browse(set([err[0] for err in errors]))
                contracts = self.env['hr.contract'].browse(set([err[1] for err in errors]))
                empl_len = len(employees)
                empl_index = 0
                for employee in employees:
                    empl_index += 1
                    employee_contracts = contracts.filtered(lambda c: c.employee_id.id == employee.id)
                    contract_len = len(employee_contracts)
                    contract_index = 0
                    for contract in employee_contracts:
                        contract_index += 1
                        msg += _('Neatitikimai darbuotojo %s žiniaraštyje pagal %s darbo sutartį:\n') % (
                        employee.name_related, contract.name)
                        contract_errors = [err for err in errors if err[0] == employee.id and err[1] == contract.id]
                        error_types = list(set([err[2] for err in contract_errors]))
                        for err_type in error_types:
                            error_type_strings = set([err[3] for err in contract_errors if err[2] == err_type])
                            for error_type_string in error_type_strings:
                                msg += error_type_string + '\n'
                                error_type_string_errors = [err for err in contract_errors if
                                                            err[2] == err_type and err[3] == error_type_string]
                                for final_error in error_type_string_errors:
                                    msg += final_error[4] + '\n'
                                msg += '\n'
                            msg += '\n'
                        msg += '\n' if contract_index != contract_len else ''
                    msg += '\n' if empl_index != empl_len else ''
            return msg

        def objects_for_period(object, start, end):
            return object.filtered(lambda o: o.date_start <= end and (not o.date_end or o.date_end >= start))

        def check_yearly_overtime_constraints(ziniarastis_days):
            date_from = month_start
            date_to = month_end
            # P3:DivOK
            ziniarastis_days = ziniarastis_days.mapped('ziniarastis_day_lines').filtered(lambda l:
                                                                               l.tabelio_zymejimas_id.id in overtime_zymejimai and not tools.float_is_zero(
                                                                                   l.worked_time_hours + l.worked_time_minutes / 60.0,
                                                                                   precision_digits=2)).mapped('ziniarastis_id')
            if ziniarastis_days:
                while date_from <= date_to:
                    date_period_back = date_from - relativedelta(years=1)
                    days_for_check = ziniarastis_days.filtered(lambda d: _strf(date_from) >= d.date >= _strf(date_period_back))
                    lines_for_check = days_for_check.mapped('ziniarastis_day_lines')
                    overtime_lines = lines_for_check.filtered(lambda l: l.tabelio_zymejimas_id.id in overtime_zymejimai)
                    overtime_amount = sum((l.worked_time_hours + l.worked_time_minutes / 60.0) for l in overtime_lines)
                    if tools.float_compare(max_overtime_per_year, overtime_amount, precision_digits=2) < 0:
                        errors.append((
                            employee_id,
                            contract_id,
                            'yearly_overtime_constraint',
                            _('Viršytas %s viršvalandžių limitas per metus') % float_to_hrs_and_mins(max_overtime_per_year),
                            _('Laikotarpiu nuo %s iki %s nustatyta %s viršvalandžių') % (
                                _strf(date_period_back),
                                _strf(date_from),
                                float_to_hrs_and_mins(overtime_amount)
                            )
                        ))
                    date_from += relativedelta(days=1)

        def check_any_seven_days_constraints(ziniarastis_days):
            date_from = month_start
            date_to = month_end + relativedelta(days=6)
            ziniarastis_days_for_check = ziniarastis_days.filtered(lambda d: _strf(date_from) <= d.date <= _strf(date_to))
            apps = self.env['hr.contract'].browse(contract_id).appointment_ids
            apps_for_this_check = objects_for_period(apps, _strf(date_from), _strf(date_to))
            while date_from <= date_to:
                check_from = date_from - relativedelta(days=6)
                check_to = date_from
                check_from_strf = _strf(check_from)
                check_to_strf = _strf(check_to)
                period_ziniarastis_days = ziniarastis_days_for_check.filtered(lambda d: check_to_strf >= d.date >= check_from_strf)
                appointments_for_period = objects_for_period(apps_for_this_check, check_from_strf, check_to_strf)
                hours_max = 0.0
                day_lines = period_ziniarastis_days.mapped('ziniarastis_day_lines')
                regular_lines = day_lines.filtered(lambda l: l.tabelio_zymejimas_id.id in regular_zymejimai)
                overtime_lines = day_lines.filtered(lambda l: l.tabelio_zymejimas_id.id in overtime_zymejimai)
                # P3:DivOK
                regular_hours = sum((l.worked_time_hours + l.worked_time_minutes / 60.0) for l in regular_lines)
                overtime_hours = sum((l.worked_time_hours + l.worked_time_minutes / 60.0) for l in overtime_lines)
                day_check = check_from
                while day_check <= check_to:
                    day_check_strf = _strf(day_check)
                    app_for_day = objects_for_period(appointments_for_period, day_check_strf, day_check_strf)
                    if app_for_day and tools.float_compare(app_for_day.schedule_template_id.etatas, 1.0, precision_digits=2) > 0:
                        hours_max += extra_contract_hour_limit / 7.0  # P3:DivOK
                    elif app_for_day and app_for_day.schedule_template_id.template_type == 'sumine':
                        hours_max += sumine_hour_limit / 7.0  # P3:DivOK
                    else:
                        hours_max += hour_limit / 7.0  # P3:DivOK
                    day_check += relativedelta(days=1)
                if tools.float_compare(regular_hours, hours_max, precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        contract_id,
                        'seven_day_constraints',
                        _('Viršyta %s darbo norma per 7 dienas') % float_to_hrs_and_mins(round(hours_max, 3)),
                        _('Laikotarpiu nuo %s iki %s nustatyta %s') % (
                            check_from_strf,
                            check_to_strf,
                            float_to_hrs_and_mins(regular_hours)
                        )
                    ))

                if tools.float_compare(overtime_hours, overtime_hour_limit, precision_digits=2) > 0:
                    errors.append((
                        employee_id,
                        contract_id,
                        'seven_day_constraints',
                        _('Viršyta %s viršvalandžių norma per 7 dienas') % float_to_hrs_and_mins(overtime_hour_limit),
                        _('Laikotarpiu nuo %s iki %s nustatyta %s viršvalandžių') % (
                            check_from_strf,
                            check_to_strf,
                            float_to_hrs_and_mins(overtime_hours)
                        )
                    ))

                temp_check_from = check_from
                temp_check_to = check_to
                any_day_not_worked = False
                while temp_check_from <= temp_check_to:
                    date_work_day = period_ziniarastis_days.filtered(lambda d: d.date == _strf(temp_check_from))
                    date_work_day_lines = date_work_day.mapped('ziniarastis_day_lines').filtered(lambda l: l.tabelio_zymejimas_id.id in all_zymejimai)
                    # P3:DivOK
                    worked_total = sum((l.worked_time_hours + l.worked_time_minutes / 60.0) for l in date_work_day_lines)
                    if tools.float_is_zero(worked_total, precision_digits=2):
                        any_day_not_worked = True
                        break
                    temp_check_from += relativedelta(days=1)
                if not any_day_not_worked:
                    errors.append((
                        employee_id,
                        contract_id,
                        'seven_day_constraints',
                        _('Negalima dirbti daugiau nei 6 dienas iš eilės'),
                        _('Laikotarpiu nuo %s iki %s dirbta 7 dienas') % (check_from_strf, check_to_strf)
                    ))
                date_from += relativedelta(days=1)

        regular_zymejimai = [
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_NT').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DLS').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VD').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VSS').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DP').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_SNV').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_KS').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_MD').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_NDL').id
        ]

        overtime_zymejimai = [
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VD').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VSS').id,
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_SNV').id
        ]

        active_budejimas_zymejimai = [
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_BĮ').id
        ]

        passive_budejimas_zymejimai = [
            self.env.ref('l10n_lt_payroll.tabelio_zymejimas_BN').id
        ]

        all_zymejimai = regular_zymejimai + overtime_zymejimai + active_budejimas_zymejimai + passive_budejimas_zymejimai

        errors = []

        min_date_from = min(self.mapped('date_from'))
        max_date_to = max(self.mapped('date_to'))

        max_date_back = _dt(min_date_from) - relativedelta(years=1)

        max_date_back_strf = _strf(max_date_back)
        company_id = self.env.user.company_id.with_context(date=max_date_to)
        max_overtime_per_year = company_id.max_overtime_per_year
        hour_limit = company_id.max_7_day_time
        sumine_hour_limit = company_id.max_7_day_sumine_apskaita_time
        overtime_hour_limit = company_id.max_7_day_overtime_time
        extra_contract_hour_limit = company_id.max_7_day_including_extra_time
        for line in self:
            employee_id = line.employee_id.id
            contract_id = line.contract_id.id
            contract_ziniarastis_days = self.env['ziniarastis.day'].search([
                ('contract_id', '=', contract_id),
                ('date', '>=', max_date_back_strf),
                ('date', '<=', max_date_to)
            ])
            # P3:DivOK
            ziniarastis_days = contract_ziniarastis_days.mapped('ziniarastis_day_lines').filtered(lambda l:
                                                             l.tabelio_zymejimas_id.id in all_zymejimai and
                                                             not tools.float_is_zero(l.worked_time_hours + l.worked_time_minutes / 60.0, precision_digits=2)).mapped('ziniarastis_id')
            month_start = _dt(line.date_from)
            month_end = _dt(line.date_to)
            check_yearly_overtime_constraints(ziniarastis_days)
            check_any_seven_days_constraints(ziniarastis_days)

        errors = list(set(errors))
        err_msg = format_error_tuple_to_string()
        if err_msg == '' and raise_if_successfull:
            err_msg = _('Žiniaraštis atitinka pagrindinius reikalavimus')

        if err_msg != '':
            raise exceptions.UserError(err_msg)

    @api.multi
    def button_single_done(self):
        self.ensure_one()
        from_date = self.date_from
        to_date = self.date_to
        journal_id = self.env.user.company_id.salary_journal_id.id
        if not journal_id:
            raise exceptions.Warning(_('Atlyginimo žurnalas neužstatytas'))

        # self.check_dk_constraints(raise_if_successfull=False)

        payslip_run_id = self.env['hr.payslip.run'].search(
            [('ziniarastis_period_id', '=', self.ziniarastis_period_id.id)], limit=1).id

        if not payslip_run_id:
            month_mapping = {
                1: _('Sausis'),
                2: _('Vasaris'),
                3: _('Kovas'),
                4: _('Balandis'),
                5: _('Gegužė'),
                6: _('Birželis'),
                7: _('Liepa'),
                8: _('Rugpjūtis'),
                9: _('Rugsėjis'),
                10: _('Spalis'),
                11: _('Lapkritis'),
                12: _('Gruodis')
            }

            month_start_dt = datetime.strptime(from_date, tools.DEFAULT_SERVER_DATE_FORMAT)
            payslip_run_name = '{0}m. {1}'.format(
                month_start_dt.year,
                month_mapping.get(month_start_dt.month)
            )

            payslip_run_vals = {'date_start': from_date,
                                'date_end': to_date,
                                'name': payslip_run_name,
                                'ziniarastis_period_id': self.ziniarastis_period_id.id,
                                'journal_id': journal_id
                                }
            payslip_run_id = self.env['hr.payslip.run'].create(payslip_run_vals).id

        contract = self.contract_id
        employee = self.employee_id

        existing_slip = self.env['hr.payslip'].search([
            ('contract_id', '=', contract.id),
            ('date_from', '=', from_date),
            ('date_to', '=', to_date),
        ], limit=1)
        good_to_recreate = not existing_slip or existing_slip.state == 'draft'
        payslip = None
        if contract.rusis in ['voluntary_internship', 'educational_internship'] or \
                (existing_slip and existing_slip.state == 'done'):
            good_to_recreate = False
        if good_to_recreate:
            if existing_slip:
                existing_slip.unlink()

            # Instead of calling onchange_employee_id twice - better to just recompute the name
            ttyme = datetime.fromtimestamp(time.mktime(time.strptime(from_date, "%Y-%m-%d")))
            locale = self.env.context.get('lang') or 'lt_LT'
            slip_name = _('Darbo užmokestis - %s / %s') % (employee.name, tools.ustr(babel.dates.format_date(date=ttyme, format='MMMM-y', locale=locale)))

            res = {
                'employee_id': employee.id,
                'name': slip_name,
                'struct_id': contract.struct_id.id,
                'contract_id': contract.id,
                'payslip_run_id': payslip_run_id,
                'date_from': from_date,
                'date_to': to_date,
                'credit_note': False,
                'journal_id': journal_id,
                'ziniarastis_period_line_id': self.id
            }
            payslip = self.env['hr.payslip'].create(res)

        if not self._context.get('thread_calc', False):
            self.button_done()
            if good_to_recreate:
                payslip.refresh_and_recompute()

    @api.multi
    def button_cancel(self):
        self.check_lock_dates()
        rec_data = list(set([(rec.date_from, rec.date_to, rec.ziniarastis_period_id.id) for rec in self]))
        related_payslips = self.env['hr.payslip']
        for rec_data_set in rec_data:
            recs_of_rec_data_set = self.filtered(lambda r: r.date_from == rec_data_set[0] and
                                                 r.date_to == rec_data_set[1] and
                                                 r.ziniarastis_period_id.id == rec_data_set[2])
            related_payslips |= self.env['hr.payslip'].search([('date_from', '=', rec_data_set[0]),
                                                              ('date_to', '=', rec_data_set[1]),
                                                              ('contract_id', 'in', recs_of_rec_data_set.mapped('contract_id.id')),
                                                              ('payslip_run_id.ziniarastis_period_id', '=', rec_data_set[2])])
        if any(slip.state == 'done' for slip in related_payslips):
            raise exceptions.Warning(_('Negalima atšaukti žiniaraščio, jei susijęs algalapis jau patvirtintas'))
        related_payslips.atsaukti()
        related_payslips.with_context(ziniarastis_period_line_is_being_cancelled=True).unlink()
        self.write({'state': 'draft'})
        self.mapped('ziniarastis_period_id').write({'state': 'draft'})

    @api.model
    def create(self, vals):
        res = super(ZiniarastisPeriodLine, self).create(vals)
        if not self._context.get('dont_auto_fill_on_ziniarastis_period_create', False):
            res.auto_fill_period_line()
        return res

    @api.multi
    @api.constrains('date_from', 'date_to')
    def constrain_datos(self):
        for rec in self:
            date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from_dt.day != 1 or date_from_dt + relativedelta(day=31) != date_to_dt:
                raise exceptions.ValidationError(_('Periodo pradžia ir pabaiga turi sutapti su mėnesio pradžios ir '
                                                   'pabaigos datomis'))

    @api.multi
    @api.constrains('contract_id', 'date_from', 'date_to')
    def constrain_intersection(self):
        for rec in self:
            existing_line = self.env['ziniarastis.period.line'].search_count([
                ('contract_id', '=', rec.contract_id.id),
                '|', '&',
                ('date_from', '<=', rec.date_to),
                ('date_from', '>=', rec.date_from),
                '&',
                ('date_from', '<=', rec.date_from),
                ('date_to', '>=', rec.date_from),
                '|',
                ('date_from', '!=', rec.date_from),
                ('date_to', '!=', rec.date_to)
            ])
            if existing_line:
                raise exceptions.ValidationError(_('Persidengiančios eilutės.'))

    def onchange_dates_constraint(self):
        if self.date_from:
            data_nuo = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            if data_nuo != datetime(data_nuo.year, data_nuo.month, 1):
                raise exceptions.Warning(_('Periodo pradžia privalo būti mėnesio pirmoji diena'))
        if self.date_to:
            data_iki = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if data_iki != datetime(data_nuo.year, data_nuo.month,
                                    calendar.monthrange(data_nuo.year, data_nuo.month)[1]):
                raise exceptions.Warning(_('Periodo pabaiga privalo būti to paties mėnesio paskutinė diena'))

    @api.multi
    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti patvirtinto žiniaraščio.'))
        self.mapped('ziniarastis_day_ids').unlink()
        return super(ZiniarastisPeriodLine, self).unlink()

    @api.multi
    @api.constrains('employee_id', 'contract_id')
    def employee_contract_constraint(self):
        for rec in self:
            if rec.employee_id != rec.contract_id.employee_id:
                raise exceptions.ValidationError(
                    _('Kontraktas %s nepriklauso darbuotojui %s') % (rec.contract_id.name, rec.employee_id.name)
                )

    @api.model
    def get_num_work_days(self, date_from, date_to, appointment):
        if appointment.date_end:
            date_to = min(date_to, appointment.date_end)
        domain = [('not_by_shedule', '=', False),
                  ('date', '>=', max(date_from, appointment.date_start)),
                  ('date', '<=', date_to),
                  ('contract_id', '=', appointment.contract_id.id),
                  ]

        return self.env['ziniarastis.day'].search_count(domain)

    @api.one
    @api.depends('ziniarastis_day_ids.normal_hours_work_in_day')
    def set_normal_hours_work_in_month(self):
        self._cr.execute('''
        SELECT SUM(normal_hours_work_in_day) FROM ziniarastis_day
        WHERE ziniarastis_period_line_id = %s''', (self.id,))
        res = self._cr.fetchall()

        self.normal_hours_work_in_month = res[0][0]


ZiniarastisPeriodLine()


class ZiniarastisDay(models.Model):

    _name = 'ziniarastis.day'

    _order = 'employee_id, date'

    _sql_constraints = [('ziniarastis_day_line_date_unique', 'unique(ziniarastis_period_line_id, date)',
                         _('There cannot more than one ziniarastis day for the same line'))]

    def _default_ziniarastis_day_lines(self):
        # ['FD', 'DN', 'VD', 'DP']
        line_1 = {'tabelio_zymejimas_id': self.env.ref('l10n_lt_payroll.tabelio_zymejimas_FD')}
        # line_2 = {'tabelio_zymejimas_id': self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DN')}
        # line_3 = {'tabelio_zymejimas_id': self.env.ref('l10n_lt_payroll.tabelio_zymejimas_VD')}
        # line_4 = {'tabelio_zymejimas_id': self.env.ref('l10n_lt_payroll.tabelio_zymejimas_DP')}
        return [(0, 0, line_1)]

    ziniarastis_period_line_id = fields.Many2one('ziniarastis.period.line', required=True, ondelete='cascade')
    ziniarastis_period_id = fields.Many2one('ziniarastis.period', related='ziniarastis_period_line_id.ziniarastis_period_id',
                                            store=True, readonly=True, compute_sudo=True)
    state = fields.Selection([('draft', 'Preliminary'), ('done', 'Done')],
                             related='ziniarastis_period_line_id.state', readonly=True, store=True, compute_sudo=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', related='ziniarastis_period_line_id.employee_id',
                                  store=True, readonly=True, compute_sudo=True)
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', compute='_contract_id', store=True)
    date = fields.Date(string='Data', required=True, readonly=True)
    ziniarastis_day_lines = fields.One2many('ziniarastis.day.line', 'ziniarastis_id',
                                            default=_default_ziniarastis_day_lines)
    worked_time_hours = fields.Integer(string='Darbo valandos', compute='_worked_times', store=True)
    worked_time_minutes = fields.Integer(string='Darbo minutės', compute='_worked_times', store=True)
    name = fields.Char(compute='get_name', store=True)
    not_by_schedule = fields.Boolean(string='Ne pagal grafiką', states={'done': [('readonly', True)]})
    holiday = fields.Boolean(string='Šventinė diena', states={'done': [('readonly', True)]})
    business_trip = fields.Boolean(string='Komandiruotė', states={'done': [('readonly', True)]})

    time_worked_hours = fields.Integer(string='Dirbta valandų', compute='_compute_time_worked', store=True)
    time_worked_minutes = fields.Integer(string='Dirbta Minučių', compute='_compute_time_worked', store=True)
    time_night_hours = fields.Integer(string='Dirbta naktį valandų', compute='_compute_time_worked', store=True)
    time_night_minutes = fields.Integer(string='Dirbta naktį minučių', compute='_compute_time_worked', store=True)
    time_overtime_hours = fields.Integer(string='Dirbta viršvalandžių valandų', compute='_compute_time_worked',
                                         store=True)
    time_overtime_minutes = fields.Integer(string='Dirbta viršvalandžių minučių', compute='_compute_time_worked',
                                           store=True)
    time_not_regular_hours = fields.Integer(string='Dirbta nukrypus nuo normalių darbo sąlygų valandų',
                                            compute='_compute_time_worked', store=True)
    time_not_regular_minutes = fields.Integer(string='Dirbta nukrypus nuo normalių darbo sąlygų minučių',
                                              compute='_compute_time_worked', store=True)
    time_watch_home_hours = fields.Integer(string='Budėjimas namuose valandų', compute='_compute_time_worked',
                                           store=True)
    time_watch_home_minutes = fields.Integer(string='Budėjimas namuose valandų minučių',
                                             compute='_compute_time_worked', store=True)
    time_watch_work_hours = fields.Integer(string='Budėjimas darbe valandų', compute='_compute_time_worked',
                                           store=True)
    time_watch_work_minutes = fields.Integer(string='Budėjimas darbe minučių', compute='_compute_time_worked',
                                             store=True)
    time_qualification_training_hours = fields.Integer(string='Kvalifikacijos kėlimo valandų', compute='_compute_time_worked',
                                           store=True)
    time_qualification_training_minutes = fields.Integer(string='Kvalifikacijos kėlimo minučių', compute='_compute_time_worked',
                                             store=True)
    time_holidays_hours = fields.Integer(string='Švenčių dienomis valandų', compute='_compute_time_worked', store=True)
    time_holidays_minutes = fields.Integer(string='Švenčių dienomis minučių', compute='_compute_time_worked', store=True)

    time_weekends_hours = fields.Integer(string='Poilsio dienomis valandų', compute='_time_poilsis2', store=True)
    time_weekends_minutes = fields.Integer(string='Poilsio dienomis minučių', compute='_time_poilsis2', store=True)
    time_not_worked_hours = fields.Integer(string='Nedirbta valandų', compute='_compute_time_not_worked', store=True)
    time_not_worked_minutes = fields.Integer(string='Nedirbta minučių', compute='_compute_time_not_worked', store=True)
    normal_hours_work_in_day = fields.Float(string='Nustatytas darbo valandų skaičius')
    report_name = fields.Char(string='Report name', compute='_report_name')

    default_fd_value = fields.Float(string='FD vertė', store=False)

    holidays_match = fields.Boolean(string='Atostogos sutampa', default=True, store=True, readonly=True, compute='_check_ziniarastis_day_holiday_match')

    shorter_before_holidays_special = fields.Boolean(compute='_compute_shorter_before_holidays_special', store=True)

    @api.one
    @api.depends('date', 'contract_id')
    def _compute_shorter_before_holidays_special(self):
        if self.contract_id:
            appointment_id = self.contract_id.with_context(date=self.date).appointment_id
            if appointment_id and appointment_id.use_hours_for_wage_calculations:
                tomorrows_date = (datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)+relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                next_day_holiday = self.env['sistema.iseigines'].search([('date', '=', tomorrows_date)])
                if next_day_holiday:
                    self.shorter_before_holidays_special = True

    @api.multi
    @api.depends('ziniarastis_day_lines.code', 'date', 'business_trip')
    def _check_ziniarastis_day_holiday_match(self):
        if not self:
            return
        CODES_HOLIDAYS = ['A', 'G', 'KA', 'KR', 'M', 'MP', 'NLL', 'MA', 'N', 'NA', 'ND', 'P', 'PV', 'TA', 'V']
        CODES_ABSENCE = ['KM', 'KT', 'L', 'NN', 'NP', 'NS', 'PB', 'PK', 'PN', 'ST', 'VV', 'N', 'KV', 'KVN']
        codes_to_check = CODES_HOLIDAYS + CODES_ABSENCE
        for day in self:
            day.holidays_match = True
        date_from = min(self.mapped('date'))
        date_to = max(self.mapped('date'))
        holidays = self.env['hr.holidays'].search([('state', '=', 'validate'),
                                                   ('date_from', '<=', date_to),
                                                   ('date_to', '>=', date_from)
                                                   ])
        days_to_check = self.mapped('ziniarastis_day_lines').filtered(lambda r: r['tabelio_zymejimas_id']['code'] in codes_to_check).mapped('ziniarastis_id')
        days_to_check |= self.filtered(lambda d: not d.ziniarastis_day_lines)
        for day in days_to_check:
            day_holidays = holidays.filtered(lambda r: r['employee_id']['id'] == day.employee_id.id and
                                                       r['date_from'].split(' ')[0] <= day.date <=
                                                       r['date_to'].split(' ')[0])
            day_holiday_codes = day_holidays.mapped('holiday_status_id.tabelio_zymejimas_id.code')
            day_codes = day.mapped('ziniarastis_day_lines.tabelio_zymejimas_id').filtered(lambda r: r['code'] in codes_to_check).mapped('code')
            day.holidays_match = not (any(code not in day_holiday_codes for code in day_codes) or (not day_codes and day_holiday_codes))

        work_days = self.mapped('ziniarastis_day_lines').filtered(
            lambda r: r['ziniarastis_id'] not in days_to_check).mapped('ziniarastis_id')
        for day in work_days:
            day_holidays = holidays.filtered(
                lambda r: r['employee_id']['id'] == day.employee_id.id and r['date_from'].split(' ')[0] <= day.date and
                          r['date_to'].split(' ')[0] >= day.date)
            if day_holidays:
                day_holiday_codes = day_holidays.mapped('holiday_status_id.tabelio_zymejimas_id.code')
                if 'K' not in day_holiday_codes:
                    day_codes = day.mapped('ziniarastis_day_lines.tabelio_zymejimas_id.code')
                    day.holidays_match = False if any(code not in day_codes for code in day_holiday_codes) else True
                else:
                    day.holidays_match = False if not day.business_trip else True

    @api.constrains('ziniarastis_day_lines')
    def _constrain_ziniarastis_day_line_holidays(self):
        ignored_holiday_statuses = [
            self.env.ref('hr_holidays.holiday_status_MP'),
            self.env.ref('hr_holidays.holiday_status_NLL'),
            self.env.ref('hr_holidays.holiday_status_PN')
        ]
        for rec in self:
            schedule_codes = rec.mapped('ziniarastis_day_lines.tabelio_zymejimas_id')
            if len(schedule_codes) > 1:
                day_holiday_statuses = schedule_codes.mapped('holiday_status_ids')
                problematic_holiday_statuses = [
                    status for status in day_holiday_statuses if status not in ignored_holiday_statuses
                ]
                if problematic_holiday_statuses:
                    raise exceptions.UserError(_('Diena negali turėti ir atostogų ir darbo laiko'))


    @api.onchange('default_fd_value')
    def _change_ziniarastis_days_lines(self):
        if self.not_by_schedule or self.holiday:
            target_code = 'DP'
        else:
            target_code = 'FD'
        zym_id = self.env['tabelio.zymejimas'].search([('code', '=', target_code)], limit=1)
        if not zym_id:
            return
        line_id = self.ziniarastis_day_lines.filtered(lambda r: r.tabelio_zymejimas_id.code == target_code)
        if not line_id:
            self.ziniarastis_day_lines |= self.ziniarastis_day_lines.new({'tabelio_zymejimas_id': zym_id.id})
        if len(line_id) == 1:
            reg_hours, reg_minutes = divmod(self.default_fd_value*60, 60)
            day_line = {
                'tabelio_zymejimas_id': zym_id.id,
                'worked_time_hours': int(round(reg_hours)),
                'worked_time_minutes': int(round(reg_minutes)),
            }
            line_id.update(day_line)

    @api.one
    def _report_name(self):
        hol_codes = ['A']
        def key_func(code):
            if code == 'FD':
                return ''
            else:
                return code
        amount_by_code_minutes = {}
        for line in self.ziniarastis_day_lines:
            code = line.code
            if code not in amount_by_code_minutes:
                amount_by_code_minutes[code] = 0
            amount_by_code_minutes[code] += line.worked_time_hours * 60 + line.worked_time_minutes
        report_name = ''
        codes = amount_by_code_minutes.keys()
        codes.sort(key=key_func)
        for code in codes:
            if amount_by_code_minutes[code] == 0:
                if code in hol_codes:
                    report_name += code + ' '
                continue
            time_hours = float(amount_by_code_minutes[code]) / 60.0  # P3:DivOK
            time_hours_rounded = tools.float_round(time_hours, precision_digits=2)
            report_name += code + ' ' + format(time_hours_rounded, 'g') + ', '
        report_name = report_name.rstrip(', ')
        self.report_name = report_name

    @api.multi
    @api.depends('not_by_schedule', 'holiday', 'ziniarastis_day_lines.worked_time_hours',
                 'ziniarastis_day_lines.worked_time_minutes', 'ziniarastis_day_lines.code')
    def _time_poilsis2(self):
        for rec in self:
            if rec.holiday or not rec.not_by_schedule:
                rec.time_weekends_hours = 0
                rec.time_weekends_minutes = 0
            else:
                day_lines = rec.ziniarastis_day_lines.filtered(lambda r: r.code == 'DP')
                num_hours = sum(day_lines.mapped('worked_time_hours'))
                num_minutes = sum(day_lines.mapped('worked_time_minutes'))
                tot_hours = num_hours + num_minutes // 60  # P3:DivOK
                tot_minutes = num_minutes % 60
                rec.time_weekends_hours = tot_hours
                rec.time_weekends_minutes = tot_minutes

    @api.multi
    @api.depends('ziniarastis_day_lines.code', 'ziniarastis_day_lines.worked_time_hours',
                 'ziniarastis_day_lines.worked_time_minutes')
    def _compute_time_worked(self):
        codes_by_fields = {
            'time_worked': ['FD', 'NT', 'DLS'],
            'time_night': ['DN', 'SNV'],
            'time_holidays': ['VSS'],
            'time_overtime': ['VD', 'VDN'],
            'time_not_regular': ['KS'],
            'time_weekends': ['DP'],
            'time_watch_home': ['BN'],
            'time_watch_work': ['BĮ'],
            'time_qualification_training': ['KV', 'KVN'],
        }
        day_fields = codes_by_fields.keys()
        all_codes = []
        for ziniarastis_day in self:
            day_lines = ziniarastis_day.mapped('ziniarastis_day_lines')
            for day_field in day_fields:
                codes = codes_by_fields.get(day_field, [])
                all_codes += codes
                lines = day_lines.filtered(lambda l: l.code in codes)
                time_in_minutes = sum(lines.mapped('worked_time_hours') * 60) + sum(lines.mapped('worked_time_minutes'))
                hours_field = day_field + '_hours'
                minutes_field = day_field + '_minutes'
                setattr(ziniarastis_day, hours_field, time_in_minutes // 60)  # P3:DivOK
                setattr(ziniarastis_day, minutes_field, time_in_minutes % 60)
            # Set the total time worked
            lines = day_lines.filtered(lambda l: l.code in all_codes)
            time_in_minutes = sum(lines.mapped('worked_time_hours') * 60) + sum(lines.mapped('worked_time_minutes'))
            setattr(ziniarastis_day, 'time_worked_hours', time_in_minutes // 60)  # P3:DivOK
            setattr(ziniarastis_day, 'time_worked_minutes', time_in_minutes % 60)

    @api.multi
    @api.depends('ziniarastis_period_line_id.contract_id.date_start', 'ziniarastis_period_line_id.contract_id.date_end',
                 'date', 'employee_id.country_id')
    def _contract_id(self):
        for rec in self:
            date = rec.date
            contract = rec.ziniarastis_period_line_id.contract_id
            if contract and date:
                contract_date_start = contract.date_start
                contract_date_end = contract.date_end
                if date >= contract_date_start and (not contract_date_end or date <= contract_date_end):
                    rec.contract_id = contract.id
                else:
                    rec.contract_id = False
            else:
                rec.contract_id = False

    @api.multi
    @api.depends('ziniarastis_day_lines.worked_time_hours', 'ziniarastis_day_lines.worked_time_minutes')
    def _worked_times(self):
        codes = PAYROLL_CODES['REGULAR'] + PAYROLL_CODES['SUMINE'] + PAYROLL_CODES['OUT_OF_OFFICE']
        for rec in self:
            lines = rec.ziniarastis_day_lines.filtered(lambda l: l.code in codes)
            total_time_minutes = sum(lines.mapped('worked_time_minutes')) + sum(lines.mapped('worked_time_hours')) * 60
            worked_hours = total_time_minutes // 60  # P3:DivOK
            worked_minutes = total_time_minutes % 60
            rec.worked_time_hours = worked_hours
            rec.worked_time_minutes = worked_minutes

    @api.multi
    @api.depends('ziniarastis_day_lines.code', 'ziniarastis_day_lines.worked_time_hours',
                 'ziniarastis_day_lines.worked_time_minutes', 'business_trip')
    def get_name(self):
        hol_codes = self.env['tabelio.zymejimas'].search([('is_holidays', '=', True)]).mapped('code')
        def key_func(code):
            if code == 'FD':
                return ''
            else:
                return code
        for rec in self:
            amount_by_code_minutes = {}
            for line in rec.ziniarastis_day_lines:
                code = line.code
                if code not in amount_by_code_minutes:
                    amount_by_code_minutes[code] = 0
                amount_by_code_minutes[code] += line.worked_time_hours * 60 + line.worked_time_minutes
            codes = amount_by_code_minutes.keys()
            codes.sort(key=key_func)
            name = ''
            for code in codes:
                if amount_by_code_minutes[code] == 0:
                    if code in hol_codes:
                        name += code + ' '
                    continue
                time_hours = float(amount_by_code_minutes[code]) / 60.0  # P3:DivOK
                time_hours_rounded = tools.float_round(time_hours, precision_digits=2)
                if name != '':
                    name += '; '
                name += code + ' ' + format(time_hours_rounded, 'g')
            name = name.rstrip(' ')
            if name == '':
                name = '0'
            if rec.business_trip:
                name += '; (K)'
            rec.name = name

    @api.depends('ziniarastis_day_lines.code', 'ziniarastis_day_lines.worked_time_hours',
                 'ziniarastis_day_lines.worked_time_minutes')
    def _compute_time_not_worked(self):
        for rec in self:
            related_lines = rec.ziniarastis_day_lines.filtered(lambda r: r.code in NEATVYKIMAI_BE_K)
            total_minutes = 60 * sum(related_lines.mapped('worked_time_hours')) + sum(related_lines.mapped('worked_time_minutes'))
            res_hours = total_minutes // 60  # P3:DivOK
            res_minutes = total_minutes % 60
            rec.time_not_worked_hours = res_hours
            rec.time_not_worked_minutes = res_minutes

    @api.multi
    @api.constrains('worked_time_hours')
    def _worked_time_less_24h(self):
        for rec in self:
            # P3:DivOK
            if rec.worked_time_hours < 0 or rec.worked_time_hours + float(rec.worked_time_minutes) / 60.0 > 24:
                raise exceptions.ValidationError(_('Darbo laikas per dieną negali viršyti 24 val.'))

    @api.multi
    @api.constrains('worked_time_minutes')
    def _worked_time_less_60m(self):
        for rec in self:
            if rec.worked_time_minutes < 0 or rec.worked_time_minutes >= 60:
                raise exceptions.ValidationError(_('Minučių skaičius negali būti didesnis už 60'))

    @api.multi
    def save(self):
        return True

    @api.model
    def get_wizard_view_id(self):
        return self.env.ref('l10n_lt_payroll.ziniarastis_day_form_wizard').id

    @api.multi
    @api.constrains('date')
    def unique_dates(self):
        for rec in self:
            if self.env['ziniarastis.day'].search([('ziniarastis_period_line_id', '=', rec.ziniarastis_period_line_id.id),
                                                   ('date', '=', rec.date),
                                                   ('id', '!=', rec.id),
                                                   ]):
                raise exceptions.Warning(_('Ziniarastis days dublicate. Please contact the system administrator.'))

    @api.multi
    def unlink(self):
        if any(zd.state == 'done' for zd in self):
            raise exceptions.UserError(_('Negalima ištrinti patvirtinto žiniaraščio.'))
        self.mapped('ziniarastis_day_lines').unlink()
        return super(ZiniarastisDay, self).unlink()

    @api.model
    def set_marked_values(self, code, data_ids):
        if not code or not data_ids:
            return False
        err_msg = _('Nenumatyta sistemos klaida, prašome perkrauti puslapį, jei problema kartosis - kreipkitės į sistemos administratorių.')
        err_raise = False
        day_ids = []
        try:
            code = str(code)
            if code not in ['FD1', 'FD2', 'FD3', 'FD4', 'FD5', 'FD6', 'FD7', 'FD8', 'FD9', 'FD10', 'VD1', 'VD2', 'VD3',
                            'VD4', 'A', 'K', 'L', 'M', 'NA', 'ND', 'NS', 'P', 'S', 'DEL']:
                err_raise = True
            for data_id in data_ids:
                day_ids.append(int(data_id))
        except:
            err_raise = True
        if err_raise:
            raise exceptions.UserError(err_msg)

        days = self.browse(day_ids)
        if days and 'done' in days.mapped('state'):
            raise exceptions.UserError(_('Jūsų pasirinkime yra įrašų, kurie jau patvirtinti'))
        if code in ['FD1', 'FD2', 'FD3', 'FD4', 'FD5', 'FD6', 'FD7', 'FD8', 'FD9', 'FD10', 'VD1', 'VD2', 'VD3', 'VD4']:
            amount_hours = int(code[2:])
            zymejimas_str = 'l10n_lt_payroll.tabelio_zymejimas_' + code[:2]
            for day in days:
                vals = {'ziniarastis_id': day.id,
                        'tabelio_zymejimas_id': self.env.ref(zymejimas_str).id,
                        'worked_time_hours': amount_hours,
                        'worked_time_minutes': 0.0,
                        }
                if code[:-1] not in ['VD', 'VDN']:
                    day.mapped('ziniarastis_day_lines').unlink()
                else:
                    day.mapped('ziniarastis_day_lines').filtered(lambda l: l.code in ['VD', 'VDN']).unlink()
                self.env['ziniarastis.day.line'].create(vals)
        elif code in ['A', 'M', 'NA', 'ND', 'NS', 'L', 'P']:
            amount_hours = 1.0
            zymejimas_str = 'l10n_lt_payroll.tabelio_zymejimas_' + code
            for day in days:
                vals = {'ziniarastis_id': day.id,
                        'tabelio_zymejimas_id': self.env.ref(zymejimas_str).id,
                        'worked_time_hours': amount_hours,
                        'worked_time_minutes': 0.0,
                        }
                day.mapped('ziniarastis_day_lines').unlink()
                self.env['ziniarastis.day.line'].create(vals)
        elif code == 'K':
            value = True
            if any(day.business_trip for day in days):
                value = False
            for day in days:
                day.write({'business_trip': value})
        # elif code == 'S':
        #     value = True
        #     if any(day.holiday for day in days):
        #         value = False
        #     for day in days:
        #         day.write({'holiday': value})
        #     day.mapped('ziniarastis_day_lines').unlink() #TODO SHOULD WE UNLINK ALL LINES?
        elif code == 'DEL':
            days.mapped('ziniarastis_day_lines').unlink()
        else:
            raise exceptions.UserError(err_msg)
        return True


ZiniarastisDay()


class ZiniarastisDayLine(models.Model):

    _name = 'ziniarastis.day.line'

    _order = 'worked_time_hours desc, worked_time_minutes desc'

    _sql_constraints = [('ziniarastis_day_zymejimas_unique', 'unique(ziniarastis_id, tabelio_zymejimas_id)',
                         _('There cannot be two lines with the same code'))]

    state = fields.Selection([('draft', 'Preliminary'), ('done', 'Done')],
                             related='ziniarastis_period_line_id.state',
                             readonly=True, store=True, compute_sudo=True)
    ziniarastis_id = fields.Many2one('ziniarastis.day', required=True, ondelete='cascade')
    ziniarastis_period_line_id = fields.Many2one('ziniarastis.period.line', related='ziniarastis_id.ziniarastis_period_line_id',
                                                 readonly=True, compute_sudo=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', related='ziniarastis_id.employee_id',
                                  readonly=True, compute_sudo=True)
    contract_id = fields.Many2one('hr.contract', string='Kontraktas', related='ziniarastis_id.contract_id',
                                  readonly=True, compute_sudo=True)
    date = fields.Date(string='Data', related='ziniarastis_id.date', store=True, readonly=True, compute_sudo=True)
    tabelio_zymejimas_id = fields.Many2one('tabelio.zymejimas', string='Žymėjimas', required=True,
                                           states={'done': [('readonly', True)]})
    worked_time_hours = fields.Integer(string='Darbo valandos', states={'done': [('readonly', True)]})
    worked_time_minutes = fields.Integer(string='Darbo minutės', states={'done': [('readonly', True)]})
    code = fields.Char(string='Kodas', related='tabelio_zymejimas_id.code', store=True, readonly=True, compute_sudo=True)
    total_worked_time_in_hours = fields.Float(string='Total worked time', compute='_compute_total_worked_time_in_hours')

    @api.multi
    @api.depends('worked_time_hours', 'worked_time_minutes')
    def _compute_total_worked_time_in_hours(self):
        for rec in self:
            # P3:DivOK
            rec.total_worked_time_in_hours = rec.worked_time_hours + rec.worked_time_minutes / 60.0

    @api.multi
    @api.constrains('worked_time_hours')
    def _worked_time_less_24h(self):
        for rec in self:
            # P3:DivOK
            if rec.worked_time_hours < 0 or rec.worked_time_hours + float(rec.worked_time_minutes)/60.0 > 24:
                raise exceptions.ValidationError(_('Darbo laikas per dieną negali viršyti 24 val.'))

    @api.multi
    @api.constrains('worked_time_minutes')
    def _worked_time_less_60m(self):
        for rec in self:
            if rec.worked_time_minutes < 0 or rec.worked_time_minutes >= 60:
                raise exceptions.ValidationError(_('Minučių skaičius negali būti didesnis už 60'))

    @api.multi
    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti patvirtinto žiniaraščio.'))
        return super(ZiniarastisDayLine, self).unlink()


ZiniarastisDayLine()


class TabelioZymejimas(models.Model):

    _name = 'tabelio.zymejimas'

    _sql_constraints = [('tabelio_zymejimas_code', 'unique(code)', _('There cannot be duplicate tabelio kodai.'))]

    code = fields.Char(string='Kodas', required=True)
    name = fields.Char(string='Pavadinimas', required=True)
    holiday_status_ids = fields.One2many('hr.holidays.status', 'tabelio_zymejimas_id')
    # is_holidays = fields.Boolean(compute='_is_holidays', store=True)
    active = fields.Boolean(string='Boolean', readonly=True, default=True)
    is_holidays = fields.Boolean(string='Žymi neatvykimą')

    # @api.multi
    # @api.depends('holiday_status_ids')
    # def _is_holidays(self):
    #     for rec in self:
    #         if rec.holiday_status_ids:
    #             rec.is_holidays = True
    #         else:
    #             rec.is_holidays = False

    @api.multi
    def name_get(self):
        return [(rec.id, '[%s] %s' % (rec.code, rec.name)) for rec in self]

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        args = list(args or [])
        if name:
            ids = self.search(['|', ('name', operator, name), ('code', operator, name)] + args, limit=limit)
        else:
            ids = self.search(args, limit=limit)
        return ids.name_get()


TabelioZymejimas()


class HrHolidayStatus(models.Model):

    _inherit = 'hr.holidays.status'

    tabelio_zymejimas_id = fields.Many2one('tabelio.zymejimas', string='Tabelio žymėjimas')
    is_holidays = fields.Boolean(string='Žymi neatvykimą', related='tabelio_zymejimas_id.is_holidays', store=True)


HrHolidayStatus()


class HrContract(models.Model):

    _inherit = 'hr.contract'

    working_schedule_number = fields.Integer(string='Darbo grafiko numeris')

    @api.multi
    def create_ziniarastis(self):
        for contract in self:
            date_from = contract.date_start
            date_to = contract.date_end
            domain = [('date_to', '>=', date_from)]
            if date_to:
                domain.append(('date_from', '<=', date_to))
            existing_ziniarasciai = self.env['ziniarastis.period'].search(domain)
            for ziniarastis_period in existing_ziniarasciai:
                if contract.id not in ziniarastis_period.mapped('related_ziniarasciai_lines.contract_id.id'):
                    line_vals = {'date_from': ziniarastis_period.date_from,
                                 'date_to': ziniarastis_period.date_to,
                                 'ziniarastis_period_id': ziniarastis_period.id,
                                 'contract_id': contract.id,
                                 'employee_id': contract.employee_id.id
                                 }
                    new_line = self.env['ziniarastis.period.line'].create(line_vals)
                    new_line.auto_fill_period_line()

    @api.multi
    def unlink(self):
        self.env['ziniarastis.period.line'].search([('contract_id', 'in', self.ids)]).unlink()
        return super(HrContract, self).unlink()


HrContract()


class HrPayslipRun(models.Model):

    _inherit = 'hr.payslip.run'

    ziniarastis_period_id = fields.Many2one('ziniarastis.period', string='Susijęs žiniaraštis')


HrPayslipRun()


class HrContractAppointment(models.Model):

    _inherit = 'hr.contract.appointment'

    @api.model
    def cron_assign_ziniarastis_to_appointments(self):
        relevant_ziniarastis_periods = self.env['ziniarastis.period'].search([('state', '=', 'draft')])
        relevant_ziniarastis_periods = relevant_ziniarastis_periods.filtered(lambda z: not z.payroll_id.busy)
        for ziniarastis_period in relevant_ziniarastis_periods:
            assigned_contract_ids = ziniarastis_period.mapped('related_ziniarasciai_lines.contract_id.id')
            unassigned_appointments = self.search([('date_start', '<=', ziniarastis_period.date_to),
                                                   '|', ('date_end', '=', False),
                                                   ('date_end', '>=', ziniarastis_period.date_from),
                                                   ('contract_id', 'not in', assigned_contract_ids)])
            for unassigned_appointment in unassigned_appointments:
                unassigned_appointment.recalculate_ziniarastis()
                self._cr.commit()

    @api.one
    def recalculate_ziniarastis(self):
        contract_id = self.contract_id.id
        date_from = self.date_start
        date_to = self.date_end
        if date_to:
            domain = ['|',
                          '&',
                              ('date_from', '>=', date_from),
                              ('date_from', '<=', date_to),
                          '&',
                              ('date_to', '>=', date_from),
                              ('date_to', '<=', date_to),
                      ]
        else:
            domain = [('date_to', '>=', date_from)]
        domain.extend([('state', '=', 'draft')])
        ziniarasciai_periods = self.env['ziniarastis.period'].search(domain)
        for zin_period in ziniarasciai_periods:
            existing_period_line = self.env['ziniarastis.period.line'].search(
                [('date_from', '=', zin_period.date_from),
                 ('date_to', '=', zin_period.date_to),
                 ('contract_id', '=', contract_id)], limit=1)
            existing_period_line._ziniarastis_period_id()
            if not existing_period_line:
                line_vals = {'date_from': zin_period.date_from,
                             'date_to': zin_period.date_to,
                             'ziniarastis_period_id': zin_period.id,
                             'contract_id': contract_id,
                             'employee_id': self.employee_id.id,
                             }
                self.env['ziniarastis.period.line'].create(line_vals)
            # else:
            #     existing_period_line.auto_fill_period_line()
            # Why auto fill if it already exists, values might be already set??

    @api.multi
    def get_hours(self, dates):
        """
            returns dict {date: {zymejimas_id: (hour, minutes)}}
        """
        schedule_template = self.schedule_template_id
        actual_hours = schedule_template.get_actual_hours(dates)
        if len(self) == 1:
            return actual_hours.get(schedule_template.id, {})
        return actual_hours


HrContractAppointment()


class ActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(selection_add=[('ziniarastis', 'Žiniaraštis')])


ActWindowView()


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('ziniarastis', 'Žiniaraštis')])


IrUiView()