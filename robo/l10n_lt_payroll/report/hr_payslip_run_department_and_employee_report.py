# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.tools.misc import formatLang
from .hr_payslip_run_report import CATEGORIES, REPORT_EXT_ID, _amounts_by_time_codes, _period, _remove, _replace
from .suvestine import _payslip_amounts, _round_time


class ReportHrPayslipRunByDepartment(models.AbstractModel):
    _name = 'report.l10n_lt_payroll.report_hr_payslip_run_by_dep_and_empl'
    _inherit = 'report.l10n_lt_payroll.report_hr_payslip_run'

    @api.multi
    def render_html(self, doc_ids, data=None):
        """
        Renders the report
        Args:
            doc_ids (list): payslip run ids
            data (dict): various params

        Returns: Rendered report

        """
        force_lang = data.get('force_lang') if data else self.env.user.lang or self.env.user.partner_id.lang
        if force_lang != self.env.context.get('lang'):
            return self.with_context(lang=force_lang).render_html(doc_ids, data)
        report_obj = self.env['report']
        if self.env.user.is_manager() or self.env.user.is_hr_manager():
            self = self.sudo()

        # Get payslip run ids and employees that should be filtered
        doc_ids = doc_ids if doc_ids else data.get('payslip_run_id', [])
        employee_ids = data.get('employee_ids', []) if data else ()

        report = report_obj._get_report_from_name(REPORT_EXT_ID)
        docs = self.env[report.model].browse(doc_ids)

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
    def _get_payslip_data(self, payslips):
        """
        Retrieves data from payslips for the salary report
        Args:
            payslips (hr.payslip): Payslips to get the data for

        Returns: Dictionary of payslip values and the total values for those payslips

        """
        # Generate a data structure to store the totals later
        absolute_totals = [
            {
                'subcategory_totals': [
                    dict() for subcategory in category.get('subcategories')
                ]
            } for category in CATEGORIES
        ]

        # Find out the departments of the payslip
        payslip_appointments = payslips.mapped('contract_id.appointment_id') + \
                               payslips.mapped('worked_days_line_ids.appointment_id')
        departments = self.env['hr.department']
        for payslip_appointment in payslip_appointments:
            department = payslip_appointment.department_id
            if not department:
                department = payslip_appointment.employee_id.department_id
            departments |= department

        department_data = list()
        for department in departments:
            department_payslips = self.env['hr.payslip']
            # Encountered a case when no department is set on appointment but is set on employee thus the following
            # payslip filter is required
            for payslip in payslips:
                slip_departments = payslip.mapped('worked_days_line_ids.appointment_id.department_id')
                if not slip_departments:
                    slip_departments = payslip.contract_id.with_context(
                        date=payslip.date_to).appointment_id.department_id
                if not slip_departments:
                    slip_departments = payslip.employee_id.department_id
                if not slip_departments:
                    continue
                is_current_department = department.id in slip_departments.ids
                # If payslip department is the current department add it to the department payslips and don't add the
                # payslip to other departments
                if is_current_department:
                    department_payslips |= payslip
                    payslips = payslips.filtered(lambda slip: slip.id != payslip.id)

            payslip_data = list()
            department_totals_line_values = {'name': department.name, 'no_index': True, 'print_bold': True}
            for payslip in department_payslips:
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

                department_data_values = department_totals_line_values.get('values', list())

                # Get data for each category
                payslip_category_data = list()
                for category_index, category in enumerate(CATEGORIES):
                    subcategories = category.get('subcategories')

                    if len(department_data_values) <= category_index:
                        department_data_values.append({'subcategory_data': list()})
                    department_data_category_values = department_data_values[category_index]

                    subcategory_data = list()

                    total_amount = total_days = total_hours = 0.0

                    is_time = category.get('type') == 'time'

                    for subcategory_index, subcategory in enumerate(subcategories):

                        if len(department_data_category_values['subcategory_data']) <= subcategory_index:
                            if is_time:
                                department_data_category_values['subcategory_data'].append(dict())
                                department_data_category_values['category_total'] = dict()
                            else:
                                department_data_category_values['subcategory_data'].append(0.0)
                                department_data_category_values['category_total'] = 0.0
                        department_data_subcategory_values = department_data_category_values['subcategory_data'][subcategory_index]

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
                            subcategory_totals = absolute_totals[category_index]['subcategory_totals'][subcategory_index]
                            subcategory_total_days = subcategory_totals.get('days', 0.0) + subcategory_days
                            subcategory_total_hours = subcategory_totals.get('hours', 0.0) + subcategory_hours
                            department_data_subcategory_values = {
                                'days': department_data_subcategory_values.get('days', 0.0) + subcategory_days,
                                'hours': department_data_subcategory_values.get('hours', 0.0) + subcategory_hours
                            }
                            absolute_totals[category_index]['subcategory_totals'][subcategory_index][
                                'days'] = subcategory_total_days
                            absolute_totals[category_index]['subcategory_totals'][subcategory_index][
                                'hours'] = subcategory_total_hours
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
                            subcategory_totals = absolute_totals[category_index]['subcategory_totals'][
                                                     subcategory_index] or 0.0
                            subcategory_total_amount = subcategory_totals + subcategory_amount
                            absolute_totals[category_index]['subcategory_totals'][
                                subcategory_index] = subcategory_total_amount

                            department_data_subcategory_values += subcategory_amount

                        department_data_category_values['subcategory_data'][subcategory_index] = department_data_subcategory_values

                    # Save the category type to the totals category data
                    absolute_totals[category_index]['type'] = category.get('type')
                    department_data_category_values['type'] = category.get('type')

                    # Calculate absolute totals for each category based on subcategories if the column has this attribute
                    if category.get('totals_column'):
                        # Get the subcategory totals for the totals category
                        subcategory_totals = absolute_totals[category_index]['subcategory_totals']
                        absolute_totals[category_index]['print_category_total'] = True
                        department_data_category_values['print_category_total'] = True
                        if is_time:
                            payslip_category_total = {
                                'days': total_days,
                                'hours': total_hours,
                            }

                            # Sum up days together
                            subcategory_total_days = sum(
                                subcategory_total.get('days', 0.0) for subcategory_total in subcategory_totals)
                            subcategory_total_hours = sum(
                                subcategory_total.get('hours', 0.0) for subcategory_total in subcategory_totals)
                            absolute_totals[category_index]['category_total'] = {
                                'days': subcategory_total_days,
                                'hours': subcategory_total_hours,
                            }
                            department_data_category_values['category_total'] = {
                                'days': department_data_category_values['category_total'].get('days') + subcategory_total_days,
                                'hours': department_data_category_values['category_total'].get('hours') + subcategory_total_hours
                            }
                        else:
                            payslip_category_total = total_amount

                            # Sum up amounts together
                            subcategory_total_amount = sum(subcategory_total for subcategory_total in subcategory_totals)
                            absolute_totals[category_index]['category_total'] = subcategory_total_amount
                            department_data_category_values['category_total'] = department_data_category_values['category_total'] + total_amount
                    else:
                        # Don't show totals for the category
                        absolute_totals[category_index]['print_category_total'] = False
                        department_data_category_values['print_category_total'] = False
                        if is_time:
                            department_data_category_values['category_total'] = {'days': 0.0, 'hours': 0.0}
                        else:
                            department_data_category_values['category_total'] = 0.0
                        payslip_category_total = None

                    # Add to the total category data
                    payslip_category_data.append({
                        'subcategory_data': subcategory_data,
                        'category_total': payslip_category_total,
                        'print_category_total': category.get('totals_column'),
                        'type': category['type']
                    })

                    department_data_values[category_index] = department_data_category_values

                payslip_values['values'] = payslip_category_data
                payslip_data.append(payslip_values)
                department_totals_line_values['values'] = department_data_values

            department_data.append(department_totals_line_values)
            department_data += payslip_data

        return {
            'totals': absolute_totals,
            'values': department_data,
        }

    @api.model
    def _sort_payslips(self, payslips):
        return payslips.sorted(lambda slip: (
            slip.contract_id.with_context(date=slip.date_from).appointment_id.department_id.name or
            slip.employee_id.department_id.name,
            slip.employee_id.name,
        ))
