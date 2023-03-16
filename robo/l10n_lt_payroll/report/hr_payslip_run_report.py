# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, models, tools
from odoo.tools.misc import formatLang
from .suvestine import CATEGORY_TO_CODE_MAPPING, _payslip_amounts, _round_time
from six import iteritems

REPORT_EXT_ID = 'l10n_lt_payroll.report_hr_payslip_run'


def _work_norm(payslips):
    """
    Gets the work norm for the given payslips based on payslip ziniarastis period lines
    Args:
        payslips (hr.payslip): payslips to get the work norm for

    Returns:
        dict: work norm - days and hours

    """
    days = hours = 0.0
    for payslip in payslips:
        period_line = payslip.ziniarastis_period_line_id
        if not period_line:
            continue
        days += period_line.num_regular_work_days_contract_only
        hours += period_line.num_regular_work_hours
    return {'days': days, 'hours': hours}


def _worked_time(payslips):
    """
    Gets worked days from payslip ziniarastis period lines
    Args:
        payslips (hr.payslip): payslips to get the worked time for

    Returns:
        dict: number of worked days and hours

    """
    days = hours = 0.0
    for payslip in payslips:
        period_line = payslip.ziniarastis_period_line_id
        if not period_line:
            continue
        days += period_line.days_total
        hours += period_line.hours_worked
    return {'days': days, 'hours': hours}


def _shorter_before_holidays_time(payslips):
    """
    Special method that returns how many hours have been shortened before holidays
    Args:
        payslips (hr.payslip): Payslips to get the number of hours shorter before holidays

    Returns:
         dict: number of days (always 0.0) and hours that have been shortened before holidays

    """
    days = 0.0
    lines = payslips.mapped('worked_days_line_ids').filtered(lambda r: r.compensated_time_before_holidays)
    hours = sum(lines.mapped('number_of_hours'))
    return {'days': days, 'hours': hours}

