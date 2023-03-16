# -*- encoding: utf-8 -*-
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import base64
import csv
from datetime import datetime
from odoo import fields, models, api, _, exceptions, tools
from odoo.addons.queue_job.job import job, identity_exact
import logging
from six import itervalues

_logger = logging.getLogger(__name__)


class SepaCsvImporter(models.AbstractModel):
    _name = 'sepa.csv.importer'
    _description = 'Base model for all CSV statements importers'

    @staticmethod
    def _default_codepage():
        return 'utf-8'

    @staticmethod
    def _default_lines_to_skip():
        return 0

    journal_id = fields.Many2one('account.journal', string='Žurnalas', required=True)

    csv_data = fields.Binary(string='Dokumentas', required=True)
    csv_fname = fields.Char(string='Dokumento pavadinimas', invisible=True)
    lines = fields.Binary(compute='_compute_lines', string='Eilutės', required=True)
    dialect = fields.Binary(compute='_compute_dialect', string='Dialektas', required=True)
    csv_separator = fields.Selection([(',', ', (kablelis)'),
                                      (';', '; (kabliataškis)')],
                                     string='CSV skirtukas', required=True, default=',')
    decimal_separator = fields.Selection([('.', '. (taškas)'),
                                          (',', ', (kablelis)')],
                                         string='Dešimtainis skirtukas', default='.', required=True)
    codepage = fields.Char(string='Koduotė', default=lambda self: self._default_codepage(),
                           help='CSV dokumento koduotė, pvz. Windows-1252, utf-8')
    lines_to_skip = fields.Integer(string='Eilutės, kurias praleisti',
                                   default=lambda self: self._default_lines_to_skip(),
                                   help='Prieš CSV transakcijų pavadinimus vyraujantis/egzistuojantis eilučių skaičius bus ignoruojamas')

    force_date_format = fields.Selection([('%d/%m/%Y', 'DD/MM/YYYY'),
                                          ('%m/%d/%Y', 'MM/DD/YYYY'),
                                          ('%Y/%m/%d', 'YYYY/MM/DD'),
                                          ('%Y/%d/%m', 'YYYY/DD/MM'),
                                          ('%d-%m-%Y', 'DD-MM-YYYY'),
                                          ('%m-%d-%Y', 'MM-DD-YYYY'),
                                          ('%Y-%m-%d', 'YYYY-MM-DD'),
                                          ('%Y-%d-%m', 'YYYY-DD-MM'),
                                          ('%d.%m.%Y', 'DD.MM.YYYY'),
                                          ('%d/%m/%y', 'DD/MM/YY'),
                                          ('%m/%d/%y', 'MM/DD/YY'),
                                          ('%y/%m/%d', 'YY/MM/DD'),
                                          ('%y/%d/%m', 'YY/DD/MM'),
                                          ('%d-%m-%y', 'DD-MM-YY'),
                                          ('%m-%d-%y', 'MM-DD-YY'),
                                          ('%y-%m-%d', 'YY-MM-DD'),
                                          ('%y-%d-%m', 'YY-DD-MM'),
                                          ('%d %b, %Y', 'DD MM, YY')
                                          ], string='Priverstinis datos formatas')

    apply_import_rules = fields.Boolean(string='Taikyti importavimo taisykles', default=True)
    skip_import_rules_error = fields.Boolean(string='Praleisti eilutes su importavimo taisyklių klaidomis',
                                             default=False,
                                             help=('Jei nustatyta, kai eilutė atitinka kelias taisykles su nesuderinamomis'
                                                   ' instrukcijomis, ji praleidžiama. Jei išjungta, iškeliama klaida.'))
    file_not_csv = fields.Boolean(compute='_compute_file_csv')
    ignore_origin_currency = fields.Boolean(string='Ignore origin currency', default=False)

    @api.one
    @api.depends('csv_data')
    def _compute_lines(self):
        if self.csv_data:
            lines = base64.decodestring(self.csv_data)
            # convert windows & mac line endings to unix style
            self.lines = lines.replace('\r\n', '\n').replace('\r', '\n')

    @api.one
    @api.depends('lines', 'csv_separator')
    def _compute_dialect(self):
        if self.lines:
            try:
                self.dialect = csv.Sniffer().sniff(self.lines[:128], delimiters=';,')
            except:
                # csv.Sniffer is not always reliable
                # in the detection of the delimiter
                self.dialect = csv.Sniffer().sniff('"header 1";"header 2";\r\n')
                if ',' in self.lines[:128]:
                    self.dialect.delimiter = ','
                elif ';' in self.lines[:128]:
                    self.dialect.delimiter = ';'
            if self.csv_separator:
                self.dialect.delimiter = str(self.csv_separator)
            self.dialect.doublequote = True

    @api.one
    @api.depends('csv_fname')
    def _compute_file_csv(self):
        if self.csv_fname:
            extension = self.csv_fname.split('.')[-1] if '.' in self.csv_fname else None
            if not extension or extension.lower() != 'csv':
                self.file_not_csv = True

    def _remove_leading_lines(self, lines):
        """ remove leading blank or comment lines """
        input_lines = StringIO.StringIO(lines)
        for n in range(self.lines_to_skip):
            input_lines.next()
        header = False
        while not header:
            ln = input_lines.next()
            if not ln or ln and ln[0] in [self.csv_separator, u'#', '#', '\n']:
                self.lines_to_skip += 1
                continue
            else:
                header = ln.lower()
        if not header:
            _logger.info('No header line found in the input file!')
            raise exceptions.UserError(_('Sistemos klaida. Kreipkitės į administratorius.'))
        output = input_lines.read()
        return output, header

    @api.multi
    def _get_csv_lines_reader(self):
        lines, header = self._remove_leading_lines(self.lines)
        self._header_fields = csv.reader(StringIO.StringIO(header), dialect=self.dialect).next()
        if self._header_fields and self._header_fields[0] and self._header_fields[0].startswith('\xEF\xBB\xBF'):
            self._header_fields[0] = self._header_fields[0].lstrip('\xEF\xBB\xBF').replace('"', '')
        self._header_fields = [h.decode(self.codepage).strip() for h in self._header_fields]
        reader = csv.DictReader(StringIO.StringIO(lines), fieldnames=self._header_fields, dialect=self.dialect)
        return lines, reader

    def get_partner_id(self, partner_name='', partner_email='', kliento_kodas=''):
        if not partner_name and not partner_email:
            return False
        ResPartner = self.env['res.partner']
        partner_ids = ResPartner
        if partner_email and partner_name:
            partner_ids = ResPartner.search([('email', '=', partner_email), ('name', '=', partner_name)])
        if not partner_ids and partner_name:
            partner_ids = ResPartner.search([('name', '=', partner_name)])
        if not partner_ids and partner_email:
            partner_ids = ResPartner.search([('email', '=', partner_email)])
        if not partner_ids and partner_name:
            partner_name_short = partner_name.replace('AB ', '').replace('UAB ', '').replace(', UAB', ''). \
                replace(', AB', '').strip()
            partner_ids = ResPartner.search([('name', 'ilike', partner_name_short)])
        if partner_ids:
            return partner_ids[0].id
        else:
            return False

    def _get_currency_info_from_lines(self, vals):
        """
        Gets currency info from lines data to process

        :param vals: a list of dictionaries (one per line) with the key 'currency'
        :return: dictionary containing journal currency, statement currency, and boolean wether it is company currency or not
        """
        company_currency = self.env.user.company_id.currency_id
        journal_currency = self.journal_id.currency_id or company_currency

        currency_name = set()
        for date_data in itervalues(vals):
            currency_name |= set(line['currency'] for line in date_data)
        if len(currency_name) > 1:
            raise exceptions.UserError(_('Visos eilutės turėtų būti ta pačia valiuta'))
        if currency_name:
            currency = self.env['res.currency'].search([('name', '=ilike', currency_name.pop())], limit=1)
            if not currency:
                raise exceptions.UserError(_('Nepavyko nustatyti išrašo valiutos'))
            if journal_currency and journal_currency != currency:
                raise exceptions.UserError(_('Išrašo valiuta nesutampa su žurnalu'))
        else:
            currency = journal_currency

        return {'currency': currency,
                'journal_currency': journal_currency,
                'use_currency': True if currency != company_currency else False}

    def _get_possible_date_formats(self):
        """ Gets possible date format strings from the selection in force_date_format. Cam be overriden to change possibilities """
        return [value[0] for value in self._fields['force_date_format'].selection]

    def _guess_date_format(self, vals):
        """ Guesses the date format from list of dict with key 'date'. Raises error when cannot settle on unique format """
        date_formats = self._get_possible_date_formats()
        valid_date_format = []
        for date_format in date_formats:
            try:
                for day in vals:
                    datetime.strptime(day, date_format)
            except ValueError:
                pass
            else:
                valid_date_format += [date_format]
        if len(valid_date_format) == 1:
            date_format = valid_date_format[0]
        else:
            raise exceptions.UserError(
                _('Nepavyko nustatyti datos formato. Pabandykite pasirinkti priverstinį datos formatą.'))

        return date_format

    @staticmethod
    def _get_input_fields():
        """ Intended to be overridden. Returns the list of field names to import from CSV file """
        return {}

    @staticmethod
    def _get_error_message_format():
        """ Intended to be overriden to return a more detailed message """
        return {'message': _('Nepavyko importuoti operacijų')}

    @staticmethod
    def _format_error_message(error_format, error_lines):
        """
        Nicely format error messages about import sent to accountants

        :param error_format dict with keys message and table_format. Table format is a list of tuples for table headers
                            and corresponding key in the error_lines dicts
        :param error_lines list of dicts containing failed CSV lines value

        :return formatted error message for email
        """
        message = error_format.get('message') or _('Nepavyko importuoti šių operacijų:')
        table_format = error_format.get('table_format')
        if table_format:
            headers = [f[0] for f in table_format]
            keys = [f[1] for f in table_format]
            table = '<table border="2" width=100%% style="text-align:center"><tr>' + ''.join(
                map(lambda h: '<th style="text-align:center"><b>' + h + '</b></th>', headers)) + '</tr>'
            err_line_base = '<tr>' + ''.join(map(lambda k: '<td>{' + str(k) + '}</td>', range(len(keys)))) + '</tr>'
            for err_line in error_lines[:100]:
                table += err_line_base.format(*(err_line.get(k, '') for k in keys))
            table += '</table>'
            message += table
        return message

    @staticmethod
    def _get_bug_subject():
        """ Intended to be overriden to return a more specific email subject """
        return _('Nepavyko importuoti operacijų')

    def _process_error_lines(self, error_lines):
        """ Sends error message according to error lines. Calls methods that should be overridden for custom messages """
        if not error_lines:
            return
        error_format = self._get_error_message_format()
        message = self._format_error_message(error_format, error_lines)
        subject = self._get_bug_subject() + ' [%s]' % self.env.cr.dbname

        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': subject,
            'error_message': message,
            'skip_ticket_creation': True,
        })
        if self.env.user.partner_id.email:
            self.env['script'].send_email(emails_to=[self.env.user.partner_id.email],
                                          subject=subject,
                                          body=message)

    def _preprocess_vals(self, vals):
        """
        Intended to be overriden. Update vals if necessary. Returns False if line should be added to errors
        :param vals: dict of read values. Might be extended to add 'reason' attribute, if line is to be skipped,
                     or other attributes to be used by the processing methods later
        :return: Boolean, True if line should be processed, False if line should be skipped
        """
        return True

    def _process_lines(self, vals):
        """ Intended to be overriden. Returns a list of IDs for generated or updated bank statements """
        return []

    def line_skip_test(self, line):
        """ Allow to define line skipping condition that would ignore a line from the CSV reading"""
        return line[0] == '#'

    @api.multi
    def csv_import(self):
        ''' called from the import csv button '''
        self.with_delay(
            channel='root.statement_import', 
            eta=5, identity_key=identity_exact
        ).csv_import_job(self._context)

    @job
    @api.multi
    def csv_import_job(self, additional_context=None):
        """ Import CSV statement """
        try:
            if not additional_context:
                additional_context = {}
            self.with_context(**additional_context).action_import()
            subject = 'Succeeded in importing a CSV statement'
            body = '''The submitted CSV file to journal %s was imported''' % self.journal_id.name
            self.env['script'].send_email([self.env.user.login], subject, body)
        except Exception as e:
            #inform user
            err_msg = str(e.args[0])
            subject = 'Failed to import CSV statement'
            body = '''CSV import error: %s\n
                    The submitted CSV file to journal %s could not be imported''' % \
                    (err_msg, self.journal_id.name)
            self.send_ticket(subject, body)

    def send_ticket(self, subject, body):
        self.env.cr.rollback()
        self.env['script'].send_email([self.env.user.login], subject, body)
        try:
            ticket_obj = self.env['mail.thread'].sudo()._get_ticket_rpc_object()
            vals = {
                'ticket_dbname': self.env.cr.dbname,
                'ticket_model_name': self._name,
                'ticket_record_id': False,
                'name': subject,
                'ticket_user_login': self.env.user.login,
                'ticket_user_name': self.env.user.name,
                'description': body,
                'ticket_type': 'accounting',
                'user_posted': self.env.user.name
            }
            res = ticket_obj.create_ticket(**vals)
            if not res:
                raise exceptions.UserError('The distant method did not create the ticket.')
        except Exception as e:
            message = 'Failed to create ticket for informing about csv import\nException: %s' % \
                    (str(e.args))
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': message,
            })

    @api.multi
    def action_import(self):
        """
        Main import method -- Not meant to be overridden, but calls to multiple methods meant to be
        overridden for specific CSV format import
        :return: action to created statements or raise if no statement
        :rtype: dict()
        """
        lines, reader = self._get_csv_lines_reader()
        input_fields = self._get_input_fields()
        val_lines = {}
        err_lines = []

        for line_nr, line in enumerate(reader, self.lines_to_skip + 2):
            vals = {'line_nr': line_nr}
            # step 1: handle codepage
            for i, hf in enumerate(self._header_fields):
                try:
                    if line[hf]:
                        line[hf] = line[hf].decode(self.codepage).strip()
                except UnicodeDecodeError as e:
                    _logger.info(_('Error while processing line: %s\nError message: %s') % (line, str(e)))
                    raise exceptions.UserError(_('Nepavyko iššifruoti failo. Pabandykite pasirinkti kitą koduotę arba '
                                                 'susisiekite su sistemos administratoriumi.'))
            # step 2: process input fields
            for i, hf in enumerate(self._header_fields):
                if i == 0 and line[hf] and self.line_skip_test(line[hf]):
                    # lines starting with # are considered as comment lines
                    break
                if hf not in input_fields:
                    continue
                vals.update({hf: line[hf]})

            if not self._preprocess_vals(vals):
                err_lines.append(vals)
                continue

            date = vals.get('date')
            if date:
                val_lines.setdefault(date, []).append(vals)

        self._process_error_lines(err_lines)
        if not val_lines:
            raise exceptions.UserError(_('Lines to import not found.'))
        statement_ids = self._process_lines(val_lines)

        if statement_ids:
            statements = self.env['account.bank.statement'].browse(statement_ids)
            # Update factual balances
            for statement in statements:
                statement.balance_end_factual = statement.balance_end_real
            if self.apply_import_rules:
                statements.with_context(
                    skip_error_on_import_rule=self.skip_import_rules_error).apply_journal_import_rules()

            action = self.env.ref('account.action_bank_statement_tree')
            return {
                'name': action.name,
                'view_type': 'form',
                'view_mode': 'tree,form',
                'res_model': action.res_model,
                'domain': [('id', 'in', statement_ids)],
                'context': action.context,
                'type': 'ir.actions.act_window',
            }

SepaCsvImporter()


def str2float(amount, decimal_separator):
    if not amount:
        return 0.0
    try:
        if decimal_separator == '.':
            return float(amount.replace(',', ''))
        else:
            return float(amount.replace('.', '').replace(',', '.'))
    except:
        return False
