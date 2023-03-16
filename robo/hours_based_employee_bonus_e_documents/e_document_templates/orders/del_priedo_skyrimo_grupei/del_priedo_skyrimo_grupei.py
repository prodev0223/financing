# -*- coding: utf-8 -*-
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, api, tools, fields, _, exceptions


class EDocument(models.Model):

    _inherit = 'e.document'

    hours_based_bonus_line_ids = fields.One2many('hours.based.bonus.line', 'e_document_id',
                                                 string='Valandomis remto priedo eilutės',
                                                 inverse='set_final_document', readonly=True,
                                                 states={'draft': [('readonly', False)]}, copy=True)
    count_bonus_by_hours = fields.Boolean(string='Skaičiuoti pagal dirbtas valandas', inverse='set_final_document',
                                          readonly=True,
                                          states={'draft': [('readonly', False)]}, copy=True)

    @api.multi
    @api.depends('e_document_line_ids', 'hours_based_bonus_line_ids', 'count_bonus_by_hours')
    def _compute_text_1(self):
        res = super(EDocument, self)._compute_text_1()
        for rec in self.filtered(lambda d: d.template_id == self.env.ref(
                'e_document.isakymas_del_priedo_skyrimo_grupei_template') and d.count_bonus_by_hours):
            compute_text_1 = '''<br>Priedas skiriamas šiems darbuotojams:
                                        <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                                        <tr style="border:1px solid black;">
                                        <td style="border:1px solid black;"><b>Vardas pavardė</b></td>
                                        <td style="border:1px solid black;"><b>Priedo dydis (bruto), EUR</b></td>
                                        </td></tr>'''
            for line in rec.hours_based_bonus_line_ids:
                amount = '%.2f' % line.float_1
                amount = amount.replace('.', ',')
                compute_text_1 += '''
                     <tr style="border:1px solid black;">
                     <td style="border:1px solid black;">%(name)s</td>
                     <td style="border:1px solid black;">%(amount)s</td>''' % {
                    'name': line.employee_id2.name,
                    'amount': amount,
                }
            compute_text_1 += """</table><br>"""
            rec.compute_text_1 = compute_text_1
        return res

    @api.depends('document_type', 'employee_id1', 'employee_id2', 'business_trip_employee_line_ids.employee_id',
                 'e_document_line_ids', 'template_id', 'count_bonus_by_hours', 'hours_based_bonus_line_ids')
    def _doc_partner_id(self):
        return super(EDocument, self)._doc_partner_id()

    @api.multi
    def check_workflow_date_constraints(self):
        res = super(EDocument, self).check_workflow_date_constraints()
        group_bonus_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template',
                                            raise_if_not_found=False)

        if self.template_id == group_bonus_template:
            employee_ids = self.hours_based_bonus_line_ids.mapped('employee_id2.id')
            has_closed_slip = bool(self.env['hr.payslip'].sudo().search_count([
                ('employee_id', 'in', employee_ids),
                ('date_from', '=', self.date_3),
                ('state', '=', 'done')
            ]))
            if has_closed_slip:
                raise exceptions.ValidationError(_(
                    'Negalite pasirašyti šio dokumento, nes periode egzistuoja patvirtintas darbuotojo algalapis'))
        return res

    @api.one
    def check_e_document_line_ids(self):
        group_bonus_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template',
                                            raise_if_not_found=False)
        if self.template_id == group_bonus_template:
            lines = self.get_document_lines()
            if not lines:
                raise exceptions.Warning(_('Įveskite bent vieną darbuotoją.'))
            elif lines:
                employee_ids = lines.mapped('employee_id2')
                if len(employee_ids) != len(lines):
                    raise exceptions.Warning(_('Įvesti darbuotojai kartojasi'))
        else:
            return super(EDocument, self).check_e_document_line_ids()

    @api.multi
    def isakymas_del_priedo_skyrimo_grupei_workflow(self):
        lines = self.get_document_lines()
        date_from, date_to = self._get_bonus_payment_dates()
        bonuses = self.env['hr.employee.bonus']
        employees_ids = lines.mapped('employee_id2').ids
        for line in lines:
            bonus_rec = self.env['hr.employee.bonus'].create({
                'employee_id': line.employee_id2.id,
                'for_date_from': self.date_1,
                'for_date_to': self.date_2,
                'payment_date_from': date_from,
                'payment_date_to': date_to,
                'bonus_type': self.bonus_type_selection,
                'amount': line.float_1,
                'amount_type': self.bonus_input_type,
                'related_document': self.id,
            })
            bonus_rec.confirm()
            bonuses += bonus_rec
        self.write({
            'record_model': 'hr.employee.bonus',
            'record_ids': self.format_record_ids(bonuses.ids),
        })

        self.inform_about_payslips_that_need_to_be_recomputed(employees_ids, date_from, date_to)

    def _search_related_employee_ids(self, operator, value):
        res = super(EDocument, self)._search_related_employee_ids(operator, value)

        if operator != 'ilike':
            return res

        employees = []
        if isinstance(value, list):
            for val in value:
                employees += self.env['hr.employee'].with_context(active_test=False).search([
                    ('name', 'ilike', val),
                ]).mapped('id')
        else:
            employees = self.env['hr.employee'].with_context(active_test=False).search([
                ('name', 'ilike', value),
            ]).mapped('id')
        if not employees:
            return res
        bonus_doc_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template',
                                          raise_if_not_found=False)
        panaikinimo_template = self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template')
        ids = []
        panaikinimo_docs = self.env['e.document'].search([
            ('template_id', '=', panaikinimo_template.id)
        ])
        for panaikinimo_doc in panaikinimo_docs:
            cancel_doc = panaikinimo_doc.cancel_id
            if cancel_doc.employee_id2.id in employees:
                ids.append(panaikinimo_doc.id)

        if bonus_doc_template:
            bonus_docs = self.env['e.document'].search([
                ('template_id', '=', bonus_doc_template.id),
                ('id', 'not in', panaikinimo_docs.mapped('id'))
            ])
            for bonus in bonus_docs:
                lines = bonus.get_document_lines()
                for bonus_doc_line in lines:
                    if bonus_doc_line.employee_id2.id in employees:
                        ids.append(bonus_doc_line.e_document_id.id)

        return ['|', ('id', 'in', ids)] + res

    @api.multi
    def _check_bonus_document_lines(self):
        self.ensure_one()
        self.check_e_document_line_ids()
        for line in self.get_document_lines():
            if tools.float_is_zero(line.float_1, precision_digits=2):  # todo: or currency precision ?
                return _('Priedo dydis (bruto) negali būti nulinis!')
            if not line.employee_id2.contract_id:
                return _('Employee {} has no contract, therefore can not get a bonus').format(
                    line.employee_id2.name_related)
        return ''

    @api.multi
    def get_document_lines(self):
        """
        Returns records based on the selection if bonus is counted by hours
        :return: either e.document.line or hours.based.bonus.line records
        """
        self.ensure_one()
        return self.hours_based_bonus_line_ids if self.count_bonus_by_hours else self.e_document_line_ids

    @api.model
    def _get_accumulative_work_time_accounting_net_bonus_warning_dependencies(self):
        dependencies = super(EDocument, self)._get_accumulative_work_time_accounting_net_bonus_warning_dependencies()
        dependencies += ['hours_based_bonus_line_ids.employee_id2']
        return dependencies

    @api.multi
    def _get_employees_for_bonuses(self):
        self.ensure_one()
        if self.template_id != self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template'):
            return super(EDocument, self)._get_employees_for_bonuses()
        return self.get_document_lines().mapped('employee_id2')
