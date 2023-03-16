# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged
import logging

_logger = logging.getLogger(__name__)


@tagged('post_install', 'robo')
class TestChangeNameAndEmail(TransactionCase):
    """
    Test that name, email changes are only not allowed from anywhere else than employee card
    """
    def setUp(self):
        super(TestChangeNameAndEmail, self).setUp()

        self.env['ir.mail_server'].search([]).unlink()
        self.employee_related = self.env['hr.employee'].create({
            'name': 'John Doe',
            'robo_access': True,
            'robo_group': 'employee',
            'work_email': 'john.doe@robolabs.lt'
        })
        self.user_related = self.env['res.users'].search([
            ('employee_ids', 'in', self.employee_related.ids)
        ], limit=1)
        self.partner_related = self.env['res.partner'].search([
            ('id', '=', self.user_related.partner_id.id),
        ], limit=1)

        self.employee_unrelated = self.env['hr.employee'].create({
            'name': 'Jane Doe',
            'work_email': 'jane.doe@robolabs.lt'
        })
        self.user_unrelated = self.env['res.users'].create({
            'name': self.employee_unrelated.name,
            'login': self.employee_unrelated.work_email,
        })
        self.partner_unrelated = self.env['res.partner'].create({
            'name': self.employee_unrelated.name,
            'email': self.employee_unrelated.work_email,
        })

        self.new_name = 'Joe Doe'
        self.new_email = 'joe.doe@robolabs.lt'
        self.new_email_2 = 'joshua.doe@robolabs.lt'

    def test_00_write_name_to_partner(self):
        # I check if changing name on partner with related employee is not successful
        with self.assertRaises(Exception):
            self.partner_related.write({'name': self.new_name})
        self.assertNotEqual(self.employee_related.name, self.new_name, 'Name of related employee was changed!')

        # I check if changing name on partner without related employee is successful
        self.assertTrue(self.partner_unrelated.write({'name': self.new_name}))
        self.assertEqual(self.partner_unrelated.name, self.new_name, 'Partners name was not changed!')

    def test_01_write_email_to_partner(self):
        # I check if changing name on partner with related employee is not successful
        with self.assertRaises(Exception):
            self.partner_related.write({'email': self.new_email})
        self.assertNotEqual(self.employee_related.work_email, self.new_email, 'Email of related employee was changed!')

        # I check if changing name on partner without related employee is successful
        self.assertTrue(self.partner_unrelated.write({'email': self.new_email}))
        self.assertEqual(self.partner_unrelated.email, self.new_email, 'Partners email was not changed!')

    def test_02_write_login_to_user(self):
        # I check if changing login of user who has an employee related is not allowed
        with self.assertRaises(Exception):
            self.user_related.write({'login': self.new_email})

        # I check if changing login of user who does not have an employee related is allowed
        self.assertTrue(self.user_unrelated.write({'login': self.new_email_2}))

    def test_03_write_work_email_to_employee(self):
        # I change work email on hr.employee
        self.assertTrue(self.employee_related.write({'work_email': self.new_email}))
        # I check if related user login and partner emails were changed in the process
        self.assertEqual(self.employee_related.work_email, self.new_email)
        self.assertEqual(self.user_related.login, self.new_email)
        self.assertEqual(self.partner_related.email, self.new_email)

    def test_04_write_name_to_employee(self):
        # I change name on hr.employee
        self.assertTrue(self.employee_related.write({'name': self.new_name}))
        # I check if related user and partner had their names changed
        self.assertEqual(self.employee_related.name, self.new_name)
        self.assertEqual(self.user_related.name, self.new_name)
        self.assertEqual(self.partner_related.name, self.new_name)
