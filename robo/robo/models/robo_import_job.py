# -*- encoding: utf-8 -*-
from odoo import models, fields, api, tools, SUPERUSER_ID, _
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo.api import Environment
import traceback


class RoboImportJob(models.Model):
    """
    Model that is used to execute front-end
    XLS (company settings) imports in threaded mode.
    """
    _name = 'robo.import.job'
    _inherit = ['mail.thread']
    _order = 'execution_start_date desc'

    # Identifiers
    action_name = fields.Char(string='Veiksmas')
    action = fields.Char(string='Veiksmas', inverse='_set_action')

    # Dates
    execution_start_date = fields.Datetime(string='Vykdymo pradžia')
    execution_end_date = fields.Datetime(string='Vykdymo Pabaiga')

    # Status/Info fields
    message_posted = fields.Boolean(string='Informuota')
    fail_message = fields.Char(string='Klaidos pranešimas')
    system_fail_message = fields.Char(string='Sisteminis klaidos pranešimas')
    state = fields.Selection([('in_progress', 'Vykdoma'),
                              ('succeeded', 'Sėkmingai įvykdyta'),
                              ('failed', 'Vykdymas nepavyko')],
                             string='Būsena')

    # File information
    imported_file = fields.Binary(string='Importuotas failas', attachment=True, readonly=True)
    imported_file_name = fields.Char(string='Failo pavadinimas')

    # Extra information
    user_id = fields.Many2one('res.users', string='Naudotojas')
    user_name = fields.Char(compute='_compute_user_name', string='Naudotojas')

    # Computes / Inverses ---------------------------------------------------------------------------------------------

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
    def _set_action(self):
        """
        Inverse //
        Set display action and file names
        :return: None
        """
        action_name_mapping = self.get_action_name_mapping()
        for rec in self:
            action_name = action_name_mapping.get(rec.action, str())
            rec.action_name = action_name
            rec.imported_file_name = '{}.xlsx'.format(action_name.replace(' ', '_'))

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.model
    def execute_threaded_import(self, parent_id, job_id, function, imported_file):
        """
        Threaded method //
        Executes any front XLS import task in the background,
        updating related job record with execution status.
        :param parent_id: robo.company.settings ID (int)
        :param job_id: robo.import.job ID (int)
        :param function: function that will be used to process the file (function)
        :param imported_file: Imported, to-process file (str)
        :return: None
        """
        with Environment.manage():
            new_cr = self.pool.cursor()
            env = api.Environment(new_cr, SUPERUSER_ID, {'lang': 'lt_LT'})

            # Re-browse the object with new cursor
            import_job = env['robo.import.job'].browse(job_id)
            # All of the functions have 'self' passed to them as a parameter
            # and they use some values from the wizard (context, etc),
            # might be refactored later.
            if isinstance(parent_id, models.BaseModel):
                parent = env[parent_id._name].browse(parent_id.id)
            else:
                parent = env['robo.company.settings'].browse(parent_id)
            try:
                function(parent, imported_file)
            except Exception as exc:
                new_cr.rollback()
                import_job.write(
                    {'state': 'failed',
                     'fail_message': str(exc.args[0]),
                     'system_fail_message': traceback.format_exc(),
                     'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
            else:
                import_job.write(
                    {'state': 'succeeded',
                     'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})

            import_job.post_message()
            new_cr.commit()
            new_cr.close()

    @api.multi
    def post_message(self):
        """
        After import thread is finished, post message about the state of the export
        And display it in the bell for specific user
        :return: None
        """
        # Be sure not to spam user with the same message several times
        for rec in self.filtered(lambda x: x.state != 'in_progress' and not x.message_posted):
            # Prepare subject and body of the message based on the state
            if rec.state == 'succeeded':
                subject = _('Sėkmingai importuotas failas. Veiksmas - {}'.format(rec.action_name))
                body = _('{}. Ją rasite paspaudę ant šio pranešimo, arba pagrindiniame '
                         'Robo lange pasirinkę "Kita" -> "Duomenų importo darbai"').format(subject)
            else:
                subject = _('Nepavyko importuoti failo. Veiksmas - {}'.format(rec.action_name))
                body = _('{}. Klaidos pranešimas - {}').format(subject, rec.fail_message)
            msg = {
                'body': body,
                'subject': subject,
                'priority': 'medium',
                'front_message': True,
                'rec_model': 'robo.import.job',
                'rec_id': rec.id,
                'partner_ids': rec.user_id.partner_id.ids,
                'view_id': self.env.ref('robo.form_robo_import_job').id,
            }
            rec.robo_message_post(**msg)
            rec.message_posted = True

    @api.multi
    def name_get(self):
        """Name-get override"""
        return [(rec.id, _('Importavimas #{}').format(rec.id)) for rec in self]

    @api.model
    def get_action_name_mapping(self):
        name_mapping = {
            'import_partners': _('Klientų tiekėjų informacija'),
            'import_customer_invoices': _('Klientų neapmokėtos sąskaitos faktūros'),
            'import_supplier_invoices': _('Tiekėjų neapmokėtos sąskaitos faktūros'),
            'import_products': _('Produktų informacija'),
            'import_financials': _('Finansinė atskaitomybė'),
            'import_assets': _('Ilgalaikio turto informacija'),
            'import_employees': _('Personalo informacija'),
            'import_aml': _('Didžiosios knygos (DK) įrašai'),
            'import_du': _('Darbo užmokesčio (DU) istorija'),
        }
        return name_mapping

    # Cron-Jobs -------------------------------------------------------------------------------------------------------

    @api.model
    def cron_import_job_cleanup(self):
        """
        Delete jobs that are older than two days
        :return: None
        """
        # Use two days gap, so system is not clogged
        current_date_dt = (datetime.now() - relativedelta(days=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        import_jobs = self.search([('execution_end_date', '<', current_date_dt)])
        import_jobs.unlink()

    @api.model
    def cron_stuck_import_job_cleanup(self):
        """
        autofails jobs that are supposedly stuck and
        start time is older than 2 hours
        :return None
        """
        current_date_dt = (datetime.utcnow() - relativedelta(hours=2)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.search([
            ('execution_start_date', '<', current_date_dt),
            ('state', '=', 'in_progress')
        ]).write({
            'state': 'failed',
            'fail_message': _('Užduotis užtruko per ilgai, todėl buvo sustabdyta, galimai tai buvo sisteminė klaida.'),
            'system_fail_message': _('Užduotis užtruko per ilgai, todėl buvo sustabdyta, galimai tai buvo sisteminė klaida.')
        })
