# -*- coding: utf-8 -*-
import calendar
import math
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, tools, exceptions
from odoo.tools import float_compare
from odoo.tools.translate import _
from ..e_vmi_tools import SKYRIAI


class FR0572(models.TransientModel):
    _name = 'e.vmi.fr0572'

    def _kompanija(self):
        return self.env.user.company_id.id

    # def _gpm_saskaita(self):
    #     return self.env['account.account'].search([('code', '=', '4481')])

    def _pradzia(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _pabaiga(self):
        metai = datetime.utcnow().year
        menuo = datetime.utcnow().month - 1
        if menuo == 0:
            metai -= 1
            menuo = 12
        return datetime(metai, menuo, calendar.monthrange(metai, menuo)[1]).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.multi
    def auto_load(self):
        if 'failas' in self._context.keys():
            return self._context['failas']
        else:
            return ''

    def failo_pavadinimas(self):
        return 'FR0572.ffdata'

    kompanija = fields.Many2one('res.company', string='Kompanija', default=_kompanija, required=True)
    data_nuo = fields.Date(string='Periodas nuo', default=_pradzia, required=True)
    data_iki = fields.Date(string='Periodas iki', default=_pabaiga, required=True)
    failas = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    failo_pavadinimas = fields.Char(string='Failo pavadinimas', default=failo_pavadinimas)
    skyrius = fields.Selection(SKYRIAI, string='Padalinys', default='13', required=True)

    # gpm_saskaita = fields.Many2one('account.account', string='GPM sąskaita', default=_gpm_saskaita, required=True)

    # @api.onchange('kompanija')
    # def onchange_kompanija(self):
    #     if self.kompanija:
    #         self.skyrius = self.kompanija.savivaldybe

    @api.model
    def get_avansas_amounts(self, avansas, gpm_account_ids, a_klase_kodas_id=False,
                            calculate_gpm_paid=False):
        return {'bruto': avansas.theoretical_bruto,
                'neto': avansas.suma,
                'gpm': avansas.theoretical_gpm,
                'gpm_paid': avansas.theoretical_gpm,
                'npd': 0,
                'pnpd': 0,
                'document_type': 'advance',
                'origin': avansas.name,
                }

    @api.model
    def get_payment_amounts(self, payment, gpm_account_ids, a_klase_kodas_id=False,
                            calculate_gpm_paid=False):
        return {'bruto': payment.theoretical_bruto,
                'neto': payment.amount_paid,
                'gpm': payment.theoretical_gpm,
                'gpm_paid': payment.theoretical_gpm,
                'npd': 0,
                'pnpd': 0,
                'document_type': 'holidays' if payment.type == 'holidays' else 'other',
                'origin': payment.name,
                'payment': payment
                }

    @api.model
    def get_payslip_amounts(self, payslip, gpm_account_ids, a_klase_kodas_id=False,
                            calculate_gpm_paid=False):

        def payslip_amounts_by_code(codes):
            return sum(payslip.line_ids.filtered(lambda r: r.code in codes).mapped('total'))

        gpm_line_ids = payslip.move_id.line_ids.filtered(lambda r: r.account_id.id in gpm_account_ids)
        gpm_paid = sum(gpm_line_ids.mapped(lambda r: -r.balance + r.amount_residual))

        # Get tax rates
        tax_rates = payslip.contract_id.with_context(date=payslip.date_to).get_payroll_tax_rates(['gpm_proc', 'gpm_ligos_proc'])
        gpm_percentage = tax_rates['gpm_proc'] / 100.0
        gpm_liga_percentage = tax_rates['gpm_ligos_proc'] / 100.0

        # Get payslip amounts
        other_payment_amounts = payslip_amounts_by_code(['AM'])
        advance_payment_amount = payslip_amounts_by_code(['AVN'])
        natura = payslip_amounts_by_code(['NTR'])
        employer_benefit_in_kind = payslip_amounts_by_code(['NTRD'])
        liga = payslip_amounts_by_code(['L'])
        holidays = payslip_amounts_by_code(['A'])
        total_bruto = payslip_amounts_by_code(['MEN', 'VAL'])
        total_gpm = payslip_amounts_by_code(['GPM'])
        npd = payslip_amounts_by_code(['NPD'])
        pnpd = payslip_amounts_by_code(['PNPD'])
        neto = payslip_amounts_by_code(['BENDM'])
        other_untaxed_amounts_that_are_not_declared = payslip_amounts_by_code(['KKPD'])
        total_npd = npd + pnpd

        holiday_payment_lines = payslip.payment_line_ids.filtered(lambda l: l.code == 'A')

        benefit_in_kind_employee_pays_tax = max(natura - employer_benefit_in_kind, 0.0)

        # Calculate NPD amounts
        natura_npd = liga_npd = 0.0
        if not tools.float_is_zero(total_bruto, precision_digits=2):
            natura_npd = benefit_in_kind_employee_pays_tax / total_bruto * total_npd
            liga_npd = liga / total_bruto * total_npd

        # Calculate GPM amounts
        holiday_gpm = 0.0
        for holiday_payment_line in holiday_payment_lines:
            gpm_amount = holiday_payment_line.amount_gpm
            if not tools.float_is_zero(gpm_amount, precision_digits=2):
                holiday_gpm += gpm_amount
                continue
            # If the GPM is zero, it might not have been set in payslip for some reason
            payment = holiday_payment_line.payment_id
            related_payment_lines = payment.payment_line_ids.filtered(
                lambda payment_line: payment_line.date_from == holiday_payment_line.date_from and
                                     payment_line.date_to == holiday_payment_line.date_to and
                                     tools.float_compare(holiday_payment_line.amount_paid, payment_line.amount_paid, precision_digits=2) == 0
            )
            holiday_gpm += sum(related_payment_lines.mapped('amount_gpm'))

        natura_gpm = (benefit_in_kind_employee_pays_tax - natura_npd) * gpm_percentage
        liga_gpm = max((liga - liga_npd) * gpm_liga_percentage, 0.0)

        # Calculate totals by subtracting
        payslip_gpm = total_gpm - holiday_gpm - natura_gpm - liga_gpm
        payslip_gpm_paid = gpm_paid - holiday_gpm - natura_gpm - liga_gpm
        payslip_neto = neto - other_payment_amounts + advance_payment_amount
        payslip_bruto = total_bruto - liga - natura - holidays

        # Negative value safety checks
        payslip_gpm = max(payslip_gpm, 0.0)
        payslip_gpm_paid = max(payslip_gpm_paid, 0.0)

        return {
            'bruto': payslip_bruto,
            'neto': payslip_neto,
            'gpm': payslip_gpm,
            'gpm_paid': payslip_gpm_paid,
            'npd': npd,
            'pnpd': pnpd,
            'document_type': 'payslip',
            'origin': payslip.name,
            'payslip_id': payslip.id,
            'liga': liga,
            'natura': natura,
            'liga_gpm': liga_gpm,
            'natura_npd': natura_npd,
            'liga_npd': liga_npd,
            'other_untaxed_amounts_that_are_not_declared': other_untaxed_amounts_that_are_not_declared,
        }

    @api.model
    def get_a_klase_amounts(self, move, gpm_account_ids, a_klase_kodas_id=False, calculate_gpm_paid=False):
        gpm_line_ids = move.line_ids.filtered(lambda r: r.account_id.id in gpm_account_ids)
        gpm_paid = sum(gpm_line_ids.mapped(lambda r: -r.balance + r.amount_residual))
        if not a_klase_kodas_id or a_klase_kodas_id == self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id:
            payslip = self.env['hr.payslip'].search([('move_id', '=', move.id)], limit=1)
            if payslip:
                return self.get_payslip_amounts(payslip, gpm_account_ids, a_klase_kodas_id=a_klase_kodas_id,
                                                calculate_gpm_paid=calculate_gpm_paid)
            # avansas = self.env['darbo.avansas'].search([('account_move_id', '=', move.id)], limit=1)
            # if avansas:
            #     return self.get_avansas_amounts(avansas, gpm_account_ids, a_klase_kodas_id=a_klase_kodas_id,
            #                                     calculate_gpm_paid=calculate_gpm_paid)
            payment = self.env['hr.employee.payment'].search(
                ['|', ('account_move_id', '=', move.id), ('account_move_ids', 'in', move.id)],
                limit=1)  # todo per m4nesius>
            if payment:
                return self.get_payment_amounts(payment, gpm_account_ids, a_klase_kodas_id=a_klase_kodas_id,
                                                calculate_gpm_paid=calculate_gpm_paid)
        amls = move.line_ids.filtered(lambda r: r.a_klase_kodas_id)
        if a_klase_kodas_id:
            amls = amls.filtered(lambda r: r.a_klase_kodas_id.id == a_klase_kodas_id)
        bruto = -sum(amls.mapped('balance'))
        neto = -sum(amls.filtered(lambda r: r.account_id.id not in gpm_account_ids).mapped('balance'))
        gpm = - sum(move.line_ids.filtered(lambda r: r.account_id.id in gpm_account_ids).mapped('balance'))
        npd = 0
        pnpd = 0
        return {'bruto': bruto,
                'neto': neto,
                'gpm': gpm,
                'gpm_paid': gpm_paid,
                'npd': npd,
                'pnpd': pnpd,
                'document_type': 'other',
                'origin': move.ref,
                }

    @api.multi
    def fr0572(self):  # todo natura
        company_data = self.kompanija.get_report_company_data()
        diena1 = datetime.strptime(self.data_nuo, tools.DEFAULT_SERVER_DATE_FORMAT)
        diena2 = datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT)
        if (diena2 - diena1).days + 1 < 15:
            raise exceptions.Warning(_('Per trumpas periodas.'))
        last_work_day_dt = datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT)
        while last_work_day_dt.weekday in (5, 6) or self.env['sistema.iseigines'].search(
                [('date', '=', last_work_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
            last_work_day_dt -= relativedelta(days=1)
        last_work_day = last_work_day_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        all_employees = self.env['hr.contract'].search([('date_start', '<=', last_work_day), '|',
                                                        ('date_end', '=', False),
                                                        ('date_end', '>=', last_work_day)]).mapped('employee_id')
        num_employees = 0
        for employee in all_employees:
            if not self.env['hr.holidays'].search([('employee_id', '=', employee.id),
                                                   ('date_from_date_format', '<=', last_work_day),
                                                   ('date_to_date_format', '>=', last_work_day),
                                                   ('holiday_status_id.kodas', '=', 'TA'),
                                                   ('type', '=', 'remove'),
                                                   ('state', '=', 'validate')]):
                num_employees += 1
        # sutartys_raw = self.env['a.klase'].search([('subscription.state', '=', 'running'), ('state', '=', 'done')])
        sutartys = []

        pildymo_data = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        periodo_metai = str(datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT).year)
        periodo_menuo = str(datetime.strptime(self.data_iki, tools.DEFAULT_SERVER_DATE_FORMAT).month)
        XML = '''<?xml version="1.0" encoding="UTF-8"?>
<FFData Version="1" CreatedByApp="Odoo" CreatedByLogin="Robo" CreatedOn="%(pildymo_data)s">
<Form FormDefId="{FEB97FE2-5DC6-4388-B22E-5237B3DB7F86}">
<DocumentPages>
<Group Name="Visa forma">
<ListPages>
<ListPage>FR0572</ListPage>
</ListPages>
</Group>
</DocumentPages>
<Pages Count="%(MaxPageNumber)s">
<Page PageDefName="FR0572" PageNumber="1">
<Fields Count="28">
<Field Name="B_MM_ID">%(imones_kodas)s</Field>
<Field Name="B_MM_SavKodas">%(sav_kodas)s</Field>
<Field Name="B_MM_Pavad">%(pavad)s</Field>
<Field Name="B_MM_Adresas">%(adresas)s</Field>
<Field Name="B_MM_Tel">%(telefonas)s</Field>
<Field Name="B_MM_Faksas">%(faksas)s</Field>
<Field Name="B_MM_Epastas">%(epastas)s</Field>
<Field Name="B_UzpildData">%(pildymo_data)s</Field>
<Field Name="B_ML_Metai">%(periodo_metai)s</Field>
<Field Name="B_ML_Menuo">%(periodo_menuo)s</Field>
<Field Name="E11">%(darbuotoju_sk)s</Field>
<Field Name="E12">%(priedoA_lapu_skaicius)s</Field>
<Field Name="E13">%(priedoA_eiluciu_skaicius)s</Field>
<Field Name="E16">0</Field>
<Field Name="E17">0</Field>
<Field Name="E18">%(A_ismoketu_ismoku_neatemus_mokesciu)s</Field>
<Field Name="E19">%(A_pajamu_mokestis_iki15d)s</Field>
<Field Name="E20">%(A_pajamu_mokestis_po15d)s</Field>
<Field Name="E21">%(B_ismoketu_ismoku_neatemus_mokesciu)s</Field>
<Field Name="E22">%(B_pajamu_mokestis_iki15d)s</Field>
<Field Name="E23">%(B_pajamu_mokestis_po15d)s</Field>
<Field Name="E24">%(pard_turto_ismokos_neatemus_mokesciu)s</Field>
<Field Name="E25">%(pard_turto_pajamu_mokestis_iki15d)s</Field>
<Field Name="E26">%(pard_turto_pajamu_mokestis_po15d)s</Field>
<Field Name="E27"></Field>
<Field Name="E28"></Field>
<Field Name="B_FormNr"></Field>
<Field Name="B_FormVerNr"></Field>
</Fields>
</Page>
''' % {
            'MaxPageNumber': '%(MaxPageNumber)d',
            'imones_kodas': company_data['code'],
            'sav_kodas': '',
            'pavad': company_data['name'],
            'adresas': company_data['full_address'],
            'epastas': company_data['email'],
            'telefonas': company_data['phone'],
            'faksas': company_data['fax'],
            'pildymo_data': pildymo_data,
            'periodo_metai': periodo_metai,
            'periodo_menuo': periodo_menuo,
            'darbuotoju_sk': num_employees,
            'priedoA_lapu_skaicius': str(int(math.ceil(len(sutartys) / 4))),
            'priedoA_eiluciu_skaicius': str(len(sutartys)),
            'pard_turto_ismokos_neatemus_mokesciu': '%(turto_viso_mokejimai)s',
            'pard_turto_pajamu_mokestis_iki15d': '%(turto_gpm_iki_15d)s',
            'pard_turto_pajamu_mokestis_po15d': '%(turto_gpm_po_15d)s',
            'B_ismoketu_ismoku_neatemus_mokesciu': '%(kitos_viso_mokejimai)s',
            'B_pajamu_mokestis_iki15d': '%(kitos_gpm_iki_15d)s',
            'B_pajamu_mokestis_po15d': '%(kitos_gpm_po_15d)s',
            'A_ismoketu_ismoku_neatemus_mokesciu': '%(du_viso_mokejimai)s',
            'A_pajamu_mokestis_iki15d': '%(du_gpm_iki_15d)s',
            'A_pajamu_mokestis_po15d': '%(du_gpm_po_15d)s',
        }
        reconciled_with_a_klase = self.env['account.move.line'].search([('date', '>=', self.data_nuo),
                                                                        ('date', '<=', self.data_iki),
                                                                        ('reconciled_with_a_klase', '=', True),
                                                                        ('company_id', '=', self.kompanija.id)])
        payslip_move_ids = self.env['hr.payslip'].search(
            [('move_id.line_ids', 'in', reconciled_with_a_klase.ids)]).mapped('move_id')
        reconciled_with_a_klase = reconciled_with_a_klase.filtered(
            lambda r: r.move_id.id not in payslip_move_ids.ids).filtered(
            lambda r: not self.env['hr.employee.isskaitos'].search([('move_id', '=', r.move_id.id)]))

        du_viso_mokejimai = 0
        du_gpm_iki_15d = 0
        du_gpm_po_15d = 0

        kitos_viso_mokejimai = 0
        kitos_gpm_iki_15d = 0
        kitos_gpm_po_15d = 0

        turto_viso_mokejimai = 0
        turto_gpm_iki_15d = 0
        turto_gpm_po_15d = 0
        gpm_account_ids = self.env['account.account'].search(
            [('code', 'in', ['4481', '4487'])]).ids  # TODO: take accounts from company settings
        a_kodas_main = self.env.ref('l10n_lt_payroll.a_klase_kodas_1').id
        for pervedimas_aml in reconciled_with_a_klase:
            if pervedimas_aml.partner_id.mokesciu_institucija:
                continue
            if datetime.strptime(pervedimas_aml.date, tools.DEFAULT_SERVER_DATE_FORMAT).day <= 15:
                iki_15 = True
            else:
                iki_15 = False
            for apr in pervedimas_aml.matched_credit_ids.filtered(
                    lambda r: r.credit_move_id.a_klase_kodas_id.id == a_kodas_main):  # account.partial.reconcile
                orig_aml = apr.credit_move_id
                a_klase_amounts = self.get_a_klase_amounts(orig_aml.move_id, gpm_account_ids)
                total_amount, amount_to_pay, total_amount_tax = a_klase_amounts['bruto'], a_klase_amounts['neto'], \
                                                                a_klase_amounts['gpm']
                amount_paid = apr.amount
                if float_compare(amount_to_pay, 0, precision_digits=2) == 0:
                    continue
                ratio = amount_paid / amount_to_pay
                amount_i_ataskaita = total_amount * ratio
                amount_tax_i_ataskaita = total_amount_tax * ratio
                a_klase_kodas = orig_aml.a_klase_kodas_id.code
                du = False
                kitos = False
                turto = False
                if a_klase_kodas in ['01']:
                    du = True
                elif a_klase_kodas in ['8', '17']:  # todo peržiūrėti
                    turto = True
                else:
                    kitos = True
                if du:
                    du_viso_mokejimai += amount_i_ataskaita
                    if iki_15:
                        du_gpm_iki_15d += amount_tax_i_ataskaita
                    else:
                        du_gpm_po_15d += amount_tax_i_ataskaita
                if kitos:
                    kitos_viso_mokejimai += amount_i_ataskaita
                    if iki_15:
                        kitos_gpm_iki_15d += amount_tax_i_ataskaita
                    else:
                        kitos_gpm_po_15d += amount_tax_i_ataskaita
                if turto:
                    turto_viso_mokejimai += amount_i_ataskaita
                    if iki_15:
                        turto_gpm_iki_15d += amount_tax_i_ataskaita
                    else:
                        turto_gpm_po_15d += amount_tax_i_ataskaita

        XML += '''</Pages>
</Form>
</FFData>'''
        PageNumber = 1
        FAILAS = XML % {
            'MaxPageNumber': PageNumber,
            'du_viso_mokejimai': str(round(du_viso_mokejimai, 2)).replace('.', ','),
            'du_gpm_iki_15d': str(round(du_gpm_iki_15d)).replace('.', ','),
            'du_gpm_po_15d': str(round(du_gpm_po_15d)).replace('.', ','),

            'turto_viso_mokejimai': str(round(turto_viso_mokejimai)).replace('.', ','),
            'turto_gpm_iki_15d': str(round(turto_gpm_iki_15d)).replace('.', ','),
            'turto_gpm_po_15d': str(round(turto_gpm_po_15d)).replace('.', ','),

            'kitos_viso_mokejimai': str(round(kitos_viso_mokejimai)).replace('.', ','),
            'kitos_gpm_iki_15d': str(round(kitos_gpm_iki_15d)).replace('.', ','),
            'kitos_gpm_po_15d': str(round(kitos_gpm_po_15d)).replace('.', ','),
        }

        if self._context.get('eds'):
            try:
                self.env.user.upload_eds_file(
                    XML.encode('utf8').encode('base64'), 'FR0572.ffdata',
                    self.data_nuo, registry_num=company_data['code']
                )
            except:
                self.sudo().env.user.upload_eds_file(
                    XML.encode('utf8').encode('base64'), 'FR0572.ffdata',
                    self.data_nuo, registry_num=company_data['code']
                )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'e.vmi.fr0572',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.vmi_fr0572_download').id,
            'context': {'failas': FAILAS.encode('utf8').encode('base64')},
        }


FR0572()
