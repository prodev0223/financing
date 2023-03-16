# -*- coding: utf-8 -*-

from odoo import _, api, models
from odoo.tools.misc import formatLang
from .hr_payslip_run_report import CATEGORIES, REPORT_EXT_ID, _amounts_by_time_codes, _period, _remove, _replace
from .suvestine import _payslip_amounts, _round_time


class ReportHrPayslipRunByDepartment(models.AbstractModel):
    _name = 'report.l10n_lt_payroll.report_hr_payslip_run_by_department'
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
            # 'payments': payments, # Pass payments if the payment tables should appear at the bottom of the report
            'tax_data': tax_data,
            'report_line_data_title': _('Padalinys')
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
        department_totals = [
            {
                'subcategory_totals': [
                    dict() for subcategory in category.get('subcategories')
                ]
            } for category in CATEGORIES
        ]

        department_data = list()

        # Find out the departments of the payslip
        payslip_appointments = payslips.mapped('contract_id.appointment_id') + \
                               payslips.mapped('worked_days_line_ids.appointment_id')
        departments = self.env['hr.department']
        for payslip_appointment in payslip_appointments:
            department = payslip_appointment.department_id
            if not department:
                department = payslip_appointment.employee_id.department_id
            departments |= department

        for department in departments:
            department_payslips = self.env['hr.payslip']
            # Encountered a case when no department is set on appointment but is set on employee thus the following
            # payslip filter is required
            for payslip in payslips:
                slip_departments = payslip.mapped('worked_days_line_ids.appointment_id.department_id')
                if not slip_departments:
                    slip_departments = payslip.contract_id.with_context(date=payslip.date_to).appointment_id.department_id
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

            # Get the name of the department to show on the report
            department_values = {'name': department.name}

            payslip_amounts = _payslip_amounts(department_payslips)  # Get payslip amounts

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

                        subcategory_res = {}

                        if method_to_call:
                            for payslip in department_payslips:
                                payslip_subcategory_res = method_to_call(payslip)
                                subcategory_res['days'] = payslip_subcategory_res.get('days', 0.0) + subcategory_res.get('days', 0.0)
                                subcategory_res['hours'] = payslip_subcategory_res.get('hours', 0.0) + subcategory_res.get('hours', 0.0)
                        else:
                            codes = subcategory.get('codes')
                            subcategory_res = _amounts_by_time_codes(department_payslips, codes)

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
                        subcategory_totals = department_totals[category_index]['subcategory_totals'][subcategory_index]
                        subcategory_total_days = subcategory_totals.get('days', 0.0) + subcategory_days
                        subcategory_total_hours = subcategory_totals.get('hours', 0.0) + subcategory_hours
                        department_totals[category_index]['subcategory_totals'][subcategory_index][
                            'days'] = subcategory_total_days
                        department_totals[category_index]['subcategory_totals'][subcategory_index][
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
                                    for payslip in department_payslips:
                                        subcategory_amount += method_to_call(payslip)
                                except:
                                    pass

                        # Add to the total payslip category amount
                        total_amount += subcategory_amount

                        # Safe subcategory data
                        subcategory_data.append(subcategory_amount)

                        # Add to the absolute totals
                        subcategory_totals = department_totals[category_index]['subcategory_totals'][
                                                 subcategory_index] or 0.0
                        subcategory_total_amount = subcategory_totals + subcategory_amount
                        department_totals[category_index]['subcategory_totals'][
                            subcategory_index] = subcategory_total_amount

                    subcategory_index += 1

                # Save the category type to the totals category data
                department_totals[category_index]['type'] = category.get('type')

                # Calculate absolute totals for each category based on subcategories if the column has this attribute
                if category.get('totals_column'):
                    # Get the subcategory totals for the totals category
                    subcategory_totals = department_totals[category_index]['subcategory_totals']
                    department_totals[category_index]['print_category_total'] = True
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
                        department_totals[category_index]['category_total'] = {
                            'days': subcategory_total_days,
                            'hours': subcategory_total_hours,
                        }
                    else:
                        payslip_category_total = total_amount

                        # Sum up amounts together
                        subcategory_total_amount = sum(subcategory_total for subcategory_total in subcategory_totals)
                        department_totals[category_index]['category_total'] = subcategory_total_amount
                else:
                    # Don't show totals for the category
                    department_totals[category_index]['print_category_total'] = False
                    payslip_category_total = None

                # Add to the total category data
                payslip_category_data.append({
                    'subcategory_data': subcategory_data,
                    'category_total': payslip_category_total,
                    'print_category_total': category.get('totals_column'),
                    'type': category['type']
                })

                category_index += 1

            department_values['values'] = payslip_category_data
            department_data.append(department_values)

        return {
            'totals': department_totals,
            'values': department_data,
        }

    @api.model
    def _sort_payslips(self, payslips):
        return payslips.sorted(lambda slip: (
            slip.employee_id.department_id.name,
        ))
