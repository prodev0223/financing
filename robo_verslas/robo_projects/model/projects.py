# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from six import iteritems
import calendar


class Employee(models.Model):

    _inherit = 'hr.employee'

    timesheet_cost = fields.Float(related='address_home_id.timesheet_cost', store=True,
                                  help='Analitinio žinaraščio valandos kaina, kai nėra algalapių.',
                                  groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,"
                                         "robo_basic.group_robo_hr_manager")
    job_code = fields.Char(string='Pareigų kodas')

    @api.one
    def _set_robo_access(self):
        super(Employee, self)._set_robo_access()
        if self.user_has_hr_management_rights() and self.sudo().user_id:
            self.sudo().user_id.write({
                'groups_id': [(4, self.env.ref('project.group_project_user').id)]
            })
    # @api.one
    # @api.depends('slip_ids', 'contract_ids.wage', 'contract_ids.date_start', 'contract_ids.date_end')
    # def _compute_timesheet_cost(self):
    #     payslip_pool = self.env['hr.payslip']
    #     vdu = 0.0
    #     today = datetime.today()
    #     first = today.replace(day=1)
    #     lastMonth_end = first - timedelta(days=1)
    #     lastMonth_start = lastMonth_end.replace(day=1)
    #
    #     algalapiai = payslip_pool.search(
    #         [('employee_id', '=', self.id), ('date_from', '<=', lastMonth_end)]).sorted(lambda r: r.date_from,
    #                                                                                                  reverse=True)
    #     if algalapiai and algalapiai[0].vdu:
    #         algalapis = algalapiai[0]
    #         vdu = (algalapis.vdu * 1.3118) / 8.0
    #     else:
    #         contract = self.contract_id
    #         total_number_of_hours = 0  # month_work_days[0]['number_of_hours']
    #         day_lines = payslip_pool.get_worked_day_lines([contract.id],
    #                                                       lastMonth_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
    #                                                       lastMonth_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
    #         if day_lines and tools.float_compare(day_lines[0]['number_of_hours'], 0, precision_digits=2) > 0:
    #             total_number_of_hours += day_lines[0]['number_of_hours']
    #             vdu = ((contract.wage * 1.3118) / day_lines[0]['number_of_hours'])
    #         else:
    #             vdu = 0
    #     # if self.id == 2:
    #     #     raise exceptions.Warning('contract: %s' %vdu)
    #     self.timesheet_cost = vdu


Employee()


