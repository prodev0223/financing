# -*- coding: utf-8 -*-
from odoo.addons.l10n_lt_payroll.tests.test_manager_creation import CommonManagerTestData

from odoo.tests import tagged


class CommonEmployeeTestData(CommonManagerTestData):

    @classmethod
    def setUpClass(cls):
        super(CommonEmployeeTestData, cls).setUpClass()

        # Create a programmer job as the manager
        cls.programmer_job = cls.env['hr.job'].sudo(cls.manager_user.id).create({'name': 'Programmer'})

        # Create an IT department as the manager
        cls.it_department = cls.env['hr.department'].sudo(cls.manager_user.id).create({'name': 'IT'})

        # Create a new employee as the manager
        cls.regular_employee = cls.env['hr.employee'].sudo(cls.manager_user.id).create({
            'name': "Robo User",
            'identification_id': '39006010013',
            'department_id': cls.it_department.id,
            'job_id': cls.programmer_job.id,
            'work_email': 'user@robolabs.lt',
            'type': 'employee',
            'robo_access': True,
            'robo_group': 'employee',
        })

        # Set employee access
        cls.regular_employee._set_robo_access()

        # I save the created employee user
        cls.regular_user = cls.env['res.users'].search([('employee_ids', 'in', cls.regular_employee.ids)], limit=1)


@tagged('post_install', 'robo')
class TestEmployeeCreation(CommonEmployeeTestData):
    def test_00_employee_creation(self):
        # Check employee created successfully
        self.assertEqual(self.regular_employee.name, 'Robo User')

    def test_01_employee_user_creation(self):
        # Check if the created employee has a related user
        self.assertIsNotNone(self.regular_user.id, 'User was not created for the regular employee')