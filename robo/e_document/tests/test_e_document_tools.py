# -*- coding: utf-8 -*-
from .. model import e_document_tools as edoc_tools

from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', 'robo')
class TestAssertCorrectLithuanianIdentificationId(TransactionCase):
    """
    Test that method assert_correct_lithuanian_identification_id()
    returns expected results with different values
    """
    def setUp(self):
        self.lithuanian_identification_correct = '39212288259'
        self.lithuanian_identification_incorrect_length = '392122882590'
        self.lithuanian_identification_incorrect_month = '39213288259'
        self.lithuanian_identification_incorrect_day = '39212338259'
        self.lithuanian_identification_incorrect_last_digit = '39212288250'
        self.not_lithuanian_identification_correct = '323011-19301'

    def test_00_lithuanian_identification_correct(self):
        self.assertTrue(edoc_tools.assert_correct_lithuanian_identification_id(
            self.lithuanian_identification_correct
        ), 'Correct lithuanian identification did not pass the test')

    def test_01_lithuanian_identification_incorrect_length(self):
        self.assertFalse(edoc_tools.assert_correct_lithuanian_identification_id(
            self.lithuanian_identification_incorrect_length
        ), 'Lithuanian identification with incorrect length passed the test')

    def test_02_lithuanian_identification_incorrect_month(self):
        self.assertFalse(edoc_tools.assert_correct_lithuanian_identification_id(
            self.lithuanian_identification_incorrect_month
        ), 'Lithuanian identification with incorrect month part passed the test')

    def test_03_lithuanian_identification_incorrect_day(self):
        self.assertFalse(edoc_tools.assert_correct_lithuanian_identification_id(
            self.lithuanian_identification_incorrect_day
        ), 'Lithuanian identification with incorrect day part passed the test')

    def test_04_lithuanian_identification_incorrect_last_digit(self):
        self.assertFalse(edoc_tools.assert_correct_lithuanian_identification_id(
            self.lithuanian_identification_incorrect_last_digit
        ), 'Lithuanian identification with incorrect last digit passed the test')

    def test_05_not_lithuanian_identification(self):
        self.assertFalse(edoc_tools.assert_correct_lithuanian_identification_id(
            self.not_lithuanian_identification_correct
        ), 'Non lithuanian identification passed the lithuanian identification assertion test')


@tagged('post_install', 'robo')
class TestRemoveLetters(TransactionCase):
    """
    Test method that takes a string, removes any non-numeric character in it
    and returns a numeric-only string
    """
    def setUp(self):
        self.digits = '0123456789'
        self.letters_and_digits = 'abc123'
        self.lithuanian_letters = 'ąčęėįšųūžĄČĘĖĮŠŲŪŽ'
        self.symbols = '!@#$%^&*()-=+_[];:\'",<.>/?'
        self.space = ' '

    def test_06_remove_non_numerics_from_digits_string(self):
        self.assertEqual(
            edoc_tools.remove_letters(self.digits), self.digits, 'Something removed from digits only string')

    def test_07_remove_non_numerics_from_letters_and_digits_string(self):
        self.assertEqual(
            edoc_tools.remove_letters(
                self.letters_and_digits), '123', 'Removing letters from letter and digit string failed')

    def test_08_remove_non_numerics_from_lithuanian_letters_string(self):
        self.assertEqual(
            edoc_tools.remove_letters(self.lithuanian_letters), '', 'Lithuanian letters not removed from string')

    def test_09_remove_non_numerics_from_special_symbols_string(self):
        self.assertEqual(edoc_tools.remove_letters(self.symbols), '', 'Special symbols not removed from string')

    def test_10_remove_non_numerics_from_space_string(self):
        self.assertEqual(edoc_tools.remove_letters(self.space), '', 'Space was not removed from string')


@tagged('post_install', 'robo')
class TestGetBirthdateFromIdentification(TransactionCase):
    """
    Test if correct birthdate is computed from given identification
    """
    def setUp(self):
        self.identification_age_past = '39212288259'  # 1992-12-28
        self.identification_age_current = '60101088035'  # 2001-01-08
        self.identification_incorrect = '49820352587'  # 1998-20-35

    def test_11_get_birthdate_from_past_age_identification(self):
        self.assertEqual(
            edoc_tools.get_birthdate_from_identification(
                self.identification_age_past), '1992-12-28', 'Birthdate of past age not calculated correctly')

    def test_11_get_birthdate_from_current_age_identification(self):
        self.assertEqual(
            edoc_tools.get_birthdate_from_identification(
                self.identification_age_current), '2001-01-08', 'Birthdate of current age not calculated correctly')

    def test_12_get_birthdate_from_incorrect_identification(self):
        self.assertFalse(
            edoc_tools.get_birthdate_from_identification(
                self.identification_incorrect), 'Birthdate was computed for incorrect identification')


@tagged('post_install', 'robo')
class TestGetAgeFromIdentification(TransactionCase):
    """
    Test if age is computed correctly from provided identification
    """
    def setUp(self):
        self.default_date = datetime(2021, 01, 01)
        self.identification = '39212288259'
        self.age_identification = relativedelta(self.default_date, datetime(1992, 12, 28)).years

        self.identification_incorrect = '49820352587'

    def test_13_get_age_from_identification(self):
        self.assertEqual(
            edoc_tools.get_age_from_identification(
                self.identification), self.age_identification, 'Age computed from identification is not correct')

    def test_14_get_age_from_identification_incorrect(self):
        self.assertFalse(
            edoc_tools.get_age_from_identification(
                self.identification_incorrect), 'Age was computed even though identification is incorrect')