class TimesheetSheet(models.Model):

    _inherit = 'hr_timesheet_sheet.sheet'

    def _months_filter(self):
        cdate = datetime.now() - relativedelta(months=15)  #FIXME: why 15?
        filter = []
        for i in range(0, 25):  #FIXME: What's '25'? Where does it come from?
            search = str(cdate.year) + str(cdate.month).zfill(2)
            val = self.env['months'].search([('code', '=', search)], limit=1)
            if val:
                filter.append(val.id)
            cdate = cdate + relativedelta(months=1)
        return filter

    def _current_month(self):
        curr_month = datetime.now().strftime('%Y%m')
        return self.env['months'].search([('code', '=', curr_month)], limit=1).id

    def default_user(self):
        return self.env.user

    timesheet_ids = fields.One2many(copy=False)

    user_domain = fields.Many2many('res.users', compute='_user_domain', store=False)
    month_filter = fields.Many2many('months', string='Month', default=_months_filter,)
    month = fields.Many2one('months', string='Month', default=_current_month, required=True, lt_string='Mėnuo')
    date_from = fields.Date(compute='_date_from', required=False, store=True)
    date_to = fields.Date(compute='_date_to', required=False, store=True)
    is_holiday_filled = fields.Boolean(string='Is holiday filled', compute='_is_holiday_filled_compute', store=True)
    employee_id = fields.Many2one('hr.employee', required=False)
    user_id = fields.Many2one('res.users', string='User', required=True, default=default_user, readonly=False)

    # @api.one
    # @api.constrains('timesheet_ids')
    # def constraint_timesheet_line_hours(self):
    #     for line in self.timesheet_ids: # .mapped('date')
    #         same_day_sheets_hours = sum(self.timesheet_ids.filtered(lambda r: r.user_id == line.user_id and
    #                                                                 r.date == line.date and
    #                                                                 r.is_timesheet).mapped('unit_amount'))
    #         if same_day_sheets_hours > 8.0:
    #             raise exceptions.ValidationError(
    #                 'Sum of hours exceeds 8 HOURS PER DAY limitation (' + line.date + ') %s' %same_day_sheets_hours)

    # FIXME: _months() seems to be used nowhere, and is a copy of _month_filter defined above with different constants,
    # FIXME: which is also used only here as default for month_filter field
    def _months(self):
        cdate = datetime.now() - relativedelta(months=5)  #FIXME: why 5?
        filter = []
        for i in range(0, 17):  #FIXME: What's '17'? Where does it come from? Should use some var with explicit name
            search = str(cdate.year) + str(cdate.month).zfill(2)
            val = self.env['months'].search([('code', '=', search)], limit=1)
            if val:
                filter.append(val.id)
            cdate = cdate + relativedelta(months=1)
        return filter

    @api.multi
    def copy(self, default=None):
        self.ensure_one()
        if default is None:
            default = {}
        curr_month = datetime.now().strftime('%Y%m')
        default['month'] = self.env['months'].search([('code', '=', curr_month)], limit=1).id
        project_ids = self.timesheet_ids.mapped('project_id.id')
        date = (datetime.now() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for project_id in project_ids:
            vals = {
                'project_id': project_id,
                'name': '/',
                'date': date,
                'unit_amount': 1.0,
                'is_timesheet': True,
                'user_id': self.user_id.id,
            }
            self.env['account.analytic.line'].create(vals)
        return super(TimesheetSheet, self).copy(default=default)

    @api.onchange('month')
    def set_dates(self):
        if self.month:
            start = datetime.strptime(str(self.month.code), '%Y%m')
            end = (start + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            start = start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_from = start
            self.date_to = end

    @api.one
    @api.depends('month')
    def _date_from(self):
        if self.month:
            start = datetime.strptime(str(self.month.code), '%Y%m')
            start = start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_from = start

    @api.one
    @api.depends('month')
    def _date_to(self):
        if self.month:
            start = datetime.strptime(str(self.month.code), '%Y%m')
            end = (start + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            self.date_to = end

    @api.one
    @api.depends('timesheet_ids')
    def _is_holiday_filled_compute(self):
        iseigines_pool = self.env['sistema.iseigines']
        timesheet_dates = self.timesheet_ids.mapped('date')
        ar_iseigine = iseigines_pool.search_count([('date', 'in', timesheet_dates)])
        if ar_iseigine:
            self.is_holiday_filled = True
            return
        for date in timesheet_dates:
            timesheet_date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            ar_savaitgalis = timesheet_date.weekday() in [5, 6]
            if ar_savaitgalis:
                self.is_holiday_filled = True
                return
        self.is_holiday_filled = False

    @api.one
    @api.depends('user_id', 'date_from', 'date_to')
    def _user_domain(self):
        if self.env.user.has_group('project.group_project_manager'):
            user_ids = self.env['res.users'].search([]).mapped('id')
        else:
            user_ids = self.user_id.ids
        self.user_domain = [(6, 0, user_ids)]

    @api.multi
    def action_timesheet_confirm(self):
        self.ensure_one()
        self.button_confirm_clicked()
        res = super(TimesheetSheet, self).action_timesheet_confirm()
        return res

    @api.multi
    def action_timesheet_confirm_warn(self):
        self.ensure_one()
        return self.action_timesheet_confirm()

    def button_confirm_clicked(self):
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        # iseigines_pool = self.env['sistema.iseigines']
        if date_from.year != date_to.year or date_from.month != date_to.month or date_from.day != 1 or \
            date_to.day != calendar.monthrange(date_to.year, date_to.month)[1]:
            raise exceptions.UserError(_('You can submit only a month period timesheets'))

        # base = date_to
        # numdays = (base - date_from)
        # date_list = []
        # for x in range(0, numdays.days + 1):
        #     month_day = base - timedelta(days=x)
        #     ar_iseigine = iseigines_pool.search_count([('date', '=', month_day)])
        #     ar_savaitgalis = month_day.weekday() in [5, 6]
        #     if not (ar_iseigine or ar_savaitgalis):
        #         date_list.append(month_day.strftime('%Y-%m-%d'))
        # missed_workdays = [x for x in date_list if x not in self[0].timesheet_ids.mapped('date')]
        # if len(missed_workdays) != 0:
        #     raise exceptions.UserError('You must fill all work days. These are missing: (%s)' % missed_workdays)
        # for analytic_line in self[0].timesheet_ids:
        #     same_day_sheets = self.env['account.analytic.line'].search([('user_id', '=', analytic_line.user_id.id),
        #                                                                 ('date', '=', analytic_line.date)])
        #     same_day_sheets_hours = 0.0
        #     for sh in same_day_sheets:
        #         same_day_sheets_hours += sh.unit_amount
        #
            # if (same_day_sheets_hours) > 8.0:
            #     raise exceptions.ValidationError(
            #         'Sum of hours exceeds 8 HOURS PER DAY limitation (' + self.date + ') %s' % same_day_sheets_hours)
            # elif (same_day_sheets_hours) < 8.0 and same_day_sheets_hours:
            #     raise exceptions.ValidationError(
            #         'Sum of hours per day must be 8 hours (' + analytic_line.date + ')')

    # Warns not to fill timesheet, which period is not month
    @api.onchange('date_to')
    def check_project_code_dateto(self):
        self.ensure_one()
        if not self.date_from:
            return
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_from.year != date_to.year or date_from.month != date_to.month or date_from.day != 1 or \
            date_to.day != calendar.monthrange(date_to.year, date_to.month)[1]:
            raise exceptions.UserError(_('Įspėjimas! Galite pateikti tik mėnesinio periodo laiko žiniaraščius'))

    @api.onchange('date_from')
    def check_project_code_datefrom(self):
        self.ensure_one()
        if not self.date_from:
            return
        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        if date_from.day != 1:
            raise exceptions.UserError(_('Įspėjimas! Galite pateikti tik mėnesinio periodo laiko žiniaraščius'))

    # Throws error on saving
    @api.multi
    @api.constrains('date_from', 'date_to')
    def check_project_code_saving(self):
        for rec in self:
            date_from = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            if date_from.year != date_to.year or date_from.month != date_to.month or date_from.day != 1 or \
                    date_to.day != calendar.monthrange(date_to.year, date_to.month)[1]:
                raise exceptions.ValidationError(
                    _('Įspėjimas! Galite pateikti tik mėnesinio periodo laiko žiniaraščius'))

    @api.multi
    def name_get(self):
        names = []
        for rec in self:
            if not rec.month:
                names.append((rec.id, _('Mėnesis')))
                continue
            start = datetime.strptime(str(rec.month.code), '%Y%m')
            name = str(start.year) + ' ' + rec.month_name[start.month]
            names.append((rec.id, name))
        return names

    month_name = {1: 'January',
                  2: 'February',
                  3: 'March',
                  4: 'April',
                  5: 'May',
                  6: 'June',
                  7: 'July',
                  8: 'August',
                  9: 'September',
                  10: 'October',
                  11: 'November',
                  12: 'December'}

    @api.multi  # bug patch
    def onchange(self, values, field_name, field_onchange):
        if isinstance(values, dict) and 'timesheet_ids' in values:
            timesheet_ids = values['timesheet_ids']
            if isinstance(timesheet_ids, list):
                for timesheet in timesheet_ids:
                    if isinstance(timesheet, list) and len(timesheet) == 3:
                        timesheet_vals = timesheet[2]
                        if isinstance(timesheet_vals, dict):
                            timesheet_vals.pop('user_domain', None)
        return super(TimesheetSheet, self).onchange(values, field_name, field_onchange)


TimesheetSheet()


class ResCompany(models.Model):

    _inherit = 'res.company'

    @api.model_cr
    def init(self):
        self.env.user.company_id.write({
            'timesheet_range': 'month',
        })


ResCompany()


class AccountAnalyticLine(models.Model):

    _inherit = 'account.analytic.line'

    project_manager = fields.Many2one('res.users', related='account_id.project_manager', store=True,
                                      string='Projektų vadovas', lt_string='Projektų vadovas', sequence=50)
    amount = fields.Monetary(groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager", copy=False)
    analytic_amount_currency = fields.Monetary(groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager")
    user_domain = fields.Many2many('res.users', compute='_user_domain', store=False)

    name = fields.Char(string='Aprašymas', lt_string='Aprašymas', required=True, default='/')
    job_code_compute = fields.Char(string='Pareigų kodas', compute='_job_code', inverse='_set_job_code')
    job_code = fields.Char(string='Pareigų kodas')
    is_billable = fields.Boolean(string='Yra apmokamas', lt_string='Yra apmokamas', compute='_is_billable', store=True, sequence=50)

    @api.onchange('user_id')
    def onchange_user_id(self):
        if self.task_id and self.name == '/':
            self.name = self.task_id.name

    @api.one
    def _is_billable(self):
        self.is_billable = self.account_id.is_billable

    @api.one
    @api.depends('user_id', 'account_id')
    def _job_code(self):
        if self.job_code:
            self.job_code_compute = self.job_code
        elif self.account_id and self.account_id.project_ids:
            inv = self.sudo().account_id.project_ids.mapped('team_involvement_ids').filtered(
                lambda r: r.user_id.id == self.user_id.id)
            if inv and inv[0].job_code:
                self.job_code_compute = inv[0].job_code or inv[0].job_code_compute
        if not self.job_code_compute:
            emp_id = self.env['hr.employee'].search([('user_id', '=', self.sudo().user_id.id)], limit=1)
            self.job_code_compute = emp_id.job_code or self.user_id.partner_id.job_code or ''

    @api.one
    def _set_job_code(self):
        self.job_code = self.job_code_compute

    @api.one
    @api.depends('user_id')
    def _user_domain(self):
        if self.env.user.has_group('project.group_project_manager'):
            user_ids = self.env['res.users'].search([]).mapped('id')
        else:
            user_ids = self.user_id.ids
        self.user_domain = [(6, 0, user_ids)]

    @api.multi
    def write(self, vals):
        self.check_access_rights('write')
        fields_to_write = vals.keys()
        new_vals = {}
        for fname, field in iteritems(self._fields):
            if fname not in fields_to_write:
                continue
            if field.groups and not self.user_has_groups(field.groups):
                continue
            new_vals[fname] = vals[fname]
        return super(AccountAnalyticLine, self.sudo()).write(new_vals)

    @api.model
    def create(self, vals):
        self.check_access_rights('create')
        fields_to_write = vals.keys()
        if 'move_id' not in fields_to_write:
            new_vals = {}
            for fname, field in iteritems(self._fields):
                if fname not in fields_to_write:
                    continue
                if field.groups and not self.user_has_groups(field.groups):
                    continue
                new_vals[fname] = vals[fname]
        else:
            new_vals = vals
        return super(AccountAnalyticLine, self.sudo()).create(new_vals)

    def _get_timesheet_cost(self, values):
        values = values if values is not None else {}
        if values.get('project_id') or self.project_id:
            if values.get('amount'):
                return {}
            unit_amount = values.get('unit_amount', 0.0) or self.unit_amount
            user_id = values.get('user_id') or self.user_id.id or self._default_user()
            user = self.env['res.users'].browse([user_id])
            emp = self.env['hr.employee'].search([('user_id', '=', user_id)], limit=1)
            date = values.get('date') or (self and self[0]).date or datetime.now().strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            timesheet_cost_method = self.project_id.timesheet_cost_method
            cost = user.get_timesheet_cost(date)
            uom = (emp or user).company_id.project_time_mode_id
            # Nominal employee cost = 1 * company project UoM (project_time_mode_id)
            amount = -unit_amount * cost if timesheet_cost_method != 'skip' else 0.0
            return {
                'amount': amount,
                'product_uom_id': uom.id,
                'account_id': values.get('account_id') or self.account_id.id,
            }
        return {}

    @api.model
    def refresh_analytic_amounts(self, date_from, date_to):
        self.env['account.analytic.line'].search([('date', '>=', date_from), ('date', '<=', date_to)]).with_context(ignore_state=True).write({})

    @api.model
    def cron_refresh_analytic_accounts(self, date=None):
        if not date:
            date = datetime.now()
        else:
            date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from = (date + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (date + relativedelta(months=-1, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.refresh_analytic_amounts(date_from, date_to)

    @api.model
    def cron_refresh_analytic_accounts_period(self, date_from, date_to):
        date_from = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)
        date_to = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        while date_from <= date_to:
            self.cron_refresh_analytic_accounts(date=date_from.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
            date_from += relativedelta(months=1)

    @api.model
    def refresh_everything(self):
        self.env['account.analytic.line'].search([]).with_context(ignore_state=True).write({})

    def _check_state(self):
        if self._context.get('ignore_state'):
            return True
        return super(AccountAnalyticLine, self)._check_state()

    # @api.onchange('date')
    # def _onchange_date(self):
    #     if self.is_timesheet:
    #         current_date = datetime.strptime(self.date, '%Y-%m-%d')
    #         if current_date.weekday() > 4:
    #             raise exceptions.ValidationError("Warning, you're filling weekend or public holiday (" + current_date + ")")

    # @api.one
    # @api.constrains('unit_amount')
    # def constraint_check_hours_before_saving(self):
    #     if self.is_timesheet:
    #         if (self.unit_amount < 0.0):
    #             raise exceptions.ValidationError('Please check fields WORKED HOURS PER DAY! Possible values to enter'
    #                                              ' are greater than 0:00')
            # if (self.unit_amount < 0.0) or (8.0 < self.unit_amount):
            #     raise exceptions.ValidationError('Please check fields WORKED HOURS PER DAY! Possible values to enter'
            #                                      ' are between 0:00 and 8:00')


AccountAnalyticLine()


class AccAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    code = fields.Char(required=True)
    project_manager = fields.Many2one('res.users', string='Project\'s manager',
                                      compute='_project_manager_user_id_compute', store=True)
    is_billable = fields.Boolean(string='Is billable', default=False)
    employee_access = fields.Many2many('hr.employee', string='Darbuotojai, kurie turi prieigą')

    @api.one
    @api.depends('project_ids.user_id')
    def _project_manager_user_id_compute(self):
        for project in self.project_ids:
            if project.user_id:
                self.project_manager = project.user_id
                continue

    @api.onchange('code')
    def onchange_code(self):
        if self.code:
            self.code = self.code.upper().replace(' ', '')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            recs = self.search([('code', '=like', name.lower() + "%")] + args,
                               limit=limit)
            add = self.search([('code', '=like', name.upper() + "%")] + args,
                              limit=limit)
            recs |= add
            if not recs:
                recs = self.search([('name', operator, name)] + args,
                                   limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()

    @api.model
    def create(self, vals):
        if 'code' in vals.keys():
            vals['code'] = vals['code'].upper()
        else:
            vals['code'] = ' '
        res = super(AccAnalyticAccount, self).create(vals)
        return res

    @api.constrains('code')
    def _code_unique(self):
        for rec in self:
            if self.sudo().env['account.analytic.account'].search_count([('code', '=', rec.code)]) >= 2:
                raise exceptions.ValidationError(_('Kodas turi būti unikalus'))


AccAnalyticAccount()


class ProjectProject(models.Model):

    _name = 'project.project'
    _inherit = ['project.project', 'ir.attachment.drop']

    _default_field_sequence = 100  # by default do not show any field in filter and group by sections.

    date_start = fields.Date(default=fields.Date.today, string='Projekto pradžia', lt_string='Projekto pradžia',
                             sequence=50)
    date_end = fields.Date(string='Projekto pabaiga', lt_string='Projekto pabaiga', sequence=50)
    project_description = fields.Html(string='Description', sequence=50)
    team_involvement_ids = fields.One2many(related='analytic_account_id.team_involvement_ids')
    user_ids = fields.Many2many('res.users', string='Team users', store=True, compute='_user_involvement',
                                compute_sudo=True)
    # code = fields.Char(related='analytic_account_id.code')
    alias_name = fields.Char(default=False)
    # privacy_visibility = fields.Selection([
    #     ('followers', 'Komandos nariams'),
    #     ('employees', 'Matoma visiems darbuotojams'),
    # ],
    #     string='Privatumas', lt_string='Privatumas', required=True,
    #     default='followers',
    #     help="")
    allow_edit = fields.Boolean(string='Allow edit', compute='_allow_edit')
    label_tasks = fields.Char(string='Pavadinti Užduotys kaip', lt_string='Pavadinti Užduotys kaip',
                              default=_('Užduotys'), help='Galite pakeisti Užduotys pavadinimą')
    label_issues = fields.Char(string='Pavadinti Pastabos kaip', lt_string='Pavadinti Pastabos kaip',
                               help='Galite pervadinti Pastabos pavadinimą', default=_('Pastabos'))
    # @api.one
    # @api.depends('team_involvement_ids')
    # def _team_involvement(self):
    #     if self.team_involvement_ids:
    #         self.team_ids = self.team_involvement_ids.mapped('user_id.id')

    duration_scale = fields.Char(string='Trukmės skalė', lt_string='Trukmės skalė', default='d,h',
                                 help='Galite nustatyti: y,mo,w,d,h,m,s,ms')
    duration_picker = fields.Selection('_get_duration_picker', string='Trukmės formatas',
                                       lt_string='Trukmės formatas', default='day', help='Rodyti: dienas, sekundes')

    project_is_billable = fields.Boolean(related='analytic_account_id.is_billable', default=True)
    stage_id = fields.Many2one('project.stage', string="Projekto etapas", lt_string="Projekto etapas", store=True)
    project_sequence = fields.Integer(related='stage_id.sequence')
    timesheet_cost_method = fields.Selection([('vdu', 'Įtraukti'),
                                              ('skip', 'Neįtraukti/Nulinis')],
                                             default='vdu',
                                             string='Valandinio įkainio skaičiavimas',
                                             # todo: add write_groups='project.group_project_manager'
                                             )

    @api.multi
    def open_stages(self):
        action = self.env.ref('robo_projects.open_project_stage_form')
        return action.read()[0]
        # return {
        #     'id': action.id,
        #     'name': action.name,
        #     'type': 'ir.actions.act_window',
        #     'view_type': 'form',
        #     'view_mode': 'tree,form',
        #     'res_model': 'project.stage',
        #     'view_id': False,
        #     # 'context': action.context,
        # }

    # ROBO: somehow reload kanban
    @api.multi
    def close_dialog_reload(self):
        return {'type': 'ir.actions.act_close_wizard_and_reload_kanban'}

    @api.model
    def _get_duration_picker(self):
        value = [
            ('day', _('Dienos')),
            ('second', _('Sekundės')),
            ('day_second', _('Dienos ir sekundės')),
        ]
        return value

    @api.model
    def _get_scheduling_type(self):
        value = [
            ('forward', _('Nuo projekto pradžios datos')),
            ('backward', _('Nuo projekto pabaigos datos')),
        ]
        return value

    @api.one
    def _allow_edit(self):
        if self.env.user.has_group('project.group_project_manager') or self.user_id == self.env.user:
            self.allow_edit = True
        else:
            self.allow_edit = False

    @api.one
    def _set_team_followers_inverse(self):

        p_ids = []
        for project_inv in self.team_involvement_ids:
            if not project_inv.id:  # only new member will be added as follower
                if project_inv.user_id:
                    p_ids.append(project_inv.user_id.partner_id.id)
        subtypes_id = self.env['mail.message.subtype'].search(['|', '&', ('default', '=', True),
                                                               ('res_model', '=', False),
                                                               '&',
                                                               ('name', 'in', ['Task Opened', 'Project Stage Changed']),
                                                               ('res_model', '=', 'project.project')]).mapped('id')
        self.message_subscribe(partner_ids=p_ids, subtype_ids=subtypes_id)

    @api.one
    @api.depends('team_involvement_ids')
    def _user_involvement(self):
        if self.team_involvement_ids:
            self.user_ids = self.team_involvement_ids.mapped('user_id.id')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            recs = self.search(['|', ('code', operator, name), ('name', operator, name)] + args, limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()

    @api.multi
    def unlink(self):
        for rec in self:
            if not rec.allow_edit:
                raise exceptions.UserError(_('Jūs negalite ištrinti projekto'))
        return super(ProjectProject, self).unlink()


ProjectProject()


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    description = fields.Text(string='Aprašymas')

    @api.model
    def create(self, vals):
        active_model = self._context.get('active_model')
        active_id = self._context.get('active_id')
        if active_model and active_model == 'project.project' and active_id:
            project = self.env['project.project'].browse(active_id)
        else:
            project = None
        if project and project.user_id == self.env.user or self.env.user.has_group('project.group_project_manager'):
            return super(ProjectTaskType, self).create(vals)
        else:
            raise exceptions.UserError(_('You are not allowed to add a column'))

        #TODO: when robo_front view is added for editing task, we will need to add an override for write or somecontrol over
        #TODO: who can edit the stages. Maybe through boolean computed field, that will prevent the menu from opening and the writing


ProjectTaskType()


class ProjectStage(models.Model):

    _name = 'project.stage'
    _description = 'Project Stage'
    _order = 'sequence'
    _default_field_sequence = 100  # by default do not show any field in filter and group by sections.

    name = fields.Char(string='Etapo pavadinimas', lt_string='Etapo pavadinimas', required=True, sequence=50)
    description = fields.Char(string='Aprašymas', lt_string='Aprašymas', sequence=50)
    sequence = fields.Integer(string='Sequence', default=1)
    legend_priority = fields.Char(string='Priority Management Explanation',
        help='Explanation text to help users using the star and priority mechanism on stages or issues that are in this stage.')
    legend_blocked = fields.Char(string='Kanban Blocked Explanation',
        help='Override the default value displayed for the blocked state for kanban selection, when the task or issue is in that stage.')
    legend_done = fields.Char(string='Kanban Valid Explanation',
        help='Override the default value displayed for the done state for kanban selection, when the task or issue is in that stage.')
    legend_normal = fields.Char(string='Kanban Ongoing Explanation',
        help='Override the default value displayed for the normal state for kanban selection, when the task or issue is in that stage.')
    fold = fields.Boolean(string='Folded in Tasks Pipeline',
                           help='This stage is folded in the kanban view when '
                           'there are no records in that stage to display.')


ProjectStage()


class ProjectTaskPredecessor(models.Model):
    _inherit = 'project.task.predecessor'

    @api.model
    def _get_link_type(self):
        value = [
            ('FS', _('Nuo pabaigos iki pradžios')),
            ('SS', _('Nuo pradžios iki pradžios')),
            ('FF', _('Nuo pabaigos iki pabaigos')),
            ('SF', _('Nuo pražios iki pabaigos')),

        ]
        return value

    @api.model
    def _get_lag_type(self):
        value = [
            ('minute', _('minutė')),
            ('hour', _('valanda')),
            ('day', _('diena')),
            ('percent', _('procentas')),
        ]
        return value


ProjectTaskPredecessor()


class ProjectTask(models.Model):

    _name = 'project.task'
    _inherit = ['project.task', 'ir.attachment.drop']
    _default_field_sequence = 100  # by default do not show any field in filter and group by sections, pivot.

    code = fields.Char(string='Automated code', readonly=True)
    tag_ids = fields.Many2many(string='Žymos', lt_string='Žymos', sequence=50)
    create_date = fields.Datetime(sequence=50)
    date_deadline = fields.Date(sequence=50)
    progress = fields.Float(string='Užregistruotas darbo laikas', lt_string='Užregistruotas darbo laikas')

    @api.model
    def _get_schedule_mode(self):
        value = [
            ('auto', _('Automatinis')),
            ('manual', _('Rankinis')),
        ]
        return value

    @api.model
    def _get_constrain_type(self):
        value = [
            ('asap', _('Kaip įmanoma greičiau/vėliau')),
            ('fnet', _('Pradėti ne anksčiau kaip')),
            ('fnlt', _('Pabaigti ne vėliau kaip')),
            ('mso', _('Privalo prasidėti')),
            ('mfo', _('Privalo baigtis')),
            ('snet', _('Pradėti ne anksčiau kaip')),
            ('snlt', _('Pradėti ne vėliau kaip')),
        ]
        return value

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            if rec.code:
                res.append((rec.id, '[%s] %s' % (rec.code, rec.name)))
            else:
                res.append((rec.id, '%s' % rec.name))
        return res

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        args = list(args or [])
        if name:
            ids = self.search(['|', ('name', operator, name), ('code', operator, name)] + args, limit=limit)
        else:
            ids = self.search(args, limit=limit)
        return ids.name_get()


ProjectTask()


class ResUsers(models.Model):

    _inherit = 'res.users'

    @api.model
    def search(self, *a, **kw):
        res = super(ResUsers, self).search(*a, **kw)
        is_count_search = isinstance(kw, dict) and 'count' in kw.keys()
        if not self.env.user.is_accountant() and not is_count_search:
            res = res.filtered(lambda r: not r.is_accountant())
        return res

    def get_timesheet_cost(self, date):
        emp = self.env['hr.employee'].search([('user_id', '=', self.id), '|', ('active', '=', True), ('active', '=', False)], limit=1)
        if self.partner_id.force_timesheet_cost:
            return self.partner_id.timesheet_cost
        cost = 0.0
        if emp:
            cost = emp.timesheet_cost or 0.0
        date_from = (datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=31)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        date_strp = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        year = date_strp.year
        month = date_strp.month
        domain = [('year', '=', year), ('month', '=', month)]
        if emp:
            domain.append('|')
            domain.append(('employee_id', '=', emp.id))
        domain.append(('user_id', '=', self.id))

        employee_monthly_analytic_amounts = sum(self.env['employee.monthly.analytic.amounts'].search(domain).mapped('amount'))

        timesheet_hours = sum(self.env['account.analytic.line'].search([('user_id', '=', self.id),
                                                                    ('date', '>=', date_from),
                                                                    ('date', '<=', date_to),
                                                                    ('project_id.timesheet_cost_method', '=', 'vdu')]).mapped('unit_amount'))

        if not tools.float_is_zero(employee_monthly_analytic_amounts, precision_digits=2) and not tools.float_is_zero(timesheet_hours, precision_digits=2):
            cost = employee_monthly_analytic_amounts / timesheet_hours

        # if vdu_rec and timesheet_hours:
        #     cost = vdu_rec.amount / timesheet_hours
        # cost = cost * (1 + (
        #     emp.contract_id.with_context(date=date).get_payroll_tax_rates(['darbdavio_sodra_proc'])[
        #         'darbdavio_sodra_proc']) / 100.0)
        return cost


ResUsers()


# ROBO: should be discourage in the future!
class ProjectIssue(models.Model):

    _inherit = 'project.issue'
    _default_field_sequence = 100

    date = fields.Datetime(sequence=50)
    name = fields.Char(sequence=50, string='Pastaba', lt_string='Pastaba')
    project_id = fields.Many2one(sequence=50)
    partner_id = fields.Many2one(sequence=50)
    task_id = fields.Many2one(sequence=50)


ProjectIssue()


class ReportProjectTaskUser(models.Model):
    _inherit = "report.project.task.user"
    _default_field_sequence = 100

    name = fields.Char(string='Užduoties pavadinimas', lt_string='Užduoties pavadinimas', sequence=50)
    state = fields.Selection(sequence=50)
    hours_planned = fields.Float(string='Suplanuotos valandos', lt_string='Suplanuotos valandos', sequence=50)
    hours_effective = fields.Float(string='Efektyvios valandos', lt_string='Efektyvios valandos', sequence=50)
    # hours_delay = fields.Float('Avg. Plan.-Eff.', readonly=True)
    remaining_hours = fields.Float(string='Likusios valandos', lt_string='Likusios valandos', sequence=50)
    progress = fields.Float(string='Progresas', lt_string='Progresas', sequence=50)
    total_hours = fields.Float(string='Viso valandų', lt_string='Viso valandų', sequence=50)

    user_id = fields.Many2one(lt_string='Priskirta', sequence=50)
    date_start = fields.Datetime(lt_string='Priskyrimo data', sequence=50)
    # no_of_days = fields.Integer(string='# Working Days', readonly=True)
    date_end = fields.Datetime(lt_string='Pabaigos data', sequence=50)
    date_deadline = fields.Date(lt_string='Terminas', sequence=50)
    # date_last_stage_update = fields.Datetime(string='Last Stage Update', readonly=True)
    project_id = fields.Many2one(lt_string='Projektas', sequence=50)
    # closing_days = fields.Float(string='# Days to Close',
    #                             digits=(16, 2), readonly=True, group_operator="avg",
    #                             help="Number of Days to close the task")
    # opening_days = fields.Float(string='# Days to Assign',
    #                             digits=(16, 2), readonly=True, group_operator="avg",
    #                             help="Number of Days to Open the task")
    delay_endings_days = fields.Float(lt_string='# Dienų iki termino', sequence=50)
    nbr = fields.Integer(string='# Užduočių', lt_string='# Užduočių', sequence=50)
    # priority = fields.Selection([
    #     ('0', 'Low'),
    #     ('1', 'Normal'),
    #     ('2', 'High')
    # ], size=1, readonly=True)
    # state = fields.Selection([
    #     ('normal', 'In Progress'),
    #     ('blocked', 'Blocked'),
    #     ('done', 'Ready for next stage')
    # ], string='Kanban State', readonly=True)
    company_id = fields.Many2one(lt_string='Kompanija', sequence=50)
    partner_id = fields.Many2one(lt_string='Partneris', sequence=50)
    stage_id = fields.Many2one(lt_string='Etapas', sequence=50)


ReportProjectTaskUser()


class ResPartner(models.Model):

    _inherit = 'res.partner'

    job_code = fields.Char(string='Pareigų kodas')
    force_timesheet_cost = fields.Boolean(string='Priverstinai naudoti valandos kainą')
    timesheet_cost = fields.Float('Valandinis įkainis', default=0.0, help='Analitinio žinaraščio valandos kaina, kai nėra algalapių.',
                                  groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager,robo_basic.group_robo_hr_manager")
    part_is_user = fields.Boolean(string='Yra vartotojas', compute='_is_user', search='search_is_user')

    def _is_user(self):
        for rec in self:
            if rec.env['res.users'].search([('partner_id', '=', rec.id)]):
                rec.part_is_user = True
            else:
                rec.part_is_user = False

    @api.model
    def search_is_user(self, operator, value):
        user_partner_ids = self.env['res.users'].search([]).mapped('partner_id.id')
        if operator == '=' and value or operator == '!=' and not value:
            return [('id', 'in', user_partner_ids)]
        else:
            return [('id', 'not in', user_partner_ids)]


ResPartner()
