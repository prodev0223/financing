from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import tools
from odoo.addons.l10n_lt_payroll.tests.test_employee_creation import CommonEmployeeTestData
from odoo.tests import tagged


@tagged('post_install', 'robo')
class TestEmployment(CommonEmployeeTestData):

    @classmethod
    def setUpClass(cls):
        super(TestEmployment, cls).setUpClass()

        # I form a list of attendance values
        fixed_attendance_values = [(5,)]
        for i in range(0, 5):
            fixed_attendance_values += [
                (0, 0, {'hour_from': 8.0, 'hour_to': 12.0, 'dayofweek': str(i)}),
                (0, 0, {'hour_from': 13.0, 'hour_to': 17.0, 'dayofweek': str(i)})
            ]

        # I store basic order dates
        order_date = datetime(2021, 9, 1)
        request_date = order_date - relativedelta(days=5)
        employment_start_date = order_date + relativedelta(days=5)

        # I create an employment order with the manager rights
        cls.employment_order = cls.env['e.document'].sudo(cls.manager_user.id).create({
            'employee_id2': cls.regular_employee.id,
            'date_document': order_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'date_2': request_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'date_from': employment_start_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'float_1': 1000,
            'template_id': cls.env.ref('e_document.isakymas_del_priemimo_i_darba_template').id,
            'fixed_schedule_template': '8_hrs_5_days',
            'fixed_attendance_ids': fixed_attendance_values,
            'document_type': 'isakymas',
        })

        # I create the employment request with the employer rights
        cls.employment_request = cls.env['e.document'].sudo(cls.regular_user.id).create({
            'employee_id1': cls.regular_employee.id,
            'vieta': 'Test',
            'date_1': request_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'text_4': 'LT887290000016467487',
            'selection_bool_1': 'false',
            'selection_bool_3': 'false',
            'selection_bool_2': 'false',
            'template_id': cls.env.ref('e_document.prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_template').id,
        })

    def test_00_employment_order_confirmation(self):
        # I confirm the employment order
        self.employment_order.sudo(self.manager_user.id).confirm()
        self.assertEqual(self.employment_order.state, 'confirm', 'Could not confirm the employment order')

    def test_01_employment_order_signing(self):
        # I reset existing payslip runs to draft state so that the order can be signed.
        confirmed_payslip_runs = self.env['hr.payslip.run'].sudo().search([
            ('date_end', '>=', self.employment_order.date_from),
            ('state', '=', 'close')]
        )
        confirmed_payslip_runs.write({'state': 'draft'})

        # I sign the employment order
        self.employment_order.sudo(self.manager_user.id).sign()
        self.assertEqual(self.employment_order.state, 'e_signed', 'Could not sign the employment order')

        # I rollback the state for the confirmed payslip runs
        confirmed_payslip_runs.write({'state': 'close'})

    def test_02_employment_request_confirmation(self):
        # I confirm the employment request
        self.employment_request.sudo(self.regular_user.id).confirm()
        self.assertEqual(self.employment_request.state, 'confirm', 'Could not confirm the employment request')

    def test_03_employment_request_signing(self):
        # I sign the employment request
        self.employment_request.sudo(self.regular_user.id).sign()
        self.assertEqual(self.employment_request.state, 'e_signed', 'Could not sign the employment request')