# This defines the main payslip report categories and subcategories.
CATEGORIES = [
    {
        'totals_column': False,
        'type': 'time',
        'name': _('Laiko priskaitymai'),
        'subcategories': [
            {
                'name': _('Maksimali darbo laiko trukmė'),
                'method': _work_norm,
                'print_zero_amounts': True
            },
            {
                'name': _('Dirbtas laikas'),
                'method': _worked_time,
                'print_zero_amounts': True
            },
            {
                'name': _('Trumpinimas prieš šventes'),
                'method': _shorter_before_holidays_time,
                'print_only_hours': True,
                'print_only_if_exists': True,
            },
            {
                'name': _('Ligos; Prastovos; Atostogos'),
                'codes': CATEGORY_TO_CODE_MAPPING['atostogos'] + CATEGORY_TO_CODE_MAPPING['ligos'] +
                         CATEGORY_TO_CODE_MAPPING['mamadieniai'] + CATEGORY_TO_CODE_MAPPING['kitu_rusiu_atostogos'] +
                         CATEGORY_TO_CODE_MAPPING['prastovos'] + CATEGORY_TO_CODE_MAPPING['virsyta_darbo_laiko_norma'] +
                         CATEGORY_TO_CODE_MAPPING['neivykdyta_darbo_laiko_norma']
            },
            {
                'name': _('Neapmokamas nedirbtas laikas'),
                'codes': CATEGORY_TO_CODE_MAPPING['neapmokamas_nedarbingumas'] +
                         CATEGORY_TO_CODE_MAPPING['nemokamos_atostogos'],
                'footnote': _('Nemokamų atostogų ir neapmokamo nedarbingumo trukmė'),
            },
        ],
    },
    {
        'totals_column': True,
        'type': 'amount',
        'name': _('Priskaitymai, Eur'),
        'subcategories': [
            {
                'name': _('Darbo užmokestis'),
                'positive_amount_keys': ['regular_amount', 'extra_amount_excl_downtime'],
            },
            {
                'name': _('Prastovos išmokos'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['downtime_amount'],
            },
            {
                'name': _('Ligos pašalpos'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['liga_amount'],
            },
            {
                'name': _('Atostoginiai ir nepanaudotų atostogų išmokos'),
                'positive_amount_keys': ['all_holidays_amount', 'tevystes_amount'],
            },
            {
                'name': _('Priedai ir premijos'),
                'positive_amount_keys': ['other_bonuses_amount'],
            },
            {
                'name': _('Kitos išmokos'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['other_additions_amount'],
            },
        ],
    },
    {
        'totals_column': True,
        'type': 'amount',
        'name': _('Išskaitymai, Eur'),
        'subcategories': [
            {
                'name': _('GPM'),
                'footnote': _('Gyventojų pajamų mokestis'),
                'positive_amount_keys': ['gpm_amount'],
            },
            {
                'name': _('PSD ir VSD'),
                'footnote': _('Privalomojo sveikatos draudimo ir valstybinio socialinio draudimo (išskyrus papildomą '
                              'pensijų kaupimą) įmokos'),
                'positive_amount_keys': ['social_security_excl_pension_amount'],
            },
            {
                'name': _('Papildomos pensijų kaupimo įmokos'),
                'positive_amount_keys': ['social_pension_security_amount'],
            },
            {
                'name': _('Kita'),
                'footnote': _('Kitos išskaitos'),
                'positive_amount_keys': ['other_deductions_amount'],
            },
        ],
    },
    {
        'totals_column': True,
        'type': 'amount',
        'name': _('Išmokėti, Eur'),
        'subcategories': [
            {
                'name': _('Darbo užmokesčio'),
                'positive_amount_keys': ['regular_amount', 'extra_amount_excl_downtime', 'downtime_amount', 'liga_amount', 'all_holidays_amount', 'tevystes_amount', 'other_bonuses_amount', 'other_additions_amount'],
                'negative_amount_keys': ['gpm_amount', 'social_security_excl_pension_amount', 'social_pension_security_amount', 'other_deductions_amount'],
            },
            {
                'name': _('Darbo užmokesčio avanso'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['advance_payment_amount'],
            },
            {
                'name': _('Vėluojančių mokėjimų'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['late_payments_amount']
            },
            {
                'name': _('Kitų mokėjimų'),
                'print_only_if_exists': True,
                'footnote': _('Dienpinigiai ir kompensacijos'),
                'method_to_call': '_get_payment_amounts'
            },
        ],
    },
    {
        'totals_column': True,
        'type': 'amount',
        'name': _('Darbdavio kaštai, Eur'),
        'subcategories': [
            {
                'name': _('Darbuotojo socialinio draudimo įmokos pritraukimas iki grindų'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['SODRA_employee_floor_amount'],
            },
            {
                'name': _('Darbdavio socialinio draudimo įmokos pritraukimas iki grindų'),
                'print_only_if_exists': True,
                'positive_amount_keys': ['SODRA_employer_floor_amount'],
            },
            {
                'name': _('Darbdaviui tenkantis mokestis socialiniam draudimui'),
                'positive_amount_keys': ['SODRA_employer_amount'],
            },
        ],
    },
    {
        'totals_column': False,
        'type': 'amount',
        'name': _('Iš viso, Eur'),
        'subcategories': [
            {
                'name': _('Darbo vietos kaštai'),
                'positive_amount_keys': ['labor_costs_amount']
            }
        ],
    },
]


def _amounts_by_time_codes(payslips, codes):
    """
    Gets the amount of days and hours by payslip code
    Args:
        payslips (hr.payslip): Payslips to get the number of hours shorter before holidays
        codes (list): Codes to get the number of hours and days for

    Returns:
        dict: number of days and hours by code
    """
    lines = payslips.mapped('worked_days_line_ids').filtered(lambda l: l.code in codes)
    days = sum(lines.mapped('number_of_days'))
    hours = sum(lines.mapped('number_of_hours'))
    return {'days': days, 'hours': hours}


def _period(payslip_run):
    """
    Get the payslip run period
    Returns:
        string: formatted payslip run period
    """
    date_dt = datetime.strptime(payslip_run.date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
    return str(date_dt.year) + '-' + str(date_dt.month)


def _replace(string):
    """
    Formats string replacing dots with commas
    Returns:
        string: formatted string with dots replaced by commas
    """
    string = str(string)
    if len(string) > 0 and '.' in string:
        return string.replace('.', ',')
    else:
        return string


def _remove(string):
    """
    Removes everything after the decimal place from float/string
    Returns:
        string: Formatted string/amount
    """
    string = str(string)
    if len(string) > 0 and '.' in string:
        return string.split('.')[0]
    else:
        return string


class ReportHrPayslipRun(models.AbstractModel):
    _name = 'report.l10n_lt_payroll.report_hr_payslip_run'

    @api.multi
    def render_html(self, doc_ids, data=None):
        """
        Renders the report
        Args:
            doc_ids (list): payslip run ids
            data (dict): various params

        Returns: Rendered report

        """
        report_obj = self.env['report']
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            self = self.sudo()

        # Get payslip run ids and employees that should be filtered
        doc_ids = doc_ids if doc_ids else data.get('payslip_run_id', [])
        employee_ids = data.get('employee_ids', []) if data else ()

        report = report_obj._get_report_from_name(REPORT_EXT_ID)
        docs = self.env[report.model].browse(doc_ids)

        force_lang = data.get('force_lang') if data else self.env.user.partner_id.lang

        # Get the data
        payments = self.with_context(lang=force_lang)._get_payment_and_compensation_data(docs, employee_ids)
        main_data = self.with_context(
            lang=force_lang,
            payments=payments
        )._get_full_data(docs, employee_ids)
        tax_data = self.with_context(lang=force_lang)._get_tax_data(docs, employee_ids, payments)

        # Generate report
        docargs = {
            'doc_ids': doc_ids,
            'doc_model': report.model,
            'docs': docs,
            'force_lang': force_lang,
            'period': lambda payslip_runs: _period(payslip_runs),
            'main_data': main_data,
            'len': lambda *args: len(*args),
            'formatLang': lambda *a, **kw: formatLang(self.env, *a, **kw),
            'replace': lambda string: _replace(string),
            'remove': lambda string: _remove(string),
            'round_time': lambda time: _round_time(time),
            'payments': payments,
            'tax_data': tax_data,
            'report_line_data_title': _('Darbuotojas')
        }
        return report_obj.render(REPORT_EXT_ID, docargs)

    @api.model
    def _get_tax_data(self, payslip_runs, employee_ids, payments):
        """
        Gets the taxes from payslip runs and payments based on employee ids
        Args:
            payslip_runs (hr.payslip.run): payslip runs to get the data for
            employee_ids (list): list of hr.employee ids
            payments (dict): payment data

        Returns:
            dict: taxes that should be paid for each payslip run
        """
        res = {}
        for payslip_run in payslip_runs:
            # Get payments
            payslip_run_payments = (payments.get(payslip_run.id) or dict()).get('payments') or list()

            # Get payslips
            slips = payslip_runs.mapped('slip_ids')
            if employee_ids:
                slips = slips.filtered(lambda s: s.employee_id.id in employee_ids)

            # Get all of the amounts for payslip
            payslip_amounts = _payslip_amounts(slips)

            # Compute tax amounts
            payment_sodra = sum(payment['sodra'] for payment in payslip_run_payments if
                                payment['type'] in ['rent', 'auto_rent', 'other', 'benefit_in_kind_employer_pays_taxes'])
            sodra_amount = payslip_amounts['SODRA_total_amount'] + \
                           payslip_amounts['social_security_excl_pension_amount'] + \
                           payslip_amounts['social_pension_security_amount'] + \
                           payment_sodra
            gpm_salary_related = payslip_amounts['gpm_amount'] + sum(
                payment['gpm'] for payment in payslip_run_payments if
                payment['type'] == 'benefit_in_kind_employer_pays_taxes'
            )
            gpm_salary_unrelated = sum(payment['gpm'] for payment in payslip_run_payments if
                                       payment['type'] in ['rent', 'auto_rent', 'other'])

            # Add taxes for payslip run
            res[payslip_run.id] = [
                (_('SODRA'), sodra_amount, '252'),
                (_('GPM nuo A kl. pajamų susijusių su darbo santykiais'), gpm_salary_related, '1311'),
                (_('GPM nuo A kl. pajamų nesusijusių su darbo užmokesčiu'), gpm_salary_unrelated, '1411'),
            ]
        return res

    @api.model
    def _get_payment_and_compensation_data(self, payslip_runs, employee_ids):
        """
        Gets the payment and compensation data for payslip runs and filters by employee.

        Args:
            payslip_runs (hr.payslip.run): Payslip runs to get the payments and compensations for
            employee_ids (list): List of hr.employee ids that the payments should be filtered for

        Returns:
            dict: Payment and compensation data for each payslip run
        """
        res = {}
        for payslip_run in payslip_runs:
            # Get payments
            payments = self.env['hr.employee.payment'].search([
                ('type', '!=', 'holidays'),
                ('date', '<=', payslip_run.date_end),
                ('date', '>=', payslip_run.date_start),
                ('state', '=', 'done')
            ])

            # Filter payments
            if employee_ids:
                payments = payments.filtered(lambda p: p.employee_id.id in employee_ids)

            # Format the payments
            payments = self.format_payment_data(payments) + \
                       self.format_compensation_data(payslip_run, employee_ids=employee_ids)
            payments += self.env['report.l10n_lt_payroll.report_suvestine_sl']._get_benefit_in_kind_employer_pays_taxes_payments(payslip_run.slip_ids)
            payments += self.env['report.l10n_lt_payroll.report_suvestine_sl']._get_benefit_in_kind_employee_pays_taxes_payments(payslip_run.slip_ids)
            # Get the payment types
            all_payment_types = [payment['type'] for payment in payments]
            payment_types = list(set(all_payment_types))

            # Payment types sorted by the amount of entries so that tables with more data appear on the left
            payment_types = sorted(
                payment_types, key=lambda p_type: len([x for x in all_payment_types if x == p_type]), reverse=True
            )

            res[payslip_run.id] = {
                'payments': payments,
                'payment_types': payment_types
            }

        return res

    @api.model
    def format_payment_data(self, payments):
        """
        Format payments in a specific way for salary report to render. Payments might not have specific
        fields/attributes so we compute them in this method and return a simple list of data
        :param payments: Employee payments
        :type payments: hr.employee.payment
        :return: list containing formatted payment data
        :rtype: list
        """
        payment_data = {}
        i = -1
        for payment in payments:
            # Get payment basic data
            contract = payment.contract_id
            employee = payment.employee_id
            partner = payment.partner_id
            if not contract:
                if not employee and partner:
                    employee = partner.employee_ids[0] if partner.employee_ids else None
                if employee:
                    contract = employee.with_context(date=payment.date).contract_id

            # Get the payment type
            payment_types = dict(payment._fields.get('type', False)._description_selection(self.env))
            payment_type = payment_types.get(payment.type, '-')

            # Create a key to sum up dictionary values as well as to sort the data later
            if not employee and not partner and not contract:
                i += 1
                key = str(i)
            else:
                key = '{}{}{}{}{}'.format(payment_type,
                                          employee.name if employee else '-',
                                          employee.id if employee else '',
                                          partner.id if partner else '',
                                          contract.id if contract else '')
            existing_data = payment_data.get(key)

            # Append or create data in data dictionary
            if not existing_data:
                payment_data[key] = {
                    'employee': payment.employee_id.name or payment.partner_id.name or '-',
                    'contract_id': payment.contract_id.id,
                    'contract': contract.name if contract else '-',
                    'bruto': payment.amount_bruto,
                    'gpm': payment.amount_gpm,
                    'neto': payment.amount_paid,
                    'type_str': payment_type,
                    'type': payment.type,
                    'sodra': payment.amount_sdb + payment.amount_sdd
                }
            else:
                payment_data[key]['bruto'] += payment.amount_bruto
                payment_data[key]['gpm'] += payment.amount_gpm
                payment_data[key]['neto'] += payment.amount_paid
                payment_data[key]['sodra'] += payment.amount_sdb + payment.amount_sdd

        # Return sorted data
        return [data for key, data in sorted(iteritems(payment_data))]  # P3:Ok

    @api.model
    def format_compensation_data(self, payslip_runs, employee_ids=None):
        """
        Format compensations in a specific way for salary report to render.
        :param payslip_runs: Employee compensations
        :type payslip_runs: hr.payslip.run
        :return: list containing formatted compensation data
        :rtype: list

        Args:
            employee_ids (list): Optional list of employee ids to filter the compensations for
        """
        compensation_data = {}

        compensation_type_map = {
            'KOMP': _('Compensation'),
            'KKPD': _('Dynamic workplace compensation')
        }

        slips = payslip_runs.mapped('slip_ids')
        if employee_ids:
            slips = slips.filtered(lambda s: s.employee_id.id in employee_ids)
        for contract in slips.mapped('contract_id'):
            contract_slips = slips.filtered(lambda s: s.contract_id == contract)
            slip_lines = contract_slips.mapped('line_ids')
            employee = contract.employee_id
            for compensation_type_by_code in compensation_type_map.keys():
                compensation_lines_by_type = slip_lines.filtered(lambda l: l.code == compensation_type_by_code)
                compensation_amount = sum(compensation_lines_by_type.mapped('amount'))
                if tools.float_is_zero(compensation_amount, precision_digits=2):
                    continue
                key = '{}{}{}'.format(employee.name, employee.id, contract.id, compensation_type_by_code)
                existing_data = compensation_data.get(key)
                if not existing_data:
                    compensation_data[key] = {
                        'employee': employee.name,
                        'contract_id': contract.id,
                        'contract': contract.name,
                        'bruto': compensation_amount,
                        'gpm': 0.0,
                        'neto': compensation_amount,
                        'type_str': compensation_type_map.get(compensation_type_by_code),
                        'type': compensation_type_by_code,
                        'sodra': 0.0
                    }
                else:
                    compensation_data[key]['bruto'] += compensation_amount
                    compensation_data[key]['neto'] += compensation_amount

        # Return sorted data
        return [data for key, data in sorted(iteritems(compensation_data))]  # P3:Ok

    @api.model
    def _get_full_data(self, payslip_runs, employee_ids):
        """
        Retrieves data for all payslips in the payslip run
        Args:
            payslip_runs (hr.payslip.run): Payslip runs to build the data for

        Returns: Dictionary of data for each payslip run

        """
        full_data = {}

        for payslip_run in payslip_runs:
            # Get the payslips and sort them
            payslips = self._sort_payslips(payslip_run.mapped('slip_ids'))
            if employee_ids:
                payslips = payslips.filtered(lambda payslip: payslip.employee_id.id in employee_ids)

            # Get the data for payslips
            payslip_data = self._get_payslip_data(payslips)

            # Build a list of which categories to show on the report
            payslip_run_categories = list(CATEGORIES)
            category_index = 0
            for category in payslip_run_categories:
                subcategory_index = 0
                for subcategory in category.get('subcategories') or list():
                    # Skip categories that should only show amounts if any amounts exist
                    if subcategory.get('print_only_if_exists'):
                        # Get the total time for the subcategory
                        subcategory_total = payslip_data['totals'][category_index]['subcategory_totals'][subcategory_index]
                        if category.get('type') == 'time':
                            subcategory_value = subcategory_total.get('days', 0.0) + subcategory_total.get('hours', 0.0)
                        else:
                            subcategory_value = subcategory_total

                        # Remove the subcategory from data lists if the total value for the subcategory is zero
                        if tools.float_is_zero(subcategory_value, precision_digits=2):
                            payslip_data['totals'][category_index]['subcategory_totals'].pop(subcategory_index)
                            for payslip in payslip_data['values']:
                                payslip['values'][category_index]['subcategory_data'].pop(subcategory_index)
                            category['subcategories'].pop(subcategory_index)
                    subcategory_index += 1

                    subcategory_name = subcategory.get('name')
                    if subcategory_name:
                        subcategory['name'] = _(subcategory_name)

                    subcategory_footnote = subcategory.get('footnote')
                    if subcategory_footnote:
                        subcategory['footnote'] = _(subcategory_footnote)

                category_name = category.get('name')
                if category_name:
                    category['name'] = _(category_name)

                category_index += 1

            # Add processed data to the payslip run data dictionary
            full_data[payslip_run.id] = {
                'categories': CATEGORIES,
                'payslip_data': payslip_data
            }

        return full_data

    @api.model
    def _sort_payslips(self, payslips):
        """
        Sorts payslips
        Args: payslips (hr.payslip): Payslips to be sorted

        Returns: payslips (hr.payslip): Sorted payslips
        """
        return payslips.sorted(lambda slip: (
            slip.employee_id.name,
        ))

    @api.model
    def _get_payslip_data(self, payslips):
        """
        Retrieves data from payslips for the salary report
        Args:
            payslips (hr.payslip): Payslips to get the data for

        Returns: Dictionary of payslip values and the total values for those payslips

        """
        # Generate a data structure to store the totals later
        payslip_totals = [
            {
                'subcategory_totals': [
                    dict() for subcategory in category.get('subcategories')
                ]
            } for category in CATEGORIES
        ]

        payslip_data = list()
        for payslip in payslips:
            payslip_values = dict()

            # Get the name of the payslip/employee to show on the report
            employee = payslip.employee_id
            number_of_employee_payslips = len(payslips.filtered(lambda slip: slip.employee_id == employee))
            payslip_name = payslip.employee_id.name
            if number_of_employee_payslips > 1:
                # Add the contract name if multiple payslips for the employee exists
                payslip_name += ' ({})'.format(payslip.contract_id.name)
            payslip_values['name'] = payslip_name

            payslip_amounts = _payslip_amounts(payslip)  # Get payslip amounts

            # Get data for each category
            payslip_category_data = list()
            category_index = 0
            for category in CATEGORIES:
                subcategories = category.get('subcategories')

                subcategory_data = list()

                total_amount = total_days = total_hours = 0.0

                is_time = category.get('type') == 'time'

                subcategory_index = 0
                for subcategory in subcategories:
                    if is_time:
                        # Get amounts for categories of type time
                        method_to_call = subcategory.get('method')
                        if method_to_call:
                            subcategory_res = method_to_call(payslip)
                        else:
                            codes = subcategory.get('codes')
                            subcategory_res = _amounts_by_time_codes(payslip, codes)

                        # Parse results
                        subcategory_days = subcategory_res.get('days') or 0.0
                        subcategory_hours = subcategory_res.get('hours') or 0.0

                        # Add to totals
                        total_days += subcategory_days
                        total_hours += subcategory_hours

                        # Add to the subcategory data
                        payslip_subcategory_data = {'hours': subcategory_hours}
                        if not subcategory.get('print_only_hours'):
                            payslip_subcategory_data['days'] = subcategory_days
                        subcategory_data.append(payslip_subcategory_data)

                        # Add to the absolute totals
                        subcategory_totals = payslip_totals[category_index]['subcategory_totals'][subcategory_index]
                        subcategory_total_days = subcategory_totals.get('days', 0.0) + subcategory_days
                        subcategory_total_hours = subcategory_totals.get('hours', 0.0) + subcategory_hours
                        payslip_totals[category_index]['subcategory_totals'][subcategory_index]['days'] = subcategory_total_days
                        payslip_totals[category_index]['subcategory_totals'][subcategory_index]['hours'] = subcategory_total_hours
                    else:
                        # Get amounts for categories of type amounts
                        subcategory_amount = 0.0

                        # Get amounts based on keys
                        positive_amount_keys = subcategory.get('positive_amount_keys') or list()
                        negative_amount_keys = subcategory.get('negative_amount_keys') or list()
                        method_to_call = subcategory.get('method_to_call')
                        if positive_amount_keys or negative_amount_keys:
                            positive_amount = sum(payslip_amounts.get(key, 0.0) for key in positive_amount_keys)
                            negative_amount = sum(payslip_amounts.get(key, 0.0) for key in negative_amount_keys)
                            subcategory_amount = positive_amount - negative_amount
                        if method_to_call:
                            try:
                                method_to_call = getattr(self.sudo(), method_to_call)
                            except AttributeError:
                                method_to_call = None
                            except TypeError:
                                method_to_call = None
                            if method_to_call:
                                try:
                                    subcategory_amount += method_to_call(payslip)
                                except:
                                    pass

                        # Add to the total payslip category amount
                        total_amount += subcategory_amount

                        # Safe subcategory data
                        subcategory_data.append(subcategory_amount)

                        # Add to the absolute totals
                        subcategory_totals = payslip_totals[category_index]['subcategory_totals'][subcategory_index] or 0.0
                        subcategory_total_amount = subcategory_totals + subcategory_amount
                        payslip_totals[category_index]['subcategory_totals'][subcategory_index] = subcategory_total_amount

                    subcategory_index += 1

                # Save the category type to the totals category data
                payslip_totals[category_index]['type'] = category.get('type')

                # Calculate absolute totals for each category based on subcategories if the column has this attribute
                if category.get('totals_column'):
                    # Get the subcategory totals for the totals category
                    subcategory_totals = payslip_totals[category_index]['subcategory_totals']
                    payslip_totals[category_index]['print_category_total'] = True
                    if is_time:
                        payslip_category_total = {
                            'days': total_days,
                            'hours': total_hours,
                        }

                        # Sum up days together
                        subcategory_total_days = sum(subcategory_total.get('days', 0.0) for subcategory_total in subcategory_totals)
                        subcategory_total_hours = sum(subcategory_total.get('hours', 0.0) for subcategory_total in subcategory_totals)
                        payslip_totals[category_index]['category_total'] = {
                            'days': subcategory_total_days,
                            'hours': subcategory_total_hours,
                        }
                    else:
                        payslip_category_total = total_amount

                        # Sum up amounts together
                        subcategory_total_amount = sum(subcategory_total for subcategory_total in subcategory_totals)
                        payslip_totals[category_index]['category_total'] = subcategory_total_amount
                else:
                    # Don't show totals for the category
                    payslip_totals[category_index]['print_category_total'] = False
                    payslip_category_total = None

                # Add to the total category data
                payslip_category_data.append({
                    'subcategory_data': subcategory_data,
                    'category_total': payslip_category_total,
                    'print_category_total': category.get('totals_column'),
                    'type': category['type']
                })

                category_index += 1

            payslip_values['values'] = payslip_category_data
            payslip_data.append(payslip_values)

        return {
            'totals': payslip_totals,
            'values': payslip_data,
        }

    @api.model
    def _get_payment_amounts(self, payslip):
        """
        Gets other payment amount for a specific payslip
        Args:
            payslip (hr.payslip): the payslip to get the payments for

        Returns: The total amount of payments

        """
        if not payslip:
            return 0.0

        payslip_run = payslip.payslip_run_id
        if not payslip_run:
            return 0.0

        # Payment data should be passed through context to reduce the number of searches
        payment_data = self._context.get('payments')
        if not payment_data:
            payment_data = self._get_payment_and_compensation_data(payslip_run, payslip.employee_id.ids)

        if not payment_data:
            return 0.0

        # Filter by payslip run and contract
        payments = payment_data.get(payslip_run.id, dict()).get('payments', list())
        # Don't show benefit in kind records where employer pays taxes since they're not really salary payments, are
        # paid differently
        payments = [
            payment for payment in payments
            if payment.get('contract_id') == payslip.contract_id.id and
               payment.get('type') not in ['benefit_in_kind_employer_pays_taxes', 'benefit_in_kind_employee_pays_taxes']
        ]
        if not payments:
            return 0.0

        return sum(payment.get('neto', 0.0) for payment in payments)