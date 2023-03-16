# -*- encoding: utf-8 -*-
from odoo import models, fields, api, tools, _, SUPERUSER_ID, exceptions
from . import robo_api_tools as at
from datetime import datetime
from dateutil.relativedelta import relativedelta, MO
import requests
import json
import logging
from odoo.addons.queue_job.job import job, identity_exact
from odoo.addons.queue_job.exception import RetryableJobError

_logger = logging.getLogger(__name__)
QUEUE_JOB_DISTRIBUTION_INTERVAL = 5


def check_is_within_update_window(date=None):
    """
    Check if the passed argument (or current time if None) is in the update window (Saturday 19 UTC to Sunday 7 UTC)
    :param date:
    :return:
    """
    if not date:
        date = datetime.utcnow()
    start = date + relativedelta(hour=19, minute=0, weekday=MO(-1)) + relativedelta(days=5)
    end = date + relativedelta(hour=7, minute=0, weekday=MO(-1)) + relativedelta(days=6)
    return start <= date <= end


def check_is_within_peak_hours(date=None):
    """
    Check if time is within the usual peak hours (10 to 16)
    :param date:
    :return:
    """
    if not date:
        date = datetime.utcnow()
    return 7 <= date.hour <= 13 and date.weekday() < 5


class RoboAPIJob(models.Model):
    """
    Model that is used to register API
    calls with their data. Registered
    jobs are executed by cron-job.
    """
    _name = 'robo.api.job'
    _inherit = ['mail.thread']
    _order = 'registration_date desc'

    # Identifiers
    action_name = fields.Char(string='Veiksmas', compute='_compute_action_name')
    action_method = fields.Char(string='Veiksmo funkcija')
    data_identifier = fields.Char(compute='_compute_data_identifier', string='Duomenų numeris', store=True)

    # Dates
    registration_date = fields.Datetime(string='Registravimo data')
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')

    # Status/Info fields
    execution_fail_count = fields.Integer(string='Nepavykusių vykdymų skaičius')
    state = fields.Selection([('to_execute', 'Laukiama vykdymo'),
                              ('to_retry', 'Vykdyti dar kartą'),
                              ('in_progress', 'Vykdoma'),
                              ('succeeded', 'Sėkmingai įvykdyta'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena', track_visibility='onchange')

    # Import data JSON
    json_data = fields.Text(string='Importuojamas JSON')

    # Data saved after execution
    response_message = fields.Char(string='API Pranešimas')
    response_code = fields.Integer(string='API kodas')
    response_data = fields.Text(string='API JSON')
    admin_response_message = fields.Char(
        string='Sisteminis API pranešimas', groups='robo_basic.group_robo_premium_accountant')

    # Callback fields
    callback_response_message = fields.Char(string='Atsako žinutė')
    callback_state = fields.Selection(
        [('sent', 'Atsakas išsiųstas sėkmingai'),
         ('failed', 'Nepavyko išsiųsti atsako'),
         ('no_action', 'Atsakas nesiųstas')], string='Atsako būsena', default='no_action')

    attachment_id = fields.Many2one('ir.attachment', string='Sąskaitos dokumento failas', ondelete='set null')

    # Computes // -----------------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('json_data', 'action_method')
    def _compute_data_identifier(self):
        """
        Compute //
        Try to fetch data identifier from passed JSON data.
        :return: None
        """
        for rec in self:
            data_identifier = '-'
            try:
                json_data = json.loads(rec.json_data)
                if isinstance(json_data, dict):
                    for field in at.DATA_IDENTIFIER_FIELDS:
                        if json_data.get(field):
                            data_identifier = json_data.get(field)
                            break
            except (ValueError, TypeError):
                pass
            rec.data_identifier = data_identifier

    @api.multi
    @api.depends('action_method')
    def _compute_action_name(self):
        """
        Compute //
        Compute action name based on the action method
        :return: None
        """

        method_name_mapping = {
            'create_invoice': _('Sąskaitos kūrimas'),
            'unlink_invoice': _('Sąskaitos trynimas'),
            'cancel_invoice': _('Sąskaitos atšaukimas'),
            'update_invoice': _('Sąskaitos atnaujinimas'),
            'get_invoice': _('Sąskaitos patikrinimas'),
            'get_invoice_list': _('Sąskaitų tikrinimas (pagal datas)'),
            'add_invoice_document': _('Sąskaitos dokumento pridėjimas'),
            'create_product': _('Produkto kūrimas'),
            'update_product': _('Produkto atnaujinimas'),
            'new_products': _('Produktų tikrinimas (pagal datas)'),
            'products': _('Produktų tikrinimas (pagal sandėlį)'),
            'product_categories': _('Produktų kategorijų tikrinimas'),
            'create_product_category': _('Produktų kategorijos kūrimas'),
            'update_product_category': _('Produktų kategorijos atnaujinimas'),
            'create_partner_payments': _('Kliento mokėjimų kūrimas'),
            'create_accounting_entries': _('Apskaitos įrašų kūrimas'),
            'get_accounting_entries': _('Apskaitos įrašų tikrinimas'),
            'write_off_products': _('Nurašyti prekių likučius'),
        }
        for rec in self:
            rec.action_name = method_name_mapping.get(rec.action_method)

    # Other methods ---------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, _('API Darbai') + ' #' + str(rec.id)) for rec in self]

    @api.multi
    def button_execute_api_job(self):
        """
        Button to execute API job.
        :return: None
        """
        self.ensure_one()
        if self.env.user.is_manager():
            self.sudo().run_api_job()

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.model
    def execute_api_action(self, method_name, json_data, force_non_threaded=False):
        """
        Method used to execute API action. Two actions are possible:
          - If API mode is threaded, create API job with json data
              and method name, which will be executed with a cron-job
          - If API mode is normal, create API job with json data
              and method name, execute it and return
              the result to the user
        :param method_name: method name of the API function
        :param json_data: passed JSON data
        :param force_non_threaded: Forces the method to execute in normal mode
            even if threaded API is activated
        :return: response structure {'error': str, 'code': int, 'data': {}} (dict)
        """
        threaded = self.sudo().env.user.company_id.enable_threaded_api
        # Try to fetch execute_immediately flag, if passed data is not JSON
        # we still register the job to check the format of the data
        try:
            if not isinstance(json_data, dict):
                json_data = json.loads(json_data)
            execute_immediately = json_data.get('execute_immediately')
        except ValueError:
            execute_immediately = False

        if method_name == 'add_invoice_document':
            # Attach document to invoice if threaded mode is not enabled
            attach_document = not threaded
            RoboAPIBase = self.env['robo.api.base'].with_context(attach_document=attach_document)
            execution_start_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            try:
                base_method_name = at.API_METHOD_MAPPING.get(method_name)
                api_method = getattr(RoboAPIBase, base_method_name)
                res = api_method(json_data)
            except Exception:
                # Generate artificial result on exception
                res = {
                    'error': 'Unexpected API Error.',
                    'code': at.API_INTERNAL_SERVER_ERROR,
                    'data': {}
                }
            if 'file_data' in json_data:
                json_data['file_data'] = ''
            response_code = res.get('code', at.API_SUCCESS)
            succeeded = response_code == at.API_SUCCESS
            state = 'failed' if not succeeded else 'succeeded'
            api_job = self.register_api_job(method_name, json_data, state, execution_start_date)
            data = res.get('data', False)
            api_job_values = {
                'admin_response_message': res.get('error', str()),
                'response_code': response_code,
                'response_message': res.get('error', str()),
                'execution_start_date': execution_start_date,
                'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            }
            attachment_id = data.get('attachment_id', False) if data else False
            if attachment_id:
                api_job_values['attachment_id'] = attachment_id
            api_job.write(api_job_values)
            self.env.cr.commit()
            res.pop('system_error', False)
            res.pop('data', False)
            return res

        api_job = self.register_api_job(method_name, json_data)
        if not threaded or execute_immediately or force_non_threaded:
            # Execute API job immediately
            api_job.execute_api_job()
            values = {'error': api_job.response_message, 'code': api_job.response_code}
            # Try to load response data, if it fails with ValueError, just pass
            if api_job.state in ['failed', 'succeeded'] and api_job.response_data:
                try:
                    data = json.loads(api_job.response_data)
                    response_data = json.loads(api_job.response_data)
                    values['data'] = data
                    if 'pdf' in response_data:
                        # Do not include base64 data in response query
                        response_data['pdf'] = ''
                        api_job.write({
                            'response_data': json.dumps(response_data)
                        })
                        self._cr.commit()
                except ValueError:
                    pass
            return values
        else:
            api_job.run_api_job()
            message = 'API Call is registered. ' \
                      'Passed data will be processed in the meantime. Registered call ID is attached.'
            return {'error': message, 'code': at.API_SUCCESS, 'data': {'api_job_id': api_job.id}}

    @api.model
    def register_api_job(self, method_name, json_data, state='to_execute', registration_date=None):
        """
        Register API job for execution - create robo.api.job record
        :param method_name: Name of the API method
        :param json_data: json_data to parse and import
        :param state: state to set
        :param registration_date: registration date to set
        :return: robo.api.job record
        """
        if not isinstance(json_data, basestring):
            json_data = json.dumps(json_data)

        vals = {
            'action_method': method_name,
            'state': state,
            'json_data': json_data,
            'registration_date': registration_date or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        }
        api_job = self.create(vals)
        self.env.cr.commit()
        return api_job

    @api.multi
    def run_api_job(self):
        api_request_parsing_retries = self.env.user.company_id.api_request_parsing_retries or 1
        channel = self.env['ir.config_parameter'].get_param('robo_api_job_queue_channel') or 'root.api'
        for i, api_job in enumerate(self, start=1):
            if api_job.state not in ['to_retry', 'to_execute']:
                continue
            api_job.with_delay(channel=channel, eta=QUEUE_JOB_DISTRIBUTION_INTERVAL * i,
                description='ROBO API: %s' % api_job.with_context(lang='en_US').action_name,
                max_retries=api_request_parsing_retries,
                identity_key=identity_exact
            ).queue_job_execute_api_job()

    @api.multi
    def api_job_repr(self):
        """
        Return representation of current object that is formatted as an API response
        :return: grouped data (dict)
        """
        self.ensure_one()
        # State is the description of selection field value
        state = str(dict(self._fields['state']._description_selection(self.env)).get(self.state))
        data = {
            'endpoint': self.action_method,
            'action': self.action_name,
            'registration_date': self.registration_date,
            'state': state,
            'job_id': self.id
        }
        if self.execution_end_date:
            data['execution_end_date'] = self.execution_end_date
        if self.response_message:
            data['response_message'] = self.response_message
        if self.response_data:
            data['response_data'] = self.response_data
        return data

    @api.model
    def cron_create_ticket_for_failed_jobs(self):
        date_gte = (datetime.utcnow() + relativedelta(months=-1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_lt = (datetime.utcnow() + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        failed_jobs_count = self.search_count([
            ('state', '=', 'failed'),
            ('execution_end_date', '>=', date_gte),
            ('execution_end_date', '<', date_lt),
            ('action_method', 'in', ['cancel_invoice', 'create_invoice', 'update_invoice', 'unlink_invoice']),
        ])

        if failed_jobs_count:
            body = """%d API darbų vykdymas praeitą mėnesį
             tarp %s ir %s nepavyko.""" % (failed_jobs_count, date_gte, date_lt)

            ticket_obj = self.sudo()._get_ticket_rpc_object()
            vals = {'ticket_dbname': self.env.cr.dbname,
                    'ticket_model_name': self._name,
                    'name': 'API darbų vykdymas nepavyko',
                    'description': body,
                    'ticket_type': 'accounting'}

            res = ticket_obj.create_ticket(**vals)

            if not res:
                raise exceptions.UserError('The method did not create the ticket.')

    @api.model
    def cron_execute_api_job(self):
        """
        Searches for api jobs that are in to retry state,
        and tries to execute them. Write the states afterwards.
        :return: None
        """
        RoboAPIJob = self.env['robo.api.job']
        IrConfig = self.env['ir.config_parameter']
        limit_amount = IrConfig.get_param('robo_api_job_limit_amount')
        if not isinstance(limit_amount, int):
            try:
                limit_amount = int(limit_amount)
            except (ValueError, TypeError):
                limit_amount = 200
            
        if check_is_within_update_window():
            return
        if IrConfig.get_param('robo_api_avoid_peak_hours'):
            if check_is_within_peak_hours():
                return
        api_jobs = RoboAPIJob.search(
            [('state', '=', 'to_retry')],
            limit=limit_amount, order='registration_date asc, id asc'
        )
        api_jobs.run_api_job()

    @api.model
    def cron_attach_invoice_documents(self):
        """
        Searches for successful add_invoice_document API jobs where attachments are not yet attached to the invoice
        and tries to attach them
        :return: None
        """
        RoboAPIJob = self.env['robo.api.job']
        api_request_parsing_retries = self.env.user.company_id.api_request_parsing_retries or 1
        api_jobs = RoboAPIJob.search(
            [('state', '=', 'succeeded'), ('action_method', '=', 'add_invoice_document'),
             ('attachment_id.res_id', '=', False)],
            order='registration_date asc')
        if not api_jobs:
            return
        # Enumerate to distribute jobs in a time period
        for i, api_job in enumerate(api_jobs, start=1):
            api_job.with_delay(channel='root.api', eta=QUEUE_JOB_DISTRIBUTION_INTERVAL * i,
                               max_retries=api_request_parsing_retries,
                               description='ROBO API: Attach invoice document',
                               identity_key=identity_exact).queue_job_attach_invoice_document()

    @api.multi
    def attach_invoice_document(self):
        """
        Try to attach invoice document to an existing invoice
        :return: None
        """
        self.ensure_one()
        RoboAPIBase = self.env['robo.api.base']
        # Load the JSON data and attach the document
        json_data = json.loads(self.json_data)
        invoice, error_message = RoboAPIBase.find_invoice(json_data)
        if error_message:
            raise exceptions.ValidationError(error_message)

        attachment_values = {
            'res_model': 'account.invoice',
            'res_id': invoice.id,
        }
        self.attachment_id.write(attachment_values)

    @job
    @api.multi
    def queue_job_attach_invoice_document(self):
        """ ROBO API: Attach invoice document """
        self.ensure_one()
        try:
            self.attach_invoice_document()
        except Exception as e:
            raise RetryableJobError(e, ignore_retry=True)

    @api.multi
    def execute_api_job(self):
        """
        Execute API job
        :return: None
        """
        self.ensure_one()
        if self.state in ['failed', 'succeeded']:
            return
        APIBase = self.env['robo.api.base']
        api_request_parsing_retries = self.env.user.company_id.api_request_parsing_retries
        base_method_name = at.API_METHOD_MAPPING.get(self.action_method)
        api_method = getattr(APIBase, base_method_name)
        try:
            # Try to load the JSON data and execute the method
            json_data = json.loads(self.json_data)
            # Write execution start date and commit before further rollbacks
            self.write({
                'execution_start_date':
                    datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            })
            self._cr.commit()
            res = api_method(json_data)
        except Exception as exc:
            import traceback
            _logger.info(
                'ROBO API job execution failed | id: %s | error: %s \nTraceback: %s' %
                (str(self.id), tools.ustr(exc), traceback.format_exc()))
            # Parse the exception message
            resp_message = 'Unexpected API Error.'
            system_error = '{} Exception - {}'.format(resp_message, exc.args[0])
            # Generate artificial result on exception
            res = {
                'error': resp_message,
                'system_error': system_error,
                'code': at.API_INTERNAL_SERVER_ERROR,
                'data': {}
            }

        # Fetch response code and determine if execution succeeded or not
        response_code = res.get('code', at.API_SUCCESS)
        data = res.get('data')
        failed_execution = response_code != at.API_SUCCESS

        # Prepare values to write
        values = {
            'admin_response_message': res.get('system_error', res.get('error', str())),
            'response_code': response_code,
            'response_data': json.dumps(data) if data else str(),
            'response_message': res.get('error', str()),
            'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        }

        # Determine state of the job
        if failed_execution:
            # rollback everything
            self._cr.rollback()
            # If fail count is higher than allowed retries, set state to 'failed'
            # otherwise set state to 'to_retry'
            fail_count = self.execution_fail_count + 1
            values.update({'execution_fail_count': fail_count})
            if response_code != at.API_INTERNAL_SERVER_ERROR or fail_count > api_request_parsing_retries:
                values.update({'state': 'failed'})
            else:
                values.update({'state': 'to_retry'})
        else:
            values.update({'state': 'succeeded'})

            # Write values to the job and commit
        self.write(values)
        self._cr.commit()
        self.send_message_to_callback_url()

    @job
    @api.multi
    def queue_job_execute_api_job(self):
        """
        ROBO API: Execute API Job
        :return: None
        """
        self.ensure_one()
        try:
            self.execute_api_job()
        except Exception as e:
            raise RetryableJobError(e, ignore_retry=True)

    @api.multi
    def send_message_to_callback_url(self):
        """
        Send information to the callback address
        :return: None
        """
        company = self.env.user.sudo().company_id
        callback_url = company.threaded_api_callback_url
        if not callback_url:
            return

        job_data = []
        for rec in self.filtered(lambda x: x.state in ['failed', 'succeeded'] and x.callback_state != 'sent'):
            data = rec.api_job_repr()
            job_data.append(data)
        if not job_data:
            return
        message = 'ROBO API Job Report {}: Failed and succeeded jobs are attached.'.format(
            datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT))
        final_data = {
            'message': message,
            'job_data': job_data
        }

        # Try to post the message to callback URL
        try:
            requests.post(callback_url, json=final_data)
        except Exception as exc:
            error = 'Failed to reach API callback endpoint. Exception - {}'.format(exc.args[0])
            self.write({
                'callback_state': 'failed',
                'callback_response_message': error
            })
        else:
            # FOR NOW -- If we do not get the exception on the post method itself,
            # We interpret as if the message was received, because it can either be an API or
            # anything for that matter
            self.write({
                'callback_state': 'sent',
                'callback_response_message': _('Atsakas išsiųstas')
            })

    @api.multi
    def server_action_reset_job(self):
        """
        Server action called from front-end robo.api.job
        tree view, used to set API jobs to retry
        If setting fails - record is skipped
        :return: None
        """
        callback_url = self.env.user.sudo().company_id.threaded_api_callback_url
        for rec in self.filtered(lambda x: x.state == 'failed'):
            try:
                values = {'state': 'to_retry'}
                if callback_url:
                    values.update({'callback_state': 'no_action',
                                   'callback_response_message': str(),
                                   })
                rec.write(values)
                self.env.cr.commit()
            except Exception:
                self.env.cr.rollback()

    @api.model
    def create_action_reset_job_multi(self):
        """
        Action method, used in robo.api.job tree view to
        set API jobs to retry
        :return: None
        """
        action = self.env.ref('robo_api.action_reset_job_multi')
        if action:
            action.create_action()

    @job
    def fix_invoices_with_wrong_partner(self):
        for job in self:
            job_invoices = self.env['account.invoice'].search([('imported_api', '=', True), ('number', '=', job.data_identifier)])
            invoice = job_invoices and job_invoices[0]
            if not invoice:
                continue
            data = json.loads(job.json_data)
            partner_data = data.get('partner')
            is_company = partner_data.get('is_company')
            vat_code = partner_data.get('vat_code')
            if is_company or not vat_code:
                continue

            partner_data.pop('vat_code')  # VAT code is incorrect
            partner, _ = self.env['robo.api.base'].find_or_create_partner(partner_data)

            if not partner or partner.id == invoice.partner_id.id:
                continue

            res = invoice.action_invoice_cancel_draft_and_remove_outstanding()

            # Force partner information
            invoice.write({
                'partner_id': partner.id
            })
            invoice._partner_data()
            invoice.with_context(skip_attachments=True).action_invoice_open()
            invoice.action_re_assign_outstanding(res, raise_exception=False, forced_partner=partner.id)


RoboAPIJob()
