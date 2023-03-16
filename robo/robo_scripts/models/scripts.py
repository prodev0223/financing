# -*- coding: utf-8 -*-
from odoo import fields, models, api, _, tools, exceptions
from odoo.tools.safe_eval import safe_eval
from odoo.addons.queue_job.job import identity_exact
import odoo
from dateutil.relativedelta import relativedelta
from datetime import datetime
import base64
import logging
import random
from urlparse import urljoin
import werkzeug
import traceback
import re
import json
from collections import Counter
import string
import time
import pytz
import requests
from . import tools as safe_tools

_logger = logging.getLogger(__name__)

_intervalTypes = {
    'year': lambda interval: relativedelta(years=interval),
    'day': lambda interval: relativedelta(days=interval),
    'hour': lambda interval: relativedelta(hours=interval),
    'week': lambda interval: relativedelta(days=7*interval),
    'month': lambda interval: relativedelta(months=interval),
    'minute': lambda interval: relativedelta(minutes=interval),
}


class Script(models.Model):

    _name = 'script'
    _order = 'create_date desc'

    def default_code(self):
        return '''# env: database Environment
# datetime: datetime object
# relativedelta: relativedelta object
# tools: robo tools
# base64: base64 module
# random: random module
# exceptions: exceptions module
# logging: logging module
# string: string module
# _: translation module
# obj: current script
# requests: requests module
# begin_table([headers]), add_row([row]), end_table: Format HTML table for return
# If you're getting an error and need to DEBUG - surround your code in a try-except clause and do 'message = traceback.format_exc()' to grab the full traceback
# Easily check output with {}[str(your_output_here)]
'''

    name = fields.Char(string='Name', required=True)
    code = fields.Text(string='Python code', default=default_code)
    date = fields.Datetime(string='Scheduled execution')
    interval = fields.Selection([('minute', 'Minute'),
                                 ('hour', 'Hour'),
                                 ('day', 'Day'),
                                 ('week', 'Week'),
                                 ('month', 'Month'),
                                 ('year', 'Year'),
                                 ], string='Interval')
    interval_number = fields.Integer('Interval number', default=1)
    running = fields.Boolean(copy=False)
    skip_update_window = fields.Boolean(string='Skip update window', help='Do not set the next call during update window')
    script_history_ids = fields.One2many('script.history', 'script_id')

    @api.constrains('skip_update_window', 'interval')
    def _check_skip_update_window(self):
        if any(rec.skip_update_window and rec.interval not in ['hour', 'minute'] for rec in self):
            raise exceptions.ValidationError(
                _('You can only skip update window if the interval unit is in hours or minutes'))

    @api.multi
    def execute_call(self):
        if not self.env.user.has_group('base.group_system'):
            return
        script_history_obj = self.env['script.history']
        env = self.env
        cr = self.env.cr
        try:
            eval_context = {
                'datetime': datetime,
                'env': env,
                'relativedelta': relativedelta,
                'tools': safe_tools,
                'base64': base64,
                'url_encode': werkzeug.url_encode,
                'url_join': urljoin,
                'Counter': Counter,
                'exceptions': exceptions,
                'random': random,
                'logging': logging,
                'string': string,
                'traceback': traceback,
                'json': json,
                're': re,
                '_': _,
                'obj': self,
                'time': time,
                'requests': requests,
                'begin_table': lambda headers: '<table border="1"><tr>' + ''.join('<td><b>%s</b></td>' % str(h) for h in headers) + '</tr>',
                'add_row': lambda line: '<tr>' + ''.join('<td>%s</td>' % str(l) for l in line) + '</tr>',
                'end_table': lambda: '</table>',
                'identity_exact': identity_exact,
            }
            locals = {}
            safe_eval(self.code, eval_context, locals, mode='exec', nocopy=True)
            script_history_obj.sudo().create({
                'name': self.name,
                'script_id': self.id,
                'code': self.code,
                'date': datetime.now(),
                'user': self.env.user.id,
                'status': 'Success',
                'state': 'success',
            })
        except Exception as exc:
            _logger.info('Exception: %s' % ', '.join(map(str, list(exc.args))))
            env.invalidate_all()
            cr.rollback()
            script_history_obj.sudo().create({
                'name': self.name,
                'script_id': self.id,
                'code': self.code,
                'date': datetime.now(),
                'user': self.env.user.id,
                'status': 'Fail. Exception message: %s' % ', '.join(map(str, list(exc.args))),
                'state': 'fail',
            })
            self.write({'running': False})
            cr.commit()
            return False
        self.write({'running': False})
        cr.commit()
        return True

    @api.multi
    def _set_next_date(self):
        self.ensure_one()
        if self.interval:
            now = fields.Datetime.context_timestamp(self, datetime.now())
            if self.skip_update_window and self.interval in ['hour', 'minute']:
                # We assume that interval_number never pushes it into the next days update window
                update_start = self.env['ir.config_parameter'].get_param('update_window_start', None)
                update_end = self.env['ir.config_parameter'].get_param('update_window_end', None)
                if update_start and update_end:
                    try:
                        start_h, start_m = divmod(int(update_start), 100)
                        end_h, end_m = divmod(int(update_end), 100)
                        update_start = now + relativedelta(hour=start_h, minute=start_m)
                        update_end = now + relativedelta(hour=end_h, minute=end_m)
                        if update_start <= now <= update_end:
                            now = update_end
                    except:
                        pass
            next_call = fields.Datetime.context_timestamp(self, fields.Datetime.from_string(self.date))
            interval_number = self.interval_number or 1
            while next_call < now:
                next_call += _intervalTypes[self.interval](interval_number)
            self.date = fields.Datetime.to_string(next_call.astimezone(pytz.UTC))
        else:
            self.date = False

    @api.multi
    def execute(self):
        if not self.env.user.has_group('base.group_system'):
            return False
        self.ensure_one()
        if not self.code:
            return False
        if self.running:
            return False
        else:
            self.write({'running': True})
            self._cr.commit()
        return self.execute_call()

    @api.multi
    def open_history(self):
        self.ensure_one()
        if len(self.script_history_ids) > 1:
            return {
                'name': _('Script history'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': 'script.history',
                'domain': [('script_id', '=', self.id)],
            }
        else:
            return {
                'name': _('Script history'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'script.history',
                'res_id': self.script_history_ids.id,
            }

    @api.model
    def cron_scheduled_scripts(self):
        failed = []
        for script_id in self.search([('date', '!=', False), ('date', '<=', datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT))], order='date'):
            passed = script_id.execute()
            if not passed:
                failed.append(script_id.name)
            script_id._set_next_date()
        if failed:
            html = '''<p>Sveiki,</p>
        <p>informuojame, kad šie suplanuoti veiksmai nebuvo sėkmingai įvykdyti: </p>
        <table border="2" width="100%%">
            <tr>
                <td><b>Pavadinimas</b></td>
            </tr>'''
            for script_name in failed:
                html += '<tr><td>%s</td></tr>' % script_name
            html += '''</table>
    <p>Dėkui,</p>
    <p>RoboLabs komanda</p>'''
            self.send_email(
                ['support@robolabs.lt'],
                'Nepavyko įvykdyti suplanuotų veiksmų - %s [%s]' % (datetime.now().strftime('%Y-%m-%d'), self.env.cr.dbname),
                html,
            )

    @api.model
    def send_email(self, emails_to, subject, body='', emails_cc=None, attachments=None):
        emails_cc = emails_cc or list()
        attachments = attachments or list()
        robo_branding_base_template = self.env.ref('robo_core.robo_branded_mail_template', False)
        if emails_to and subject:
            if robo_branding_base_template:
                html = self.env['mail.template'].sudo().format_body_based_on_branded_template(
                    robo_branding_base_template,
                    body
                )
            else:
                html = body
            mail_id = self.env['mail.mail'].create({
                'subject': subject,
                'email_from': 'RoboLabs <noreply@robolabs.lt>',
                'body_html': html,
                'email_to': ';'.join(emails_to),
                'email_cc': ';'.join(emails_cc),
                'attachment_ids': attachments,
            })
            mail_id.send()


Script()


class ScriptHistory(models.Model):

    _name = 'script.history'
    _order = 'id desc'

    name = fields.Char(string='Script name', readonly=True)
    script_id = fields.Many2one('script', 'Originating script', ondelete='set null')
    code = fields.Text(string='Python code', readonly=True)
    date = fields.Datetime(string='Execution time', readonly=True)
    database = fields.Char(string='Database', readonly=True)
    status = fields.Text(string='Status', readonly=True)
    user = fields.Many2one('res.users', string='User', readonly=True)
    state = fields.Selection([('fail', 'Fail'), ('success', 'Success')], string='State', default='success', readonly=True)

    @api.multi
    def unlink(self):
        return False


ScriptHistory()


class RoboBug(models.Model):
    _inherit = 'robo.bug'

    @api.model
    def create(self, vals):
        subject = vals.pop('subject', False)
        res = super(RoboBug, self).create(vals)
        if res.skip_ticket_creation:
            res.message_post(body='Ticket creation was skipped', message_type='notification', subtype='mail.mt_comment')
            return res
        now = datetime.utcnow()
        # Check if a bug has already been created
        time_before = (now - relativedelta(minutes=10)).strftime(odoo.tools.DEFAULT_SERVER_DATETIME_FORMAT)
        bug_already_exists = self.env['robo.bug'].sudo().search_count([
            ('id', '!=', res.id),
            ('user_id', '=', res.user_id.id),
            ('error_message', '=', vals.get('error_message', '')),
            ('date', '>=', time_before),
            ('date', '<=', now.strftime(odoo.tools.DEFAULT_SERVER_DATETIME_FORMAT))
        ])

        if not bug_already_exists:
            error_message = vals.get('error_message', '')
            error_message = re.sub('\n\s*File', '<br/><br/>File', error_message).replace('\n', '<br/>')
            self.env['script'].send_email(
                emails_to=['support@robolabs.lt'],
                body=error_message,
                subject=subject or 'Bug in robo (%s) [%s]' % (res.user_id.login, self.env.cr.dbname)
            )
        return res


RoboBug()
