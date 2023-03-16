from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _


class HrEmployeeKindPeriodic(models.Model):
    _name = 'hr.employee.kind.periodic'

    kind_id = fields.Many2one('hr.employee.natura', string='Payment in kind template', required=True)
    kind_ids = fields.One2many('hr.employee.natura', 'periodic_id', string='Created payments')
    date = fields.Date(string='Next payment date')
    date_stop = fields.Date(string='Until')
    employee_id = fields.Many2one('hr.employee', string='Employee', related='kind_id.employee_id',
                                  store=True, readonly=True)

    @api.multi
    def set_next_date(self):
        self.ensure_one()
        if not self.date:
            return
        date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_day = date.day
        last_day_date = date + relativedelta(day=31)
        last_day = date.day == last_day_date.day
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
                current_date = datetime.utcnow()
                if not rec.date_stop and rec.employee_id.contract_id.date_end:
                    rec.date_stop = rec.employee_id.contract_id.date_end
                if datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) > current_date:
                    continue
                if rec.date_stop and datetime.strptime(rec.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT).date() < \
                        current_date.date():
                    continue
                start_date = datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(day=1)
                end_date = start_date + relativedelta(day=31)
                kind_payment = rec.kind_id.copy({
                    'date_from': start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'date_to': end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                })
                kind_payment.confirm()
                rec.set_next_date()
                self._cr.commit()
            except:
                import traceback
                message = traceback.format_exc()
                self._cr.rollback()
                if message:
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'subject': 'Failed to create periodic payment in kind [%s]' % self._cr.dbname,
                        'error_message': message,
                    })
                    self._cr.commit()

    @api.model
    def cron_create_periodic_payment_in_kind(self):
        current_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodic_payments = self.search([('date', '<=', current_date), '|', ('date_stop', '=', False),
                                         ('date_stop', '>=', current_date)])
        periodic_payments.run()

    @api.multi
    def open_related_kind_payments(self):
        self.ensure_one()
        if not self.kind_ids:
            raise exceptions.UserError(_('No related employee payments in kind created.'))
        action = self.env.ref('l10n_lt_payroll.action_open_natura').read()[0]
        action['domain'] = [('periodic_id', '=', self.id)]
        return action
