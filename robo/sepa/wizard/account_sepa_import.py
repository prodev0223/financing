# -*- encoding: utf-8 -*-
from __future__ import division
import base64
from odoo import fields, models, api, exceptions, tools
from odoo.tools.translate import _
import logging
import re
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError, tostring
import os
from dateutil.parser import parse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from six import iteritems
import pytz

_logger = logging.getLogger(__name__)

bank_codes_limitations = ['72900']

force_partner_codes = {
    'Valstybinė mokesčių inspekcija prie Lietuvos Respublikos finansų ministerijos': '188659752'
}


def xml_validator(some_xml_string, xsd_file='/path/to/my_schema_file.xsd'):
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True
    except XMLSyntaxError:
        return False


def find_corrupt_statement_lines(env, data):
    """
    Admin tool used to find entries for the period of the statement
    that are in the system but not in the file, used for de-duplicating entries
    and finding corrupt entries in the system
    :param env: odoo environment
    :param data: statements data (dict)
    :return: None
    """
    # Return if user is not admin
    if not env.user.has_group('base.group_system'):
        return

    # Get the needed data
    dates = data.get('dates')
    transactions = data.get('transactions')
    journal_id = data.get('journal_id')
    delete_entries = data.get('delete_entries')

    latest_date = max(dates)
    earliest_date = min(dates)
    # Search for all of the statements in given period
    period_statements = env['account.bank.statement'].search(
        [('journal_id', '=', journal_id), ('sepa_imported', '=', True),
         ('date', '>=', earliest_date), ('date', '<=', latest_date)]
    )
    period_system_lines = period_statements.mapped('line_ids')

    amount_to_import = 0.0
    file_found_lines = env['account.bank.statement.line']

    duplicate_lines = env['account.bank.statement.line']
    # Loop through transactions and search for the lines
    # by comparing date, amount and entry reference
    for tr in transactions:
        date = tr['date']
        ref = tr['entry_reference']
        amounts = tr['amounts']
        amt = amounts['transaction']['amount']
        found_line = period_system_lines.filtered(
            lambda x: x.date == date and x.entry_reference == ref and x.amount == amt)
        if not found_line:
            for ref in tr.get('other_references', {}).values():
                found_line = period_system_lines.filtered(
                    lambda x: x.date == date and x.entry_reference == ref and x.amount == amt)
                if found_line:
                    break
        if not found_line:
            amount_to_import += amt
        elif len(found_line) > 1:
            duplicate_lines |= found_line[0]
        else:
            file_found_lines |= found_line

    # Potentially corrupt entries are those that were in the system
    # but are not contained in the actual file
    corrupt_entries = period_system_lines - file_found_lines
    to_import = not tools.float_is_zero(amount_to_import, precision_digits=2)

    if corrupt_entries or duplicate_lines or to_import:
        if delete_entries:
            data = {}
            # Use this instead of filtered, for speed
            for entry in corrupt_entries:
                data.setdefault(entry.statement_id, env['account.bank.statement.line'])
                data[entry.statement_id] |= entry
            # Loop through statements, delete the lines
            # recalculate balances and reconfirm them
            for statement, lines in iteritems(data):
                reconfirm = statement.state == 'confirm'
                statement.button_draft()
                lines.button_cancel_reconciliation()
                statement.write({'balance_end_real': statement.balance_end_real - sum(lines.mapped('amount'))})
                lines.unlink()
                if reconfirm:
                    statement.check_confirm_bank()
            env.cr.commit()
            raise exceptions.ValidationError('Entries were removed')
        else:
            # If entries are not meant to be deleted
            # Collect them into a report, and display the result
            total_corrupt_amount = 0.0
            base = str()
            if corrupt_entries:
                corrupt_entries = corrupt_entries.sorted(key=lambda r: r.date)
                base = 'Found following corrupt lines that are in the system ' \
                       'but not in the statement\n Period {} - {}\n\n'.format(earliest_date, latest_date)
                for entry in corrupt_entries:
                    base += 'Date - {}, Name - {}, Amt - {}, EnRef - {}\n'.format(
                        entry.date, entry.name, entry.amount, entry.entry_reference)
                    total_corrupt_amount += entry.amount
                base += 'Total corrupt amount {}'.format(total_corrupt_amount)
            if duplicate_lines:
                base += '\n\n\n Duplicates that correspond to same entry_ref were found\n\n'
                for entry in duplicate_lines:
                    base += 'Date - {}, Name - {}, Amt - {}, EnRef - {}\n'.format(
                        entry.date, entry.name, entry.amount, entry.entry_reference)
            if to_import:
                base += '\n\n\n Amount that is not yet in the system - {}'.format(amount_to_import)
            raise exceptions.ValidationError(base)


