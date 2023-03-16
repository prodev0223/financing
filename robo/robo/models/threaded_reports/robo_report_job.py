# -*- coding: utf-8 -*-
from odoo import fields, models, api, tools, exceptions, _
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo.api import Environment
import threading
import odoo
import base64
from odoo.addons.controller_report_xls.controllers import main as controller


ALLOWED_ACTIVE_JOB_COUNT = 5


class RoboReportJob(models.Model):

    """
    Model used to generate front robo reports using a separate thread
    threaded front Robo report generation results are saved as files
    """

    _name = 'robo.report.job'
    _inherit = ['mail.thread']
    _order = 'execution_start_date desc'

    report_name = fields.Char(string='Ataskaitos pavadinimas')

    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')

    exported_file_name = fields.Char(string='Eksportuoto failo pavadinimas')
    exported_file = fields.Binary(string='Eksportuotas failas', attachment=True, readonly=True)
    exported_file_type = fields.Selection([('xls', 'Excel'),
                                           ('xlsx', 'Excel'),
                                           ('pdf', 'PDF'),
                                           ('ffdata', 'FFdata'),
                                           ('xml', 'XML'),
                                           ], string='Eksportuoto failo tipas')
    pdf_view = fields.Binary(compute='_compute_pdf_view')

    message_posted = fields.Boolean(string='Informuota')

    user_id = fields.Many2one('res.users', string='Naudotojas')
    user_name = fields.Char(compute='_compute_user_name', string='Naudotojas')
    fail_message = fields.Char(string='Klaidos pranešimas')
    state = fields.Selection([('in_progress', 'Vykdoma'),
                              ('succeeded', 'Sėkmingai įvykdyta'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')

    job_type = fields.Selection(
        [('export', 'Eksportas'), ('refresh', 'Perkrovimas')], string='Veiksmo tipas')
    refresh_model = fields.Char(string='Perkraunamas modelis')

    # Computes --------------------------------------------------------------------------------------------------------

    @api.multi
    def _compute_user_name(self):
        """
        Compute //
        Get user name from user_id, so m2o field is not displayed in form
        :return: None
        """
        for rec in self.filtered(lambda x: x.user_id):
            rec.user_name = rec.user_id.name

    @api.multi
    def _compute_pdf_view(self):
        """
        Compute //
        Display another binary field for PDF view.
        It's used as a separate field, because it has different widget
        :return: None
        """
        for rec in self.filtered(lambda x: x.exported_file and x.exported_file_type == 'pdf'):
            rec.pdf_view = rec.exported_file

    # Constraints ----------------------------------------------------------------------------------------------------

    @api.multi
    @api.constrains('job_type', 'refresh_model')
    def _check_refresh_model(self):
        """
        Constraints //
        If job type is of 'refresh' type, refresh_model must be specified
        :return: None
        """
        for rec in self:
            if rec.job_type == 'refresh' and not rec.refresh_model:
                raise exceptions.ValidationError(_('Nenurodytas perkrovimo modelis'))

    @api.multi
    @api.constrains('state')
    def _check_currently_running_job_count(self):
        # Check if a user is trying to start another report
        user = self.env.user
        export_jobs = self.filtered(lambda job: job.job_type == 'export')
        if any(job.state == 'in_progress' for job in export_jobs) and user.id != odoo.SUPERUSER_ID:
            if self.search_count([
                ('state', '=', 'in_progress'),
                ('user_id', '=', user.id),
                ('job_type', '=', 'export'),
                ('id', 'not in', export_jobs.ids)
            ]) >= ALLOWED_ACTIVE_JOB_COUNT:
                raise exceptions.UserError(
                    _('Šiuo metu eksportuojamos kelios ataskaitos, pabandykite po kelių minučių.'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.model
    def generate_report(self, report_object, report_method_name, report_name, **kwargs):
        """
        Method that takes generates report for specific model based on passed method name.
        If threaded report option is activated method runs report generation as a separate thread
        Otherwise method is executed normally and it's result is returned.
        Method can be used on any method that returns the action as a result
        :param report_object: record of the model that contains the report generation method
        :param report_method_name: method name that generates the report
        :param report_name: report type name
        :param kwargs:
                Thus far expects three types of variables - returns:
                Signifies what kind of structure does the passed method return action and base64
                are possible for now
                forced_extension:
                Signifies the extension of the report if return type is not 'action'
                forced_name:
                Signifies the name of the report if return type is not 'action'
        :return: report result or action dict
        """

        threaded = self.sudo().env.user.company_id.activate_threaded_front_reports
        if threaded:
            # If report threading is activated, create separate thread for the report
            user_id = self.env.user.id

            vals = {
                'report_name': report_name,
                'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'state': 'in_progress',
                'user_id': user_id,
                'job_type': 'export'
            }
            import_job = self.create(vals)
            self.env.cr.commit()

            # Start the thread
            threaded_calculation = threading.Thread(
                target=self.generate_report_threaded, args=(
                    import_job.id, report_object.id, report_method_name,
                    report_object._name, kwargs))
            threaded_calculation.start()

            # Return the wizard which displays some information on where to find the report
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'robo.report.job',
                'view_mode': 'form',
                'view_type': 'form',
                'res_id': import_job.id,
                'views': [(self.env.ref('robo.form_robo_report_job_info').id, 'form')],
                'target': 'new',
                'view_id': self.env.ref('robo.form_robo_report_job_info').id,
            }

        else:
            # If report threading is not activated, proceed with previous behaviour - just execute the method
            report_method = getattr(report_object, report_method_name)
            return report_method()

    @api.model
    def generate_report_threaded(self, job_id, report_object_id, report_method_name, report_object_model, extra_args):
        """
        Thread //
        Generate report using separate thread, save the result in the file, and inform
        The user that initiated the export about the result
        :param job_id: ID of current model record, that initiated the job
        :param report_object_id: ID of the record that is going to be used for report generation
        :param report_method_name: method name that generates the report
        :param report_object_model: model name of the record that is going to be used for report generation
        :param extra_args: extra arguments passed as a dict
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT', 'threaded_report': True})

            # Re-browse the object with new cursor
            import_job = env['robo.report.job'].browse(job_id)
            report_object = env[report_object_model].browse(report_object_id)
            report_method = getattr(report_object, report_method_name)

            # Special argument that ensures XLS type forcing if action['context'] loses
            # the value (which sometimes happens in this case with new env)
            forced_xls = extra_args.get('forced_xls')
            try:
                if extra_args.get('returns', 'action') == 'action':
                    action = report_method()
                    if not isinstance(action, dict):
                        raise exceptions.UserError(_('Ataskaitos metodo struktūra yra nepritaikyta šiam veiksmui'))
                    # Check whether XLS report tag is in the context
                    # if it is, behaviour differs from PDF
                    data = import_job.render_report(action, forced_xls=forced_xls)
                    base64_file = data.get('base64_file')
                    exported_file_name = data.get('exported_file_name')
                    exported_file_type = data.get('exported_file_type')
                else:
                    # So far base64 return type is expected in else block
                    # consider adding more options in the future
                    exported_file_type = extra_args.get('forced_extension', 'pdf')
                    forced_name = extra_args.get('forced_name', 'action') or import_job.report_name
                    base64_file = report_method()
                    exported_file_name = '{}.{}'.format(forced_name, exported_file_type)

            except Exception as exc:
                new_cr.rollback()
                import_job.write(
                    {'state': 'failed',
                     'fail_message': str(exc.args[0]),
                     'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                import_job.write(
                    {'state': 'succeeded',
                     'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                     'exported_file': base64_file,
                     'exported_file_name': exported_file_name,
                     'exported_file_type': exported_file_type})

            import_job.post_message()
            new_cr.commit()
            new_cr.close()

    @api.multi
    def render_report(self, action, forced_xls=False):
        """
        Renders report with custom file name
        :param action: Report action data -- DICT
        :param forced_xls: flag that indicates
               whether XLS export should be forced -- BOOL
        :return: File in base64 and name -- DICT
        """
        self.ensure_zero_or_one()
        export_user_id = self.user_id.id if self else self.env.user.id
        if action['context'].get('xls_report') or forced_xls:
            xls_stream = controller.prepare_excel(
                env=self.env,
                doc_ids=None,
                report_name=action['report_name'],
                data=action['data'],
                context=action['context'],
                uid=export_user_id)
            base64_file = base64.b64encode(xls_stream)
            exported_file_type = 'xls'
            exported_file_name = '{}.{}'.format(action['name'], exported_file_type)

        else:
            res, exported_file_type = self.env['ir.actions.report.xml'].with_context(
                **action['context']).render_report(None, action['report_name'], action['data'])
            base64_file = base64.b64encode(res)
            exported_file_name = '{}.{}'.format(action['name'], exported_file_type)

        return {
            'base64_file': base64_file,
            'exported_file_name': exported_file_name,
            'exported_file_type': exported_file_type,
        }

    @api.multi
    def render_report_with_attachment(self, action, calling_record, forced_xls=False, forced_file_name=False):
        """
        Renders the report with attachment creation
        :param action: Report action data -- DICT
        :param calling_record: Record that is used for attachment creation -- RECORD
        :param forced_xls: Indicates whether XLS export should be forced -- BOOL
        :param forced_file_name: Forced file name to use -- STR
        :return: attachment download action -- DICT
        """
        self.ensure_zero_or_one()
        # Render the report
        data = self.env['robo.report.job'].render_report(action, forced_xls=forced_xls)
        exported_file_name = data.get('exported_file_name')
        base64_file = data.get('base64_file')
        # Check what file name should be used
        exported_file_name = forced_file_name or exported_file_name
        # Create the attachment
        attachment = self.env['ir.attachment'].create({
            'res_model': calling_record._name,
            'res_id': calling_record.id,
            'type': 'binary',
            'name': exported_file_name,
            'datas_fname': exported_file_name,
            'datas': base64_file,
        })
        # Return download link
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=%s&res_id=%s&attach_id=%s' % (
                calling_record._name, calling_record.id, attachment.id),
            'target': 'self',
        }

    @api.model
    def refresh_materialized_view(self, refresh_model, report_name):
        """
        Method that creates a thread which calls 'refresh_view' method for given model.
        Threaded job is created, and action that informs the user is returned
        :param refresh_model: model of the materialized report
        :param report_name: name of the materialized report
        :return: action (dict)
        """
        if self.search_count(
                [('state', '=', 'in_progress'), ('job_type', '=', 'refresh'), ('refresh_model', '=', refresh_model)]):
            raise exceptions.UserError(
                _('Šiuo metu ataskaita yra perkraunama, pabandykite po kelių minučių.'))

        vals = {
            'report_name': report_name,
            'execution_start_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'in_progress',
            'user_id': self.env.user.id,
            'refresh_model': refresh_model,
            'job_type': 'refresh'
        }
        import_job = self.create(vals)
        self.env.cr.commit()

        # Start the thread
        threaded_calculation = threading.Thread(target=self.refresh_materialized_view_threaded, args=(import_job.id, ))
        threaded_calculation.start()

        # Return the wizard which displays some information on where to find the report
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'robo.report.job',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': import_job.id,
            'views': [(self.env.ref('robo.form_robo_report_job_info').id, 'form')],
            'target': 'new',
            'view_id': self.env.ref('robo.form_robo_report_job_info').id,
        }

    @api.model
    def refresh_materialized_view_threaded(self, job_id):
        """
        Thread //
        Threaded job that refreshes the view of materialized report
        and posts the message to the user after its done
        :param job_id: robo.report.job ID
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, odoo.SUPERUSER_ID, {'lang': 'lt_LT'})

            # Re-browse the object with new cursor
            import_job = env['robo.report.job'].browse(job_id)
            try:
                model = import_job.refresh_model
                env[model].with_context(force_refresh=True).refresh_view()
            except Exception as exc:
                new_cr.rollback()
                import_job.write(
                    {'state': 'failed',
                     'fail_message': str(exc.args[0]),
                     'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                import_job.write(
                    {'state': 'succeeded',
                     'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})

            import_job.post_message()
            new_cr.commit()
            new_cr.close()

    # Misc methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def post_message(self):
        """
        After export thread is finished, post message about the state of the export
        And display it in the bell for specific user
        :return: None
        """
        # Be sure not to spam user with the same message several times
        for rec in self.filtered(lambda x: x.state != 'in_progress' and not x.message_posted):

            # Prepare subject and body of the message based on the state
            if rec.state == 'succeeded':
                if rec.job_type == 'refresh':
                    body = template = _('Perkrauta ataskaita - {}'.format(rec.report_name))
                else:
                    template = _('Eksportuota ataskaita - {}'.format(rec.report_name))
                    body = _('{}. Ją rasite paspaudę ant šio pranešimo, arba pagrindiniame '
                             'Robo lange pasirinkę "Kita" -> "Eksportuotos ataskaitos"').format(template)
            else:
                if rec.job_type == 'refresh':
                    template = _('Nepavyko perkrauti ataskaitos - {}').format(rec.report_name)
                else:
                    template = _('Nepavyko eksportuoti ataskaitos - {}').format(rec.report_name)
                body = _('{}. Klaidos pranešimas - {}').format(template, rec.fail_message)

            msg = {
                'body': body,
                'subject': template,
                'priority': 'medium',
                'front_message': True,
                'rec_model': 'robo.report.job',
                'rec_id': rec.id,
                'partner_ids': rec.user_id.partner_id.ids,
                'view_id': self.env.ref('robo.form_robo_report_job').id,
            }
            rec.robo_message_post(**msg)
            rec.message_posted = True

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, _('Ataskaitų eksportas/perkrovimas') + ' #' + str(rec.id)) for rec in self]

    # Cron-job --------------------------------------------------------------------------------------------------------

    @api.model
    def cron_job_cleanup(self):
        """
        Delete jobs that are older than two days
        :return: None
        """
        # Use two days gap, so system is not clogged
        current_date_dt = (datetime.utcnow() - relativedelta(days=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        report_jobs = self.search([('execution_end_date', '<', current_date_dt)])
        report_jobs.unlink()
    
    @api.model
    def cron_cleanup_stuck_report_jobs(self):
        """
        autofails jobs that are supposedly stuck and
        execution start time is older than 6 hours
        :return None
        """
        min_execution_start_date = (datetime.utcnow() - relativedelta(hours=6)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.search([
            ('execution_start_date', '<', min_execution_start_date),
            ('state', '=', 'in_progress')
        ]).write({
            'state': 'failed',
            'fail_message': _('This job has been marked as failed because it was stuck for over 6hours.')
        })