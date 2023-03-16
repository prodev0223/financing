# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import SingleTransactionCase


class CommonManagerTestData(SingleTransactionCase):

    @classmethod
    def setUpClass(cls):
        super(CommonManagerTestData, cls).setUpClass()
        # I firstly create a user for the manager
        manager_email = 'manager@robolabs.lt'
        cls.manager_user = cls.env['res.users'].create({
            'login': manager_email,
            'email': manager_email,
            'name': 'Robo Manager',
            'groups_id': [(6, 0, [cls.env.ref('robo_basic.group_robo_free_manager').id])]
        })
        # I then reset the related partner values
        if cls.manager_user:
            cls.manager_user.partner_id.write({'customer': False, 'supplier': True})

        # I try to find an administration department and if it does not exist - I create one
        try:
            cls.administration_department = cls.env.ref('hr.dep_administration')
        except ValueError:
            cls.administration_department = cls.env['hr.department'].create({'name': 'Administration'})

        # I create a new manager job
        cls.manager_job = cls.env['hr.job'].create({'name': 'CEO'})

        # I create a new manager employee - "Robo Manager"
        cls.manager_employee = cls.env['hr.employee'].create({
            'name': "Robo Manager",
            'identification_id': '39006010003',
            'department_id': cls.administration_department.id,
            'job_id': cls.manager_job.id,
            'work_email': manager_email,
            'user_id': cls.manager_user.id,
            'robo_access': True,
            'robo_group': 'manager',
            'address_home_id': cls.manager_user.partner_id.id if cls.manager_user.partner_id else False,
            'type': 'employee',
        })
        # I trigger the identification onchange for the manager so that the gender is automatically set
        cls.manager_employee._onchange_identification_id()
        # I set the new manager as the manager of the company
        cls.manager_employee.company_id.write({'vadovas': cls.manager_employee.id})


@tagged('post_install', 'robo')
class TestManagerCreation(CommonManagerTestData):

    def test_00_manager_user_creation(self):
        # Check that the manager user was created
        self.assertIsNotNone(self.manager_user.id, 'User was not created for the company manager')

    def test_01_manager_employee_creation(self):
        # Check that the company manager has been successfully created
        self.assertEqual(self.manager_employee.name, 'Robo Manager')

    def test_02_manager_set_as_company_ceo(self):
        # Check that the manager is in fact set as the company ceo
        self.assertEqual(self.env.user.company_id.vadovas, self.manager_employee, '')
