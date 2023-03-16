# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, tools, exceptions
from odoo.addons.queue_job.job import job, identity_exact
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class PeriodicFrontBankStatement(models.Model):
    _name = 'periodic.front.bank.statement'

    front_statement_id = fields.Many2one('front.bank.statement', string='Mokėjimo ruošinio šablonas',
                                         required=True, readonly=True)
    front_statement_ids = fields.One2many('front.bank.statement', 'periodic_id')
    date = fields.Date(string='Kito ruošinio data')
    date_stop = fields.Date(string='Sustabdyti nuo')
    action = fields.Selection([('no', 'Neinformuoti vadovo'),
                               ('inform', 'Informuoti vadovą'),
                               ('send_bank', 'Informuoti ir siųsti į Banką')], string='Automatinis veiksmas',
                              default='no', required=True)
    interval = fields.Selection([('week', 'Savaitė'),
                                 ('month', 'Mėnuo')], string='Intervalas', required=True, default='month')
    interval_number = fields.Integer(string='Intervalo numeris', help='Pakartoti kiekvieną x', default=1, required=True)

    @api.multi
    @api.constrains('action')
    def _check_action(self):
        """
        Constraints //
        If action is set to 'send_bank' check whether parent
        statement journal belongs to integrated banks,
        raise an error if it does not.
        :return: None
        """
        for rec in self:
            if rec.action == 'send_bank' and not rec.front_statement_id.api_integrated_journal:
                raise exceptions.ValidationError(
                    _('Negalite automatiškai siųsti šio šablono į banką, '
                      'šablono banko sąskaita nepriklauso integruotiems bankams'))

    @api.multi
    def set_next_date(self):
        self.ensure_one()
        if self.interval == 'week':
            delta = {'weeks': self.interval_number}
        else:
            statement_date = datetime.strptime(self.front_statement_id.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            statement_day = statement_date.day
            last_day_date = statement_date + relativedelta(day=31)
            if statement_date.day == last_day_date.day:
                last_day = True
            else:
                last_day = False
            new_day = 31 if last_day else statement_day
            delta = {'months': self.interval_number, 'day': new_day}
        date = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
        date += relativedelta(**delta)
        if self.date_stop and date > datetime.strptime(self.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT):
            self.date = False
        else:
            self.date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    @job
    def run(self):
        """ Create front bank statement from periodic records """
        for rec in self:
            try:
                current_date = datetime.utcnow()
                if datetime.strptime(rec.date, tools.DEFAULT_SERVER_DATE_FORMAT) > current_date:
                    continue
                if rec.date_stop and datetime.strptime(rec.date_stop, tools.DEFAULT_SERVER_DATE_FORMAT) < current_date:
                    continue
                statement_id = rec.front_statement_id.copy({
                    'date': rec.date,
                    'periodic_id': rec.id,
                    'active': True,
                })
                statement_id.message_unsubscribe([self.env.user.partner_id.id])
                if rec.action in ['inform', 'send_bank']:
                    statement_id.inform()
                if rec.action == 'send_bank':
                    statement_id.send_to_bank()
                rec.set_next_date()
                self._cr.commit()
            except Exception as exc:
                _logger.info('Bank Statement exception %s' % exc.args[0])
                import traceback
                message = traceback.format_exc()
                self._cr.rollback()
                if message:
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'subject': 'Failed to create periodic front bank statement [%s]' % self._cr.dbname,
                        'error_message': message,
                    })
                    self._cr.commit()

    @api.model
    def cron_create_periodic_front_statements(self):
        current_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodic_ids = self.search([('date', '<=', current_date),
                                    '|', ('date_stop', '=', False), ('date_stop', '>', current_date)])

        for periodic in periodic_ids:
            periodic.with_delay(channel='root.statement_import', eta=30, identity_key=identity_exact).run()

    @api.multi
    def delete(self):
        self.ensure_one()
        self.unlink()

    @api.multi
    def open_statements(self):
        self.ensure_one()
        if self.front_statement_ids:
            action = self.env.ref('robo.open_payments_report').read()[0]
            action['domain'] = [('periodic_id', '=', self.id)]
            return action
        else:
            raise exceptions.Warning(_('Dar nėra sukurtų periodinių mokėjimo ruošinių.'))


PeriodicFrontBankStatement()


class FrontBankStatement(models.Model):
    _inherit = 'front.bank.statement'

    periodic_ids = fields.One2many('periodic.front.bank.statement', 'front_statement_id', copy=False,
                                   groups='robo_basic.group_robo_periodic_front_statement')
    periodic_id = fields.Many2one('periodic.front.bank.statement', string='Periodinis įrašas', readonly=True,
                                  groups='robo_basic.group_robo_periodic_front_statement',
                                  ondelete='set null', copy=False)
    has_periodic_ids = fields.Boolean(compute='_has_periodic_ids')

    @api.one
    def _has_periodic_ids(self):
        if self.env.user.has_group('robo_basic.group_robo_periodic_front_statement'):
            self.has_periodic_ids = True if self.periodic_ids else False

    @api.multi
    def make_periodic(self):
        self.ensure_one()
        if not self.periodic_ids:
            if not self.date:
                raise exceptions.Warning(_('Turite nurodyti mokėjimo ruošinio datą, '
                                           'kad galėtume padaryti jį periodiniu.'))
            date = self.date
            date_st = datetime.strptime(self.date, tools.DEFAULT_SERVER_DATE_FORMAT)
            curr_date = datetime(datetime.utcnow().year, datetime.utcnow().month, datetime.utcnow().day)
            if (date_st + relativedelta(months=1)) <= curr_date:
                date = datetime(curr_date.year, curr_date.month, date_st.day).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            periodic_id = self.env['periodic.front.bank.statement'].create({
                'front_statement_id': self.id,
                'date': date,
            })
            periodic_id.set_next_date()
            self.periodic_id = periodic_id.id

    @api.multi
    def stop_periodic(self):
        self.ensure_one()
        if self.periodic_ids:
            self.periodic_ids.unlink()


FrontBankStatement()
