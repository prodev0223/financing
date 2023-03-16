# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


# class Employee(models.Model):
#
#     _inherit = 'hr.employee'
#
#     job_code = fields.Char(string='Pareigų kodas')
#     timesheet_cost = fields.Float(related='address_home_id.timesheet_cost', store=True)
#
#     @api.one
#     def _set_robo_access(self):
#         super(Employee, self)._set_robo_access()
#         if self.env.user.is_premium_manager() and self.user_id:
#             self.user_id.groups_id = [(4, self.env.ref('project.group_project_user').id)]
#
# Employee()
#
#
# class ResPartner(models.Model):
#
#     _inherit = 'res.partner'
#
#     job_code = fields.Char(string='Pareigų kodas')
#     force_timesheet_cost = fields.Boolean(string='Priverstinai naudoti valandos kainą')
#     timesheet_cost = fields.Float('Timesheet Cost', default=0.0, help='Analitinio žinaraščio valandos kaina, kai nėra algalapių.',
#                                   groups="robo_basic.group_robo_premium_manager,robo_basic.group_robo_free_manager")
#     part_is_user = fields.Boolean(string='Yra vartotojas', compute='_is_user', search='search_is_user')
#
#     def _is_user(self):
#         for rec in self:
#             if rec.env['res.users'].search([('partner_id', '=', rec.id)]):
#                 rec.part_is_user = True
#             else:
#                 rec.part_is_user = False
#
#     @api.model
#     def search_is_user(self, operator, value):
#         user_partner_ids = self.env['res.users'].search([]).mapped('partner_id.id')
#         if operator == '=' and value or operator == '!=' and not value:
#             return [('id', 'in', user_partner_ids)]
#         else:
#             return [('id', 'not in', user_partner_ids)]
#
# ResPartner()
#
#
# class ProjectInvolvement(models.Model):
#
#     _inherit = 'project.involvement'
#
#     job_code_compute = fields.Char(string='Pareigų kodas', compute='_job_code', inverse='_set_job_code')
#     job_code = fields.Char(string='Pareigų kodas')
#
#     @api.one
#     @api.depends('user_id')
#     def _job_code(self):
#         if self.job_code:
#             self.job_code_compute = self.job_code
#         elif self.user_id.employee_ids and self.user_id.employee_ids[0].job_code:
#             self.job_code_compute = self.employee_id.job_code
#         else:
#             self.job_code_compute = self.user_id.partner_id.job_code
#
#     @api.one
#     def _set_job_code(self):
#         self.job_code = self.job_code_compute
#
# ProjectInvolvement()


# class TimesheetSheet(models.Model):
#
#     _inherit = 'account.analytic.account'
#
#     is_billable = fields.Boolean(string='Is billable', default=False)
#
# TimesheetSheet()