class AccountSepaImport(models.TransientModel):

    _name = 'account.sepa.import'

    _description = 'SEPA importavimas'
    coda_data = fields.Binary(string='SEPA failas', required=True)
    coda_fname = fields.Char(string='SEPA failo pavadinimas', size=128, required=False)
    skip_currency_rate_checks = fields.Boolean(string='Praleisti valiutos kursų skirtumų tikrinimus')
    skip_group_payment_import = fields.Boolean(string='Skip group payment import', default=True)

    # Used when file passes the schema validation but does not contain a namespace header
    force_sepa_import = fields.Boolean(string='Forcibly import SEPA file')
    forced_import_type = fields.Selection([
        ('053.001.02', 'Full day statement (CAMT 053)'),
        ('052.001.02', 'Partial day statement (CAMT 052)'),
    ], default='053.001.02')
    display_psd2_warning = fields.Boolean(compute='_compute_display_psd2_warning')

    @api.model
    def default_get(self, fields):
        res = super(AccountSepaImport, self).default_get(fields)
        journal = self.get_related_journal()
        if journal:
            res['display_psd2_warning'] = journal.has_psd2_statements()
        return res

    @api.multi
    def _compute_display_psd2_warning(self):
        """
        Check whether warning for SEPA/PSD2 mismatch-skipping should be displayed
        """
        journal = self.get_related_journal()
        has_psd2_statements = journal.has_psd2_statements() if journal else False
        for rec in self:
            rec.display_psd2_warning = has_psd2_statements

    @api.model
    def get_related_journal(self):
        journal = False
        active_id = self._context.get('active_id')
        active_model = self._context.get('active_model')
        if active_id and active_model == 'account.journal':
            journal = self.env[active_model].browse(active_id).exists()
        return journal

    def get_namespace(self, element):
        m = re.match('\{.*\}', element.tag)
        return m.group(0) if m else ''

    def save_attachment(self):
        attach_vals = {'res_model': 'account.bank.statement',
                       'name': 'Sepa import' + str(self.coda_fname),
                       'datas_fname': str(self.coda_fname),
                       'type': 'binary',
                       'datas': self.coda_data,
                       }
        self.env['ir.attachment'].sudo().create(attach_vals)

    def get_partner_id(self, partner_name='', partner_identification='',  partner_iban='', ext_id=''):
        """
        :param ext_id: is meant to be overridden in dedicated client modules
        :param partner_name
        :param partner_identification contains a tuple of value and key. e.g. LT123 and vat_code
        :param partner_iban contains partner iban_code
        """

        def partner_search(s_cases, operator='ilike', s_field='name'):
            """Search for partners by passed search_field using passed case list
               Return partner record only if single instance was found"""
            if not isinstance(s_cases, list):
                s_cases = [s_cases]
            for s_case in s_cases:
                # If search field is name, do extra check on sanitized name
                if s_field == 'name':
                    r_partners = partner.search([('sanitized_name', operator, s_case)])
                    if len(r_partners) == 1:
                        return r_partners
                # Otherwise proceed with usual operation, and break the loop if partner is found
                r_partners = partner.search([(s_field, operator, s_case)])
                if len(r_partners) == 1:
                    return r_partners
                # If we find more than one partner with the same company code,
                # try to filter out subsidiary companies and find the parent one
                # if there are partners with no parent, return the first one
                # since 'kodas' search is very explicit
                elif len(r_partners) > 1 and s_field == 'kodas':
                    r_partners = r_partners.filtered(lambda x: not x.parent_id)
                    if r_partners:
                        return r_partners[0]
            return partner

        # If none of the needed values are passed, just return
        if not partner_name and not partner_identification and not partner_iban:
            return False

        partner = self.env['res.partner']
        searchable = value = False

        # Perform basic partner searches
        if partner_identification:
            searchable, value = partner_identification
            if searchable and value:
                # Strip the code value
                value = str(value).strip()
                partner = partner_search(value, operator='=', s_field=searchable)
        if not partner and partner_iban:
            partner = partner_search(partner_iban, operator='=', s_field='bank_ids.acc_number')
        if not partner and partner_name:
            partner = partner_search([partner_name, partner_name.lower()], operator='=')

        # Perform more nuanced partner searches if partner name exists
        if not partner and partner_name:
            index = None
            w_form = str()
            work_forms = ['uab', 'mb', 'vsi', 'vši', 'všį', 'ab']
            for work_form in work_forms:
                if work_form in partner_name.lower():
                    index = partner_name.lower().find(work_form)
                    w_form = work_form
                    break
            if index is not None:
                sanitize_rules = [',', '.', "'", '"']
                try:
                    form = partner_name[index: index + len(w_form)]
                    name = partner_name.replace(form, '')
                except ValueError:
                    return False
                for rule in sanitize_rules:
                    name = name.replace(rule, '')
                name = name.strip()
                cases = ['{}, {}'.format(form, name), '{}, {}'.format(name, form), '"{}", {}'.format(name, form),
                         '{}, "{}"'.format(form, name), '{} {}'.format(name, form), '{} {}'.format(form, name),
                         '{} "{}"'.format(form, name), '"{}" {}'.format(name, form),
                         '{}'.format(name), '"{}"'.format(name), "'{}'".format(name)]
                partner = partner_search(cases)
            if not partner:
                name_parts = partner_name.split(' ')
                cases = []
                if len(name_parts) > 3:
                    filtered_out = []
                    for part in name_parts:
                        if len(part) > 4 and not part.isdigit():
                            filtered_out.append(part)
                    if len(filtered_out) in [2, 3]:
                        name_parts = filtered_out
                if len(name_parts) == 2:
                    cases = ['{} {}'.format(name_parts[0], name_parts[1]), '{} {}'.format(name_parts[1], name_parts[0])]
                if len(name_parts) == 3:
                    cases = ['{} {} {}'.format(name_parts[0], name_parts[1], name_parts[2]),
                             '{} {} {}'.format(name_parts[0], name_parts[2], name_parts[1]),
                             '{} {} {}'.format(name_parts[1], name_parts[0], name_parts[2]),
                             '{} {} {}'.format(name_parts[1], name_parts[2], name_parts[0]),
                             '{} {} {}'.format(name_parts[2], name_parts[0], name_parts[1]),
                             '{} {} {}'.format(name_parts[2], name_parts[1], name_parts[0]),
                             ]
                partner = partner_search(cases)
            # Perform one final check
            if not partner:
                short_name = partner_name.replace('AB ', '').replace('UAB ', '').replace(', UAB', '').\
                    replace(', AB', '').strip()
                partner = partner_search(short_name, operator='like')

        # If there's no partner, and we have name and code, create it
        if not partner and partner_name and value and searchable == 'kodas':
            partner = partner.create({'name': partner_name, searchable: value})
            partner.vz_read()
        return partner.id

    @api.multi
    def coda_parsing(self):
        statement_ids, err_message, num_errors = self.import_camt()
        self._cr.commit()
        if num_errors:
            raise exceptions.Warning(err_message)
        else:
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

    def import_camt(self):
        self.ensure_one()
        codafile = self.coda_data
        recordsfile = base64.b64decode(codafile)
        if self._context.get('no_save', True):
            self.save_attachment()
        # Build extra context dict and pass it to parsing functions
        extra_context = {
            'skip_group_payment_import': self.skip_group_payment_import,
            'skip_currency_rate_checks': self.skip_currency_rate_checks,
            'force_sepa_import': self.force_sepa_import,
            'forced_import_type': self.forced_import_type,
        }
        rpt_vals, version = self.env['account.bank.statement.import.sepa.parser'].with_context(
            **extra_context).parse(recordsfile)
        statement_ids, notifications, num_errors = self.create_statements(rpt_vals, version)
        if num_errors > 0:
            err_message = _('%s įrašų neimportuota dėl šių klaidų: %s') % (num_errors, ', '.join(set(notifications)))
        else:
            err_message = ''
        return statement_ids, err_message, num_errors

    def get_lines(self, line_vals, journal_id, stmt_curr):
        '''returns list of values of lines to create'''
        num_duplicate = 0
        num_imported = 0
        amount_duplicate = 0
        partial_statement = False
        if 'entry_reference' not in line_vals:
            raise exceptions.UserError(_('Nerastas eilutės identifikavimo kodas'))
        entry_reference = line_vals['entry_reference']
        amounts = line_vals['amounts']
        instructed_amount_ccy, instructed_ccy = amounts['instructed']['amount'], amounts['instructed']['ccy']
        tx_amount_ccy, tx_ccy = amounts['transaction']['amount'], amounts['transaction']['ccy']

        # Check if charges exist, and if they do, subtract them from tx_amount_ccy
        charges = True if 'charges' in amounts else False
        if charges:
            charges_amount, charges_ccy = amounts['charges']['amount'], amounts['charges']['ccy']
            if charges_ccy != tx_ccy:
                raise exceptions.ValidationError(
                    _('Komisinių valiuta %s skiriasi nuo gautos valiutos %s') % (charges_ccy, tx_ccy))
            tx_amount_ccy -= charges_amount

        # Search for duplicate account bank statement line based on most precise entry reference
        st_line_obj = self.env['account.bank.statement.line']

        base_domain = [('journal_id', '=', journal_id)]
        # Get both of the dates
        value_date = line_vals.get('value_date')
        line_date = line_vals['date']
        # Check value date, if they differ check them both
        if value_date and value_date != line_date:
            base_domain += ['|', ('date', '=', value_date)]
        base_domain += [('date', '=', line_date)]

        found_duplicate = st_line_obj.search(base_domain + [('entry_reference', '=', entry_reference)])
        # Use filtered and float_compare, very important
        found_duplicate = found_duplicate.filtered(
            lambda x: not tools.float_compare(x.amount, tx_amount_ccy, precision_digits=2))
        if not found_duplicate:
            # If duplicate is not found, search for lines using other references
            for name, ref in iteritems(line_vals.get('other_references', {})):
                found_duplicate = st_line_obj.search(base_domain + [('entry_reference', '=', ref)])
                # Amounts must match for line to be actually considered a duplicate
                found_duplicate = found_duplicate.filtered(lambda x: not tools.float_compare(
                        x.amount, tx_amount_ccy, precision_digits=2))
                if found_duplicate:
                    break

        if found_duplicate:
            num_duplicate += 1
            amount_duplicate += line_vals['amounts']['transaction']['amount']
            partial_statement = found_duplicate[0].statement_id.partial_statement
            return [], num_imported, num_duplicate, amount_duplicate, partial_statement

        instructed_currency_id = self.env['res.currency'].search([('name', '=', instructed_ccy)], limit=1)
        if not instructed_currency_id:
            raise exceptions.Warning(_('Valiuta %s nerasta') % instructed_ccy)
        tx_currency_id = self.env['res.currency'].search([('name', '=', tx_ccy)], limit=1)
        if not tx_currency_id:
            raise exceptions.Warning(_('Valiuta %s nerasta') % tx_ccy)
        if stmt_curr != tx_currency_id:
            raise exceptions.Warning(_('Nesutampa valiutos: žurnalo valiuta %s, o bandoma importuoti %s')
                                     % (stmt_curr.name, tx_currency_id.name))
        partner_name = line_vals.get('partner_name', '')
        partner_code_inf = line_vals.get('partner_inf', '')
        partner_code_ext = line_vals.get('partner_code', '')
        partner_iban = line_vals.get('partner_iban', '')
        partner_id = self.get_partner_id(partner_name=partner_name, partner_identification=partner_code_inf,
                                         partner_iban=partner_iban, ext_id=partner_code_ext)
        new_line_val = {'name': line_vals['name'],
                        'partner_id': partner_id,
                        'info_type': line_vals['info_type'],
                        'sepa_instruction_id': line_vals.get('sepa_instruction_id', ''),
                        'date': line_date,
                        'entry_reference': line_vals['entry_reference'],
                        'ref': line_vals['ref'],
                        'family_code': line_vals.get('family_code', False),
                        'sub_family_code': line_vals.get('sub_family_code', False),
                        'imported_partner_name': partner_name,
                        'imported_partner_code': partner_code_inf[1],
                        'imported_partner_iban': partner_iban,
                        # 'bank_account_id': False,  # todo
                        }
        amount_values = {'amount': tx_amount_ccy}
        if instructed_currency_id != tx_currency_id:
            amount_values.update({'amount_currency': instructed_amount_ccy,
                                  'currency_id': instructed_currency_id.id})
        new_line_val.update(amount_values)
        all_lines = [new_line_val]
        num_imported += 1
        if charges:
            charges_line = dict(new_line_val)
            charges_line.pop('amount', None)
            charges_line.pop('amount_currency', None)
            charges_line.pop('currency_id', None)
            charges_line.update({'charges_line_code': new_line_val['entry_reference'],
                                 'amount': charges_amount,
                                 'sepa_instruction_id': '',
                                 'ref': '',
                                 'entry_reference': '',
                                 'name': 'Komisiniai',
                                 })
            all_lines.append(charges_line)
        return all_lines, num_imported, num_duplicate, amount_duplicate, partial_statement

    @api.model
    def get_statement_values(self, rpt, journal_id, currency):
        """
        Fetch bank statement data from SEPA XML rpt node
        (data is already structured)
        :param rpt: structured RPT data (dict)
        :param journal_id: journal_id of the statement that is being parsed
        :param currency: currency of the statement
        :return: return_data variable structure (dict)
        """

        # Prepare data block to return
        return_data = {
            'statements': [],
            'notifications': [],
            'num_duplicate': 0,
            'num_errors': 0,
            'num_imported': 0,
        }

        # Map and fetch dates that contains at least one transaction, return if there's no dates
        dates_unsorted = list(set(map(lambda tx: tx['date'], rpt['transactions'])))
        if not dates_unsorted:
            return return_data

        balance_start_date = rpt['balance_start_date']
        # If balance_start_date exists and is not in the list, fill it up
        while balance_start_date and balance_start_date not in dates_unsorted:
            dates_unsorted.append(balance_start_date)
            # Balance start date can be later than any statement date,
            # thus we have to execute this check to prevent infinite loop
            if max(dates_unsorted) <= balance_start_date:
                break
            # Add day by day, until every day from balance start to finish is in the list
            next_day_dt = datetime.strptime(
                balance_start_date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
            balance_start_date = next_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        # Sort the dates and determine earliest date of the batch
        dates = sorted(dates_unsorted)
        earliest_date = min(dates)

        # ADMIN TOOL
        if self._context.get('find_corrupt_entries'):
            find_corrupt_statement_lines(self.env, data={
                'dates': dates,
                'transactions': rpt['transactions'],
                'journal_id': journal_id,
                'delete_entries': self._context.get('delete_entries'),
            })
        # // ADMIN TOOL

        # Check whether there is a statement earlier than earliest batch date
        last_stmt = self.env['account.bank.statement']
        if journal_id and earliest_date:
            last_stmt = self.env['account.bank.statement'].search(
                [('journal_id', '=', journal_id),
                 ('sepa_imported', '=', True), ('date', '<', earliest_date)], limit=1, order='date desc')

        # If latest statement exits, and it's not a partial statement, we take it's end balance
        balance_end_compute = last_stmt.balance_end_real \
            if last_stmt and not last_stmt.partial_statement else rpt['balance_start']
        total_entry_sum = 0
        # Loop though the list of dates
        for en, date in enumerate(dates):
            balance_start_compute = balance_end_compute
            lines = []
            amount_duplicate = 0
            for transaction in rpt['transactions']:
                if transaction['date'] != date:
                    continue
                # Try to fetch the lines of the transaction
                try:
                    # Check whether there is any new or duplicate lines
                    new_lines, num_new_imported, num_new_dup, amount_new_dup, partial_statement = self.get_lines(
                        transaction, journal_id, currency)
                    if not partial_statement:
                        amount_duplicate += amount_new_dup
                except exceptions.Warning as e:
                    new_lines, num_new_imported, num_new_dup = [], 0, 0
                    return_data['num_errors'] += 1
                    return_data['notifications'].append(e.name)
                return_data['num_imported'] += num_new_imported
                return_data['num_duplicate'] += num_new_dup
                lines.extend(new_lines)
            total_entry_sum += amount_duplicate
            newly_imported_amount = sum(map(lambda l: l['amount'], lines))
            balance_end_compute = balance_start_compute + newly_imported_amount + amount_duplicate
            statement_vals = {
                'name': '/',
                'date': date,
                'journal_id': journal_id,
                'balance_start': balance_start_compute,
                'balance_end_real': balance_end_compute,
                'balance_end_factual': balance_end_compute,
                'statement_id_bank': rpt['statement_id_bank'],
                'sepa_imported': True,
                'line_ids': lines,
            }

            # If its first iteration of the loop, use fetched balance start
            if not en:
                statement_vals['balance_start_factual'] = rpt['balance_start']
            # If it's the last iteration of the loop, use fetched balance end if it's not zero
            if en + 1 == len(dates) and not tools.float_is_zero(
                    rpt.get('balance_end_real', 0.0), precision_digits=2
            ):
                statement_vals['balance_end_factual'] = rpt['balance_end_real']

            return_data['statements'].append(statement_vals)
        return return_data

    def _complete_rpt_vals(self, rpts_vals):
        stmnts = []
        balance_vals = []
        num_orig_txs = 0
        notifications = []
        num_duplicate = 0
        num_errors = 0
        num_imported = 0
        c_registry = self.env.user.company_id.company_registry
        for rpt_val in rpts_vals:
            # Check for company mismatch
            company_mismatch = rpt_val.get('stmt_company') and c_registry != rpt_val.get('stmt_company')
            currency_code, account_number = rpt_val.get('currency', 'EUR'), rpt_val.get('account_number')  # assume default currency EUR

            if not account_number:
                raise exceptions.ValidationError(_('Account number is not specified'))

            # Some banks still pass statements in historic LTL currency,
            # if we encounter it we just skip to the next loop without importing.
            if currency_code == 'LTL':
                continue
            currency, journal = self._find_additional_data(currency_code, account_number)

            # If we find a journal and it's not active, we skip statement parsing by default.
            # Client has to activate the journal manually if they want the statements to be imported.
            if journal and not journal.active:
                continue

            num_orig_txs += len(rpt_val.get('transactions', []))
            bank_code = account_number[4:9]
            if not journal:
                # If company mismatches or bank code is in limitations, throw the error
                if company_mismatch or bank_code in bank_codes_limitations:
                    raise exceptions.ValidationError(
                        _('Reikia pririšti sąskaitą %s (%s) prie žurnalo') % (account_number, currency_code))

                code = self.env['account.journal'].get_journal_code_bank()
                bank_id = self.env['res.bank'].search([('kodas', '=', bank_code)], limit=1)
                journal = self.sudo().env['account.journal'].create({
                    'name': '%s (%s) %s' % (bank_id.name or _('Bankas'), account_number[-4:], currency.name),
                    'code': code,
                    'bank_statements_source': 'file_import',
                    'type': 'bank',
                    'company_id': self.env.user.company_id.id,
                    'currency_id': currency.id,
                    'bank_acc_number': account_number,
                    'bank_id': bank_id.id,
                })

            if company_mismatch and bank_code not in bank_codes_limitations:
                raise exceptions.ValidationError(_('Neatitikimas tarp kompanijų!'))
            # Fetch statement values
            values = self.get_statement_values(rpt_val, journal.id, currency)
            stmnts.extend(values['statements'])
            balance_end_real = rpt_val['balance_end_real']
            balance_end_date = rpt_val['balance_end_date']
            balance_vals.append({'journal_id': journal.id, 'date': balance_end_date, 'amount': balance_end_real})
            num_imported += values['num_imported']
            num_duplicate += values['num_duplicate']
            num_errors += values['num_errors']
            notifications.extend(values['notifications'])
        # If context is passed for admin check, raise here, outside of the loop
        if self._context.get('find_corrupt_entries'):
            raise exceptions.ValidationError('No corrupt entries were found')
        return stmnts, num_imported, balance_vals, num_orig_txs, num_duplicate, num_errors, notifications

    def _find_additional_data(self, currency_code, account_number):
        currency = self.env['res.currency'].search([('name', '=ilike', currency_code)], limit=1)
        # sometimes banks give old ISO currency code for Belorussian ruble
        if not currency and currency_code == 'BYR':
            currency_code = 'BYN'
            currency = self.env['res.currency'].search([('name', '=ilike', currency_code)], limit=1)
        if not currency:
            raise exceptions.Warning(_("No currency found matching '%s'.") % currency_code)
        journal = self.env['account.journal']
        if len(account_number) > 0:
            self._cr.execute(
                "select id from res_partner_bank where replace(replace(acc_number,' ',''),'-','') = %s",
                (account_number,))
            bank_ids = [id[0] for id in self._cr.fetchall()]
            bank_accs = self.env['res.partner.bank'].browse(bank_ids)
            journals = bank_accs.with_context(active_test=False).mapped('journal_id').filtered(
                lambda x: (x.currency_id and x.currency_id == currency) or (
                        not x.currency_id and x.company_id.currency_id == currency)
            )
            if journals:
                # Give priority to the already active journal
                active_journal = journals.filtered(lambda x: x.active)
                journal = active_journal and active_journal[0] or journals[0]

        return currency, journal

    def _update_balances(self, journal_id, date, end_balance):
        new_statement_ids = []
        if not date:
            return new_statement_ids
        # Search for bank statement for current date
        statement = self.env['account.bank.statement'].search(
            [('journal_id', '=', journal_id), ('date', '=', date), ('sepa_imported', '=', True)], limit=1
        )
        # If statement is found and it's imported via PSD2, SEPA XML import can't modify it in any way
        if statement.psd2_statement:
            return new_statement_ids

        if statement:
            statement.balance_end_real = end_balance
            statement.balance_end_factual = end_balance
        else:
            bank_statement = self.env['account.bank.statement'].create({'name': '/',
                                                                        'date': date,
                                                                        'journal_id': journal_id,
                                                                        'balance_start': end_balance,
                                                                        'balance_end_real': end_balance,
                                                                        'balance_end_factual': end_balance,
                                                                        'sepa_imported': True,
                                                                        })
            bank_statement.button_confirm_bank()
            new_statement_ids.append(bank_statement.id)
        if not statement.line_ids:
            try:
                statement._balance_check()
            except exceptions.UserError:
                pass
            else:
                statement.button_confirm_bank()
        return new_statement_ids

    @api.model
    def update_balance_values(self, statement, statement_vals):
        """
        Update found account.bank.statement values with
        newly fetched values from XML file
        :param statement: account.bank.statement record
        :param statement_vals: statement values from XML
        :return: None
        """
        statement.balance_end_real = statement_vals['balance_end_real']
        statement.balance_start = statement_vals['balance_start']

        # Only first and last statements of the batch have factual balances
        if statement_vals.get('balance_start_factual'):
            statement.balance_start_factual = statement_vals.get('balance_start_factual')
        if statement_vals.get('balance_end_factual'):
            statement.balance_end_factual = statement_vals.get('balance_end_factual')

    def _create_bank_statements(self, stmts_vals, version, partial_days):
        stm_line_obj = self.env['account.bank.statement.line']
        statement_ids = []
        for stmt_val in stmts_vals:
            old_statement = True
            journal_id = stmt_val['journal_id']
            date = stmt_val['date']
            statement = self.env['account.bank.statement'].search(
                [('date', '=', date), ('journal_id', '=', journal_id), ('sepa_imported', '=', True)], limit=1
            )
            # If statement is found and it's imported via PSD2, SEPA XML import can't modify it in any way
            if statement.psd2_statement:
                continue

            partial_vals = True if version in ['052'] and date in partial_days else False
            # If corresponding partial statement is found, and current vals are not partial -- update it
            if statement.partial_statement and (version in ['053'] or date not in partial_days):
                statement.partial_statement = False
                self.update_balance_values(statement, stmt_val)

            # If bank statement is not partial and normalization is skipped, always update the values
            if statement and not statement.partial_statement and \
                    statement.journal_id.skip_bank_statement_normalization:
                self.update_balance_values(statement, stmt_val)

            # Skip further creation/updates if there are no new lines
            if not stmt_val['line_ids']:
                continue

            if not statement:
                old_statement = False
                new_statement_vals = {'name': stmt_val['name'],
                                      'balance_start': 0 if partial_vals else stmt_val['balance_start'],
                                      'journal_id': stmt_val['journal_id'],
                                      'statement_id_bank': stmt_val['statement_id_bank'],
                                      'date': stmt_val['date'],
                                      'sepa_imported': True,
                                      'balance_end_real': 0 if partial_vals else stmt_val['balance_end_real'],
                                      'partial_statement': partial_vals
                                      }
                if stmt_val.get('balance_start_factual', False):
                    new_statement_vals['balance_start_factual'] = stmt_val.get('balance_start_factual', False)
                if stmt_val.get('balance_end_factual', False):
                    new_statement_vals['balance_end_factual'] = stmt_val.get('balance_end_factual', False)
                statement = self.env['account.bank.statement'].create(new_statement_vals)

            # Always set artificial statement to False
            # if we receive it's values during SEPA import
            values_to_write = {'artificial_statement': False}

            newly_imported_lines = False
            for line in stmt_val['line_ids']:
                if tools.float_is_zero(line['amount'], precision_digits=2):
                    continue
                if line.get('charges') and line.get('charges_line_code'):
                    orig_ref = line['charges_line_code']
                    orig_line = stm_line_obj.search([('entry_reference', '=', orig_ref)], limit=1)
                    if orig_line:
                        line['commission_of_id'] = orig_line.id
                    line.pop('charges_line_code')
                else:
                    pass
                line.update({'statement_id': statement.id})
                new_line = stm_line_obj.create(line)
                if old_statement:
                    statement.balance_end_real += new_line.amount
                newly_imported_lines = True
            # Force 'open' state if there are any newly imported lines during this operation
            if newly_imported_lines:
                values_to_write.update({'state': 'open'})

            statement.write(values_to_write)
            statement_ids.append(statement.id)
        return statement_ids

    @api.multi
    def create_statements(self, rpt_vals, version):
        # Prepare statement data to be used for bank statements creation
        stmts_vals, num_imported, balance_vals, num_orig_tx, num_duplicate, num_errors, notifications = self._complete_rpt_vals(rpt_vals)
        # Partial days are going to be the same for all rpt_vals, so we take them from the first one
        partial_days = rpt_vals and rpt_vals[0].get('partial_days') or []
        # Create the bank statements
        statement_ids = self._create_bank_statements(stmts_vals, version, partial_days)
        for balance_val in balance_vals:
            journal_id = balance_val['journal_id']
            date = balance_val['date']
            end_balance = balance_val['amount']
            additional_ids = self._update_balances(journal_id, date, end_balance)
            statement_ids.extend(additional_ids)
        if num_orig_tx != num_imported + num_duplicate + num_errors:
            raise exceptions.Warning(_('Nenumatyta sistemos klaida importuojant. Kreipkitės į sistemos administratorių.'))
        journal_ids = self.env['account.bank.statement'].browse(statement_ids).mapped('journal_id.id')
        empty_statements = self.env['account.bank.statement'].normalize_balances_descending(journal_ids=journal_ids)
        statement_ids.extend(empty_statements.ids)
        statements = self.env['account.bank.statement'].browse(statement_ids)
        lines_to_skip = self.env['account.bank.statement.line']
        if not self.env.context.get('skip_autoreconciliation_sodra_gpm'):
            lines_to_skip += statements._auto_reconcile_SODRA_and_GPM()
        lines_to_skip += statements.with_context(skip_error_on_import_rule=True).apply_journal_import_rules()
        statements.mapped('line_ids').auto_reconcile_with_accounting_entries(lines_to_skip=lines_to_skip)
        return statement_ids, notifications, num_errors


AccountSepaImport()


def rmspaces(s):
    return " ".join(s.split())


class CamtParser(models.AbstractModel):

    _name = 'account.bank.statement.import.sepa.parser'

    def parse_amount(self, ns, node):
        if node is None:
            return 0.0
        sign = 1
        amount = 0.0
        sign_node = node.xpath('ns:CdtDbtInd', namespaces={'ns': ns})
        if sign_node and sign_node[0].text == 'DBIT':
            sign = -1
        amount_node = node.xpath('ns:Amt', namespaces={'ns': ns})
        if amount_node:
            amount = sign * float(amount_node[0].text)
        return amount

    def parse_info_type(self, ns, node):
        if node is None:
            return 'unstructured'
        structured = node.xpath('ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Strd', namespaces={'ns': ns})
        if structured:
            return 'structured'
        return 'unstructured'

    def parse_amounts(self, ns, node):
        if node is None:
            return 0.0
        sign = 1

        sign_node_paths = ['ns:CdtDbtInd', 'ns:NtryDtls/ns:TxDtls/ns:CdtDbtInd']
        for path in sign_node_paths:
            sign_node = node.xpath(path, namespaces={'ns': ns})
            if sign_node and sign_node[0].text == 'DBIT':
                sign = -1

        # Path of amount details node
        amt_dls = 'ns:NtryDtls/ns:TxDtls/ns:AmtDtls/'
        tx_amount_nodes = node.xpath(amt_dls + 'ns:TxAmt/ns:Amt', namespaces={'ns': ns})
        if not tx_amount_nodes:
            tx_amount_nodes = node.xpath('ns:NtryDtls/ns:TxDtls/ns:Amt', namespaces={'ns': ns})

        if tx_amount_nodes:
            tx_amount_node = tx_amount_nodes[0]
            tx_amount_currency = sign * float(tx_amount_node.text)
            tx_currency_name = tx_amount_node.attrib['Ccy']
        else:
            amount_node = node.xpath('ns:Amt', namespaces={'ns': ns})
            if amount_node:
                tx_amount_currency = sign * float(amount_node[0].text)
                tx_currency_name = amount_node[0].attrib['Ccy']
            else:
                tx_amount_currency = 0.0
                tx_currency_name = ''

        istd_amount_nodes = node.xpath(amt_dls + 'ns:InstdAmt/ns:Amt', namespaces={'ns': ns})
        if istd_amount_nodes:
            istd_amount_node = istd_amount_nodes[0]
            inst_amount_currency = sign * float(istd_amount_node.text)
            inst_currency_name = istd_amount_node.attrib['Ccy']
        else:  # pvz. banko komisiniai
            inst_amount_currency = tx_amount_currency
            inst_currency_name = tx_currency_name

        skip_checks = self._context.get('skip_currency_rate_checks')
        if not skip_checks and inst_currency_name and inst_currency_name != tx_currency_name:
            # Search for source currency if its not found, or
            exchange_rate_amount = 1.0

            curr_exchange_nodes = node.xpath(amt_dls + 'ns:TxAmt/ns:CcyXchg', namespaces={'ns': ns})
            if not curr_exchange_nodes:
                curr_exchange_nodes = node.xpath(amt_dls + 'ns:CntrValAmt/ns:CcyXchg', namespaces={'ns': ns})
            if curr_exchange_nodes:
                chg_node = curr_exchange_nodes[0]
                try:
                    inst_currency_name = chg_node.find('ns:TrgtCcy', namespaces={'ns': ns}).text
                    exchange_rate_amount = float(chg_node.find('ns:XchgRate', namespaces={'ns': ns}).text)
                except (AttributeError, ValueError):
                    pass

            allowed_error_percentage = 2
            # If exchange rate is 1, try to fetch the exchange rate from system currency
            if not tools.float_compare(1.0, exchange_rate_amount, precision_digits=2):
                tx_currency = self.env['res.currency'].search([('name', '=', tx_currency_name)])
                inst_currency = self.env['res.currency'].search([('name', '=', inst_currency_name)])

                # Get transaction date and try to fetch conversion rate
                exchange_date = self._context.get('exchange_date')
                try:
                    exchange_rate_amount = tx_currency.with_context(date=exchange_date)._get_conversion_rate(
                        tx_currency, inst_currency)
                    allowed_error_percentage = 10
                except Exception as exc:
                    _logger.info('SEPA Import. Currency exchange rate exception: {}'.format(exc.args[0]))

            raise_conversion_error = False
            # Try to convert amount currency to the source amount using exchange rate
            converted_amount = tools.float_round(tx_amount_currency * exchange_rate_amount, precision_digits=2)
            calculated_diff = abs(abs(converted_amount) - abs(inst_amount_currency))
            if not tools.float_is_zero(calculated_diff, precision_digits=2):

                # We allow 10% error in conversion rate from original currency if system rate is used,
                # otherwise 2% of error
                # P3:DivOK -- tx amount currency is always a float
                allowed_diff = abs(tx_amount_currency / 100 * allowed_error_percentage)
                if tools.float_compare(calculated_diff, allowed_diff, precision_digits=2) > 0:
                    raise_conversion_error = True

            if raise_conversion_error:
                # If error is meant to be raised, we check it with reversed exchange rate
                converted_amount = tools.float_round(inst_amount_currency * exchange_rate_amount, precision_digits=2)
                calculated_diff = abs(abs(converted_amount) - abs(tx_amount_currency))
                if not tools.float_is_zero(calculated_diff, precision_digits=2):
                    # P3:DivOK -- inst amount currency is always a float
                    allowed_diff = abs(inst_amount_currency / 100 * allowed_error_percentage)
                    if not tools.float_compare(calculated_diff, allowed_diff, precision_digits=2) > 0:
                        # If it's not bigger than the threshold amount, we do not raise the error
                        raise_conversion_error = False
                else:
                    raise_conversion_error = False

            if raise_conversion_error:
                error_message = _('Klaida SEPA faile, gauti šie duomenys:\n\nSuma transakcijos valiuta: {} {}\n'
                                  'Konvertavimo procentas: {}\nSuma originalia valiuta: {} {}.').format(
                    tx_amount_currency, tx_currency_name,
                    exchange_rate_amount, inst_amount_currency, inst_currency_name)
                raise exceptions.ValidationError(error_message)

        res = {'instructed': {'ccy': inst_currency_name,
                              'amount': inst_amount_currency},
               'transaction': {'ccy': tx_currency_name,
                               'amount': tx_amount_currency},
               'source_currency': inst_currency_name,
               'target_currency': tx_currency_name
               }

        charges_nodes = node.xpath('ns:NtryDtls/ns:TxDtls/ns:Chrgs/ns:Amt', namespaces={'ns': ns})
        if charges_nodes and sign == 1:  # we don't care about outgoing charges
            charges_node = charges_nodes[0]
            charges_amount_currency = -float(charges_node.text)
            charges_currency_name = charges_node.attrib['Ccy']
            res['charges'] = {'ccy': charges_currency_name,
                              'amount': charges_amount_currency}
        return res

    def add_value_from_node(self, ns, node, xpath_str, obj, attr_name, join_str=None):
        if not isinstance(xpath_str, (list, tuple)):
            xpath_str = [xpath_str]
        for search_str in xpath_str:
            found_node = node.xpath(search_str, namespaces={'ns': ns})
            if found_node:
                if join_str is None:
                    attr_value = found_node[0].text
                else:
                    attr_value = join_str.join([x.text for x in found_node])
                obj[attr_name] = attr_value
                break

    @api.model
    def fetch_node_value(self, ns, node, xpath_str):
        """
        Fetch value from the node using passed xpath_string.
        :param ns: namespace of the structure
        :param node: parent node that is being searched
        :param xpath_str: xpath string
        :return: node text or None
        """
        found_node = node.xpath(xpath_str, namespaces={'ns': ns})
        return found_node[0].text if found_node else None

    @api.model
    def check_partial_day(self, datetime_str, partial_days):
        """
        Check if statement day is partial -- If it's time is not 00:00:00 or 23:59:59 day is partial
        :param datetime_str: datetime string to check
        :param partial_days: list of partial days to append to
        :return: None
        """
        if isinstance(datetime_str, basestring):
            datetime_str = datetime_str.replace('T', ' ')
            dt = parse(datetime_str)
            if (dt.hour and dt.hour != 23) or (dt.minute and dt.minute != 59) or (dt.second and dt.second != 59):
                date_format = dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                partial_days.append(date_format)

    def check_value_from_node(self, ns, node, xpath_str, join_str=None):
        if not isinstance(xpath_str, (list, tuple)):
            xpath_str = [xpath_str]
        for search_str in xpath_str:
            found_node = node.xpath(search_str, namespaces={'ns': ns})
            if found_node:
                if join_str is None:
                    attr_value = found_node[0].text
                else:
                    attr_value = join_str.join([x.text for x in found_node])
                return attr_value

    def get_special_ref(self, ns, node):
        for search_str in ['./ns:BookgDt/ns:DtTm',
                           './ns:ValDt/ns:DtTm']:
            found_node = node.xpath(search_str, namespaces={'ns': ns})
            if found_node:
                try:
                    dt = found_node[0].text
                    date = parse(dt)
                    try:
                        dt_utc = date.astimezone(pytz.utc)
                    except ValueError:  # naive datetime object
                        dt_utc = date
                    ref = 'internal_ref ' + dt_utc.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    return ref
                except:
                    continue
        # ISO -- 20022
        for search_str in ['./ns:BookgDt/ns:Dt',
                           './ns:ValDt/ns:Dt']:
            found_node = node.xpath(search_str, namespaces={'ns': ns})
            if found_node:
                dt = found_node[0].text if found_node[0] is not None else ''
                ref = 'internal_ref ' + dt
                return ref

    def get_name(self, ns, node):
        name = '/'
        cdtrrefinfnode = node.xpath('./ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref', namespaces={'ns': ns})
        if cdtrrefinfnode:
            name = cdtrrefinfnode[0].text
        prtry = node.xpath('./ns:Refs/ns:Prtry', namespaces={'ns': ns})
        if prtry:
            tp_node = prtry[0].xpath('./ns:Tp', namespaces={'ns': ns})
            ref_node = prtry[0].xpath('./ns:Ref', namespaces={'ns': ns})
            type_str = tp_node and tp_node[0].text or ''
            ref_str = ref_node and ref_node[0].text or ''
            name = '%s %s' % (type_str, ref_str)
        endtoend_id_node = node.xpath('./ns:Refs/ns:EndToEndId', namespaces={'ns': ns})
        if endtoend_id_node and endtoend_id_node[0].text != 'NOTPROVIDED':
            name = endtoend_id_node[0].text
        othr_paths = [
            './ns:RmtInf/ns:Ustrd',
            './ns:AddtlNtryInf']
        for othr_path in othr_paths:
            nd = node.xpath(othr_path, namespaces={'ns': ns})
            if nd:
                name = ''.join([n.text or name for n in nd])
                break
        return name

    def parse_transaction_details(self, ns, node, transaction):
        self.add_value_from_node(
            ns, node, [
                './ns:AddtlTxInf',
            ], transaction, 'name', join_str='\n')
        transaction['name'] = self.get_name(ns, node)
        party_type = 'Dbtr'
        party_type_node = node.xpath(
            '../../ns:CdtDbtInd', namespaces={'ns': ns})
        if not party_type_node:
            party_type_node = node.xpath('./ns:CdtDbtInd', namespaces={'ns': ns})
        if party_type_node and party_type_node[0].text != 'CRDT':
            party_type = 'Cdtr'
        party_node = node.xpath(
            './ns:RltdPties/ns:%s' % party_type, namespaces={'ns': ns})
        if party_node:
            self.add_value_from_node(
                ns, party_node[0], './ns:Nm', transaction, 'partner_name')
            self.add_value_from_node(
                ns, party_node[0], './ns:PstlAdr/ns:Ctry', transaction,
                'partner_country'
            )
            address_node = party_node[0].xpath(
                './ns:PstlAdr/ns:AdrLine', namespaces={'ns': ns})
            if address_node:
                transaction['partner_address'] = [address_node[0].text]
        account_node = node.xpath(
            './ns:RltdPties/ns:%sAcct/ns:Id' % party_type,
            namespaces={'ns': ns}
        )
        if account_node:
            iban_node = account_node[0].xpath(
                './ns:IBAN', namespaces={'ns': ns})
            if iban_node:
                transaction['account_number'] = iban_node[0].text
                bic_node = node.xpath(
                    './ns:RltdAgts/ns:%sAgt/ns:FinInstnId/ns:BIC' % party_type,
                    namespaces={'ns': ns}
                )
                if bic_node:
                    transaction['account_bic'] = bic_node[0].text
            else:
                self.add_value_from_node(
                    ns, account_node[0], './ns:Othr/ns:Id', transaction,
                    'account_number'
                )

    # INFO: overridden in gemma
    def add_partner_name_code(self, ns, node, transaction):
        incoming = 1
        sign_node = node.xpath('ns:CdtDbtInd', namespaces={'ns': ns})
        if not sign_node:
            sign_node = node.xpath('./ns:NtryDtls/ns:TxDtls/ns:CdtDbtInd', namespaces={'ns': ns})
        if sign_node and sign_node[0].text == 'DBIT':
            incoming = -1
        if incoming == 1:
            partner_code_val_nodes = [  # todo BICOrBEI
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Id/ns:PrvtId/ns:Othr/ns:Id',
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Id/ns:OrgId/ns:Othr/ns:Id',
            ]
            partner_code_type_node = [
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Id/ns:OrgId/ns:Othr/ns:SchmeNm/ns:Cd']

            partner_name_nodes = ['./ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Nm']
            partner_iban_nodes = ['./ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:DbtrAcct/ns:Id/ns:IBAN']

            # todo will be used in future
            # partner_ext_code_nodes = partner_code_nodes + \
            #                          ['./ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref']
        else:
            partner_code_val_nodes = [  # todo BICOrBEI
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Id/ns:PrvtId/ns:Othr/ns:Id',
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Id/ns:OrgId/ns:Othr/ns:Id',
            ]
            partner_code_type_node = [
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Id/ns:OrgId/ns:Othr/ns:SchmeNm/ns:Cd']

            partner_name_nodes = ['./ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Nm']
            partner_iban_nodes = ['./ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:CdtrAcct/ns:Id/ns:IBAN']

            # todo will be used in future
            # partner_ext_code_nodes = partner_code_nodes + \
            #                          ['./ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref']

        if not transaction.get('partner_inf'):
            code_type = self.check_value_from_node(
                ns, node, partner_code_type_node,
            )
            code_value = self.check_value_from_node(
                ns, node, partner_code_val_nodes,
            )

            searchable = None
            if code_type == 'COID':
                searchable = 'kodas'
            elif code_type == 'TXID':
                searchable = 'vat'
            elif code_type == 'CUST':
                # Sanitize
                try:
                    int(code_value)
                except ValueError:
                    pass
                else:
                    if len(code_value) < 10:
                        searchable = 'id'

            transaction['partner_inf'] = (searchable, code_value)

        if not transaction.get('partner_name'):
            self.add_value_from_node(
                ns, node, partner_name_nodes,
                transaction, 'partner_name'
            )

        if not transaction.get('partner_iban'):
            self.add_value_from_node(
                ns, node, partner_iban_nodes,
                transaction, 'partner_iban'
            )

        # todo will be used in future
        # if not transaction.get('partner_code'):
        #     self.add_value_from_node(
        #         ns, node, partner_ext_code_nodes,
        #         transaction, 'partner_code'
        #     )

    def parse_transaction(self, ns, node):
        transaction = {}

        # Bank returns transactions line by line, and also includes the batch amount
        # as a separate line if it was a group payment, thus it results in
        # doubled lines, that's why if we find a batch node, we do not parse it.
        batch_payment_node = node.xpath('ns:NtryDtls/ns:Btch', namespaces={'ns': ns})
        # Group payments can optionally be parsed, check for the context, defaults to True
        skip_group_payments = self._context.get('skip_group_payment_import', True)
        if batch_payment_node and skip_group_payments:
            return transaction

        self.add_value_from_node(
            ns, node, './ns:BkTxCd/ns:Prtry/ns:Cd', transaction,
            'transfer_type'
        )
        self.add_value_from_node(
            ns, node, './ns:BookgDt/ns:Dt', transaction, 'date')
        if 'date' not in transaction:
            self.add_value_from_node(
                ns, node, './ns:BookgDt/ns:DtTm', transaction, 'date')
            if 'date' in transaction:
                transaction['date'] = transaction['date'][:10]
        # self.add_value_from_node(
        #     ns, node, './ns:BookgDt/ns:Dt', transaction, 'execution_date')  # not used
        self.add_value_from_node(
            ns, node, './ns:ValDt/ns:Dt', transaction, 'value_date')

        exchange_date = transaction.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        transaction['amounts'] = self.with_context(exchange_date=exchange_date).parse_amounts(ns, node)

        details_node = node.xpath(
            './ns:NtryDtls/ns:TxDtls', namespaces={'ns': ns})
        if details_node:
            self.parse_transaction_details(ns, details_node[0], transaction)
        if not transaction.get('ref'):
            self.add_value_from_node(ns, node, './ns:AddtlNtryInf', transaction, 'ref')
        if not transaction.get('ref'):
            transaction['ref'] = '/'

        if not transaction.get('sepa_instruction_id'):
            self.add_value_from_node(
                ns, node, [
                    './ns:NtryDtls/ns:TxDtls/ns:Refs/ns:InstrId',
                ],
                transaction, 'sepa_instruction_id'
            )
        self.add_partner_name_code(ns, node, transaction)
        if not transaction.get('family_code'):
            self.add_value_from_node(
                ns, node, [
                    './ns:BkTxCd/ns:Domn/ns:Fmly',
                ],
                transaction, 'family_code'
            )
        if not transaction.get('sub_family_code'):
            self.add_value_from_node(
                ns, node, [
                    './ns:BkTxCd/ns:Domn/ns:SubFmlyCd',
                ],
                transaction, 'sub_family_code'
            )

        # All possible transaction reference nodes
        reference_nodes = {
            'tx_id': './ns:NtryDtls/ns:TxDtls/ns:Refs/ns:TxId',
            'entry_ref': './ns:NtryRef',
            'svc_ref': './ns:AcctSvcrRef',
            'tx_svc_ref': './ns:NtryDtls/ns:TxDtls/ns:Refs/ns:AcctSvcrRef',
        }
        if not transaction.get('entry_reference'):
            self.add_value_from_node(
                # TxId is the most accurate identifier for a transaction, other fields are not.
                # However this behaviour is left, because certain fields (like TxId) might not exist on legacy files.
                ns, node, reference_nodes.values(), transaction, 'entry_reference'
            )

        if not transaction.get('other_references'):
            # Gather all possible transaction reference nodes
            # And store them in 'other references' dictionary

            transaction.setdefault('other_references', {})
            for ref, node_path in iteritems(reference_nodes):
                self.add_value_from_node(
                    # Add every other possible reference
                    ns, node, [node_path], transaction['other_references'], ref
                )

        if not transaction.get('entry_reference'):
            sp_ref = self.get_special_ref(ns, node)
            if sp_ref:
                transaction['entry_reference'] = sp_ref
        if not transaction.get('info_type'):
            transaction['info_type'] = self.parse_info_type(ns, node)
        if not transaction.get('bic'):
            self.add_value_from_node(
                ns, node, [
                    './ns:NtryDtls/ns:TxDtls/ns:RltdAgts/ns:DbtrAgt/ns:FinInstnId/ns:BIC',
                    './ns:NtryDtls/ns:TxDtls/ns:RltdAgts/ns:DctrAgt/ns:FinInstnId/ns:BIC',
                ],
                transaction, 'bic'
            )
        if not transaction.get('bank_name'):
            self.add_value_from_node(
                ns, node, [
                    './ns:NtryDtls/ns:TxDtls/ns:RltdAgts/ns:DbtrAgt/ns:FinInstnId/ns:Nm',
                    './ns:NtryDtls/ns:TxDtls/ns:RltdAgts/ns:CdtrAgt/ns:FinInstnId/ns:Nm',
                ],
                transaction, 'bank_name'
            )
        if not transaction.get('iban'):
            self.add_value_from_node(
                ns, node, [
                    './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:CdtrAcct/ns:Id/ns:IBAN',
                    './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:DbtrAcct/ns:Id/ns:IBAN',
                ],
                transaction, 'iban'
            )
        transaction['data'] = etree.tostring(node)
        return transaction

    def get_balance_amounts(self, ns, node):
        start_balance_node = None
        end_balance_node = None
        date_start = None
        date_end = None
        for node_name in ['OPBD', 'PRCD', 'CLBD', 'ITBD', 'OPAV', 'CLAV']:
            code_expr = (
                './ns:Bal/ns:Tp/ns:CdOrPrtry/ns:Cd[text()="%s"]/../../..' %
                node_name
            )
            balance_node = node.xpath(code_expr, namespaces={'ns': ns})
            if balance_node:
                date_node = balance_node[0].xpath('./ns:Dt/ns:Dt', namespaces={'ns': ns})
                if date_node:
                    date = date_node[0].text
                else:
                    date_node = balance_node[0].xpath('./ns:Dt/ns:DtTm', namespaces={'ns': ns})
                    if date_node:
                        date = date_node[0].text[:10]
                    else:
                        date = ''
                if node_name in ['OPBD', 'PRCD', 'OPAV']:
                    start_balance_node = balance_node[0]
                    date_start = date
                # elif node_name == 'CLBD':
                else:
                    end_balance_node = balance_node[0]
                    date_end = date
                # else:
                #     if not start_balance_node:
                #         start_balance_node = balance_node[0]
                #     if not end_balance_node:
                #         end_balance_node = balance_node[-1]
        amount_balance_start = self.parse_amount(ns, start_balance_node)
        amount_balance_end = self.parse_amount(ns, end_balance_node)
        return amount_balance_start, amount_balance_end, date_start, date_end

    def parse_statement(self, ns, node):
        result = {'partial_days': []}
        self.add_value_from_node(
            ns, node, [
                './ns:Acct/ns:Id/ns:IBAN',
                './ns:Acct/ns:Id/ns:Othr/ns:Id',
            ], result, 'account_number'
        )
        self.add_value_from_node(
            ns, node, [
                './ns:Acct/ns:Ownr/ns:Id/ns:OrgId/ns:Othr/ns:Id',
                './ns:Acct/ns:Ownr/ns:Id/ns:PrvtId/ns:Othr/ns:Id',
            ], result, 'stmt_company'
        )

        self.add_value_from_node(
            ns, node, './ns:Id', result, 'name')

        # Check whether report date from/date_to are partial days.
        # If they exist in the file and they are partial -- append them to the list
        self.check_partial_day(self.fetch_node_value(ns, node, './ns:FrToDt/ns:FrDtTm'), result['partial_days'])
        self.check_partial_day(self.fetch_node_value(ns, node, './ns:FrToDt/ns:ToDtTm'), result['partial_days'])

        self.add_value_from_node(
            ns, node, './ns:Dt', result, 'date')
        self.add_value_from_node(
            ns, node, './ns:Acct/ns:Ccy', result, 'currency')
        result['balance_start'], result['balance_end_real'], result['balance_start_date'], result['balance_end_date'] = \
            (self.get_balance_amounts(ns, node))
        transaction_nodes = node.xpath('./ns:Ntry', namespaces={'ns': ns})
        result['transactions'] = []
        for entry_node in transaction_nodes:
            transaction = self.parse_transaction(ns, entry_node)
            if transaction:
                result['transactions'].append(transaction)
        return result

    def check_version(self, ns, root):
        re_camt = re.compile(
            r'(^urn:iso:std:iso:20022:tech:xsd:camt.'
            r'|^ISO:camt.)'
        )
        if not re_camt.search(ns):
            raise exceptions.UserError(_('Netinkamas failas: \n') + ns)
        re_camt_version = re.compile(
            r'(^urn:iso:std:iso:20022:tech:xsd:camt.053.'
            r'|^urn:iso:std:iso:20022:tech:xsd:camt.052.'
            r'|^ISO:camt.053.'
            r'|^ISO:camt.052.)'
        )
        if not re_camt_version.search(ns):
            raise exceptions.Warning(_('Netinkamas failo formatas'))
        try:
            root_0_0 = root[0][0].tag[len(ns) + 2:]  # strip namespace
        except IndexError:
            raise exceptions.Warning(_('Netinkamas failo formatas'))
        if root_0_0 != 'GrpHdr':
            raise exceptions.Warning(_('Netinkamas failo formatas'))

    def get_version(self, data):
        is_camt_052 = xml_validator(data, xsd_file=os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.052.001.02.xsd')
        if is_camt_052:
            return '052'
        is_camt_053 = xml_validator(data, xsd_file=os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'xsd_schemas')) + '/camt.053.001.02.xsd')
        if is_camt_053:
            return '053'
        raise exceptions.Warning(_('Netinkamas failo formatas'))

    def parse(self, data):
        try:
            root = etree.fromstring(
                data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            root = etree.fromstring(
                data.decode('iso-8859-15').encode('utf-8'))
        if root is None:
            raise exceptions.Warning(_('Netinkamas failo formatas'))
        try:
            ns = root.tag[1:root.tag.index("}")]
        except Exception as exc:
            _logger.info('SEPA Import exception: %s' % exc.args[0])
            # Manually force the  namespace if forced import is activated
            forced_namespace = self._context.get('forced_import_type')
            if self._context.get('force_sepa_import') and forced_namespace:
                # Convert the namespace to full format
                forced_namespace = 'urn:iso:std:iso:20022:tech:xsd:camt.%s' % forced_namespace
                # Replace namespace prefixes for child elements
                for elem in root.getiterator():
                    elem.tag = '{%s}%s' % (
                        forced_namespace, etree.QName(elem).localname
                    )
                # Remove unused namespace declarations and force new mapping
                etree.cleanup_namespaces(root)
                root.nsmap['xmlns'] = ns = forced_namespace
            else:
                raise exceptions.ValidationError(_('Netinkamas failo formatas'))
        path = str('{' + ns + '}')
        self.check_version(ns, root)
        data = tostring(root, encoding='utf8', method='xml')
        try:
            version = self.get_version(data)
            if version == '052':
                statement_id_bank = root.xpath('./ns:BkToCstmrAcctRpt/ns:GrpHdr/ns:MsgId',
                                               namespaces={'ns': ns})[0].text
            else:
                statement_id_bank = root.xpath('./ns:BkToCstmrStmt/ns:GrpHdr/ns:MsgId', namespaces={'ns': ns})[0].text
        except:
            try:
                statement_id_bank = root.xpath('./ns:BkToCstmrAcctRpt/ns:GrpHdr/ns:MsgId',
                                               namespaces={'ns': ns})[0].text
                version = '052'
            except:
                try:
                    statement_id_bank = root.xpath('./ns:BkToCstmrStmt/ns:GrpHdr/ns:MsgId',
                                                   namespaces={'ns': ns})[0].text
                    version = '053'
                except:
                    raise exceptions.Warning(_('Netinkama failo versija'))
        statements = []
        # Define accepted node list - main node that stores the statement data
        accepted_nodes = ['{}Rpt'.format(path), '{}Stmt'.format(path)]
        for node in root[0][1:]:
            # Only parse Rpt and Stmt nodes, other information that passes the schema
            # can be stored in the file, but should not be parsed
            if node.tag not in accepted_nodes:
                continue
            statement = self.parse_statement(ns, node)
            statement['statement_id_bank'] = statement_id_bank
            # if len(statement['transactions']):
            statements.append(statement)
        return statements, version
