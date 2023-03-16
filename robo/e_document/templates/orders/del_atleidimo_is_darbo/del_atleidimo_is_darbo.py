# -*- coding: utf-8 -*-

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import _, api, exceptions, fields, models, tools

TEMPLATE = 'e_document.isakymas_del_atleidimo_is_darbo_template'


class EDocument(models.Model):
    _inherit = 'e.document'

    request_field_type = fields.Selection([
        ('request', 'Prašymas'),
        ('agreement', 'Susitarimas'),
        ('none', 'none')
    ], string='Prašymo laukelio tipas', compute='_compute_request_field_type')
    possible_negative_holiday_deduction = fields.Boolean(compute='_compute_possible_negative_holiday_deduction')
    is_severance_pay_needed = fields.Boolean(compute='_compute_is_severance_pay_needed')
    allow_deducting_overused_holidays_from_salary = fields.Boolean(
        compute='_compute_allow_deducting_overused_holidays_from_salary'
    )

    @api.multi
    @api.depends('template_id', 'dk_nutraukimo_straipsnis', 'dk_nutraukimo_straipsnis.request')
    def _compute_request_field_type(self):
        for rec in self:
            if rec.template_id.id == self.env.ref(TEMPLATE).id:
                article = rec.dk_nutraukimo_straipsnis
                is_request = article and article.request
                if not is_request:
                    rec.request_field_type = 'none'
                elif is_request and 'susitar' in article.straipsnio_pav.lower():
                    rec.request_field_type = 'agreement'
                else:
                    rec.request_field_type = 'request'
            else:
                rec.request_field_type = 'request'

    @api.multi
    @api.depends('template_id', 'employee_id2', 'dk_nutraukimo_straipsnis', 'date_1')
    def _compute_allow_deducting_overused_holidays_from_salary(self):
        """ Checks if the document should allow deducting overused holidays from employee's salary """
        template = self.env.ref(TEMPLATE, False)
        applicable_article_numbers = ['55', '58']
        today = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self.filtered(lambda x: x.template_id == template):
            # Check if the document has the correct article
            has_applicable_article = rec.dk_nutraukimo_straipsnis.straipsnis in applicable_article_numbers
            if not has_applicable_article:
                continue

            # Check remaining leaves are negative
            date = rec.date_1 or today
            remaining_leaves = rec.employee_id2.with_context(date=date).remaining_leaves
            has_negative_holidays = tools.float_compare(remaining_leaves, 0.0, precision_digits=2) < 0
            if not has_negative_holidays:
                continue

            rec.allow_deducting_overused_holidays_from_salary = has_negative_holidays

    @api.multi
    def isakymas_del_atleidimo_is_darbo_workflow(self):
        self.ensure_one()
        contracts = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id2.id),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', self.date_1),
        ])
        if not contracts:
            raise exceptions.UserError(_('Nerasta darbuotojo {} sutartis, kuri galėtų būti nutraukta').format(self.employee_id2.name))
        for contract in contracts:
            straipsnis = self.dk_nutraukimo_straipsnis
            contract.end_contract(self.date_1,
                                  teises_akto_straipsnis=straipsnis.straipsnis,
                                  teises_akto_straipsnio_dalis=straipsnis.dalis,
                                  teises_akto_straipsnio_dalies_punktas=straipsnis.punktas,
                                  priezastis='atleidimas iš darbo (pagal darbo sutartį)',
                                  priezasties_kodas='02',
                                  priezasties_patikslinimo_kodas='K01',
                                  priezasties_patikslinimas='Darbo kodeksas'
                                  )
            if self.bool_1 and self.allow_deducting_overused_holidays_from_salary:
                contract.create_deduction_for_overused_holidays_for_ending_contract()

            self.inform_about_creation(contract, reason='automatiškai pakeistas')
        self.write({
            'record_model': 'hr.contract',
            'record_ids': self.format_record_ids(contracts.ids),
            'record_id': contracts.id if len(contracts) == 1 else False,
        })
        self.employee_id2.with_context(
            document_date=self.date_document
        ).inform_accountant_about_work_relation_end_with_delegate_or_department_manager()

    @api.multi
    def execute_cancel_workflow(self):
        self.ensure_one()
        template = self.env.ref(TEMPLATE, False)
        document_to_cancel = self.cancel_id
        if document_to_cancel and document_to_cancel.template_id == template:
            date_dt = datetime.strptime(document_to_cancel.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day = (date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            period_line_ids = self.env['ziniarastis.period.line'].search([
                ('employee_id', '=', document_to_cancel.employee_id2.id),
                ('date_from', '<=', next_day),
                ('date_to', '>=', next_day)
            ], limit=1)
            if period_line_ids and period_line_ids[0].period_state == 'done':
                raise exceptions.ValidationError(_('Įsakymo patvirtinti negalima, nes atlyginimai jau buvo '
                                                   'paskaičiuoti. Informuokite buhalterį '
                                                   'parašydami žinutę dokumento apačioje.'))
            else:
                findir_email = self.sudo().env.user.company_id.findir.partner_id.email
                database = self._cr.dbname
                subject = 'Įsakymas dėl atleidimo iš darbo buvo atšauktas [%s]' % database
                doc_url = document_to_cancel._get_document_url()
                doc_name = '<a href=%s>%s</a>' % (doc_url, document_to_cancel.name) if doc_url else document_to_cancel.name
                message = 'Dokumentas %s buvo atšauktas. Reikia rankiniu būdu atstatyti sutarties pakeitimus. Turėjo ' \
                          'būti sukurtas ticketas.' % doc_name
                additional_overused_holiday_deduction_message = ' Taip pat turėjo būt sukurtas ir pernaudotų atostogų ' \
                                                                'dienų išskaitos įrašas. Šį įrašą taip pat reikėtų ' \
                                                                'atšaukti.'
                show_overused_holiday_message = document_to_cancel.bool_1 and \
                                                document_to_cancel.allow_deducting_overused_holidays_from_salary
                if show_overused_holiday_message:
                    message += additional_overused_holiday_deduction_message
                if findir_email:
                    self.env['script'].send_email(emails_to=[findir_email],
                                                  subject=subject,
                                                  body=message)
                try:
                    body = "Įsakymas dėl atleidimo iš darbo buvo atšauktas. Reikia atlikti pakeitimus sutarčiai " \
                           "rankiniu būdu, kad būtų atstatyta buvusi būsena."
                    if show_overused_holiday_message:
                        body += additional_overused_holiday_deduction_message
                    document_to_cancel.create_internal_ticket(subject, body)
                except Exception as exc:
                    self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)
        else:
            super(EDocument, self).execute_cancel_workflow()

    @api.one
    @api.depends('template_id', 'employee_id2', 'date_1', 'dk_nutraukimo_straipsnis')
    def _compute_possible_negative_holiday_deduction(self):
        nutraukimo_isakymas = self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template').id
        self.possible_negative_holiday_deduction = False
        if self.template_id.id == nutraukimo_isakymas and self.employee_id2 and self.date_1 and \
                self.dk_nutraukimo_straipsnis:
            remaining_leaves = self.employee_id2.with_context(date=self.date_1).remaining_leaves
            if tools.float_compare(remaining_leaves, 0.0, precision_digits=2) < 0:
                request_dk_nutraukimo_straipsniai = self.env['dk.nutraukimo.straipsniai'].search([
                    ('request', '=', True)
                ])
                if self.dk_nutraukimo_straipsnis.id in request_dk_nutraukimo_straipsniai.mapped('id'):
                    self.possible_negative_holiday_deduction = True

    @api.multi
    @api.depends('template_id', 'dk_nutraukimo_straipsnis')
    def _compute_is_severance_pay_needed(self):
        template_id = self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template').id
        article_no = ['56', '57', '59', '60', '62', '69', '95', '104']
        severance_pay_articles = self.env['dk.nutraukimo.straipsniai'].search([('straipsnis', 'in', article_no)])
        for rec in self:
            if rec.template_id.id == template_id and rec.dk_nutraukimo_straipsnis in severance_pay_articles:
                rec.is_severance_pay_needed = True

    @api.multi
    def check_workflow_constraints(self):
        """
        Checks constraints before allowing workflow to continue
        :return: error message as str
        """
        body = super(EDocument, self).check_workflow_constraints()  # has self.ensure_one()
        if self.sudo().template_id == self.env.ref(TEMPLATE, False):
            trial_period_contract_terminate_articles = [
                self.env.ref('e_document.sk_nutraukimo_straipsn_53'),
                self.env.ref('e_document.sk_nutraukimo_straipsn_57')
            ]
            if self.dk_nutraukimo_straipsnis in trial_period_contract_terminate_articles:
                appointment = self.employee_id2.with_context(date=self.date_1).appointment_id
                if appointment:
                    if not appointment.trial_date_end:
                        body += _('Negalite nutraukti darbo sutarties pagal šį straipsnį, nes darbo sutartyje '
                                  'atleidimo datai nėra nustatytas bandomasis laikotarpis')
                    elif self.date_1 > appointment.trial_date_end:
                        body += _('Nutraukiant darbo santykius pagal LR DK 36 str. - darbo santykiai privalo būti '
                                  'nutraukti prieš nustatyto bandomojo laikotarpio pabaigą. Bandomasis laikotarpis '
                                  'šiam darbuotojui baigiasi {}, o bandoma nutraukti sutartį nuo {}.').format(
                                    appointment.trial_date_end, self.date_1
                        )
            date_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            next_day = (date_dt + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            period_line_ids = self.env['ziniarastis.period.line'].search([
                ('employee_id', '=', self.employee_id2.id),
                ('date_from', '<=', next_day),
                ('date_to', '>=', next_day)
            ], limit=1)
            if period_line_ids and period_line_ids[0].period_state == 'done':
                body +=_('Įsakymo patvirtinti negalima, nes atlyginimai jau buvo paskaičiuoti. Informuokite buhalterį '
                         'parašydami žinutę dokumento apačioje.')
            other_docs = self.search([('template_id', '=', self.template_id.id),
                                      ('employee_id2', '=', self.employee_id2.id),
                                      ('record_ids', '!=', False),
                                      ('record_model', '=', 'hr.contract'),
                                      ('state', '=', 'e_signed'),
                                      ('rejected', '=', False),
                                      ])
            if other_docs:
                contracts = self.env['hr.contract'].search([
                    ('employee_id', '=', self.employee_id2.id),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>', self.date_1),
                ])
                if not contracts:
                    body += _('Nerasta darbuotojo {} sutartis, kuri galėtų būti nutraukta').format(self.employee_id2.name)
                else:
                    ids = set(i for doc in other_docs for i in doc.parse_record_ids())
                    if any(contract.id in ids for contract in contracts):
                        body += _('Jau yra pasirašytas darbuotojo {} atleidimo įsakymas, turintis įtakos tai pačiai sutarčiai. '
                                  'Pirmiausia atšaukite pasirašytą atleidimo įsakymą.').format(self.employee_id2.name)
        return body


EDocument()