# class TimesheetSheet(models.Model):
#
#     _inherit = 'account.analytic.line'
#
#     # def default_job_code(self):
#     #     employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
#     #     if employee:
#     #         return employee.job_code
#     #     else:
#     #         return False
#     #
#     # job_code = fields.Char(string='Pareigų kodas', default=default_job_code)
#
#
#     name = fields.Char('Description', required=True, default='/')
#     job_code_compute = fields.Char(string='Pareigų kodas', compute='_job_code', inverse='_set_job_code')
#     job_code = fields.Char(string='Pareigų kodas')
#     is_billable = fields.Boolean(string='Is Billable', compute='_is_billable', store=True)
#
#     @api.onchange('user_id')
#     def onchange_user_id(self):
#         if self.task_id and self.name == '/':
#             self.name = self.task_id.name
#
#     @api.one
#     def _is_billable(self):
#         self.is_billable = self.account_id.is_billable
#
#     @api.one
#     @api.depends('user_id', 'account_id')
#     def _job_code(self):
#         if self.job_code:
#             self.job_code_compute = self.job_code
#         elif self.account_id and self.account_id.project_ids:
#             inv = self.sudo().account_id.project_ids.mapped('team_involvement_ids').filtered(lambda r: r.user_id.id == self.user_id.id)
#             if inv and inv[0].job_code:
#                 self.job_code_compute = inv[0].job_code or inv[0].job_code_compute
#         if not self.job_code_compute:
#             emp_id = self.env['hr.employee'].search([('user_id', '=', self.sudo().user_id.id)], limit=1)
#             self.job_code_compute = emp_id.job_code or self.user_id.partner_id.job_code or ''
#
#     @api.one
#     def _set_job_code(self):
#         self.job_code = self.job_code_compute
#
#     # basically copy paste from robo_projects, but we use partner
#     # def _get_timesheet_cost(self, values):
#     #     values = values if values is not None else {}
#     #     if values.get('project_id') or self.project_id:
#     #         if values.get('amount'):
#     #             return {}
#     #         unit_amount = values.get('unit_amount', 0.0) or self.unit_amount
#     #         user_id = values.get('user_id') or self.user_id.id or self._default_user()
#     #         user = self.env['res.users'].browse([user_id])
#     #         emp = self.env['hr.employee'].search([('user_id', '=', user_id)], limit=1)
#     #         # cost = 0.0
#     #         if emp:
#     #             cost = emp.timesheet_cost or 0.0
#     #             date = values.get('date') or (self and self[0]).date or datetime.now().strftime(
#     #                 tools.DEFAULT_SERVER_DATE_FORMAT)
#     #             date_from = (datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
#     #             vdu_rec = self.env['employee.vdu'].search([('employee_id', '=', emp.id), ('date_from', '=', date_from)], limit=1)
#     #             if vdu_rec and vdu_rec.hours_worked > 0:
#     #                 cost = vdu_rec.amount / vdu_rec.hours_worked
#     #             cost = cost * (1 + (emp.contract_id.with_context(date=date).get_payroll_tax_rates(['darbdavio_sodra_proc'])['darbdavio_sodra_proc']) / 100.0)
#     #         else:
#     #             cost = user.partner_id.timesheet_cost or 0.0
#     #         uom = (emp or user).company_id.project_time_mode_id
#     #         # Nominal employee cost = 1 * company project UoM (project_time_mode_id)
#     #         return {
#     #             'amount': -unit_amount * cost,
#     #             'product_uom_id': uom.id,
#     #             'account_id': values.get('account_id') or self.account_id.id or emp.account_id.id,
#     #         }
#     #     return {}
#
# TimesheetSheet()


# class HrTimesheetReport(models.Model):
#
#     _inherit = 'hr.timesheet.report'
#
#     job_code = fields.Char(string='Pareigų kodas')
#
#     def _select(self):
#         res = super(HrTimesheetReport, self)._select()
#         res += ''',
#         aal.job_code as job_code'''
#         return res
#
#     def _group_by(self):
#         res = super(HrTimesheetReport, self)._group_by()
#         res += ''',
#         aal.job_code'''
#         return res

# HrTimesheetReport()


# class ProjectProject(models.Model):
#
#     _inherit = 'project.project'
#
#     # project_manager_emp = fields.Many2one('hr.employee', required=False)
#
#     project_is_billable = fields.Boolean(related='analytic_account_id.is_billable', default=True)
#
#     @api.multi
#     def open_stages(self):
#         action = self.env.ref('doarchitects.open_project_stage_form')
#         return {
#             'id': action.id,
#             'name': action.name,
#             'type': 'ir.actions.act_window',
#             'view_type': 'form',
#             'view_mode': 'tree,form',
#             'res_model': 'project.stage',
#             'view_id': False,
#         }

#
#     def _currency(self):
#         return self.env.user.company_id.currency_id
#
#     project_is_billable = fields.Boolean(related='analytic_account_id.is_billable', default=True)
#     planned_weeks = fields.Float(string="Planned weeks", compute='_get_planned_weeks', store=False, compute_sudo=True)
#     team_ids = fields.Many2many('hr.employee', string='Team members', store=True, compute='_team_involvement', compute_sudo=True)
#     team_involvement_ids = fields.One2many('project.involvement', 'project_id', readonly=False, string="Team involvement", inverse='_set_team_followers_inverse')
#     budg_manhours = fields.Float(string="Budgeted manhours")
#     spent_manhours = fields.Float(string="Spent manhours", compute='_get_spent_manhours', store=False, compute_sudo=True)
#     project_manhours_progress = fields.Float(string=" ", compute='_get_manhours_progress', store=False, compute_sudo=True)
#     project_budget = fields.Float(string="Total budget", store=True)
#     # project_invoiced = fields.Float(string="Invoiced already", compute="_get_project_invoiced", store=False, compute_sudo=True, groups='project.group_project_manager')
#     # project_invoices_paid = fields.Float(string="Paid invoices", compute="_get_invoices_paid", store=False, compute_sudo=True, groups='project.group_project_manager')
#     # project_invoices_paid_progress = fields.Float(string="Invoices paid progress", compute='_get_invoices_paid_progress', store=False, compute_sudo=True, groups='project.group_project_manager', digits=(5,2))
#     # project_invoices_left = fields.Float(string="Left to invoice", compute="_get_project_invoices_left", store=False, compute_sudo=True, groups='project.group_project_manager')
#     # gross_profit = fields.Float(string="Gross profit", compute="_get_gross_profit", store=False)
#     # color = fields.Integer()
#     stage_id = fields.Many2one('project.stage', string="Project Stage", store=True)
    # project_sequence = fields.Integer(related='stage_id.sequence')
