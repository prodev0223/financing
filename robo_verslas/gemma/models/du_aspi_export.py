# -*- coding: utf-8 -*-
import StringIO
import cStringIO as StringIO
import datetime
import logging
import os
from datetime import datetime
from sys import platform

import xlrd
import xlwt
from dateutil.relativedelta import relativedelta
from xlutils.filter import process, XLRDReader, XLWTWriter

from odoo import models, fields, api, _, tools

ezxf = xlwt.easyxf

_logger = logging.getLogger(__name__)

kwd_mark = object()
cache_styles = {}


def copy2(wb):
    w = XLWTWriter()
    process(XLRDReader(wb, 'unknown.xlsx'), w)
    return w.output[0][1], w.style_list


class DUASPIExcel:
    def __init__(self):
        self.wb = False

    def load_document(self):
        if platform == 'win32':
            xls_flocation = '\\static\\src\\xls\\DU_ASPI.xls'
        else:
            xls_flocation = '/static/src/xls/DU_ASPI.xls'
        file_loc = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + xls_flocation
        rb = xlrd.open_workbook(file_loc, formatting_info=True)
        wb, wstyle = copy2(rb)
        base_sheet = wb.get_sheet(0)
        base_sheet.set_portrait(True)
        base_sheet.paper_size_code = 9
        base_sheet.print_scaling = 100
        base_sheet.horz_page_breaks.append((46, 0, 0))
        base_sheet.vert_page_breaks.append((6, 0, 0))
        self.wb = wb

    def load_main(self, name, info, province, founder, illness_fund_province, date, number, period_year, period_month, ceo_name, accountant_data):
        style = ezxf(
            'font: height 220; align: wrap on, vert centre, horiz center;')
        style_left = ezxf(
            'font: height 220; align: wrap on, vert centre, horiz left;')
        sheet = self.wb.get_sheet(0)
        sheet.write(4, 0, unicode(name or ''), style)
        sheet.write(7, 0, unicode(info or ''), style)
        sheet.write(10, 0, unicode(province or ''), style)
        sheet.write(13, 0, unicode(founder or ''), style)

        illness_fund_province = illness_fund_province + ' teritorinei ligonių kasai'
        sheet.write(16, 0, unicode(illness_fund_province or ''), style_left)

        date_nr = date + ' Nr. ' + number
        sheet.write(21, 0, unicode(date_nr or ''), style)

        period = period_year + ' m. ' + period_month + ' mėn.'

        sheet.write(24, 0, unicode(period or ''), style)
        sheet.write(40, 5, unicode(ceo_name or ''), style)
        sheet.write(43, 2, unicode(accountant_data['email'] or ''), style)
        sheet.write(43, 5, unicode(accountant_data['phone'] or ''), style)

    def write_table(self, row, pay, num_empl, etatai):
        style = ezxf(
            'font: height 220; align: wrap on, vert centre, horiz center; borders: top thin, left thin, right thin, bottom thin, top_colour black, bottom_colour black, left_colour black, right_colour black')
        sheet = self.wb.get_sheet(0)
        sheet.write(row, 2, unicode(pay or 0.0), style)
        sheet.write(row, 3, unicode(num_empl or 0), style)
        sheet.write(row, 4, unicode(etatai or 0.0), style)

        pay_div_num_empl = round(pay / num_empl, 2) if num_empl != 0 else 0.0
        pay_div_etatai = round(pay / etatai, 2) if etatai != 0 else 0.0

        sheet.write(row, 5, unicode(pay_div_num_empl), style)
        sheet.write(row, 6, unicode(pay_div_etatai), style)

    def export(self):
        f = StringIO.StringIO()
        self.wb.save(f)
        return f.getvalue().encode('base64')


class ResCompany(models.Model):
    _inherit = 'res.company'

    du_aspi_administracijos_pareigos = fields.Many2many('hr.job', relation='rel_du_aspi_administracijos_pareigos', string='Administracijos pareigos')
    du_aspi_gydytoju_pareigos = fields.Many2many('hr.job', relation='rel_du_aspi_gydytoju_pareigos', string='Gydytojų pareigos')
    du_aspi_slaugytoju_pareigos = fields.Many2many('hr.job', relation='rel_du_aspi_slaugytoju_pareigos', string='Slaugytojų pareigos')
    du_aspi_kitas_personalas_sveikata_pareigos = fields.Many2many('hr.job', relation='rel_du_aspi_kitas_personalas_sveikata_pareigos', string='Kito personalo, teikiančio asmens sveikatos priežiūros paslaugas pareigos',)


ResCompany()


