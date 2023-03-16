# -*- coding: utf-8 -*-

import base64
from datetime import datetime

import xlrd
from xlrd import XLRDError

from odoo import _, exceptions, tools

FIELD_MAPPING = {
    'employee': 'Darbuotojas',
    'identification_id': 'Darbuotojo asmens kodas',
    'date_document': 'Įsakymo pildymo data',
    'date_from': 'Prastovos pradžia',
    'date_to': 'Prastovos pabaiga',
    'subtype': 'Prastovos subtipas',
    'declared_emergency': 'Ekstremali situacija ar karantinas',
    'pay': 'Prastovos apmokėjimas',
    'reason': 'Prastovos priežastis',
}

FIELDS = ['employee', 'identification_id,', 'date_document', 'date_from', 'date_to', 'subtype', 'declared_emergency',
          'pay', 'reason']
REQUIRED_FIELDS = ['employee', 'date_document', 'date_from', 'date_to', 'subtype']
STRING_FIELDS = ['employee', 'identification_id', 'subtype', 'declared_emergency', 'pay', 'reason']
DATE_FIELDS = ['date_document', 'date_from', 'date_to']


def import_downtime_order(self, import_file):
    """
    Creates e-document records from values specified in the import file
    """
    env = self.sudo().env

    record_set = parse_import_file(import_file)
    record_values = parse_record_values(env, record_set)
    for record_vals in record_values:
        env['e.document'].create(record_vals)


def parse_import_file(import_file):
    """
    Parse the import file checking if all of the fields neccessary are in the file.
    Args:
        import_file (): File that's being imported

    Returns: List of parsed values

    """
    try:
        wb = xlrd.open_workbook(file_contents=base64.decodestring(import_file))
    except XLRDError:
        raise exceptions.UserError(_('Netinkamas prastovų įsakymų importavimo failo formatas!'))
    sheet = wb.sheets()[0]

    record_set = []

    errors = ''

    for row in range(sheet.nrows):
        if row == 0:
            continue
        col = 0
        record_required_fields = list(REQUIRED_FIELDS)
        record = {'row_number': str(row + 1)}
        for field in FIELDS:
            try:
                value = sheet.cell(row, col).value
            except IndexError:
                value = False

            # Formatting
            if field in DATE_FIELDS and value:
                try:
                    value = datetime(*xlrd.xldate_as_tuple(value, wb.datemode)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                except Exception as e:
                    errors += _('Netinkamas datos formatas | Eilutės nr: {} | Klaida {}').format(e.args[0], row + 1) + \
                              '\n'
            elif field in STRING_FIELDS and not isinstance(field, (str, unicode)):
                try:
                    value = str(float(value))
                except ValueError:
                    try:
                        value = str(int(value))
                    except ValueError:
                        try:
                            value = str(value)
                        except ValueError:
                            errors += _('Klaidinga reikšmė laukui %s | Eilutės nr: %s') % (field, row + 1) + '\n'

            # Update the required fields for the record based on downtime subtype
            if field == 'subtype':
                if value == 'Įprasta':
                    record_required_fields.append('reason')
                else:
                    record_required_fields += ['pay', 'declared_emergency']

            # General required field checks
            if field in record_required_fields and not value and not isinstance(value, (int, float)):
                errors += _('Nerasta reikšmė privalomam laukui: {}. | Eilutės nr: {}').format(
                    FIELD_MAPPING[field],
                    str(row + 1)
                ) + '\n'

            record[field] = value
            col += 1

        record_set.append(record)

    if errors:
        raise exceptions.UserError(errors)

    return record_set


def parse_record_values(env, parsed_file_values):
    """
    Generates record values from parsed file values
    Args:
        env (): Environment object used for object look up
        parsed_file_values (): Values to create record values from

    Returns: Formatted record values

    """
    list_of_record_values = []

    errors = ''

    for record in parsed_file_values:
        row = record.get('row_number')

        # Find the employee
        employee_name = record.get('employee')
        employee = env['hr.employee'].with_context(active_test=False).search([
            ('name', '=', employee_name)
        ])
        if len(employee) > 1:
            identification_id = record.get('identification_id')
            if not identification_id:
                errors += _('Sistemoje rasti keli darbuotojai su vardu {}. Nurodykite darbuotojo '
                                             'asmens kodą').format(employee_name) + '\n'
                continue
            employee = env['hr.employee'].with_context(active_test=False).search([
                ('identification_id', '=', identification_id)
            ])
        if not employee:
            errors += _('Nerastas darbuotojas {}').format(employee_name) + '\n'
            continue

        # Get the downtime subtype
        subtype = record.get('subtype')
        state_declared_emergency_id = None
        pay_amount = 0.0
        pay = None
        subtype = 'ordinary' if subtype == 'Įprasta' else 'due_to_special_cases'
        if subtype != 'ordinary':
            # Get the required data for downtimes that are not of type ordinary
            declared_emergency = record.get('declared_emergency')
            state_declared_emergency = env['state.declared.emergency'].search([
                ('name', '=', declared_emergency)
            ], limit=1)
            if not state_declared_emergency:
                errors += _('Nerasta ekstremali situacija ar karantinas su pavadinimu {}. Patikrinkite eilutę nr.'
                            '{}.').format(declared_emergency, row) + '\n'
                continue
            state_declared_emergency_id = state_declared_emergency.id

            pay = record.get('pay')
            if pay == 'Mokėti darbuotojo atlyginimą, neviršijantį 1.5 MMA':
                pay = 'salary'
            elif pay == 'Minimalų atlyginimą':
                pay = 'mma'
            else:
                try:
                    pay_amount = float(pay)
                    pay = 'custom'
                except ValueError:
                    errors += _('Neteisingai nurodytas prastovos apmokėjimas eilutėje nr. {}').format(row) + '\n'
                    continue

                if tools.float_compare(pay_amount, 0.0, precision_digits=2) <= 0:
                    errors += _('Prastovos apmokėjimo suma privalo būti teigiamas skaičius. Eilutė nr. {}').format(row) + \
                              '\n'
                    continue

        # Create value list
        list_of_record_values.append({
            'template_id': env.ref('e_document.isakymas_del_prastovos_skelbimo_template').id,
            'document_type': 'isakymas',
            'employee_id2': employee.id,
            'date_document': record.get('date_document'),
            'downtime_type': 'full',
            'date_from': record.get('date_from'),
            'date_to': record.get('date_to'),
            'downtime_subtype': subtype,
            'downtime_reason': record.get('reason', ''),
            'downtime_related_state_declared_emergency': state_declared_emergency_id,
            'downtime_employee_ids': [(4, employee.id)],
            'downtime_pay_selection': pay,
            'float_1': pay_amount,
        })

    if errors:
        raise exceptions.UserError(errors)

    return list_of_record_values
