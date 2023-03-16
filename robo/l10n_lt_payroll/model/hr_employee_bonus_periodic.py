# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime

from dateutil.relativedelta import relativedelta
from odoo import _, models, fields, api, tools, exceptions


class HrEmployeeBonusPeriodic(models.Model):
    _name = 'hr.employee.bonus.periodic'

    bonus_id = fields.Many2one('hr.employee.bonus', string='Premijų šablonas', required=True)
    bonus_ids = fields.One2many('hr.employee.bonus', 'periodic_id', string='Sukurtos premijos')
    date = fields.Date(string='Kitos premijos data')
    date_stop = fields.Date(string='Sustabdyti nuo')
    action = fields.Selection([('no', 'Netvirtinti'),
                               ('open', 'Tvirtinti')], string='Automatinis veiksmas',
                              default='no', required=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', related='bonus_id.employee_id', store=True,
                                  readonly=True, required=True)

    slip_ids = fields.Many2many('hr.payslip', compute='_compute_slip_ids')

    @api.one
    @api.depends('employee_id', 'date')
    def _compute_slip_ids(self):
        HrPayslip = self.env['hr.payslip']
        payslips = HrPayslip
        if self.date:
            payslips = HrPayslip.search([
                ('employee_id', '=', self.employee_id.id),
                ('date_from', '<=', self.date),
                ('date_to', '>=', self.date)
            ])
        self.slip_ids = payslips.ids

    @api.model
    def create(self, vals):
        res = super(HrEmployeeBonusPeriodic, self).create(vals)
        res.mapped('slip_ids')._compute_planned_periodic_payments_exist()
        return res

    @api.multi
    def set_next_date(self):
        self.ensure_one()
        date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_day = date.day
        last_day_date = date + relativedelta(day=31)
        if date.day == last_day_date.day:
            last_day = True
        else:
            last_day = False
        new_day = 31 if last_day else date_day
        date += relativedelta(months=1, day=new_day)
        if self.date_stop and date > datetime.strptime(self.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT):
            self.date = False
        else:
            self.date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def run(self):
        for rec in self:
            try:
                cdate = datetime.utcnow()
                if not rec.date_stop and rec.employee_id.contract_id.date_end:
                    rec.date_stop = rec.employee_id.contract_id.date_end
                if not self._context.get('force_create') and \
                        datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) > cdate:
                    continue
                if rec.date_stop and datetime.strptime(rec.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT).date() < \
                        cdate.date() and not self._context.get('skip_past_date_check'):
                    continue
                start_date = datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)
                end_date = start_date + relativedelta(day=31)
                bonus_id = rec.bonus_id.copy({
                    'for_date_from': start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'for_date_to': end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'payment_date_from': start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'payment_date_to': end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                })
                if rec.action in ['open']:
                    bonus_id.with_context(lang=self.env.context.get('lang') or 'lt_LT').confirm() #lang is None because of copy
                rec.set_next_date()
                self._cr.commit()
            except:
                import traceback
                message = traceback.format_exc()
                self._cr.rollback()
                if message:
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'subject': 'Failed to create periodic bonus [%s]' % self._cr.dbname,
                        'error_message': message,
                    })
                    self._cr.commit()

    @api.model
    def cron_create_periodic_bonus(self):
        cdate = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodic_ids = self.search([('date', '<=', cdate),
                                    '|', ('date_stop', '=', False), ('date_stop', '>=', cdate)])
        periodic_ids.run()

    @api.multi
    def delete(self):
        self.ensure_one()
        payslips = self.slip_ids
        self.unlink()
        payslips._compute_planned_periodic_payments_exist()

    @api.multi
    def open_bonuses(self):
        self.ensure_one()
        if self.bonus_ids:
            action = self.env.ref('l10n_lt_payroll.action_open_hr_employee_bonus').read()[0]
            action['domain'] = [('periodic_id', '=', self.id)]
            return action
        else:
            raise exceptions.Warning(_('Dar nėra sukurtų periodinių bonusų.'))

    @api.model
    def create_hr_employee_bonus_periodic_up_front_action(self):
        action = self.env.ref('l10n_lt_payroll.hr_employee_bonus_periodic_up_front_action')
        if action:
            action.create_action()

    @api.multi
    def create_hr_employee_bonus_periodic_up_front(self):
        """
        Action that creates the upcoming bonus for selected employees;
        """
        today_dt = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        records = self.filtered(lambda periodic_bonus: periodic_bonus.date_stop < today_dt and periodic_bonus.date)
        if not records:
            raise exceptions.ValidationError(_('All of the selected periodic bonuses have been finished already.'))
        for rec in records:
            rec.with_context(force_create=True).run()


HrEmployeeBonusPeriodic()
