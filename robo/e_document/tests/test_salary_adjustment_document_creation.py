from odoo.addons.l10n_lt_payroll.tests.test_common_payroll import TestCommonPayroll
from odoo.tests import tagged
from odoo.tools import float_round


@tagged('post_install', 'robo', 'salary_adjustment', 'payroll')
class TestSalaryAdjustmentDocumentCreation(TestCommonPayroll):

    @classmethod
    def setUpClass(cls):
        super(TestSalaryAdjustmentDocumentCreation, cls).setUpClass()
        cls.HrPayroll = cls.env['hr.payroll']
        cls.test_date = '2021-12-20'
        cls.monthly_appointment = cls.monthly_salary_structure_contract.with_context(date=cls.test_date).appointment_id
        cls.hourly_appointment = cls.hourly_salary_structure_contract.with_context(date=cls.test_date).appointment_id

    def test_00_salary_less_than_minimum_wage_no_adjustments_for_monthly_structure(self):
        self.monthly_appointment.write({'wage': 700.0})  # Manually force update appointment wage

        # Get contract change data
        kwargs = {'date_from': self.test_date}
        document_creation_data = self.HrPayroll.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        contract_change_data = document_creation_data.get('contract_change_data')

        # Check if contract that needs changes is in the contract change data
        self.assertTrue(
            self.monthly_salary_structure_contract.id in contract_change_data,
            'Contract that should be changed was not found in contract change data'
        )

        # Limit the data to change to only this one contract
        contract_change_data = {
            self.monthly_salary_structure_contract.id: contract_change_data[self.monthly_salary_structure_contract.id],
        }

        # Prepare other data for creation
        change_date = document_creation_data['change_date']
        auto_confirm = False

        # Create salary adjustment document
        self.HrPayroll._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

        # Find created documents
        created_document = self.env['e.document'].search([
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.monthly_salary_structure_employee.id),
            ('date_3', '=', change_date)
        ])
        # Assure both documents were created
        self.assertEqual(len(created_document), 1, 'Document for salary change was not created')

        # Check the document was created with the correct wage
        document_wage = float_round(created_document.float_1, precision_digits=2)
        expected_wage = 730.0
        self.assertEqual(
            document_wage, expected_wage, 'Expected document wage does not match the wage set in the document!'
        )

        # Cleanup - unlink document
        created_document.sudo().with_context(unlink_from_script=True).unlink()

    def test_01_salary_less_than_minimum_wage_no_adjustments_for_hourly_structure(self):
        self.hourly_appointment.write({'wage': 4.0})  # Manually force update appointment wage

        # Get contract change data
        kwargs = {'date_from': self.test_date}
        document_creation_data = self.HrPayroll.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        contract_change_data = document_creation_data.get('contract_change_data')

        # Check if contract that needs changes is in the contract change data
        self.assertTrue(
            self.hourly_salary_structure_contract.id in contract_change_data,
            'Contract that should be changed was not found in contract change data'
        )

        # Limit the data to change to only this one contract
        contract_change_data = {
            self.hourly_salary_structure_contract.id: contract_change_data[self.hourly_salary_structure_contract.id],
        }

        # Prepare other data for creation
        change_date = document_creation_data['change_date']
        auto_confirm = False

        # Create salary adjustment document
        self.HrPayroll._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

        # Find created documents
        created_document = self.env['e.document'].search([
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.hourly_salary_structure_employee.id),
            ('date_3', '=', change_date)
        ])
        # Assure both documents were created
        self.assertEqual(len(created_document), 1, 'Document for salary change was not created')

        # Check the document was created with the correct wage
        document_wage = float_round(created_document.float_1, precision_digits=2)
        expected_wage = 4.47
        self.assertEqual(
            document_wage, expected_wage, 'Expected document wage does not match the wage set in the document!'
        )

        # Cleanup - unlink document
        created_document.sudo().with_context(unlink_from_script=True).unlink()

    def test_02_salary_less_than_minimum_wage_post_adjustments_for_monthly_structure(self):
        self.monthly_appointment.write({'wage': 350.0})  # Manually force update appointment wage
        # Adjust post and fixed attendances
        fixed_attendance_values = [(5,)]
        for i in range(0, 5):
            fixed_attendance_values.append((0, 0, {'hour_from': 8.0, 'hour_to': 12.0, 'dayofweek': str(i)}))
        self.monthly_appointment.schedule_template_id.write({
            'etatas_stored': 0.5, 'fixed_attendance_ids': fixed_attendance_values
        })

        # Get contract change data
        kwargs = {'date_from': self.test_date}
        document_creation_data = self.HrPayroll.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        contract_change_data = document_creation_data.get('contract_change_data')

        # Check if contract that needs changes is in the contract change data
        self.assertTrue(
            self.monthly_salary_structure_contract.id in contract_change_data,
            'Contract that should be changed was not found in contract change data'
        )

        # Limit the data to change to only this one contract
        contract_change_data = {
            self.monthly_salary_structure_contract.id: contract_change_data[self.monthly_salary_structure_contract.id],
        }

        # Prepare other data for creation
        change_date = document_creation_data['change_date']
        auto_confirm = False

        # Create salary adjustment document
        self.HrPayroll._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

        # Find created documents
        created_document = self.env['e.document'].search([
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.monthly_salary_structure_employee.id),
            ('date_3', '=', change_date)
        ])
        # Assure both documents were created
        self.assertEqual(len(created_document), 1, 'Document for salary change was not created')

        # Check the document was created with the correct wage
        document_wage = float_round(created_document.float_1, precision_digits=2)
        expected_wage = 365.0  # Work norm does not play a role. Expecting wage for half post - 730 * 0.5
        self.assertEqual(
            document_wage, expected_wage, 'Expected document wage does not match the wage set in the document!'
        )

        # Cleanup - unlink document
        created_document.sudo().with_context(unlink_from_script=True).unlink()

    def test_03_salary_less_than_minimum_wage_post_adjustments_for_hourly_structure(self):
        self.hourly_appointment.write({'wage': 4.0})  # Manually force update appointment wage
        # Adjust post and work norm
        self.hourly_appointment.schedule_template_id.write({'etatas_stored': 0.5, 'work_norm': 0.95})

        # Get contract change data
        kwargs = {'date_from': self.test_date}
        document_creation_data = self.HrPayroll.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        contract_change_data = document_creation_data.get('contract_change_data')

        # Check if contract that needs changes is in the contract change data
        self.assertTrue(
            self.hourly_salary_structure_contract.id in contract_change_data,
            'Contract that should be changed was not found in contract change data'
        )

        # Limit the data to change to only this one contract
        contract_change_data = {
            self.hourly_salary_structure_contract.id: contract_change_data[self.hourly_salary_structure_contract.id],
        }

        # Prepare other data for creation
        change_date = document_creation_data['change_date']
        auto_confirm = False

        # Create salary adjustment document
        self.HrPayroll._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

        # Find created documents
        created_document = self.env['e.document'].search([
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.hourly_salary_structure_employee.id),
            ('date_3', '=', change_date)
        ])
        # Assure both documents were created
        self.assertEqual(len(created_document), 1, 'Document for salary change was not created')

        # Check the document was created with the correct wage
        document_wage = float_round(created_document.float_1, precision_digits=2)
        expected_wage = 4.47  # Nor work norm nor post plays a role. Expecting new hourly wage - 4.47
        self.assertEqual(
            document_wage, expected_wage, 'Expected document wage does not match the wage set in the document!'
        )

        # Cleanup - unlink document
        created_document.sudo().with_context(unlink_from_script=True).unlink()

    def test_04_salary_less_than_minimum_wage_multiple_adjustments_for_monthly_structure(self):
        # Add an adjustment to the new minimum hourly wage
        minimum_monthly_wage_adjustment = 70
        self.env['ir.config_parameter'].set_param('minimum_monthly_wage_adjustment', str(minimum_monthly_wage_adjustment))

        self.monthly_appointment.write({'wage': 350.0})  # Manually force update appointment wage
        # Adjust post and fixed attendances
        fixed_attendance_values = [(5,)]
        for i in range(0, 5):
            fixed_attendance_values.append((0, 0, {'hour_from': 8.0, 'hour_to': 12.0, 'dayofweek': str(i)}))
        self.monthly_appointment.schedule_template_id.write({
            'etatas_stored': 0.5, 'fixed_attendance_ids': fixed_attendance_values
        })

        # Get contract change data
        kwargs = {'date_from': self.test_date}
        document_creation_data = self.HrPayroll.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        contract_change_data = document_creation_data.get('contract_change_data')

        # Check if contract that needs changes is in the contract change data
        self.assertTrue(
            self.monthly_salary_structure_contract.id in contract_change_data,
            'Contract that should be changed was not found in contract change data'
        )

        # Limit the data to change to only this one contract
        contract_change_data = {
            self.monthly_salary_structure_contract.id: contract_change_data[self.monthly_salary_structure_contract.id],
        }

        # Prepare other data for creation
        change_date = document_creation_data['change_date']
        auto_confirm = False

        # Create salary adjustment document
        self.HrPayroll._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

        # Find created documents
        created_document = self.env['e.document'].search([
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.monthly_salary_structure_employee.id),
            ('date_3', '=', change_date)
        ])
        # Assure both documents were created
        self.assertEqual(len(created_document), 1, 'Document for salary change was not created')

        # Check the document was created with the correct wage
        document_wage = float_round(created_document.float_1, precision_digits=2)
        expected_wage = 400  # Work norm does not play a role. Expecting wage for half post - (730+70) * 0.5
        self.assertEqual(
            document_wage, expected_wage, 'Expected document wage does not match the wage set in the document!'
        )

        # Cleanup - unlink document
        created_document.sudo().with_context(unlink_from_script=True).unlink()

        # Reset config parameter
        self.env['ir.config_parameter'].set_param('minimum_monthly_wage_adjustment', '')

    def test_05_salary_less_than_minimum_wage_multiple_adjustments_for_hourly_structure(self):
        # Add an adjustment to the new minimum hourly wage
        minimum_hourly_wage_adjustment = 1.0
        self.env['ir.config_parameter'].set_param('minimum_hourly_wage_adjustment', str(minimum_hourly_wage_adjustment))

        self.hourly_appointment.write({'wage': 4.0})  # Manually force update appointment wage
        # Adjust post and work norm
        self.hourly_appointment.schedule_template_id.write({'etatas_stored': 0.5, 'work_norm': 0.95})

        # Get contract change data
        kwargs = {'date_from': self.test_date}
        document_creation_data = self.HrPayroll.prepare_data_for_minimum_wage_salary_adjustment(**kwargs)
        contract_change_data = document_creation_data.get('contract_change_data')

        # Check if contract that needs changes is in the contract change data
        self.assertTrue(
            self.hourly_salary_structure_contract.id in contract_change_data,
            'Contract that should be changed was not found in contract change data'
        )

        # Limit the data to change to only this one contract
        contract_change_data = {
            self.hourly_salary_structure_contract.id: contract_change_data[self.hourly_salary_structure_contract.id],
        }

        # Prepare other data for creation
        change_date = document_creation_data['change_date']
        auto_confirm = False

        # Create salary adjustment document
        self.HrPayroll._create_minimum_wage_salary_adjustment_documents(change_date, contract_change_data, auto_confirm)

        # Find created documents
        created_document = self.env['e.document'].search([
            ('template_id', '=', self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id),
            ('employee_id2', '=', self.hourly_salary_structure_employee.id),
            ('date_3', '=', change_date)
        ])
        # Assure both documents were created
        self.assertEqual(len(created_document), 1, 'Document for salary change was not created')

        # Check the document was created with the correct wage
        document_wage = float_round(created_document.float_1, precision_digits=2)
        # Nor work norm nor post plays a role. Expecting new hourly wage - 4.47
        expected_wage = 4.47 + minimum_hourly_wage_adjustment
        self.assertEqual(
            document_wage, expected_wage, 'Expected document wage does not match the wage set in the document!'
        )

        # Cleanup - unlink document
        created_document.sudo().with_context(unlink_from_script=True).unlink()

        # Reset config parameter
        self.env['ir.config_parameter'].set_param('minimum_hourly_wage_adjustment', '')