#     project_is_billable = fields.Boolean(related='analytic_account_id.is_billable', default=True)
#     # project_gauge_paid = fields.Boolean(string="Show paid invoices gauge", compute="_project_gauge_paid", store=False)
#     company_currency_id = fields.Many2one('res.currency', string='Company currency', default=_currency)
#     is_project_manager = fields.Boolean(string='Is Project Manager', compute='_is_project_manager', store=False)
#     user_ids = fields.Many2many('res.users', string='Team users', store=True, compute='_user_involvement', compute_sudo=True)
#     # from parent class option "Customer Project" was deleted
#     def _get_visibility_selection(self, cr, uid, context=None):
#         return [('employees', 'All Employees Project: all employees can access'),
#                 ('followers', 'Private Project: team members only')]
#
#     def count_businessdays(self, my_date):
#         date = datetime.strptime(my_date, '%Y-%m-%d')
#         businessdays = 0.0
#         for i in range(1, 32):
#             try:
#                 thisdate = datetime.date(date.year, date.month, i)
#             except ValueError:
#                 break
#             if thisdate.weekday() < 5:    # and thisdate not in holidays:  Monday == 0, Sunday == 6
#                 businessdays += 1.0
#         return businessdays
#
#     @api.one
#     @api.depends('stage_id.show_invoice_paid_gauge')
#     def _project_gauge_paid(self):
#         self.project_gauge_paid = self.stage_id.show_invoice_paid_gauge
#
#     @api.one
#     @api.depends('project_manager')
#     def _is_project_manager(self):
#         if self.env['res.users'].browse(self._uid).has_group('project.group_project_manager'):
#             self.is_project_manager = True
#         elif self.project_manager and self.sudo().project_manager.id == self._uid:
#             self.is_project_manager = True
#         else:
#             self.is_project_manager = False
#
#     @api.one
#     @api.depends('date_start', 'date_end')
#     def _get_planned_weeks(self):
#         date_start = fields.Date.from_string(self.date_start)
#         date_end = fields.Date.from_string(self.date_end)
#         delta = timedelta(days=1)
#         diff = 0
#         if date_start and date_end:
#             while date_end >= date_start:
#                 diff += 1
#                 date_start += delta
#         weeks = diff / 7.0
#         self.planned_weeks = weeks
#
#     @api.one
#     def _set_followers_inverse(self):
#         if self.project_manager:
#             partner_ids = self.mapped('partner_id.id')
#             subtypes_id = self.env['mail.message.subtype'].search(['|', '&', ('default', '=', True),
#                                                                    ('res_model', '=', False),
#                                                                    '&', ('name', 'in',
#                                                                          ['Task Opened', 'Project Stage Changed']),
#                                                                    ('res_model', '=', 'project.project')]).mapped('id')
#             self.message_subscribe(partner_ids=partner_ids, subtype_ids=subtypes_id)
#
#     @api.one
#     def _set_team_followers_inverse(self):
#
#         p_ids = []
#         for project_inv in self.team_involvement_ids:
#             if not project_inv.id:  # only new member will be added as follower
#                 if project_inv.employee_id.user_id:
#                     p_ids.append(project_inv.employee_id.user_id.partner_id.id)
#         subtypes_id = self.env['mail.message.subtype'].search(['|', '&', ('default', '=', True),
#                                                                ('res_model', '=', False),
#                                                                '&',
#                                                                ('name', 'in', ['Task Opened', 'Project Stage Changed']),
#                                                                ('res_model', '=', 'project.project')]).mapped('id')
#         self.message_subscribe(partner_ids=p_ids, subtype_ids=subtypes_id)
#
#     @api.one
#     @api.depends('team_involvement_ids')
#     def _team_involvement(self):
#         if self.team_involvement_ids:
#             self.team_ids = self.team_involvement_ids.mapped('employee_id.id')
#
#     @api.one
#     @api.depends('team_involvement_ids')
#     def _user_involvement(self):
#         if self.team_involvement_ids:
#             self.user_ids = self.team_involvement_ids.mapped('employee_id.user_id.id')
#
#     @api.one
#     def unlink(self):
#         self.team_involvement_ids.unlink()
#         super(ProjectsCorrection, self).unlink()
#
#     @api.one
#     @api.depends('partner_id')
#     def _get_spent_manhours(self):
#         hours = 0.0
#
#         project_account_lines = self.sudo().env['account.analytic.line'].search([('account_id', '=', self.analytic_account_id.id)])
#         for line in project_account_lines:
#             hours += line.unit_amount
#         self.spent_manhours = hours
#
#     @api.one
#     @api.depends('partner_id')
#     def _get_manhours_progress(self):
#
#         if self.budg_manhours and self.spent_manhours:
#             self.project_manhours_progress = round((100.0 * self.spent_manhours / self.budg_manhours), 1)
#         else:
#             self.project_manhours_progress = 0.0
#
#     @api.one
#     @api.depends('partner_id')
#     def _get_project_invoiced(self):
#         money_invoiced = 0.0
#
#         project_invoice_lines = self.env['account.invoice.line'].search([('account_analytic_id', '=', self.analytic_account_id.id),
#                                                                          ('partner_id', '=', self.partner_id.id),
#                                                                          ('company_id', '=', self.company_id.id),
#                                                                          ('invoice_id.state', 'in', ['open', 'paid'])])
#         for line in project_invoice_lines:
#             if line.company_currency_id.id != line.currency_id.id:
#                 money_invoiced += line.currency_id.compute(line.price_subtotal, line.company_currency_id)
#             else:
#                 money_invoiced += line.price_subtotal
#
#         self.project_invoiced = money_invoiced
#
#     @api.one
#     @api.depends('partner_id')
#     def _get_invoices_paid(self):
#         project_invoice_lines = self.env['account.invoice.line'].search([('account_analytic_id', '=', self.analytic_account_id.id),
#                                                                          ('partner_id', '=', self.partner_id.id),
#                                                                          ('company_id', '=', self.company_id.id),
#                                                                          ('invoice_id.state', 'in', ['open', 'paid'])])
#         invoice_ids = project_invoice_lines.mapped('invoice_id.id')
#         account_ids = project_invoice_lines.mapped('account_id.id')
#         total_credit = 0.0
#         if len(invoice_ids) == 0:
#             self.project_invoices_paid = 0.0
#             return False
#         tmp=[]
#         for line in self.env['account.move.line'].search([('invoice_id', 'in', invoice_ids),
#                                                           ('account_id', 'in', account_ids),
#                                                           ('partner_id', '=', self.partner_id.id),
#                                                           ('company_id', '=', self.company_id.id)]):
#             total_credit += line.credit_cash_basis
#             tmp.append(line.id)
#
#         self.project_invoices_paid = total_credit
#
#     @api.one
#     @api.depends('partner_id')
#     def _get_invoices_paid_progress(self):
#
#         if self.project_invoiced and self.project_invoices_paid:
#             self.project_invoices_paid_progress = 100.0 * self.project_invoices_paid / self.project_invoiced
#         else:
#             self.project_invoices_paid_progress = 0.0
#
#     @api.one
#     @api.depends('partner_id', 'project_budget')
#     def _get_project_invoices_left(self):
#         self.project_invoices_left = self.project_budget - self.project_invoiced
#
#     @api.onchange('project_manager')
#     def onchange_project_manager(self):
#         if not self.project_manager:
#             return
#         for involvement in self.team_involvement_ids:
#             self.team_involvement_ids = [(2, involvement.id)]
#         employee_id = self.project_manager.employee_ids[0].id if self.project_manager.employee_ids else False
#         if employee_id:
#             self.team_involvement_ids = [(0, 0, {'employee_id': employee_id})]
#
#     @api.model
#     def _stage_groups(self, present_ids, domain, **kwargs):
#         stage_obj = self.env['project.stage']
#         stage_ids = stage_obj.search([])
#         stages = self.env['project.stage'].search([]).name_get()
#         fold = {}
#         for stage in stage_ids:
#             fold[stage.id] = stage.fold or False
#         return stages, fold
#
#     @api.model
#     def create(self, vals):
#         if 'code' in vals.keys():
#             vals['alias_name'] = vals.get('code')
#             vals['code'] = vals['code'].upper()
#         stage = self.env['project.stage'].search([], order='sequence', limit=1)
#         if stage:
#             vals['stage_id'] = stage.id
#
#         res = super(ProjectsCorrection, self).create(vals)
#         return res
#
#     @api.multi
#     def read(self, fields=None, load='_classic_read'):
#         secret_fields = set(['project_budget', 'project_invoiced',
#                              'project_invoices_paid', 'project_invoices_left',
#                              'budg_manhours', 'spent_manhours'])
#         all_fields = set(fields)
#         secret_read = list(all_fields.intersection(secret_fields))
#         if len(secret_read) > 0:
#             data = self.read(['is_project_manager', 'privacy_visibility'])
#             privacy = 'followers'
#             open = False
#             if data:
#                 privacy = data[0]['privacy_visibility']
#                 open = data[0]['is_project_manager']
#             if not open and privacy == 'followers':
#                 res = super(ProjectsCorrection, self).read(fields=list(all_fields-secret_fields), load=load)
#                 for f in secret_read:
#                     for r in res:
#                         r[f] = 0.0
#                 return res
#
#         return super(ProjectsCorrection, self).read(fields=fields, load=load)
#
#     _group_by_full = {
#         'stage_id': _stage_groups,
#     }
#
# ProjectProject()


