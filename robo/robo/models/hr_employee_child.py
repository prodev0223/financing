# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models, tools


class HrEmployeeChild(models.Model):
    _name = "hr.employee.child"

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    birthdate = fields.Date(string='Child Birthdate', required=True)
    has_disability = fields.Boolean(string='Has disability')

    @api.multi
    def get_number_of_children_by_age_and_disability(self, date):
        """
        Get list of number, which children under twelve and which with disability.
        @param date: the date by which the age of the children is calculated
        @return dict() - return a number of children ({under twelve, with disability})
        """
        date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        with_disability = under_twelve = 0
        for child in self:
            birthdate = datetime.strptime(child.birthdate, tools.DEFAULT_SERVER_DATE_FORMAT)
            years = relativedelta(date, birthdate).years
            if child.has_disability and years < 18:
                with_disability += 1
            if years < 12:
                under_twelve += 1
        return {
            'under_twelve': under_twelve,
            'with_disability': with_disability
        }

    @api.multi
    def get_allowed_parental_leaves_per_month(self, date):
        """
        @param date: the date by which the age of the children is calculated
        @return int - return number of free days, which depends on available children
        """
        children_list = self.get_number_of_children_by_age_and_disability(date)
        if children_list['under_twelve'] >= 3:
            return 2
        elif children_list['with_disability'] or children_list['under_twelve'] == 2:
            return 1
        return 0
