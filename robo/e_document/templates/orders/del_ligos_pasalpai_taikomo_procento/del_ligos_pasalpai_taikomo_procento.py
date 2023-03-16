# -*- coding: utf-8 -*-
from __future__ import division
from datetime import datetime
from odoo import models, api, exceptions, _, tools


LIGO_COEFF_MIN = 62.06
LIGO_COEFF_MAX = 100.0


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def isakymas_del_ligos_pasalpai_taikomo_procento_workflow(self):
        self.ensure_one()
        param = self.env['payroll.parameter.history'].search([
            ('date_from', '=', self.date_from),
            ('field_name', '=', 'ligos_koeficientas'),
            ('company_id', '=', self.company_id.id)
        ])
        if not param:
            param = self.env['payroll.parameter.history'].create({
                'date_from': self.date_from,
                'field_name': 'ligos_koeficientas',
                'value': self.float_1 / 100.0,  # P3:DivOK
                'company_id': self.company_id.id
            })
        else:
            param.write({'value': self.float_1 / 100.0})  # P3:DivOK
        self.write({
            'record_model': 'payroll.parameter.history',
            'record_id': param.id,
        })

    @staticmethod
    def check_ligo_koeficientage_percentage(coefficient):
        """
        Check that the "ligo" coefficient is within the valid range of percentage values
        :return: True if within range, False otherwise
        """
        return tools.float_compare(abs(coefficient - (LIGO_COEFF_MAX + LIGO_COEFF_MIN) / 2.0),  # P3:DivOK
                                   (LIGO_COEFF_MAX - LIGO_COEFF_MIN) / 2.0,  # P3:DivOK
                                   precision_digits=2) <= 0

    @api.constrains('float_1')
    def _check_float_1_percentage(self):
        template = self.env.ref('e_document.isakymas_del_ligos_pasalpai_taikomo_procento_template', False)
        for rec in self:
            if rec.sudo().template_id == template:
                if not rec.check_ligo_koeficientage_percentage(rec.float_1):
                    raise exceptions.ValidationError(_('Taikomas procentas turi būti reikšmė tarp %.2f ir %.2f.')
                                                     % (LIGO_COEFF_MIN, LIGO_COEFF_MAX))

    @api.multi
    def execute_confirm_workflow_check_values(self):
        """ Checks value before allowing to confirm an edoc """
        super(EDocument, self).execute_confirm_workflow_check_values()
        template = self.env.ref('e_document.isakymas_del_ligos_pasalpai_taikomo_procento_template', False)
        for rec in self:
            if rec.sudo().skip_constraints_confirm:
                continue
            if rec.sudo().template_id == template:
                if not rec.check_ligo_koeficientage_percentage(rec.float_1):
                    raise exceptions.UserError(_('Taikomas procentas turi būti reikšmė tarp %.2f ir %.2f.')
                                               % (LIGO_COEFF_MIN, LIGO_COEFF_MAX))
                existing_record = self.env['payroll.parameter.history'].search([
                    ('date_from', '=', rec.date_from),
                    ('field_name', '=', 'ligos_koeficientas'),
                    ('company_id', '=', rec.company_id.id)
                ])
                if existing_record:
                    document_defining_the_record = self.search([
                        ('record_model', '=', 'payroll.parameter.history'),
                        ('record_id', '=', existing_record.id)
                    ])
                    if document_defining_the_record:
                        doc_number = document_defining_the_record.document_number
                        if doc_number and doc_number != '-':
                            doc_number = _(' (Nr. {})').format(doc_number)
                        else:
                            doc_number = ''
                        raise exceptions.UserError(_('Šiai datai jau yra nustatytas ligos pašalpai taikomas procentas. '
                                                     'Norėdami iš naujo nustatyti ligos pašalpai taikomą procentą - '
                                                     'atšaukite įsakymą nustatantį ligos procentą'
                                                     '{}.').format(doc_number))

    @api.multi
    def check_workflow_constraints(self):
        """
        Checks constraints before allowing workflow to continue
        :return: error message as str
        """
        body = super(EDocument, self).check_workflow_constraints()  # has self.ensure_one()
        template_id = self.sudo().template_id

        if template_id == self.env.ref('e_document.isakymas_del_ligos_pasalpai_taikomo_procento_template', False):
            if not self.check_ligo_koeficientage_percentage(self.float_1):
                body += _('Taikomas procentas turi būti reikšmė tarp %.2f ir %.2f.') % (LIGO_COEFF_MIN, LIGO_COEFF_MAX)

        return body

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref('e_document.isakymas_del_ligos_pasalpai_taikomo_procento_template', False)
        document = self.cancel_id
        if document and document.sudo().template_id == template:
            record_model = document.record_model
            record_id = document.record_id
            if record_model == 'payroll.parameter.history' and record_id:
                record = self.env['payroll.parameter.history'].search([('id', '=', record_id)])
            if not record:
                record = self.env['payroll.parameter.history'].search([
                    ('date_from', '=', self.date_from),
                    ('field_name', '=', 'ligos_koeficientas'),
                    ('value', '=', self.float_1 / 100.0),  # P3:DivOK
                    ('company_id', '=', self.company_id.id)
                ])
            if not record:
                raise exceptions.UserError(_('Nerastas susijęs parametras'))
            record.unlink()
        else:
            super(EDocument, self).execute_cancel_workflow()


EDocument()
