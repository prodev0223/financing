# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import tools
from odoo.tests.common import TransactionCase, tagged


import logging


_logger = logging.getLogger(__name__)


@tagged('post_install', 'robo')
class TestVoluntaryInternship(TransactionCase):
    """
    Test EDoc voluntary internship agreement
    """
    def setUp(self):
        super(TestVoluntaryInternship, self).setUp()
        self.employee = self.env['hr.employee'].create({
            'name': 'John Doe',
        })
        self.supervisor = self.env['hr.employee'].create({
            'name': 'Jane Doe',
        })

        attendance_line_ids = []
        attendance_line = self.env['e.document.fix.attendance.line'].create({
            'dayofweek': '1',
            'hour_from': 8.0,
            'hour_to': 17.0
        })
        self.date = datetime.utcnow()
        attendance_line_ids.append(attendance_line.id)
        self.document = self.env['e.document'].create({
            'template_id': self.env.ref('e_document.voluntary_internship_agreement_template', False).id,
            'date_document': self.date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'vieta': 'Vilnius',
            'employee_id1': self.supervisor.id,
            'employee_id2': self.employee.id,
            'text_1': '39710158183',
            'text_2': 'Vilnius',
            'text_3': 'Internship description',
            'text_6': 'street 1, Vilnius',
            'date_from': self.date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'date_to': (self.date + relativedelta(months=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            'int_1': 5,
            'fixed_attendance_ids': [(6, 0, attendance_line_ids)],
        })

    def test_00_confirm_dates(self):
        # I check if document confirm fails with date_to earlier than date_from
        self.document.write({
            'date_from': self.document.date_to,
            'date_to': self.document.date_from,
        })
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm', 'Document confirmed with date_to earlier than date_from!')

    def test_01_confirm_duration(self):
        # I check if document confirm fails with durations exceeding the maximum voluntary internship duration
        self.document.write({
            'date_to': (self.date + relativedelta(years=10)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        })
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm',
                            'Document confirmed with longer than maximum voluntary internship duration!')

    def test_02_confirm_notice_period(self):
        # I check if document confirm fails on incorrect notice period
        self.document.write({'int_1': 0})
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm', 'Document confirmed with incorrect notice period!')

    def test_03_confirm_intern_is_own_supervisor(self):
        # I check if document confirm fails if intern and supervisor are the same person
        self.document.write({'employee_id1': self.employee.id})
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm',
                            'Document confirmed with the same person as intern and supervisor!')

    def test_04_confirm_attendance_lines(self):
        # I check if document confirm fails if there are no attendance lines
        self.document.write({'fixed_attendance_ids': False})
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm',
                            'Document confirmed with no attendance lines!')

    def test_05_confirm_personal_code(self):
        # I check if document confirm fails if the personal code is incorrect
        self.document.write({'text_1': '33303033333'})
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm', 'Document confirmed with incorrect format personal code!')

        # I check if document confirm fails if the person is 30y.o. or older;
        self.document.write({'text_1': '32011019933'})
        with self.assertRaises(Exception):
            self.document.confirm()
        self.assertNotEqual(self.document.state, 'confirm',
                            'Document confirmed with intern older than maximum allowed age for this type of contract!')