# class ProjectStage(models.Model):
#
#     _name = 'project.stage'
#     _description = 'Project Stage'
#     _order = 'sequence'
#
#     name = fields.Char(string='Stage Name', required=True)
#     description = fields.Char(string='Description')
#     sequence = fields.Integer(string='Sequence', default=1)
#     legend_priority = fields.Char(string='Priority Management Explanation',
#         help='Explanation text to help users using the star and priority mechanism on stages or issues that are in this stage.')
#     legend_blocked = fields.Char(string='Kanban Blocked Explanation',
#         help='Override the default value displayed for the blocked state for kanban selection, when the task or issue is in that stage.')
#     legend_done = fields.Char(string='Kanban Valid Explanation',
#         help='Override the default value displayed for the done state for kanban selection, when the task or issue is in that stage.')
#     legend_normal = fields.Char(string='Kanban Ongoing Explanation',
#         help='Override the default value displayed for the normal state for kanban selection, when the task or issue is in that stage.')
#     fold = fields.Boolean(string='Folded in Tasks Pipeline',
#                            help='This stage is folded in the kanban view when '
#                            'there are no records in that stage to display.')
#
# ProjectStage()


# class HrTimesheetSheet(models.Model):
#
#     _inherit = 'hr_timesheet_sheet.sheet'
#
#     timesheet_ids = fields.One2many(copy=False)
#     month = fields.Many2one('months', required=True)
#
#     @api.multi
#     def copy(self, default=None):
#         self.ensure_one()
#         if default is None:
#             default = {}
#         curr_month = datetime.now().strftime('%Y%m')
#         default['month'] = self.env['months'].search([('code', '=', curr_month)], limit=1).id
#         account_ids = self.timesheet_ids.mapped('account_id.id')
#         sheet_id = self.id
#         date = (datetime.now() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
#         vals = []
#         for account_id in account_ids:
#             vals.append((0, 0, {
#                 'account_id': account_id,
#                 'name': '/',
#                 'date': date,
#                 'unit_amount': 1.0,
#                 'sheet_id': sheet_id,
#                 'is_timesheet': True,
#                 'user_id': self.user_id.id,
#             }))
#         default['timesheet_ids'] = vals
#         return super(HrTimesheetSheet, self).copy(default=default)
#
# HrTimesheetSheet()
#
#
# class ResUsers(models.Model):
#
#     _inherit = 'res.users'
#
#     def get_timesheet_cost(self, date):
#         emp = self.env['hr.employee'].search([('user_id', '=', self.id)], limit=1)
#         if not emp or self.partner_id.force_timesheet_cost:
#             return self.partner_id.timesheet_cost
#         return super(ResUsers, self).get_timesheet_cost(date)
#
# ResUsers()