class DUASPIExportWizard(models.TransientModel):
    _name = 'du.aspi.export.wizard'

    def current_month(self):
        return str(datetime.utcnow().month)

    def default_administracijos_pareigos(self):
        return self.env.user.company_id.du_aspi_administracijos_pareigos.mapped('id')

    def default_gydytoju_pareigos(self):
        return self.env.user.company_id.du_aspi_gydytoju_pareigos.mapped('id')

    def default_slaugytoju_pareigos(self):
        return self.env.user.company_id.du_aspi_slaugytoju_pareigos.mapped('id')

    def default_kitas_personalas_sveikata_pareigos(self):
        return self.env.user.company_id.du_aspi_kitas_personalas_sveikata_pareigos.mapped('id')

    illness_fund_province = fields.Selection([
        ('vilniaus', 'Vilniaus'),
        ('kauno', 'Kauno'),
        ('klaipedos', 'Klaipedos'),
        ('siauliu', 'Šiaulių'),
        ('panevezio', 'Panevėžio')
        ], string='Teritorinė ligonių kasa', default='vilniaus', required=True)
    doc_number = fields.Integer(string='Dokumento numeris', default=1, required=True)
    period_year = fields.Integer(string='Apksaitinio periodo metai', required=True, default=int(datetime.utcnow().year))
    period_month = fields.Selection([('1', 'Sausis'),
                              ('2', 'Vasaris'),
                              ('3', 'Kovas'),
                              ('4', 'Balandis'),
                              ('5', 'Gegužė'),
                              ('6', 'Birželis'),
                              ('7', 'Liepa'),
                              ('8', 'Rugpjūtis'),
                              ('9', 'Rugsėjis'),
                              ('10', 'Spalis'),
                              ('11', 'Lapkritis'),
                              ('12', 'Gruodis')], string='Apksaitinio periodo mėnuo', required=True, default=current_month)

    administracijos_pareigos = fields.Many2many('hr.job', relation='rel_administracijos_pareigos', string='Administracijos pareigos', required=True, default=default_administracijos_pareigos)
    gydytoju_pareigos = fields.Many2many('hr.job', relation='rel_gydytoju_pareigos', string='Gydytojų pareigos', required=True, default=default_gydytoju_pareigos)
    slaugytoju_pareigos = fields.Many2many('hr.job', relation='rel_slaugytoju_pareigos', string='Slaugytojų pareigos', required=True, default=default_slaugytoju_pareigos)
    kitas_personalas_sveikata_pareigos = fields.Many2many('hr.job', relation='rel_kitas_personalas_sveikata_pareigos', string='Kito personalo, teikiančio asmens sveikatos priežiūros paslaugas pareigos', required=True, default=default_kitas_personalas_sveikata_pareigos)
    other_pareigos = fields.Many2many('hr.job', relation='rel_already_selected_pareigos', compute='_compute_selected_pareigos')

    @api.one
    @api.depends('administracijos_pareigos', 'gydytoju_pareigos', 'slaugytoju_pareigos', 'kitas_personalas_sveikata_pareigos')
    def _compute_selected_pareigos(self):
        adm = self.mapped('administracijos_pareigos.id')
        gyd = self.mapped('gydytoju_pareigos.id')
        sla = self.mapped('slaugytoju_pareigos.id')
        kit = self.mapped('kitas_personalas_sveikata_pareigos.id')
        all = adm+gyd+sla+kit
        self.other_pareigos = [(6, 0, all)]

    @api.multi
    def generate_and_export(self):
        if not self.env.user.is_manager():
            return
        accountant_data = {
            'email': self.env.user.email,
            'phone': self.env.user.work_phone,
        }
        self = self.sudo()
        excel = DUASPIExcel()
        excel.load_document()
        company = self.sudo().env.user.company_id
        company.write({
            'du_aspi_administracijos_pareigos': [(6, 0, self.administracijos_pareigos.mapped('id'))],
            'du_aspi_gydytoju_pareigos': [(6, 0, self.gydytoju_pareigos.mapped('id'))],
            'du_aspi_slaugytoju_pareigos': [(6, 0, self.slaugytoju_pareigos.mapped('id'))],
            'du_aspi_kitas_personalas_sveikata_pareigos': [(6, 0, self.kitas_personalas_sveikata_pareigos.mapped('id'))],
        })
        name = company.name
        info = 'įm k.: ' + str(company.company_registry or '') + ', ID ' + str(company.health_institiution_id_code or '')
        province = str(company.city) or ''
        health_institution_description = company.health_institiution_type_name or ''
        illness_fund_province = str(dict(self._fields['illness_fund_province'].selection).get(self.illness_fund_province))
        date = str(datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
        number = str(self.doc_number)
        period_year = str(self.period_year)
        month_mapping = {
            '1': 'Sausio',
            '2': 'Vasario',
            '3': 'Kovo',
            '4': 'Balandžio',
            '5': 'Gegužės',
            '6': 'Birželio',
            '7': 'Liepos',
            '8': 'Rugpjūčio',
            '9': 'Rugsėjo',
            '10': 'Spalio',
            '11': 'Lapkričio',
            '12': 'Gruodžio'
        }
        period_month = month_mapping[self.period_month]

        ceo_name = self.env.user.company_id.vadovas.name_related
        excel.load_main(name, info, province, health_institution_description, illness_fund_province, date, number, period_year, period_month, ceo_name, accountant_data)

        if self.period_year > 2200 or self.period_year < 2000:
            period_year = datetime.utcnow().year
        else:
            period_year = self.period_year

        date_from = datetime(period_year, int(self.period_month), 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = (datetime(period_year, int(self.period_month), 1) + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        payslips = self.env['hr.payslip'].search([
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
            ('state', '=', 'done')
        ])
        appointments = self.env['hr.contract.appointment'].search([
            ('contract_id', 'in', payslips.mapped('contract_id.id')),
            ('date_start', '<=', date_to),
            '|',
            ('date_end', '=', False),
            ('date_end', '>=', date_from),
        ])

        values = {
            'payslips': payslips,
            'appointments': appointments,
            'date_from': date_from,
            'date_to': date_to,
        }

        total_pay = 0
        total_num_empl = 0
        total_etatai = 0
        values.update({
            'job_ids': self.mapped('administracijos_pareigos.id'),
            'not_in_job_ids': False,
        })
        pay, num_empl, etatai = self.get_amounts(**values)

        total_pay += pay
        total_num_empl += num_empl
        total_etatai += etatai
        excel.write_table(32, pay, num_empl, etatai)
        values.update({
            'job_ids': self.mapped('gydytoju_pareigos.id')
        })
        pay, num_empl, etatai = self.get_amounts(**values)

        total_pay += pay
        total_num_empl += num_empl
        total_etatai += etatai
        excel.write_table(33, pay, num_empl, etatai)
        values.update({
            'job_ids': self.mapped('slaugytoju_pareigos.id'),
        })
        pay, num_empl, etatai = self.get_amounts(**values)
        total_pay += pay
        total_num_empl += num_empl
        total_etatai += etatai
        excel.write_table(34, pay, num_empl, etatai)
        values.update({
            'job_ids': self.mapped('kitas_personalas_sveikata_pareigos.id'),
        })
        pay, num_empl, etatai = self.get_amounts(**values)
        total_pay += pay
        total_num_empl += num_empl
        total_etatai += etatai
        excel.write_table(35, pay, num_empl, etatai)
        values.update({
            'job_ids': list(self.mapped('kitas_personalas_sveikata_pareigos.id')
                            + self.mapped('slaugytoju_pareigos.id')
                            + self.mapped('gydytoju_pareigos.id')
                            + self.mapped('administracijos_pareigos.id')),
            'not_in_job_ids': True,
        })
        pay, num_empl, etatai = self.get_amounts(**values)
        total_pay += pay
        total_num_empl += num_empl
        total_etatai += etatai
        excel.write_table(36, pay, num_empl, etatai)
        excel.write_table(31, total_pay, total_num_empl, total_etatai)

        base64_file = excel.export()
        filename = 'DU_ASPI (' + str(period_month) + ' ' + str(period_year) + ').xls'
        company_id = self.env.user.sudo().company_id.id
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'res.company',
            'res_id': company_id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        if self._context.get('archive', False):
            return base64_file
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=res.company&res_id=%s&attach_id=%s' % (company_id, attach_id.id),
            'target': 'self',
        }

    @api.model
    def get_amounts(self, payslips, appointments, date_from, date_to, job_ids=[], not_in_job_ids=False):
        if not_in_job_ids:
            job_payslips = payslips.filtered(lambda r: r['employee_id']['job_id']['id'] not in job_ids)
        else:
            job_payslips = payslips.filtered(lambda r: r['employee_id']['job_id']['id'] in job_ids)

        pay = self.compute_pay(job_payslips, date_from, date_to)

        num_empl = len(set(job_payslips.mapped('employee_id'))) or 0
        etatai = 0.0
        for payslip in job_payslips:
            payslip_appointments = appointments.filtered(
                lambda r: r['contract_id']['id'] == payslip.contract_id.id).sorted(key=lambda l: l['date_start'],
                                                                                   reverse=True)
            if payslip_appointments:
                etatai += payslip_appointments[0].schedule_template_id.etatas
        return pay, num_empl, etatai

    @api.model
    def compute_pay(self, payslips, date_from, date_to):
        pay = sum(payslips.mapped('bruto')) or 0.0

        # Lines with particular codes need to be deducted
        exclude_codes = ['AK', 'IST']
        amount_exclude_codes = sum(payslips.mapped('line_ids').filtered(
            lambda c: c.code in exclude_codes).mapped('amount'))

        # Deduct bonuses that are marked to not be included
        employee_ids = payslips.mapped('employee_id').ids
        amount_bonus_from_bonus_records = sum(self.env['hr.employee.bonus'].search([
            ('employee_id', 'in', employee_ids),
            ('state', '=', 'confirm'),
            ('payment_date_from', '=', date_from),
            ('payment_date_to', '=', date_to),
            ('exclude_bonus_from_du_aspi', '=', True),
        ]).mapped('amount'))
        amount_bonus_from_payslips = sum(
            payslips.mapped('line_ids').filtered(lambda c: c.code == 'PD').mapped('amount')
        )
        amount_bonus_exclude = min(
            amount_bonus_from_bonus_records, amount_bonus_from_payslips) if amount_bonus_from_bonus_records else 0.0

        # Deduct and return the final amount
        amount_exclude = amount_exclude_codes + amount_bonus_exclude
        return pay - amount_exclude


DUASPIExportWizard()
