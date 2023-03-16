# -*- coding: utf-8 -*-
from odoo.addons.e_document.model.e_document import LINKSNIAI_FUNC as linksnis

from odoo import models, api, fields, _, exceptions


class EDocument(models.Model):
    _inherit = 'e.document'

    qualification_order_employee_lines = fields.One2many('e.document.qualification.order.employee.lines', 'document_id',
                                                         string='Darbuotojai', inverse='set_final_document',
                                                         readonly=True,
                                                         states={'draft': [('readonly', False)]})

    qualification_order_employee_text = fields.Char(compute='_compute_qualification_order_employee_text')
    qualification_order_employee_group_text = fields.Char(compute='_compute_qualification_order_employee_group_text')
    qualification_employee_name = fields.Char(compute='_compute_qualification_employee_name')
    qualification_order_date_string = fields.Char(compute='_compute_qualification_order_date_string')

    @api.one
    @api.depends('qualification_order_employee_lines', 'qualification_order_employee_lines.employee_id')
    def _compute_qualification_order_employee_text(self):
        text = ''
        if self.is_qualification_improvement_doc() and self.qualification_order_employee_lines:
            if len(self.qualification_order_employee_lines.mapped('employee_id')) == 1:
                employee = self.qualification_order_employee_lines.mapped('employee_id')
                text = linksnis['ka'](employee.job_id.name.lower()) + ' ' + linksnis['ka'](employee.name)
            else:
                text = _('darbuotojų grupę')
        self.qualification_order_employee_text = text

    @api.one
    @api.depends('qualification_order_employee_lines', 'qualification_order_employee_lines.employee_id')
    def _compute_qualification_order_employee_group_text(self):
        text = ''
        if self.is_qualification_improvement_doc() and len(
                self.qualification_order_employee_lines.mapped('employee_id')) > 1:
            text = _('<br/><br/>Į renginį išleidžiami šie darbuotojai:\n')
            text += '''<ul style="margin-left:20px;">'''
            for employee in self.qualification_order_employee_lines.mapped('employee_id').sorted(key=lambda e: e.name):
                text += '<li>' + employee.name + '</li>\n'
            text += '''</ul>'''
        self.qualification_order_employee_group_text = text

    @api.one
    @api.depends('qualification_order_employee_lines')
    def _compute_qualification_employee_name(self):
        employee_name = ''
        if self.is_qualification_improvement_doc() and self.qualification_order_employee_lines and \
                len(self.qualification_order_employee_lines.mapped('employee_id')) == 1:
            employee_name = self.qualification_order_employee_lines.mapped('employee_id').name
            employee_name = linksnis['ko'](employee_name).upper() + ' '
        self.qualification_employee_name = employee_name

    @api.one
    @api.depends('date_from', 'date_to', 'template_id')
    def _compute_qualification_order_date_string(self):
        text = ''
        if self.is_qualification_improvement_doc():
            if self.date_from == self.date_to:
                text = self.date_string(self.date_from, 'ko', 'ko', 'ka')
            else:
                text = 'nuo ' + self.date_from + ' iki ' + self.date_to
            text += ' '
        self.qualification_order_date_string = text

    @api.onchange('date_from')
    def _qualification_order_set_date_to_on_date_from_change(self):
        if self.is_qualification_improvement_doc() and self.date_from:
            self.date_to = self.date_from

    @api.multi
    @api.constrains('qualification_order_employee_lines')
    def _check_qualification_employee_lines_set(self):
        for rec in self:
            if rec.is_qualification_improvement_doc() and not rec.qualification_order_employee_lines:
                raise exceptions.UserError(
                    _('Nenustatyti darbuotojai, kurie dalyvaus kvalifikacijos tobulinimo renginyje')
                )
            amount_of_lines = len(rec.qualification_order_employee_lines)
            amount_of_employees = len(rec.qualification_order_employee_lines.mapped('employee_id'))
            if amount_of_employees < amount_of_lines:
                raise exceptions.UserError(
                    _('Kai kurie darbuotojai įvesti kelis kartus. Patikrinkite darbutojų sąrašą')
                )

    @api.multi
    @api.constrains('date_from', 'date_to')
    def _check_qualification_dates_set(self):
        for rec in self:
            if rec.is_qualification_improvement_doc() and rec.date_from > rec.date_to:
                raise exceptions.UserError(_('Renginio pradžia privalo būti prieš renginio pabaigą'))

    @api.multi
    def is_qualification_improvement_doc(self):
        self.ensure_one()
        doc_to_check = self.env.ref('e_document.isakymas_del_kvalifikacijos_tobulinimo_template',
                                    raise_if_not_found=False)
        is_doc = doc_to_check and self.sudo().template_id.id == doc_to_check.id
        if not is_doc:
            try:
                is_doc = doc_to_check and self.template_id.id == doc_to_check.id
            except:
                pass
        return is_doc

    @api.multi
    def isakymas_del_kvalifikacijos_tobulinimo_workflow(self):
        self.ensure_one()
        qualification_status_id = self.env.ref('hr_holidays.holiday_status_KV').id
        for line in self.qualification_order_employee_lines:
            hol_id = self.env['hr.holidays'].create({
                'name': 'Kvalifikacijos Kėlimas',
                'data': self.date_document,
                'employee_id': line.employee_id.id,
                'holiday_status_id': qualification_status_id,
                'date_from': self.calc_date_from(self.date_from),
                'date_to': self.calc_date_to(self.date_to),
                'type': 'remove',
                'numeris': self.document_number,
            })
            hol_id.action_approve()
            self.inform_about_creation(hol_id)

        if len(self.qualification_order_employee_lines) == 1:
            self.write({'employee_id2': self.qualification_order_employee_lines.employee_id.id})

        self.write({'record_model': 'hr.holidays'})


EDocument()


class EDocumentQualificationOrderEmployeeLines(models.Model):
    _name = 'e.document.qualification.order.employee.lines'

    document_id = fields.Many2one('e.document', string='Dokumentas', required=True)
    employee_id = fields.Many2one('hr.employee', string='Darbuotojas', required=True)
    request_date = fields.Date(string='Prašymo data')


EDocumentQualificationOrderEmployeeLines()
