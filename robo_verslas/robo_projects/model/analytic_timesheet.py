# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions, tools
from datetime import datetime
from datetime import *
from dateutil.relativedelta import *
import locale
import babel.dates
import dateutil.parser
from odoo.osv.expression import normalize_domain

# Pastabos:
# checkai dėl savaitgalių/ išeiginių atliekami pitone kiekvienam laukeliui
# gridą atidarius defaultai pagal konkretų laukelę galėtų būti


class ResUsers(models.Model):
    _inherit = 'res.users'

    timesheet_validated = fields.Date(string='Patvirtinta', groups="project.group_project_manager")
    timesheet_submitted = fields.Date(string='Pateikta')

    @api.multi
    def is_project_manager(self):
        self.ensure_one()
        return self.has_group('project.group_project_manager')


ResUsers()


class TimesheetValidationLine(models.TransientModel):
    _name = "timesheet.validation.line"

    user_id = fields.Many2one('res.users', string='Darbuotojas')
    validate = fields.Boolean(string='Patvirtinti')
    validation_id = fields.Many2one('timesheet.validation', string='Patvirtinimas')


TimesheetValidationLine()


class TimesheetValidation(models.TransientModel):
    _name = "timesheet.validation"

    def default_date(self):
        if self._context.get('date'):
            grid_range = self._context.get('grid_range')
            if grid_range:
                if grid_range['name'] == 'month':
                    return datetime.strptime(self._context.get('date'), tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=31)
                elif grid_range['name'] == 'week':
                    return datetime.strptime(self._context.get('date'), tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(weekday=SU(+1))
        return datetime.now()

    def default_line_ids(self):
        user_ids = self._context.get('user_ids', False)
        if user_ids:
            lines = []
            for user_id in user_ids:
                lines.append((0, 0, {'user_id': user_id, 'validate': True}))
            return lines

    date = fields.Date(string='Patvirtinta iki', default=default_date, required=True)
    next_date = fields.Date(compute='_compute_next_date')
    line_ids = fields.One2many('timesheet.validation.line', 'validation_id', default=default_line_ids)
    show_warning = fields.Boolean(string='Įspėjimas', compute='_compute_show_warning')

    @api.one
    @api.depends('date')
    def _compute_next_date(self):
        cr_dt = fields.Date.from_string(self.date) + relativedelta(days=+1)
        self.next_date = fields.Date.to_string(cr_dt)

    @api.one
    @api.depends('date', 'line_ids.validate')
    def _compute_show_warning(self):
        self.show_warning = False
        for line in self.line_ids:
            line_dt = fields.Date.from_string(line.user_id.timesheet_validated)
            wz_dt = fields.Date.from_string(self.date)
            if line_dt and wz_dt and line_dt > wz_dt and line.validate:
                self.show_warning = True
                return

    @api.multi
    def action_validate(self):
        if not self.env.user.is_project_manager():
            return
        for r in self:
            for line in r.line_ids:
                if line.validate:
                    user_id = line.user_id.id
                    self.sudo().with_context({'ignore_state': True}).env['account.analytic.line'].search([('user_id', '=', user_id), ('date', '<=', r.date), ('validated', '=', False)]).write({'validated': True})
                    self.sudo().with_context({'ignore_state': True}).env['account.analytic.line'].search([('user_id', '=', user_id), ('date', '>', r.date), ('validated', '=', True)]).write({'validated': False})
                    line.sudo().user_id.timesheet_validated = r.date


TimesheetValidation()


class TimesheetSubmissionLine(models.TransientModel):
    _name = "timesheet.submission.line"
    _inherit = "timesheet.validation.line"

    validate = fields.Boolean(string='Pateikti')
    validation_id = fields.Many2one('timesheet.submission', string='Pateikimas')


TimesheetSubmissionLine()


class TimesheetSubmission(models.TransientModel):
    _name = "timesheet.submission"
    _inherit = "timesheet.validation"

    line_ids = fields.One2many('timesheet.submission.line', 'validation_id')

    @api.one
    @api.depends('date', 'line_ids.validate')
    def _compute_show_warning(self):
        self.show_warning = False
        for line in self.line_ids:
            line_dt = line.user_id.timesheet_submitted
            wz_dt = self.date
            if line_dt and wz_dt and line_dt > wz_dt and line.validate:
                self.show_warning = True
                return

    @api.multi
    def action_validate(self):
        return

    @api.multi
    def action_submit(self):
        for r in self:
            for line in r.line_ids:
                if line.validate:
                    user_id = line.user_id.id
                    self.with_context({'ignore_state': True}).env['account.analytic.line'].search([('user_id', '=', user_id),
                                                                                                   ('date', '<=', r.date),
                                                                                                   ('submitted', '=', False)]).write({'submitted': True})
                    self.with_context({'ignore_state': True}).env['account.analytic.line'].search([('user_id', '=', user_id),
                                                                                                   ('date', '>', r.date),
                                                                                                   ('submitted', '=', True)]).write({'submitted': False})
                    line.user_id.sudo().timesheet_submitted = r.date


TimesheetSubmission()


class TimesheetMonthPattern(models.TransientModel):
    _name = 'timesheet.month.pattern'

    def _prev_month(self):
        prev_month = (fields.Datetime.from_string(self._context.get('start', fields.Date.today()))+relativedelta(months=-1)).strftime('%Y%m')
        return self.env['months'].search([('code', '=', prev_month)], limit=1).id

    def _default_project_ids(self):
        user_id = self._context.get('user_id', False) or self._uid
        start = self._context.get('start', False)
        end = self._context.get('end', False)
        if user_id and start and end:
            ids = self.env['account.analytic.line'].search([('is_timesheet', '=', True),
                                                            ('user_id', '=', user_id),
                                                            ('date', '>=', start),
                                                            ('date', '<=', end)]).mapped('project_id').ids
            return ids

    def default_month_filter(self):
        curr_date = datetime.now()
        code_from = (curr_date + relativedelta(months=-4)).year * 100 + (curr_date + relativedelta(months=-4)).month
        code_to = curr_date.year * 100 + curr_date.month
        months = self.env['months'].search([('code', '>', code_from),
                                            ('code', '<', code_to)])
        return months.ids

    month = fields.Many2one('months', string='Mėnuo, iš kurio paimti projektus', default=_prev_month, required=True)
    month_filter = fields.Many2many('months', string='Month domain', default=default_month_filter)
    project_ids = fields.Many2many('project.project', default=_default_project_ids)
    project_filter_ids = fields.Many2many('project.project', default=_default_project_ids)

    @api.onchange('month')
    def onchange_month(self):
        if self.month:
            user_id = self._context.get('user_id') or self._uid
            start = (datetime.strptime(str(self.month.code), '%Y%m')+relativedelta(day=1)).date()
            end = (datetime.strptime(str(self.month.code), '%Y%m')+relativedelta(day=31)).date()
            if user_id and start and end:
                ids = self.env['account.analytic.line'].search([('is_timesheet', '=', True),
                                                                ('user_id', '=', user_id),
                                                                ('date', '>=', start),
                                                                ('date', '<=', end)]).mapped('project_id').ids
                #ROBO: projektas, kurį tau priskyrė vadovas, o tu neturi teisių skaityti to 'project.project' = prieigos klaida
                self.project_ids = ids

    @api.multi
    def action_make_pattern(self):
        self.ensure_one()
        user_id = self._context.get('user_id') or self._uid
        view_start = self._context.get('start', False)
        view_end = self._context.get('end', False)

        if user_id and self.month and self.month.code and view_start and view_end:
            pattern_start = (datetime.strptime(str(self.month.code), '%Y%m') + relativedelta(day=1)).date()
            pattern_end = (datetime.strptime(str(self.month.code), '%Y%m') + relativedelta(day=31)).date()

            view_ids = self.env['account.analytic.line'].search([('is_timesheet', '=', True),
                                                                 ('user_id', '=', user_id),
                                                                 ('date', '>=', view_start),
                                                                 ('date', '<=', view_end)]).mapped(lambda r: (r.project_id.id, r.task_id.id))
            view_ids = set(view_ids)

            pattern_ids = self.env['account.analytic.line'].search([('is_timesheet', '=', True),
                                                                    ('user_id', '=', user_id),
                                                                    ('date', '>=', pattern_start),
                                                                    ('date', '<=', pattern_end),
                                                                    ('project_id', 'in', self.project_ids.ids)]).mapped(lambda r: (r.project_id.id, r.task_id.id))
            pattern_ids = set(pattern_ids)

            new_ids = pattern_ids - view_ids

            for id in new_ids:
                rec = {
                    'user_id': user_id,
                    'date': view_start,
                    'unit_amount': 0,
                    'project_id': id[0],
                    'task_id': id[1]
                }
                self.env['account.analytic.line'].create(rec)


TimesheetMonthPattern()


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    is_timesheet = fields.Boolean(string='Laiko žiniaraštis', compute='_compute_is_timesheet', store=True)
    validated = fields.Boolean(string='Patvirtintas', readonly=True, groups="project.group_project_manager", default=False, copy=False)
    submitted = fields.Boolean(string='Pateiktas', readonly=True, default=False, copy=False)

    @api.multi
    def month_pattern(self):
        date = self._context.get('grid_anchor') or fields.Date.today()
        if date:
            start = fields.Date.from_string(date) + relativedelta(day=1)
            end = fields.Date.from_string(date) + relativedelta(day=31)
            if len(self.mapped('user_id')) > 1:
                raise exceptions.UserError(_('Visos analitinės eilutės turi būti to paties naudotojo.'))
            ctx = {
                'start': str(start),
                'end': str(end),
                'user_id': self.mapped('user_id').id,
            }
            return {
                'context': ctx,
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'timesheet.month.pattern',
                'view_id': self.env.ref('robo_projects.timesheet_pattern_view_form').id,
                'type': 'ir.actions.act_window',
                'target': 'new',
            }
        return {}

    @api.multi
    def validate(self):
        ctx = {
                'user_ids': self.mapped('user_id').ids,
                'date': self.mapped('date') and max(self.mapped('date')),
               }
        if not (ctx['user_ids']):
           raise exceptions.Warning(_('Nėra žiniaraščių, kurių dar nebūtumėte pateikę.'))

        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'timesheet.validation',
            'view_id': self.env.ref('robo_projects.timesheet_validation_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def submit(self):
        ctx = {
            'user_ids': self.mapped('user_id').ids,
            'date': self.mapped('date') and max(self.mapped('date')),
        }
        if not (ctx['user_ids']):
            raise exceptions.Warning(_('Nėra žiniaraščių, kurių dar nebūtumėte pateikę.'))

        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'timesheet.submission',
            'view_id': self.env.ref('robo_projects.timesheet_submission_view_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.one
    @api.depends('project_id')
    def _compute_is_timesheet(self):
        self.is_timesheet = self.project_id and True or False

    @api.model
    def read_grid_domain(self, field=None, col_range=None):
        _tmp, start, end, _tmp = self.get_range(field, col_range)
        return ['&', ["date", ">=", fields.Date.to_string(start)], ["date", "<=", fields.Date.to_string(end)]]

    @api.multi
    def _grid_adjust(self, row_domain, col_field, column_name, cell_field, diff):
        # ROBO: no action if domain without user, project_id, task_id

        stop_adjust = not all([rec in str(row_domain) for rec in ['user_id', 'project_id', 'task_id']])
        if stop_adjust:
            return
        # ROBO: edit last created that specific day or create new
        col_field_value = column_name.split('/')[0]
        records_in_row = self.sudo().search(row_domain)
        rec_to_edit = records_in_row.filtered(lambda r: r.date == col_field_value).sorted(lambda r: r.create_date, reverse=True)
        if rec_to_edit:
            rec_to_edit = rec_to_edit[0]
            new_value = rec_to_edit[cell_field] + diff
            rec_to_edit.write({cell_field: new_value})
        else:
            if records_in_row:  # if row is displayed, there is always a record
                records_in_row[0].copy({cell_field: diff, col_field: column_name.split('/')[0]})


    @api.multi
    def grid_adjust(self, row_domain, col_field, column_name, cell_field, value):

        domain = normalize_domain(row_domain)
        domain = ['&'] + domain + [[col_field, '=', column_name.split('/')[0]]]

        current_value = sum(self.env[self._name].search(domain).mapped(cell_field))
        diff = value - current_value

        return self._grid_adjust(row_domain, col_field, column_name, cell_field, diff)

    @api.multi
    def unlink(self):
        for rec in self:
            if rec.is_timesheet:
                user = rec.user_id
                if user:
                    if not self.env.user.is_project_manager():
                        lock_date = max(user.sudo().timesheet_validated, user.timesheet_submitted)
                        if rec.date <= lock_date:
                            raise exceptions.UserError('Negalima trinti žiniaraščio įrašų iki paskutinės patvirtinimo/pateikimo dienos - %s' % lock_date)
                    else:
                        lock_date = user.sudo().timesheet_validated
                        if rec.date <= lock_date:
                            raise exceptions.UserError('Negalima trinti žiniaraščio įrašų iki paskutinės patvirtinimo dienos- %s.' % lock_date)

        return super(AccountAnalyticLine, self).unlink()

    @api.model
    def create(self, values):
        user_id = values.get('user_id')
        if values.get('project_id'):
            user = self.env['res.users'].browse(user_id)
            if user:
                if not self.env.user.is_project_manager():
                    lock_date = max(user.sudo().timesheet_validated, user.sudo().timesheet_submitted)
                    if values.get('date') <= lock_date:
                        raise exceptions.UserError('Negalima kurti naujų žiniaraščio įrašų iki paskutinės patvirtinimo/pateikimo dienos - %s' % lock_date)
                else:
                    lock_date = user.sudo().timesheet_validated
                    if values.get('date') <= lock_date:
                        raise exceptions.UserError('Negalima kurti naujų žiniaraščio įrašų iki paskutinės patvirtinimo dienos- %s.' % lock_date)

        return super(AccountAnalyticLine, self).create(values)

    @api.multi
    def write(self, values):
        lock_fields = ['unit_amount', 'date', 'user_id', 'project_id', 'task_id']
        if any(lf in values for lf in lock_fields):
            for rec in self:
                if rec.is_timesheet:
                    user_ids = [values.get('user_id'), rec.user_id.id]
                    user_ids = [u_id for u_id in user_ids if u_id]  # we might be writing user_id
                    user_ids = list(set(user_ids))
                    for user in self.sudo().env['res.users'].browse(user_ids):
                        dates = list({values.get('date', rec.date), rec.date})
                        for date in dates:
                            if not self.env.user.is_project_manager():
                                lock_date = max(user.sudo().timesheet_validated, user.timesheet_submitted)
                                if date <= lock_date:
                                    raise exceptions.UserError('Negalima keisti žiniaraščio eilučių iki paskutinės patvirtinimo/pateikimo dienos - %s' % lock_date)
                            else:
                                lock_date = user.timesheet_validated
                                if date <= lock_date:
                                    raise exceptions.UserError('Negalima keisti žiniaraščio eilučių iki paskutinės patvirtinimo dienos - %s' % lock_date)

        return super(AccountAnalyticLine, self).write(values)

    @api.model
    def remove_grid_line(self, row_domain=None):
        if row_domain:
            remove_lines = self.search(row_domain)
            if not all(tools.float_is_zero(l.unit_amount, precision_digits=2) for l in remove_lines):
                raise exceptions.UserError(_('Negalite ištrinti šios eilutės, nes yra nenulinių įrašų.'))
            else:
                remove_lines.unlink()

    @api.model
    def get_range(self, col_field, col_range=None):

        col_range = col_range or {}

        # IMPORTANT
        # currently col_field = 'date' is the only working setting
        if col_field != 'date':
            raise exceptions.UserError('Sisteminė klaida. Kreipkitės į administratorių.')

        if self._context.get('default_date'):
            current_day = fields.Datetime.from_string(self._context.get('default_date'))
        else:
            current_day = datetime.utcnow()
        period = col_range.get('name')
        if period == 'week':
            start = current_day + relativedelta(weekday=MO(-1))
            end = current_day + relativedelta(weekday=SU(+1))
        elif period == 'month':
            start = current_day + relativedelta(day=1)
            end = current_day + relativedelta(day=31)
        # ROBO: remove in the future
        else:
            raise exceptions.UserError('Sisteminė klaida. Kreipkitės į administratorių.')
        # truncate;
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end.replace(hour=0, minute=0, second=0, microsecond=0)
        current_day = current_day.replace(hour=0, minute=0, second=0, microsecond=0)

        return period, start, end, current_day

    @api.model
    def _get_weekday_format(self, dt):
        my_locale = self._context.get('lang', 'en_US')
        return babel.dates.format_date(dt, format='EEE\n MMM\n dd', locale=my_locale)

    @api.model
    def read_grid(self, cell_field='unit_amount', col_field='date', domain=None, col_range=None, row_fields=None):
        domain = normalize_domain(domain or [])
        row_fields = row_fields or ['user_id']

        no_user_id = 'user_id' not in str(domain)
        no_project_id = 'project_id' not in row_fields
        no_task_id = 'task_id' not in row_fields

        empl_val_datetime = None
        empl_sub_datetime = None
        if not no_user_id:
            domain_user_id = self.search(domain).mapped('user_id')
            domain_user_id = domain_user_id and domain_user_id[0]
            empl_val_datetime = fields.Datetime.from_string(domain_user_id.sudo().timesheet_validated)
            empl_sub_datetime = fields.Datetime.from_string(domain_user_id.timesheet_submitted)

        today = datetime.utcnow()
        # Period
        period, start, end, current_day = self.get_range(col_field, col_range)

        # Available columns
        cols = []
        indx = start
        holidays = self.env['sistema.iseigines'].search([('date', '>=', start), ('date', '<=', end)]).mapped('date')
        while indx <= end:
            next = indx + relativedelta(days=+1)
            indx_str = indx.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            next_str = next.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            is_current = today.date() == indx.date()
            col_domain = ['&', ["date", ">=", indx_str], ["date", "<", next_str]],
            date_weekday = self._get_weekday_format(indx)
            encoding = locale.getlocale()[1]
            if encoding == '1257':
                try:
                    date_weekday = date_weekday.decode(encoding) # we could probably always decode, but it is usually not nesccesary
                except:
                    pass
            values = {
                'date': [indx_str + '/' + next_str, date_weekday.title()]}

            cols.append({
                'domain': col_domain,
                'is_current': is_current,
                'is_holiday': (indx_str in holidays) or (indx.isoweekday() in [6, 7]),
                'values': values
            })

            indx = next

        # Format grid
        grid = []
        cols_domain = ['&', ["date", ">=", start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)], ["date", "<=", end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)]]
        domain = [u'&']+domain+cols_domain

        # main? unit_amount != 0
        main_grid_lines = self.read_group(domain, row_fields + ['date'] + [cell_field], row_fields + ['date:day'], lazy=False)  # could we avoid two read groups?
        grid_pairs = self.read_group(domain, row_fields+[cell_field], row_fields, lazy=False)

        if main_grid_lines:
            exmpl_domain = main_grid_lines[0]['__domain']
            for line in grid_pairs:
                grid_lines = []
                indx = start
                while indx <= end:

                    def _check_equal(r):
                        for f in row_fields:
                            if r[f] != line[f]:
                                return False
                            try:
                                date = dateutil.parser.parse(r['date:day'])
                                date = date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)[:10]
                                indx_str = indx.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)[:10]
                                if indx_str != date:
                                    return False
                            except:
                                # read_group formatof datetime:day!
                                locale = self._context.get('lang', 'en_US')
                                label = babel.dates.format_date(
                                    indx, format='dd MMM yyyy',
                                    locale=locale
                                )
                                if r['date:day'] != label:
                                    return False
                        return True

                    grid_value = filter(_check_equal, main_grid_lines) or {}

                    # somehow update/create domain for some grid elements (where unit_amount == 0)
                    next = indx + relativedelta(days=+1)
                    indx_str = indx.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    next_str = next.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    if not grid_value:
                        def _renew_domain(el):
                            if type(el) is tuple or type(el) is list:
                                if el[0] in row_fields:
                                    return el[0], el[1], line[el[0]] and line[el[0]][0]
                                if el[0] == 'date' and el[1] == '>=':
                                    return el[0], el[1], indx_str
                                if el[0] == 'date' and el[1] == '<':
                                    return el[0], el[1], next_str
                            return el

                        # last two should be date period domain;
                        grid_value['__domain'] = map(_renew_domain, exmpl_domain[:-2])+exmpl_domain[-2:]
                    else:
                        grid_value = grid_value[0]

                    validated = empl_val_datetime and indx <= empl_val_datetime
                    submitted = empl_sub_datetime and indx <= empl_sub_datetime

                    grid_lines.append({
                        'submitted': submitted,
                        'validated': validated,
                        'readonly': submitted or validated or no_user_id or no_task_id or no_project_id,
                        'domain': grid_value.get("__domain", []),
                        'is_current': indx.date() == today.date(),
                        'is_holiday':  (indx_str in holidays) or (indx.isoweekday() in [6, 7]),
                        'size': grid_value.get("__count", 0),
                        'value': grid_value.get(cell_field, 0),
                        'date': str(indx.date()),
                    })
                    indx = next
                grid.append(grid_lines)

        if period == 'month':
            next = {
                'default_date': (current_day + relativedelta(months=+1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'grid_anchor': (current_day + relativedelta(months=+1,)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            }
            prev = {
                'default_date': (current_day + relativedelta(months=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'grid_anchor': (current_day + relativedelta(months=-1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            }
        else:
            next = {
                'default_date': (current_day + relativedelta(days=+1, weekday=MO(+1))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'grid_anchor': (current_day + relativedelta(days=+1, weekday=MO(+1))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            }
            prev = {
                'default_date': (current_day + relativedelta(days=-1, weekday=MO(-1))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                'grid_anchor': (current_day + relativedelta(days=-1, weekday=MO(-1))).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            }

        # row headers
        rows = []
        for row in grid_pairs:
            values = {}
            for f in row_fields:
                values[f] = row[f]
            rows.append({
                'domain': row.get('__domain') or domain,
                'values': values
            })

        rez = {
            'cols': cols,
            'grid': grid,
            'next': next,
            'prev': prev,
            'rows': rows,
        }
        return rez

    @api.model
    def move_to_new_timesheets(self):
        analytic_lines_confirm = self.env['account.analytic.line'].search([('sheet_id.state', '=', 'confirm')])
        analytic_lines_done = self.env['account.analytic.line'].search([('sheet_id.state', '=', 'done')])
        analytic_lines_confirm.with_context(ignore_state=True).write({'timesheet_submitted': True})
        analytic_lines_done.with_context(ignore_state=True).write({'timesheet_submitted': True,
                                                                   'timesheet_validated': True})


AccountAnalyticLine()
