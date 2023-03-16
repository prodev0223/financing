# -*- coding: utf-8 -*-
from collections import OrderedDict
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _

from six import iteritems
from odoo.addons.l10n_lt_payroll.model.darbuotojai import correct_lithuanian_identification


class GPM312(models.TransientModel):
    _name = 'e.vmi.gpm312'

    def _kompanija(self):
        return self.env.user.company_id.id

    def _pradzia(self):
        return (datetime.now() + relativedelta(years=-1, month=1, day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        return (datetime.now() + relativedelta(years=-1, month=12, day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        if 'failas' in self._context.keys():
            return self._context['failas']
        else:
            return ''

    def failo_pavadinimas(self):
        return 'GPM312.ffdata'

    @api.multi
    def get_errors(self):
        if 'errors' in self._context.keys():
            return self._context['errors']
        else:
            return ''

    kompanija = fields.Many2one('res.company', string='Kompanija', default=_kompanija, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    errors = fields.Text(string='Klaidos', readonly=True, default=get_errors)
    corrections_exist = fields.Boolean(string='Yra korekcijų', compute='_compute_corrections_exist')

    @api.multi
    @api.depends('data_nuo', 'data_iki')
    def _compute_corrections_exist(self):
        for rec in self:
            if rec.data_nuo and rec.data_iki:
                if self.env['fr.0573.report'].search([
                    ('date', '>=', rec.data_nuo), ('date', '<=', rec.data_iki), ('correction', '=', True)
                ], count=True):
                    rec.corrections_exist = True

    @api.onchange('data_nuo', 'data_iki')
    def set_dates(self):
        if self.data_nuo:
            data_nuo_dt = datetime.strptime(self.data_nuo, tools.DEFAULT_SERVER_DATE_FORMAT)
            self.data_nuo = (data_nuo_dt + relativedelta(year=data_nuo_dt.year, month=1, day=1)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)
            self.data_iki = (data_nuo_dt + relativedelta(year=data_nuo_dt.year, month=12, day=31)).strftime(
                tools.DEFAULT_SERVER_DATE_FORMAT)

    def open_report(self):
        data = self.get_full_data()
        self.env['gpm312.report'].refresh_report(data)
        action = self.env.ref('e_ataskaitos.action_gpm312_report')
        return action.read()[0]

    @api.model
    def fit_data(self, rec):
        if rec['identification_code'] and len(rec['identification_code']) > 20:
            rec['identification_code'] = rec['identification_code'][:20]
        if rec['full_name'] and len(rec['full_name']) > 34:
            rec['full_name'] = rec['full_name'][:34]
        if rec['foreign_address'] and len(rec['foreign_address']) > 67:
            rec['foreign_address'] = rec['foreign_address'][:67]
        return rec

    @api.model
    def float_to_string(self, value):
        return str(round(value, 2)).replace('.', ',') if isinstance(value, float) else str(value)

    @api.model
    def get_country_code(self, partner, a_klase_kodas, is_resident=True):
        if a_klase_kodas in ['26', '62']:  # TODO
            country_code = partner.country_id.code or ''
        else:
            country_code = ''
        if country_code == 'LT':
            country_code = ''
        if not is_resident:
            country_code = partner.country_id.code or ''
            if country_code == 'LT':
                partner_employees = partner.with_context(active_test=False).employee_ids
                for employee in partner_employees:
                    if employee.nationality_id and employee.nationality_id.code != 'LT':
                        country_code = employee.nationality_id.code
                        break
        return country_code

    @api.model
    def get_form_header_values(self, company_id, date_from):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        company = self.env['res.company'].browse(company_id)
        period_year = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT).year
        pildymo_data = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        return {'num_of_pages': '%(num_of_pages)s',
                'pildymo_data': pildymo_data,
                'company_id': company.company_registry,
                'company_name': (company.name or str()).upper().replace('&', '&amp;'),
                'period_year': period_year,
                'total_amount': '%(total_amount)s',
                'gpm_amount': '%(total_gpm_amount)s',
                'gpm_paid_by_employer_amound': '%(total_gpm_person_payed_amount)s',
                'overseas_paid_gpm_amount': '%(total_gpm_foreign_payed_amount)s',
                'group_GPM312L': '%(group_GPM312L)s',
                'group_GPM312U': '%(group_GPM312U)s',
                }

    @api.model
    def get_partner_id_data(self, partner, prefer_identification_id=False):
        partner_code_mapping = {
            'mmak': 1,
            'vlm': 2,
            'PVMmk': 3,
            'ivvpn': 4,
            'atpdsin': 1,
        }

        partner_id = ''
        partner_id_type = 3
        is_correct_identification_id = correct_lithuanian_identification(partner.employee_ids and partner.employee_ids[0].identification_id or '')

        if prefer_identification_id and partner.employee_ids:
            identification = partner.employee_ids[0].identification_id.strip() if is_correct_identification_id else ''
            if identification:
                return identification, 1

        if partner.kodas:
            partner_id = partner.kodas
            partner_id_type = 1
            if partner.partner_code_type:
                partner_id_type = partner_code_mapping[partner.partner_code_type]
        elif partner.vat:
            partner_id = partner.vat
            partner_id_type = 3
        elif partner.employee_ids and partner.employee_ids[0]:
            partner_id = partner.employee_ids[0].identification_id.strip() if is_correct_identification_id else ''
            partner_id_type = 1
        else:
            employees = self.env['hr.employee'].search([
                ('address_home_id.id', '=', partner.id),
                '|',
                ('active', '=', True),
                ('active', '=', False),
            ])
            for employee in employees:
                is_correct_identification_id = correct_lithuanian_identification(employee.identification_id or '')
                if is_correct_identification_id:
                    partner_id = employee.identification_id.strip() if is_correct_identification_id else ''
                    partner_id_type = 1
                    break
        if not partner_id:
            partner_id = ''
            partner_id_type = ''

        return partner_id, partner_id_type

    @api.model
    def get_b_class_data(self, foreign_residents=False):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        if not self.env.context.get('do_not_refresh_fr0573'):
            self.env['fr.0573.report'].refresh_report(self.data_nuo, self.data_iki, is_annual_declaration=True)
        data = {}
        operator = '=' if not foreign_residents else '!='
        report_values = self.env['fr.0573.report'].search([
            ('partner_id.rezidentas', operator, 'rezidentas'),
            ('date', '>=', self.data_nuo),
            ('date', '<=', self.data_iki),
            ('b_klase_kodas_id', '!=', False)
        ])
        for rep_val in report_values:
            partner = rep_val.partner_id
            rezidentas = partner.rezidentas == 'rezidentas'
            b_klase_record = rep_val.b_klase_kodas_id
            b_klase_kodas = b_klase_record.code
            country_code = self.get_country_code(partner, b_klase_kodas, is_resident=rezidentas)
            partner_id, partner_id_type = self.get_partner_id_data(partner)
            partner_address = partner.with_context(skip_name=True).contact_address_line or ''
            partner_employees = partner.with_context(active_test=False).employee_ids
            dob = ''
            if not rezidentas:
                for employee in partner_employees:
                    if employee.birthday:
                        dob = employee.birthday
                        break
            report_value_date = rep_val.date
            is_employer_payout = rep_val.employer_payout
            if not is_employer_payout:
                # Check if partner is employee
                is_employer_payout = partner.sudo().employee_ids.with_context(date=report_value_date).appointment_id

            update_values = {
                'identification_code': partner_id,
                'identification_type': partner_id_type,
                'full_name': partner.name,
                'class': 'B',
                'type': b_klase_kodas,
                'natura': '',  # B class always blank
                'employer_payout': 'D' if is_employer_payout else '',
                'full_amount': rep_val.amount_bruto,
                'gpm_percentage': 0.0,  # B class always 0
                'gpm_amount': 0.0,  # B class always 0
                'gpm_for_responsible_person_amount': rep_val.gpm_for_responsible_person_amount,

                # ---Lithuanian residents only---
                'foreign_country_code': rep_val.foreign_country_id.code if rep_val.foreign_country_id else country_code,
                'foreign_payed_gpm_amount': rep_val.foreign_paid_gpm_amount,

                # ---Foreign residents only---
                'dob': dob,
                'code': '',  # No data
                'country_code': country_code,
                'foreign_address': partner_address,
                'partner_name': partner.display_name,
                'document_type': False,
                'date': report_value_date,
                'resident': not foreign_residents,
            }
            update_values = self.fit_data(update_values)
            data_key = (partner.id, rep_val.b_klase_kodas_id.id, 'B', '')
            existing_values = data.get(data_key, {})
            for k in update_values.keys():
                if k in ['full_amount', 'gpm_amount', 'gpm_for_responsible_person_amount', 'foreign_payed_gpm_amount']:
                    existing_values[k] = existing_values.get(k, 0.0) + update_values[k]
                else:
                    existing_values[k] = update_values[k]
            data[data_key] = existing_values
        return data

    @api.model
    def get_b_class_data_from_aml(self, foreign_residents=False):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        data = {}
        QUERY = '''
        SELECT 
            transaction.date,
            transaction.partner_id,
            main_aml.b_klase_kodas_id,
            (apr.amount - COALESCE(main_inv.amount_tax, 0)) as amount_paid,
            main_aml.ref as account_move_line_ref,
            partneris.rezidentas as rezidentas
        FROM account_move_line transaction
            INNER JOIN account_partial_reconcile apr on apr.debit_move_id = transaction.id
            INNER JOIN account_move_line main_aml on apr.credit_move_id = main_aml.id
            LEFT JOIN account_invoice main_inv on main_aml.invoice_id = main_inv.id
            INNER JOIN res_partner partneris on transaction.partner_id = partneris.id
        WHERE transaction.date >= %s and transaction.date <= %s 
            AND main_aml.b_klase_kodas_id IS NOT NULL
        '''

        REFUND_QUERY = '''
        SELECT 
            transaction.date,
            transaction.partner_id,
            main_aml.b_klase_kodas_id,
            (apr.amount - COALESCE(main_inv.amount_tax, 0)) as amount_paid,
            main_aml.ref as account_move_line_ref,
            partneris.rezidentas as rezidentas
        FROM account_move_line transaction
            INNER JOIN account_partial_reconcile apr on apr.credit_move_id = transaction.id
            INNER JOIN account_move_line main_aml on apr.debit_move_id = main_aml.id
            LEFT JOIN account_invoice main_inv on main_aml.invoice_id = main_inv.id
            INNER JOIN res_partner partneris on transaction.partner_id = partneris.id
        WHERE transaction.date >= %s and transaction.date <= %s 
            AND main_aml.b_klase_kodas_id IS NOT NULL
        '''

        if foreign_residents:
            QUERY += ''' AND rezidentas != 'rezidentas' '''
            REFUND_QUERY += ''' AND rezidentas != 'rezidentas' '''
        else:
            QUERY += ''' AND rezidentas = 'rezidentas' '''
            REFUND_QUERY += ''' AND rezidentas = 'rezidentas' '''

        self._cr.execute(QUERY, (self.data_nuo, self.data_iki))
        all_data = self._cr.dictfetchall()
        for el in all_data:
            key = (el['partner_id'], el['b_klase_kodas_id'], 'B', '')
            amount = el['amount_paid']
            if key not in data:
                partner = self.env['res.partner'].browse(el['partner_id'])
                partner_id, partner_id_type = self.get_partner_id_data(partner)
                # name = el['account_move_line_ref']
                b_klase_record = self.env['b.klase.kodas'].browse(el['b_klase_kodas_id'])
                b_klase_kodas = b_klase_record.code
                country_code = partner.country_id.code or ''
                if country_code == 'LT' and not foreign_residents:
                    country_code = ''
                partner_address = partner.with_context(skip_name=True).contact_address_line or ''

                report_value_date = el['date']

                # Check if partner is employee
                is_employer_payout = partner.sudo().employee_ids.with_context(date=report_value_date).appointment_id

                vals = {
                    'identification_code': partner_id,
                    'identification_type': partner_id_type,
                    'full_name': partner.name,
                    'class': 'B',
                    'type': b_klase_kodas,
                    'natura': '',  # B klase always blank
                    'employer_payout': 'D' if is_employer_payout else '',
                    'full_amount': amount,
                    'gpm_percentage': 0.0,  # B klase always 0
                    'gpm_amount': '',  # B klase always blank
                    'gpm_for_responsible_person_amount': 0.0,

                    # ---Lithuanian residents only---
                    'foreign_country_code': country_code,
                    'foreign_payed_gpm_amount': 0.0,

                    # ---Foreign residents only---
                    'dob': '',  # No data
                    'code': '',  # No data
                    'country_code': country_code,
                    'foreign_address': partner_address,
                    'partner_name': partner.display_name,

                    'document_type': False,
                    'date': report_value_date,
                    'resident': not foreign_residents,
                }
                vals = self.fit_data(vals)
                data[key] = vals
            else:
                data[key]['full_amount'] += amount

        self._cr.execute(REFUND_QUERY, (self.data_nuo, self.data_iki))
        refund_data = self._cr.dictfetchall()

        for el in refund_data:
            key = (el['partner_id'], el['b_klase_kodas_id'], 'B', '')
            amount = el['amount_paid'] * -1
            if key not in data or tools.float_compare(amount, 0.0, precision_digits=2) > 0:
                continue
            else:
                data[key]['full_amount'] += amount

        good_data = dict()
        for key, dict_data in iteritems(data):
            full_amount = data[key].get('full_amount', False)
            if tools.float_compare(full_amount, 0.0, precision_digits=2) > 0:
                good_data[key] = dict_data

        return good_data

    @api.model
    def get_a_class_data(self, foreign_residents=False):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        if not self.env.context.get('do_not_refresh_fr0573'):
            self.env['fr.0573.report'].refresh_report(self.data_nuo, self.data_iki, is_annual_declaration=True)
        data = {}
        operator = '=' if not foreign_residents else '!='
        main_a_klase_record = self.env.ref('l10n_lt_payroll.a_klase_kodas_1')
        report_values = self.env['fr.0573.report'].search([
            ('partner_id.rezidentas', operator, 'rezidentas'),
            ('date', '>=', self.data_nuo),
            ('date', '<=', self.data_iki),
            ('a_klase_kodas_id', '!=', False)
        ])
        for rep_val in report_values:
            partner = rep_val.partner_id
            rezidentas = partner.rezidentas == 'rezidentas'
            a_klase_record = rep_val.a_klase_kodas_id
            if a_klase_record == main_a_klase_record and rep_val.date < '2019-01-01' and datetime.utcnow().strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT) >= '2019-01-01':
                a_klase_record = main_a_klase_record
            a_klase_kodas = a_klase_record.code
            country_code = self.get_country_code(partner, a_klase_kodas, is_resident=rezidentas)
            partner_id, partner_id_type = self.get_partner_id_data(partner, prefer_identification_id=True)
            tarifas = a_klase_record.gpm_proc
            partner_address = partner.with_context(skip_name=True).contact_address_line or ''
            partner_employees = partner.with_context(active_test=False).employee_ids
            dob = ''
            if not rezidentas:
                for employee in partner_employees:
                    if employee.birthday:
                        dob = employee.birthday
                        break
            gpm_for_responsible_person_amount = rep_val.gpm_for_responsible_person_amount
            if rep_val.document_type in ['natura', 'own_expense'] and \
                    tools.float_is_zero(gpm_for_responsible_person_amount, precision_digits=2):
                gpm_for_responsible_person_amount = rep_val.amount_tax

            update_values = {
                'identification_code': partner_id,
                'identification_type': partner_id_type,
                'full_name': partner.name,
                'class': 'A',
                'type': a_klase_kodas,
                'natura': 'N' if rep_val.document_type == 'natura' else '',
                'employer_payout': 'D' if rep_val.employer_payout else '',
                'full_amount': rep_val.amount_bruto,
                'gpm_percentage': tarifas,
                'gpm_amount': rep_val.amount_tax,
                'gpm_for_responsible_person_amount': gpm_for_responsible_person_amount,

                # ---Lithuanian residents only---
                'foreign_country_code': rep_val.foreign_country_id.code if rep_val.foreign_country_id else country_code,
                'foreign_payed_gpm_amount': rep_val.foreign_paid_gpm_amount,

                # ---Foreign residents only---
                'dob': dob or '',
                'code': '',  # No data
                'country_code': country_code,
                'foreign_address': partner_address,
                'partner_name': partner.display_name,

                'document_type': rep_val.document_type,

                'date': rep_val.date,
                'resident': not foreign_residents,
            }
            update_values = self.fit_data(update_values)
            data_key = (partner.id, rep_val.a_klase_kodas_id.id, 'A', 'N' if rep_val.document_type == 'natura' else '')
            existing_values = data.get(data_key, {})
            for k in update_values.keys():
                if k in ['full_amount', 'gpm_amount', 'gpm_for_responsible_person_amount', 'foreign_payed_gpm_amount']:
                    existing_values[k] = existing_values.get(k, 0.0) + update_values[k]
                else:
                    existing_values[k] = update_values[k]
            data[data_key] = existing_values
        return data

    @api.model
    def get_full_data(self, foreign_residents=False):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))
        data = OrderedDict()
        data.update(self.get_a_class_data(foreign_residents))
        data.update(self.get_b_class_data_from_aml(foreign_residents))
        data.update(self.get_b_class_data(foreign_residents))
        return data

    @api.multi
    def form_gpm312(self):
        failas, errors = self._form_gpm312()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.gpm312',
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_gpm312_download').id,
            'context': {'failas': failas, 'errors': errors},
        }

    @api.multi
    def _form_gpm312(self):
        FORM = ''

        GROUP_GPM312L = \
            '''<Group Name="Priedas_GPM312L">
                                <ListPages>
                                    %(gpm312l_pages)s
                                </ListPages>
                            </Group>'''

        GROUP_GPM312U = \
            '''<Group Name="Priedas_GPM312U">
                                <ListPages>
                                    %(gpm312u_pages)s
                                </ListPages>
                            </Group>'''

        FORM_HEADER = \
            '''<?xml version="1.0" encoding="UTF-8"?>
            <FFData Version="1" CreatedByApp="robo" CreatedByLogin="robo" CreatedOn="%(pildymo_data)s">
                <Form FormDefId="{DD0F88DD-A858-4595-AF2F-3643D0069A39}">
                    <DocumentPages>
                        <Group Name="Visa forma">
                            <ListPages>
                                <ListPage>GPM312</ListPage>
                            </ListPages>
                            %(group_GPM312L)s
                            %(group_GPM312U)s
                        </Group>
                    </DocumentPages>
                    <Pages Count="%(num_of_pages)s">
                        <Page PageDefName="GPM312" PageNumber="1">
                            <Fields Count="9">
                                <Field Name="B_MM_ID">%(company_id)s</Field>
                                <Field Name="B_MM_Pavad">%(company_name)s</Field>
                                <Field Name="B_ML_Metai">%(period_year)s</Field>
                                <Field Name="G4">%(total_amount)s</Field>
                                <Field Name="G5">%(gpm_amount)s</Field>
                                <Field Name="G6">%(gpm_paid_by_employer_amound)s</Field>
                                <Field Name="G7">%(overseas_paid_gpm_amount)s</Field>
                                <Field Name="B_FormNr"></Field>
                                <Field Name="B_FormVerNr"></Field>
                            </Fields>
                        </Page>'''

        LITHUANIAN_RESIDENTS_PAGE_HEADER = '''
            <Page PageDefName="GPM312L" PageNumber="%(current_page_number)s">
                <Fields Count="135">'''

        LITHUANIAN_RESIDENT_FIELDS = '''
                    <Field Name="L1-%(page_rec_number)s">%(identification_code)s</Field>
                    <Field Name="L2-%(page_rec_number)s">%(identification_type)s</Field>
                    <Field Name="L3-%(page_rec_number)s">%(full_name)s</Field>
                    <Field Name="L4-%(page_rec_number)s">%(class)s</Field>
                    <Field Name="L5-%(page_rec_number)s">%(type)s</Field>
                    <Field Name="L6-%(page_rec_number)s">%(natura)s</Field>
                    <Field Name="L7-%(page_rec_number)s">%(employer_payout)s</Field>
                    <Field Name="L8-%(page_rec_number)s">%(full_amount)s</Field>
                    <Field Name="L9-%(page_rec_number)s">%(gpm_percentage)s</Field>
                    <Field Name="L10-%(page_rec_number)s">%(gpm_amount)s</Field>
                    <Field Name="L11-%(page_rec_number)s">%(gpm_for_responsible_person_amount)s</Field>
                    <Field Name="L12-%(page_rec_number)s">%(foreign_country_code)s</Field>
                    <Field Name="L13-%(page_rec_number)s">%(foreign_payed_gpm_amount)s</Field>'''

        LITHUANIAN_RESIDENTS_PAGE_FOOTER = '''
                    <Field Name="B_MM_ID"></Field>
                    <Field Name="B_ML_Metai">%(period_year)s</Field>
                    <Field Name="B_FormNr"></Field>
                    <Field Name="B_FormVerNr"></Field>
                    <Field Name="LapoNr">%(current_lithuanian_residents_page_number)s</Field>
                </Fields>
            </Page>'''

        FOREIGN_RESIDENTS_PAGE_HEADER = '''
            <Page PageDefName="GPM312U" PageNumber="%(current_page_number)s">
                <Fields Count="80">'''

        FOREIGN_RESIDENT_FIELDS = '''
                    <Field Name="U1-%(page_rec_number)s">%(identification_code)s</Field>
                    <Field Name="U2-%(page_rec_number)s">%(identification_type)s</Field>
                    <Field Name="U3-%(page_rec_number)s">%(full_name)s</Field>
                    <Field Name="U4-%(page_rec_number)s">%(class)s</Field>
                    <Field Name="U5-%(page_rec_number)s">%(type)s</Field>
                    <Field Name="U6-%(page_rec_number)s">%(natura)s</Field>
                    <Field Name="U7-%(page_rec_number)s">%(employer_payout)s</Field>
                    <Field Name="U8-%(page_rec_number)s">%(full_amount)s</Field>
                    <Field Name="U9-%(page_rec_number)s">%(gpm_percentage)s</Field>
                    <Field Name="U10-%(page_rec_number)s">%(gpm_amount)s</Field>
                    <Field Name="U11-%(page_rec_number)s">%(gpm_for_responsible_person_amount)s</Field>
                    <Field Name="U12-%(page_rec_number)s">%(dob)s</Field>
                    <Field Name="U13-%(page_rec_number)s">%(code)s</Field>
                    <Field Name="U14-%(page_rec_number)s">%(country_code)s</Field>
                    <Field Name="U15-%(page_rec_number)s">%(foreign_address)s</Field>'''

        FOREIGN_RESIDENTS_PAGE_FOOTER = '''
                    <Field Name="B_MM_ID"></Field>
                    <Field Name="B_ML_Metai">%(period_year)s</Field>
                    <Field Name="B_FormNr"></Field>
                    <Field Name="B_FormVerNr"></Field>
                    <Field Name="LapoNr">%(current_foreign_residents_page_number)s</Field>
                </Fields>
            </Page>'''

        FORM_FOOTER = '''
        </Pages>
    </Form>
</FFData>'''

        if not self.env.user.has_group('hr.group_hr_manager'):
            raise exceptions.UserError(_('Jūs neturite pakankamai teisių'))

        errors = list()

        # ---Document settings---
        lithuanian_residents_per_page = 10
        foreign_residents_per_page = 5

        # ---Basic header sheet vals---
        header_values = self.env['e.vmi.gpm312'].get_form_header_values(self.kompanija.id, self.data_nuo)
        period_year = header_values['period_year']
        FORM += FORM_HEADER % header_values

        # ---TOTALS Calc declaration---
        total_amount = 0.0
        total_gpm_amount = 0.0
        total_gpm_person_payed_amount = 0.0
        total_gpm_foreign_payed_amount = 0.0

        num_of_pages = 1
        page_rec_number = 0
        page_num = 0
        lithuanian_resident_data = self.get_full_data()
        group_lithuanain_residents = ''
        if len(lithuanian_resident_data) > 0:
            group_lithuanain_residents = GROUP_GPM312L
        group_lithuanian_list_pages = ''
        for key, values in iteritems(lithuanian_resident_data):
            page_rec_number += 1
            if page_rec_number == 1:
                group_lithuanian_list_pages += '''<ListPage>GPM312L</ListPage>\n'''
                num_of_pages += 1
                PAGE_HEADER = LITHUANIAN_RESIDENTS_PAGE_HEADER % {'current_page_number': num_of_pages}
                FORM += PAGE_HEADER
                page_num += 1

            gpm_amount = gpm_for_responsible_person_amount = values['gpm_amount']
            report_code_type = values.get('type')
            is_a_class = values.get('class') == 'A'
            if values['natura'] != 'N':
                gpm_for_responsible_person_amount = values.get('gpm_for_responsible_person_amount', '') or ''
            if is_a_class:
                if tools.float_is_zero(gpm_amount, precision_digits=2) and values['document_type'] != 'payslip':
                    gpm_amount = ''
                if report_code_type in [70, '70']:
                    gpm_for_responsible_person_amount = ''

            is_correct_identification_id = correct_lithuanian_identification(values.get('identification_code') or '')
            vals = {
                'page_rec_number': page_rec_number,
                'identification_code': values.get('identification_code').strip() if is_correct_identification_id else '',
                'identification_type': values['identification_type'],
                'full_name': (values.get('full_name') or '').replace('&', '&amp;'),
                'class': values['class'],
                'type': report_code_type,
                'natura': values['natura'],
                'employer_payout': values['employer_payout'],
                'full_amount': self.float_to_string(values['full_amount']),
                'gpm_percentage': self.float_to_string(values['gpm_percentage']),
                'gpm_amount': self.float_to_string(gpm_amount),
                'gpm_for_responsible_person_amount': self.float_to_string(gpm_for_responsible_person_amount),
                'foreign_country_code': values['foreign_country_code'],
                'foreign_payed_gpm_amount': self.float_to_string(values['foreign_payed_gpm_amount']),
                'dob': values['dob'],
                'code': values['code'],
                'country_code': values['country_code'],
                'foreign_address': values['foreign_address']
            }
            total_amount += values['full_amount']
            total_gpm_amount += values['gpm_amount'] if values['gpm_amount'] != '' else 0.0
            total_gpm_person_payed_amount += values['gpm_for_responsible_person_amount']
            total_gpm_foreign_payed_amount += values['foreign_payed_gpm_amount']
            if not is_correct_identification_id:
                errors.append({
                    'page': num_of_pages - 1,
                    'page_record': page_rec_number,
                    'partner_name': values['partner_name'],
                })
            FORM += LITHUANIAN_RESIDENT_FIELDS % vals

            if page_rec_number >= lithuanian_residents_per_page:
                page_rec_number = 0
                PAGE_FOOTER = LITHUANIAN_RESIDENTS_PAGE_FOOTER % {'current_lithuanian_residents_page_number': page_num,
                                                                  'period_year': period_year}
                FORM += PAGE_FOOTER

        if page_rec_number < lithuanian_residents_per_page and page_rec_number > 0:  # DO NOT DO ANYTHING, THIS IS USED TO WRITE BLANK DATA TO FILL PAGE
            if page_num == 0:
                PAGE_HEADER = LITHUANIAN_RESIDENTS_PAGE_HEADER % {'current_page_number': num_of_pages}
                FORM += PAGE_HEADER
                page_num += 1

            for i in range(page_rec_number, lithuanian_residents_per_page):
                page_rec_number += 1
                vals = {
                    'page_rec_number': page_rec_number,
                    'identification_code': '',
                    'identification_type': '',
                    'full_name': '',
                    'class': '',
                    'type': '',
                    'natura': '',
                    'employer_payout': '',
                    'full_amount': '',
                    'gpm_percentage': '',
                    'gpm_amount': '',
                    'gpm_for_responsible_person_amount': '',
                    'foreign_country_code': '',
                    'foreign_payed_gpm_amount': ''
                }
                FORM += LITHUANIAN_RESIDENT_FIELDS % vals
                if page_rec_number >= lithuanian_residents_per_page:
                    page_rec_number = 0
                    PAGE_FOOTER = LITHUANIAN_RESIDENTS_PAGE_FOOTER % {
                        'current_lithuanian_residents_page_number': page_num, 'period_year': period_year}
                    FORM += PAGE_FOOTER

        page_rec_number = 0
        page_num = 0
        foreign_resident_data = self.with_context(do_not_refresh_fr0573=True).get_full_data(foreign_residents=True)
        group_foreign_residents = ''
        if len(foreign_resident_data) > 0:
            group_foreign_residents = GROUP_GPM312U
        group_foreign_list_pages = ''
        for key, values in iteritems(foreign_resident_data):
            page_rec_number += 1
            if page_rec_number == 1:
                group_foreign_list_pages += '''<ListPage>GPM312U</ListPage>\n'''
                num_of_pages += 1
                PAGE_HEADER = FOREIGN_RESIDENTS_PAGE_HEADER % {'current_page_number': num_of_pages}
                FORM += PAGE_HEADER
                page_num += 1

            gpm_amount = values['gpm_amount']
            is_a_class = values.get('class') == 'A'
            report_code_type = values.get('type')
            gpm_for_responsible_person_amount = values.get('gpm_for_responsible_person_amount', '')
            if is_a_class:
                if tools.float_is_zero(gpm_amount, precision_digits=2) and values['document_type'] != 'payslip':
                    gpm_amount = ''
                if report_code_type in [70, '70']:
                    gpm_for_responsible_person_amount = ''

            is_correct_identification_id = correct_lithuanian_identification(values.get('identification_code') or '')
            vals = {
                'page_rec_number': page_rec_number,
                'identification_code': values.get('identification_code').strip() if is_correct_identification_id else '',
                'identification_type': values['identification_type'],
                'full_name': (values.get('full_name') or '').replace('&', '&amp;'),
                'class': values['class'],
                'type': values['type'],
                'natura': values['natura'],
                'employer_payout': values['employer_payout'],
                'full_amount': self.float_to_string(values['full_amount']),
                'gpm_percentage': self.float_to_string(values['gpm_percentage']),
                'gpm_amount': self.float_to_string(gpm_amount),
                'gpm_for_responsible_person_amount': self.float_to_string(gpm_for_responsible_person_amount),
                'dob': values['dob'],
                'code': values['code'],
                'country_code': values['country_code'],
                'foreign_address': values['foreign_address']
            }
            total_amount += values['full_amount']
            total_gpm_amount += values['gpm_amount'] if values['gpm_amount'] != '' else 0.0
            total_gpm_person_payed_amount += values['gpm_for_responsible_person_amount']
            total_gpm_foreign_payed_amount += values['foreign_payed_gpm_amount']
            FORM += FOREIGN_RESIDENT_FIELDS % vals
            # if values['identification_code'] == '': GPM312U form allows for empty U1 / U2 fields
            #     errors.append({
            #         'page': num_of_pages-1,
            #         'page_record': page_rec_number,
            #         'partner_name': values['partner_name'],
            #     })
            if page_rec_number >= foreign_residents_per_page:
                page_rec_number = 0
                PAGE_FOOTER = FOREIGN_RESIDENTS_PAGE_FOOTER % {'current_foreign_residents_page_number': page_num,
                                                               'period_year': period_year}
                FORM += PAGE_FOOTER

        if page_rec_number < foreign_residents_per_page and page_rec_number > 0:  # DO NOT DO ANYTHING, THIS IS USED TO WRITE BLANK DATA TO FILL PAGE
            if page_num == 0:
                PAGE_HEADER = FOREIGN_RESIDENTS_PAGE_HEADER % {'current_page_number': num_of_pages}
                FORM += PAGE_HEADER
                page_num += 1

            for i in range(page_rec_number, foreign_residents_per_page):
                page_rec_number += 1
                vals = {
                    'page_rec_number': page_rec_number,
                    'identification_code': '',
                    'identification_type': '',
                    'full_name': '',
                    'class': '',
                    'type': '',
                    'natura': '',
                    'employer_payout': '',
                    'full_amount': '',
                    'gpm_percentage': '',
                    'gpm_amount': '',
                    'gpm_for_responsible_person_amount': '',
                    'dob': '',
                    'code': '',
                    'country_code': '',
                    'foreign_address': ''
                }
                FORM += FOREIGN_RESIDENT_FIELDS % vals
                if page_rec_number >= foreign_residents_per_page:
                    page_rec_number = 0
                    PAGE_FOOTER = FOREIGN_RESIDENTS_PAGE_FOOTER % {
                        'current_foreign_residents_page_number': page_num,
                        'period_year': period_year}
                    FORM += PAGE_FOOTER

        if len(group_lithuanain_residents) > 0 and len(group_lithuanian_list_pages) > 0:
            group_lithuanain_residents = group_lithuanain_residents % {'gpm312l_pages': group_lithuanian_list_pages}
        if len(group_foreign_residents) > 0 and len(group_foreign_list_pages) > 0:
            group_foreign_residents = group_foreign_residents % {'gpm312u_pages': group_foreign_list_pages}

        # ---Write total values, num of pages and generate---
        FORM = FORM % ({'total_amount': self.float_to_string(total_amount),
                        'total_gpm_amount': self.float_to_string(total_gpm_amount),
                        'total_gpm_person_payed_amount': self.float_to_string(total_gpm_person_payed_amount),
                        'total_gpm_foreign_payed_amount': self.float_to_string(total_gpm_foreign_payed_amount),
                        'num_of_pages': num_of_pages,
                        'group_GPM312L': group_lithuanain_residents,
                        'group_GPM312U': group_foreign_residents,
                        })
        failas = FORM + FORM_FOOTER
        if self._context.get('eds') and not errors:
            try:
                self.env.user.upload_eds_file(failas.encode('utf8').encode('base64'), 'GPM312.ffdata', self.data_nuo)
            except:
                self.sudo().env.user.upload_eds_file(failas.encode('utf8').encode('base64'), 'GPM312.ffdata',
                                                     self.data_nuo)

        string = ''
        for error in errors:
            string += _('Puslapyje %s, %s įraše nebuvo įmanoma nustatyti partnerio %s kodo\n') % (
                error['page'], error['page_record'], error['partner_name'])

        return failas.encode('utf8').encode('base64'), string

    @api.multi
    def import_data(self):
        action = self.env.ref('e_ataskaitos.action_open_fr0573_data_import').read()[0]
        return action


GPM312()
