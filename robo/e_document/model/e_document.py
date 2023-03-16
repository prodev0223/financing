# -*- coding: utf-8 -*-
from __future__ import division
import logging
import mimetypes
import re
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from urlparse import urljoin

import jinja2
import magic
import werkzeug
from dateutil.relativedelta import relativedelta
from jinja2 import meta
from lxml import etree
from pytz import timezone

import linksnis as linksniuoti
from odoo import _, api, exceptions, fields, models, tools
from odoo.addons.base_iban.models.res_partner_bank import validate_iban
from odoo.addons.l10n_lt_payroll.model.hr_contract import SUTARTIES_RUSYS
from odoo.fields import One2many as OdooOne2manyField
from odoo.tools import float_compare, float_is_zero
from odoo.tools.safe_eval import safe_eval
from odoo.addons.l10n_lt_payroll.model.schedule_template import time_cross_constraints
from odoo.addons.queue_job.job import job

from six import iteritems

_logger = logging.getLogger(__name__)

LINKSNIAI_FUNC = {
    'ko': linksniuoti.kas_to_ko,
    'kam': linksniuoti.kas_to_kam,
    'ka': linksniuoti.kas_to_ka,
    'kuo': linksniuoti.kas_to_kuo,
    'kur': linksniuoti.kas_to_kur,
    'sauksm': linksniuoti.kas_to_sauksm,
}


def sanitize_account_number(acc_number):
    if acc_number:
        return re.sub(r'\W+', '', acc_number).upper()
    return False


def check_time_overlap(lines):
    field_name = ''
    if lines._name == 'e.document.fix.attendance.line':
        days = list(set(lines.mapped('dayofweek')))
        field_name = 'dayofweek'
    elif lines._name == 'e.document.time.line':
        days = list(set(lines.mapped('date')))
        field_name = 'date'
    for weekday in days:
        if field_name == 'dayofweek':
            day_lines = lines.filtered(lambda l: l.dayofweek == weekday)
            times = [(x.hour_from, x.hour_to) for x in day_lines]
        elif field_name == 'date':
            day_lines = lines.filtered(lambda l: l.date == weekday)
            times = [(x.time_from, x.time_to) for x in day_lines]
        time_cross_constraints(times)

# nerekomenduojama keisti state iš to paties į tą patį :)
class EDocument(models.Model):
    _name = 'e.document'
    _inherit = ['mail.thread', 'ir.needaction_mixin']

    def _generate_order_by(self, order_spec, query):
        my_order = '''CASE WHEN state='confirm' or state='draft' 
                   THEN 0 ELSE 1 END, "e_document"."date_signed" desc NULLS LAST, "e_document"."create_date" desc'''
        if order_spec:
            return super(EDocument, self)._generate_order_by(order_spec, query)
        return " order by " + my_order

    @api.model_cr
    def init(self):
        sequence = self.env['ir.cron'].search([('name', '=', 'e.document.name.sequence')], limit=1)
        local, utc = datetime.now(), datetime.utcnow()
        diff = utc - local
        local_time_to_execute = local + relativedelta(days=1, hour=0, minute=0)
        utc_time_to_execute = local_time_to_execute + diff
        if sequence:
            sequence.write({'nextcall': utc_time_to_execute.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)})

    def default_type(self):
        if self._context.get('e_document_view_type', False) in ['rigid', 'free']:
            return self._context['e_document_view_type']
        else:
            return 'free'

    def default_template(self):
        template_ref = self._context.get('rec_template_id')
        if template_ref:
            if '.' in template_ref:
                return self.sudo().env.ref(template_ref)
            else:
                return self.sudo().env.ref('e_document.' + template_ref)

    def default_document_date(self):
        return datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_advance_setup(self):
        return self.env.user.company_id.sudo().e_documents_enable_advance_setup

    def _default_job_3(self):
        uid = self.env.user.id
        employee = self.sudo().env['hr.employee'].search([('user_id', '=', uid)], limit=1)
        if employee:
            return employee.job_id
        else:
            return False

    def _track_subtype(self, init_values):
        self.ensure_one()
        if 'state' in init_values and self.state == 'confirm':
            partner_ids = self.mapped('employee_id1.address_home_id.id')
            if self.user_ids:
                partner_ids += self.user_ids.mapped('user_id.partner_id.id')
            msg = {
                'body': _('Atsirado dokumentas, laukiantis jūsų pasirašymo.'),
                'subject': _('Laukiantis pasirašymo'),
                'priority': 'low',
                'front_message': True,
                'rec_model': 'e.document',
                'rec_id': self.id,
                'view_id': self.view_id.id or False,
            }
            if partner_ids:
                msg['partner_ids'] = partner_ids
            self.robo_message_post(**msg)
            if self.document_type == 'isakymas' and self.template_id and not self.check_user_can_sign(raise_if_false=False):
                if not self.env['e.document'].search_count([('record_id', '=', self.id), ('record_model', '=', 'e.document')]):
                    self.inform_ceo_about_order_waiting_for_signature()
        elif 'state' in init_values and self.state == 'cancel':
            self.message_ids.filtered(lambda
                                          r: r.front_message and r.res_id == self.id and r.model == 'e.document' and r.subtype_id.id == self.env.ref(
                'robo.mt_robo_front_message').id).set_roboFrontMessage_done()
            prasymai = self.sudo().env['e.document'].search(
                [('record_model', '=', 'e.document'), ('record_id', '=', self.id)])
            if prasymai:
                prasymai.write({'rejected': True})
                for prasymas in prasymai:
                    msg = {
                        'body': _('Jūsų prašymas buvo atmestas skyriaus vadovo.'),
                        'subject': _('Atmestas prašymas'),
                        'priority': 'high',
                        'front_message': True,
                        'rec_model': 'e.document',
                        'rec_id': prasymas.id,
                        'view_id': prasymas.view_id.id or False,
                    }
                    partner_ids = prasymas.mapped('employee_id1.user_id.partner_id.id')
                    if partner_ids:
                        msg['partner_ids'] = partner_ids
                    prasymas.robo_message_post(**msg)
        elif 'state' in init_values and self.state == 'e_signed' and self.cancel_id:
            self.message_ids.filtered(lambda
                                          r: r.front_message and r.res_id == self.id and r.model == 'e.document' and r.subtype_id.id == self.env.ref(
                'robo.mt_robo_front_message').id).set_roboFrontMessage_done()
            cancel_id = self.sudo().cancel_id
            cancel_id.rejected = True
            prasymai = self.sudo().env['e.document'].search(
                [('record_model', '=', 'e.document'), ('record_id', '=', cancel_id.id)])
            if prasymai:
                prasymai.write({'rejected': True})
                for prasymas in prasymai:
                    msg = {
                        'body': _('Jūsų prašymas buvo atmestas.'),
                        'subject': _('Atmestas prašymas'),
                        'priority': 'high',
                        'front_message': True,
                        'rec_model': 'e.document',
                        'rec_id': prasymas.id,
                        'view_id': prasymas.view_id.id or False,
                    }
                    partner_ids = prasymas.mapped('employee_id1.user_id.partner_id.id')
                    if partner_ids:
                        msg['partner_ids'] = partner_ids
                    prasymas.robo_message_post(**msg)
        elif 'state' in init_values and self.state != 'confirm':
            self.message_ids.filtered(lambda
                                          r: r.front_message and r.res_id == self.id and r.model == 'e.document' and r.subtype_id.id == self.env.ref(
                'robo.mt_robo_front_message').id).set_roboFrontMessage_done()
        else:
            super(EDocument, self)._track_subtype(init_values)

    @api.depends('date_3', 'selection_nedarbingumas')
    def _get_selection_nedarbingumas_npd(self):
        if self.selection_nedarbingumas == '0_25':
            npd_max = self.sudo().company_id.get_historical_field_value(self.date_3,
                                                                        'npd_0_25_max') if self.date_3 else getattr(
                self.sudo().company_id, 'npd_0_25_max')
        else:
            npd_max = self.sudo().company_id.get_historical_field_value(self.date_3,
                                                                        'npd_30_55_max') if self.date_3 else getattr(
                self.sudo().company_id, 'npd_30_55_max')
        self.nedarbingumas_npd = str(int(npd_max))

    def _default_payslip_year_id(self):
        return self.env['years'].search([('code', '=', datetime.utcnow().year)], limit=1)

    def format_record_ids(self, record_ids):
        if not isinstance(record_ids, list):
            raise exceptions.ValidationError(_('Record ids must be of type list'))
        return ','.join(str(e) for e in record_ids)

    @api.multi
    def parse_record_ids(self):
        self.ensure_one()
        ids = self.record_ids
        res = []
        if ids:
            res = [int(rid) for rid in ids.split(',')]
        return res

    state = fields.Selection([('draft', 'Nesuformuotas'), ('confirm', 'Laukiantis pasirašymo'),
                              ('e_signed', 'Pasirašytas'), ('cancel', 'Atšauktas')],
                             default='draft', string='Būsena', required=True, readonly=True,
                             track_visibility='onchange')
    rejected = fields.Boolean(string='Atmestas', default=False, readonly=True, copy=False)
    show_annotation = fields.Boolean(readonly=True, compute='do_show_annotation')
    name = fields.Char(string='Pavadinimas', compute='_compute_name', store=True)
    name_force = fields.Char(string='Priverstinis pavadinimas')
    active = fields.Boolean(default=True, string='Active', groups='base.group_system', copy=False)
    employee_id1 = fields.Many2one('hr.employee', inverse='set_final_document', readonly=True,
                                   states={'draft': [('readonly', False)]})
    employee_id2 = fields.Many2one('hr.employee', inverse='set_final_document', readonly=True,
                                   states={'draft': [('readonly', False)]})
    employee_id3 = fields.Many2one('hr.employee', inverse='set_final_document', readonly=True,
                                   states={'draft': [('readonly', False)]})
    employee_id4 = fields.Many2one('hr.employee', inverse='set_final_document', readonly=True,
                                   states={'draft': [('readonly', False)]})
    employee_id5 = fields.Many2one('hr.employee', inverse='set_final_document', readonly=True,
                                   states={'draft': [('readonly', False)]})
    company_id = fields.Many2one('res.company', inverse='set_final_document')
    document_number = fields.Char(string='Įsakymo numeris', default='-', inverse='set_final_document',
                                  readonly=True, copy=False)
    contract_id_1 = fields.Many2one('hr.contract', inverse='set_final_document', readonly=True,
                                    states={'draft': [('readonly', False)]},
                                    domain="[('employee_id', '=', employee_id2)]")
    contract_id_2 = fields.Many2one('hr.contract', inverse='set_final_document', readonly=True,
                                    states={'draft': [('readonly', False)]},
                                    domain="[('employee_id', '=', employee_id2)]")
    text_1 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_2 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_3 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_4 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_5 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_6 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_7 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_8 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_9 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_10 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_11 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    text_12 = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    int_1 = fields.Integer(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    int_2 = fields.Integer(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    int_3 = fields.Integer(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    int_4 = fields.Integer(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    float_1 = fields.Float(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    float_2 = fields.Float(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    float_3 = fields.Float(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    time_1 = fields.Float(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    time_2 = fields.Float(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})

    job_id1 = fields.Many2one('hr.job', compute='_compute_job_id_1', store=True, readonly=True,
                              states={'draft': [('readonly', False)]})
    job_id2 = fields.Many2one('hr.job', compute='_compute_job_id_2', store=True, readonly=True,
                              inverse='_set_job_id_2', states={'draft': [('readonly', False)]})
    job_id3 = fields.Many2one('hr.job', compute='_compute_job_id_3', store=True, readonly=True,
                              states={'draft': [('readonly', False)]})
    job_id4 = fields.Many2one('hr.job', inverse='set_final_document', store=True, readonly=True,
                              states={'draft': [('readonly', False)]})
    country_allowance_id = fields.Many2one('country.allowance', inverse='set_final_document', readonly=True,
                                           states={'draft': [('readonly', False)]})
    country_id = fields.Many2one('res.country')
    department_id = fields.Many2one('hr.department', compute='_compute_department_id', readonly=True, store=True)
    department_id2 = fields.Many2one('hr.department', inverse='set_final_document', readonly=True,
                                     states={'draft': [('readonly', False)]})
    manager_id = fields.Many2one('hr.employee', compute='_compute_manager_id', readonly=True, store=True)
    date_document = fields.Date(default=default_document_date, inverse='set_final_document', readonly=True,
                                states={'draft': [('readonly', False)]})
    date_from = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_to = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_time_from = fields.Datetime(inverse='set_final_document', readonly=True,
                                     states={'draft': [('readonly', False)]})
    date_time_to = fields.Datetime(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_1 = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_2 = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_3 = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_4 = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_5 = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_6 = fields.Date(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    date_1_computed = fields.Date(compute='_compute_date_1_computed')
    terminuota_sutartis = fields.Boolean(string='Terminuota sutartis', compute='_terminuota_sutartis')
    document_1 = fields.Binary(readonly=True, states={'draft': [('readonly', False)]})
    document_1_filename = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    document_2 = fields.Binary(readonly=True, states={'draft': [('readonly', False)]})
    document_2_filename = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    document_3 = fields.Binary(readonly=True, states={'draft': [('readonly', False)]})
    document_3_filename = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    attached_signed_document = fields.Binary('Prisegtas pasirašytas dokumentas',
                                             inverse='_inverse_check_attached_signed_document')
    attached_signed_document_filename = fields.Char('Attached signed document filename', readonly=True,
                                                    states={'draft': [('readonly', False)]})
    selection_1 = fields.Selection([('once_per_month', 'vieną kartą'), ('twice_per_month', 'du kartus')],
                                   readonly=True, states={'draft': [('readonly', False)]}, inverse='set_final_document',
                                   default='once_per_month')
    selection_nedarbingumas = fields.Selection([('0_25', '0-25 %'), ('30_55', '30-55 %')], readonly=True,
                                               states={'draft': [('readonly', False)]}, inverse='set_final_document')
    nedarbingumas_npd = fields.Char(compute="_get_selection_nedarbingumas_npd", readonly=True, store=False,
                                    required=False, invisible=True)
    template_id = fields.Many2one('e.document.template', string='template', default=default_template,
                                  inverse='set_final_document', readonly=True)
    final_document = fields.Text(string='Dokumentas', copy=False)
    view_type = fields.Selection([('rigid', 'Rigid'), ('free', 'Free')], default=default_type, readonly=True)
    view_id = fields.Many2one('ir.ui.view', compute='_view_id', store=True)
    num_calendar_days = fields.Integer(compute='_num_calendar_days', store=True)
    num_work_days = fields.Integer(compute='_num_work_days', store=True, inverse='_set_num_work_days')
    manager_job_id = fields.Many2one('hr.job', related='manager_id.job_id', readonly=True, store=True, compute_sudo=True)
    document_type = fields.Selection([('prasymas', 'Prasymas'), ('isakymas', 'Isakymas'),
                                      ('akcininku_sprendimas', 'Akcininkų sprendimas'),
                                      ('act', 'Aktas'),
                                      ('agreement', 'Sutartis'),
                                      ('other', 'Kita')], required=True,
                                     default='prasymas', readonly=True, inverse='set_final_document')
    generated_document = fields.Binary(readonly=True, attachment=True, copy=False)
    generated_document_download = fields.Binary(compute='_generated_document_download')
    file_name = fields.Char(string='Failo pavadinimas', default='dokumentas.pdf', copy=False)
    vieta = fields.Char(inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    record_model = fields.Char(inverse='_set_document_link', copy=False)
    record_id = fields.Integer(copy=False)
    record_ids = fields.Text(copy=False)
    susijes_isakymas_pasirasytas = fields.Boolean(string='Susijęs įsakymas psirašytas', readonly=True, copy=False)
    date_signed = fields.Datetime(string='Pasirašymo data', readonly=True, copy=False)
    signed_user_id = fields.Many2one('res.users', readonly=True, copy=False)
    user_ids = fields.One2many('signed.users', 'document_id', string='Pasirašę', copy=False)
    user_id = fields.Many2one('res.users', string='Darbuotojas')
    darbo_rusis = fields.Selection(SUTARTIES_RUSYS, string='Darbo sutarties rūšis', default='neterminuota',
                                   inverse='set_final_document', readonly=True, states={'draft': [('readonly', False)]})
    struct = fields.Selection([('MEN', 'Mėnesinis'), ('VAL', 'Valandinis')], string='Atlyginimo struktūra',
                              default='MEN', inverse='set_final_document', readonly=True,
                              states={'draft': [('readonly', False)]})
    bool_1 = fields.Boolean(readonly=True, states={'draft': [('readonly', False)]}, inverse='set_final_document')
    selection_bool_1 = fields.Selection([('true', 'Taip'), ('false', 'Ne')],
                                        inverse='set_final_document', readonly=True,
                                        states={'draft': [('readonly', False)]})
    selection_bool_2 = fields.Selection([('true', 'Taip'), ('false', 'Ne')],
                                        inverse='set_final_document', readonly=True,
                                        states={'draft': [('readonly', False)]})
    selection_bool_3 = fields.Selection([('true', 'Taip'), ('false', 'Ne')],
                                        inverse='set_final_document', readonly=True,
                                        states={'draft': [('readonly', False)]})
    sodra_papildomai_type = fields.Selection(
        [('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
        string='Sodros kaupimo būdas', default='full', readonly=True,
        states={'draft': [('readonly', False)]}, inverse='set_final_document')
    sodra_papildomai_type_stored = fields.Selection(
        [('full', 'Iš karto (3 proc. nuo atlyginimo)'),
         ('exponential', 'Palaipsniui (2019 - 1.8%, 2020 - 2.1%, 2021 - 2.4% nuo atlyginimo)')],
        string='Sodros kaupimo būdas', readonly=True)
    compute_bool_1 = fields.Selection([('true', 'Taip'), ('false', 'Ne')], readonly=True, compute='_compute_bool_1')
    compute_bool_1_stored = fields.Selection([('true', 'Taip'), ('false', 'Ne')], readonly=True)
    compute_sodra_papildomai_type = fields.Selection(
        [('full', 'Pilnas (3%)'), ('exponential', 'Palaipsniui (Nuo 2022 - 2.7%)')],
        string='Sodros kaupimo būdas', default='full', readonly=True, compute='_compute_sodra_papildomai_type')
    reported = fields.Boolean(string='Informuota buhalterija', default=False)
    dk_nutraukimo_straipsnis = fields.Many2one('dk.nutraukimo.straipsniai', readonly=True,
                                               states={'draft': [('readonly', False)]}, inverse='set_final_document', )
    dk_detalizacija = fields.Text(readonly=True, states={'draft': [('readonly', False)]})
    business_trip_holidays_selection = fields.Selection([('double', 'Dvigubai'),
                                                         ('extra_day', 'Papildoma diena')],
                                                        inverse='set_final_document',
                                                        readonly=True,
                                                        states={'draft': [('readonly', False)]})
    acc_number = fields.Char(string='Banko sąskaitos nr.', inverse='set_final_document', readonly=True,
                             states={'draft': [('readonly', False)]})
    surname = fields.Char(compute='_compute_surname')
    du_input_type = fields.Selection([('bruto', 'Bruto'), ('neto', 'Neto')], string='Atlyginimas',
                                     inverse='set_final_document',
                                     readonly=True, states={'draft': [('readonly', False)]}, default='bruto')

    bonus_input_type = fields.Selection([('bruto', 'Bruto'), ('neto', 'Neto')], string='Skaičiuojama',
                                        inverse='set_final_document',
                                        readonly=True, states={'draft': [('readonly', False)]}, default='bruto')

    npd_type = fields.Selection(
        [('auto', 'Pagrindinė darbovietė (taikyti NPD)'), ('manual', 'Netaikyti NPD')],
        default='auto', string='NPD skaičiavimas', inverse='set_final_document',
        readonly=True, states={'draft': [('readonly', False)]})
    vaikus_augina = fields.Selection([('vienas', 'Vienas'), ('su_sutuoktiniu', 'Su sutuoktiniu')],
                                     inverse='set_final_document', readonly=True,
                                     states={'draft': [('readonly', False)]}, default='su_sutuoktiniu')
    atlyginimo_lentele = fields.Html(compute='_compute_payroll', store=True)
    wage_bruto = fields.Float(compute='_compute_payroll', store=True)
    num_extra_days = fields.Selection([('1', '1'), ('2', '2')], readonly=True,
                                      states={'draft': [('readonly', False)]},
                                      inverse='set_final_document', default='1')
    num_children = fields.Selection([('1', '1 (Neįgalus iki 18 metų)'),
                                     ('1_under_12', '1 (under 12 years old'),
                                     ('2', '2 (Iki 12 metų)'),
                                     ('3', '3 ir daugiau (Iki 12 metų)')], readonly=True,
                                    states={'draft': [('readonly', False)]},
                                    inverse='set_final_document'
                                    , default='2')
    locked = fields.Boolean(readonly=True, default=False, string='Locked', copy=False)
    darbo_grafikas = fields.Selection([('fixed', 'Nekintančio darbo laiko režimas'),
                                       ('sumine', 'Suminės darbo laiko apskaitos darbo laiko režimas'),
                                       ('lankstus', 'Lankstaus darbo laiko režimas'),
                                       ('suskaidytos', 'Suskaidytos darbo dienos laiko režimas'),
                                       ('individualus', 'Individualus darbo laiko režimas')
                                       ], readonly=True, states={'draft': [('readonly', False)]},
                                      inverse='set_final_document', default='fixed')
    fixed_schedule_template = fields.Selection([('8_hrs_5_days', '8:00 - 12:00 | 13:00 - 17:00'),
                                                ('8_hrs_5_days_from_9', '9:00 - 12:00 | 13:00 - 18:00'),
                                                ('6_hrs_5_days', '8:00 - 14:00'),
                                                ('4_hrs_5_days', '8:00 - 12:00'),
                                                ('2_hrs_5_days', '8:00 - 10:00'),
                                                ('custom', 'Kitas')],
                                               string=_('Grafiko šablonas'), readonly=True,
                                               states={'draft': [('readonly', False)]},
                                               inverse='set_final_document', default='8_hrs_5_days')
    fixed_attendance_ids = fields.One2many('e.document.fix.attendance.line', 'e_document', string='Grafikas',
                                           readonly=True, states={'draft': [('readonly', False)]},
                                           inverse='set_final_document')

    dk_tekstas = fields.Text(related='dk_nutraukimo_straipsnis.text_in_document', readonly=True)
    dk_pavadinimas = fields.Text(related='dk_nutraukimo_straipsnis.straipsnio_pav', readonly=True)
    paperformat_id = fields.Many2one('report.paperformat', 'Paper format')

    reikia_pasirasyti_iki = fields.Date(string='Pasirašyti iki', compute='_compute_reikia_pasirasyti_iki',
                                        store=True)
    doc_partner_id = fields.Many2one('res.partner', string='Darbuotojas', compute='_doc_partner_id', store=True, inverse='set_final_document')
    related_employee_ids = fields.One2many('hr.employee', string='Darbuotojas', compute='_compute_related_employee_ids',
                                           search='_search_related_employee_ids')
    atostoginiu_ismokejimas = fields.Selection([('su_du', 'Su darbo užmokesčiu'), ('pries', 'Prieš atostogas')],
                                               string='Atostoginių išmokėjimas', default='su_du',
                                               inverse='set_final_document', readonly=True,
                                               states={'draft': [('readonly', False)]})
    politika_atostoginiai = fields.Selection(
        [('su_du', 'Visada su darbo užmokesčiu'), ('rinktis', 'Leisti rinktis')],
        string='Atostoginių politika', compute='_apskaitos_politika')
    holiday_policy_inform_manager = fields.Boolean(compute='_apskaitos_politika')
    politika_atostogu_suteikimas = fields.Selection(
        [('ceo', 'Tvirtina vadovas'), ('department', 'Padalinio vadovas')], string='Atostogų tvirtinimas',
        compute='_apskaitos_politika')
    cancel_id = fields.Many2one('e.document', string='Atšaukiamas įsakymas', readonly=True, copy=False)
    cancel_name = fields.Char(string='Atšaukiamo įsakymo pavadinimas', compute='_cancel_data')
    cancel_date = fields.Date(string='Atšaukiamo įsakymo data', compute='_cancel_data')
    cancel_number = fields.Char(string='Atšaukiamo įsakymo numeris', compute='_cancel_data')
    cancel_body = fields.Char(string='Atšaukiamo įsakymo tekstas', compute='_cancel_data')
    cancelled_ids = fields.One2many('e.document', 'cancel_id', domain=[('state', '!=', 'cancel')])
    force_view_id = fields.Many2one('ir.ui.view')
    extra_text = fields.Text(string='Papildomas tekstas', inverse='set_final_document', readonly=True,
                             states={'draft': [('readonly', False)]})
    extra_text_html = fields.Html(compute='_compute_extra_text_html')
    extra_business_trip_weekend_text = fields.Text(string='Papildomas komandiruociu dirbtu savaitgali tekstas',
                                                   inverse='set_final_document', readonly=True,
                                                   compute='_show_extra_komandiruotes_text')
    not_check_holidays = fields.Boolean(string='Netikrinti atostogų', readonly=True)
    approve_status = fields.Selection(
        [('waiting_approval', 'Laukia patvirtinimo'), ('approved', 'Patvirtintas'), ('rejected', 'Atmestas')],
        string='Tiesioginio vadovo tvirtinimas', readonly=True)
    allow_approve = fields.Boolean(string='Leisti tvirtinti', compute='_allow_approve')
    allow_reject = fields.Boolean(string='Leisti atšaukti', compute='_allow_reject')
    show_cancel_request = fields.Boolean(string='Rodyti prašymo atšaukimą', compute='_show_cancel_request')
    show_warning = fields.Boolean(string='Rodyti įspėjimą', compute='_show_warning')
    hide_view = fields.Boolean(string='Rodyti formą', compute='_hide_view')
    bonus_type_selection = fields.Selection([('1men', 'Mėnesinė'),
                                             ('3men', 'Ketvirtinė'),
                                             ('ilgesne', 'Ilgesnė nei 3 mėn., bet ne ilgesnė nei 12 mėn.'),
                                             ('ne_vdu', 'Nepatenkanti į vdu')], string='Premijos rūšis',
                                            inverse='set_final_document',
                                            readonly=True, states={'draft': [('readonly', False)]})
    date_from_display = fields.Date(string='Data nuo', compute='_compute_dates_display', store=True)
    date_to_display = fields.Date(string='Data iki', compute='_compute_dates_display', store=True)
    no_mark = fields.Boolean(string='Nedėti žymos', default=False)
    signed_multiple = fields.Boolean(string='Pasirašyta', compute='_signed_multiple')

    cancel_uid = fields.Many2one('res.users', string='Canceled by', readonly=True, lt_string='Atšaukęs vartotojas',
                                 copy=False)

    e_document_line_ids = fields.One2many('e.document.line', 'e_document_id', string='EDocument Lines',
                                          inverse='set_final_document', readonly=True,
                                          states={'draft': [('readonly', False)]}, copy=True)
    e_document_time_line_ids = fields.One2many('e.document.time.line', 'e_document_id',
                                               string='EDocument Worked time lines',
                                               inverse='set_final_document', readonly=True,
                                               states={'draft': [('readonly', False)]}, copy=True)

    compute_text_1 = fields.Text(compute='_compute_text_1', store=True, readonly=True,
                                 states={'draft': [('readonly', False)]})

    show_user = fields.Boolean(compute='_compute_do_show_user', readonly=False)

    skip_constraints = fields.Boolean(string='Praleisti apribojimų tikrinimą vykdymo eigoje', default=False,
                                      groups='robo_basic.group_robo_premium_accountant', copy=False,
                                      track_visibility='onchange')
    skip_constraints_confirm = fields.Boolean(string='Praleisti apribojimų tikrinimą dokumento formavime',
                                              default=False, groups='robo_basic.group_robo_premium_accountant',
                                              copy=False, track_visibility='onchange')
    uploaded_document = fields.Boolean(string='Įkeltas dokumentas', default=False)
    business_trip_worked_on_weekends = fields.Selection([('true', 'Taip'), ('false', 'Ne')],
                                                        inverse='set_final_document', readonly=True,
                                                        states={'draft': [('readonly', False)]})
    compensate_employee_business_trip_holidays = fields.Selection(
        [('free_days', 'Kompensuoti poilsiu darbo dienas grįžus'),
         ('holidays', 'Pridėti dirbtas poilsio dienas prie kasmetinių atostogų laiko')],
        string='Kompensacija už darbą poilsio dienomis',
        inverse='set_final_document', default='free_days', readonly=True, states={'draft': [('readonly', False)]})
    dates_contain_weekend = fields.Boolean(compute="_dates_contain_weekends")
    base_amount_weekly_hours_flexible_schedule = fields.Float(string='Darbo laikas per savaitę', readonly=True,
                                                              states={'draft': [('readonly', False)]}, copy=True,
                                                              inverse='set_final_document')
    etatas = fields.Float(string='Etatas', readonly=True, states={'draft': [('readonly', False)]}, copy=True,
                          inverse='set_final_document', default=1.0, digits=(16, 5))
    etatas_computed = fields.Float(string='Etatas', readonly=True, compute='compute_etatas', digits=(16, 5))
    holiday_dates = fields.Text(compute="_get_holiday_dates")
    holiday_fix_id = fields.Many2one('hr.holidays.fix', copy=False)
    warn_about_sumine_holidays_abuse = fields.Boolean(readonly=True, compute='_warn_about_sumine_holidays_abuse')
    show_etatas = fields.Boolean(compute='_get_show_values')
    show_etatas_computed = fields.Boolean(compute='_get_show_values')
    show_weekly_work_hours = fields.Boolean(compute='_get_show_values')
    show_weekly_work_hours_computed = fields.Boolean(compute='_get_show_values')
    show_fixed_attendance_lines = fields.Boolean(compute='_get_show_values')
    weekly_work_hours = fields.Float(string='Valandų skaičius per savaitę', readonly=True,
                                     states={'draft': [('readonly', False)]}, copy=True, inverse='set_final_document',
                                     default=40.0)
    weekly_work_hours_computed = fields.Float(string='Valandų skaičius per savaitę', readonly=True,
                                              compute='_weekly_work_hours_computed')
    current_salary = fields.Float(string='Dabartinis darbo užmokestis (prieš dokumento pasirašymą)',
                                  compute='get_current_salary')
    current_salary_recalculated = fields.Float(string='Dabartinis darbo užmokestis (pagal etatą)',
                                               compute='compute_etatas')
    salary_diff = fields.Float(compute='set_salary_diff', string='Darbo užmokesčio skirtumas')
    work_norm = fields.Float(string='Darbo normos koeficientas (pagal profesiją)', default=1.0, readonly=True,
                             states={'draft': [('readonly', False)]}, inverse='set_final_document')
    failed_workflow = fields.Boolean(string='Nepavykusi darbo eiga', readonly=True, default=False, copy=False)
    display_warning_decorator = fields.Boolean(compute='do_display_warning_decorator')
    weekly_work_days_computed = fields.Integer(compute='_weekly_work_days')
    darbo_grafikas_string = fields.Char(compute='_darbo_grafikas_string')
    extra_fields_visible = fields.Boolean(compute='_compute_extra_fields_visible')
    running = fields.Boolean('Pasirašinėjama', copy=False)

    appointment_id_computed = fields.Many2one('hr.contract.appointment', compute='_compute_appointment_id')
    contract_id_computed = fields.Many2one('hr.contract', compute='_compute_contract_id')
    job_id = fields.Many2one('hr.job', readonly=True, states={'draft': [('readonly', False)]},
                             inverse='set_final_document')
    new_appointment_created = fields.Boolean()
    date_end_change = fields.Boolean()
    marked_as_signed = fields.Boolean('Buvo pažymėtas kaip pasirašytas (nepasirašytas sistemoje)', default=False)
    holiday_days_text = fields.Char(compute='_compute_holiday_days_text')
    holiday_request_banner = fields.Boolean(compute='_holiday_request_banner')
    negative_holiday_banner = fields.Boolean(compute='_compute_negative_holiday_banner')
    employee_identification_id = fields.Char(compute='_compute_employee_identification_id')
    employee_street = fields.Char(compute='_compute_employee_street')
    lock_date = fields.Boolean(string='Neleisti keisti datos', readonly=True)
    enable_advance_setup = fields.Boolean(string='Leisti nustatyti avansą', readonly=True,
                                          default=default_advance_setup)
    advance_amount = fields.Float(string='Avanso dydis (neto)', digits=(2, 2), default=0.0)
    company_code = fields.Char(compute='_compute_company_code')
    company_address = fields.Char(compute='_compute_company_address')
    topic = fields.Char(string='Tema')
    invite_to_sign_new_users = fields.Boolean(string='Kviesti pasirašyti naujus darbuotojus', default=False)
    multi_user_state = fields.Selection([('none', 'Tuščia'), ('pending', 'Laukia pasirašymo'),
                                         ('signed', 'Pasirašyta')], string='Būsena', default='none',
                                        compute='_compute_multi_user_state', search='_search_multi_user_state')
    payslip_month = fields.Selection([('01', 'January'), ('02', 'February'), ('03', 'March'), ('04', 'April'),
                                      ('05', 'May'), ('06', 'June'), ('07', 'July'), ('08', 'August'),
                                      ('09', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')],
                                     string='Month of payslip to payout with',
                                     default=str(datetime.utcnow().month).zfill(2), readonly=True,
                                     states={'draft': [('readonly', False)]}, inverse='set_final_document')
    payslip_year_id = fields.Many2one('years', string='Year of payslip to payout with',
                                      default=_default_payslip_year_id, readonly=True,
                                      states={'draft': [('readonly', False)]}, inverse='set_final_document')
    show_wage_is_mma_warning = fields.Boolean(compute='_compute_show_wage_is_mma_warning')
    freeze_net_wage = fields.Selection([('true', 'Yes'), ('false', 'No')], string='Freeze NET wage', default='false',
                                     help="When enabled the employee's wage will be adjusted if the additional SODRA "
                                          "pension payment percentage changes", readonly=True,
                                     states={'draft': [('readonly', False)]}, inverse='set_final_document')
    last_message_sent = fields.Char(string='Last error message',
                                    help='Stores the last error message from workflow execution failure')
    min_e_document_time_line_date = fields.Date(compute='_compute_min_e_document_time_line_date')
    max_e_document_time_line_date = fields.Date(compute='_compute_max_e_document_time_line_date')
    current_user_department_delegate = fields.Boolean(compute='_compute_current_user_department_delegate',
                                                      search='_search_current_user_department_delegate', default=False)
    show_reset_running_button = fields.Boolean(compute='_compute_show_reset_running_button')
    min_date_from = fields.Date(compute='_compute_min_max_dates')
    max_date_to = fields.Date(compute='_compute_min_max_dates')
    show_ending_fixed_term_contract_box = fields.Boolean(related='employee_id2.show_ending_fixed_term_contract_box')

    @api.multi
    @api.depends(lambda self: self._min_max_date_dependencies())
    def _compute_min_max_dates(self):
        return

    @api.multi
    def _min_max_date_dependencies(self):
        return []

    @api.multi
    @api.depends('running', 'write_date')
    def _compute_show_reset_running_button(self):
        has_accountant_rights = self.env.user.is_accountant()
        minutes_after_to_show = 5  # Number of minutes after which to show the button if other conditions are met
        for rec in self:
            if not has_accountant_rights or not rec.running:
                rec.show_reset_running_button = False
                continue
            write_date = rec.write_date
            sufficient_time_elapsed_since_last_write_date = True
            if write_date:
                write_date_dt = datetime.strptime(write_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                now = datetime.now()
                deadline = write_date_dt + relativedelta(minutes=minutes_after_to_show)
                sufficient_time_elapsed_since_last_write_date = now >= deadline
            rec.show_reset_running_button = sufficient_time_elapsed_since_last_write_date

    @api.multi
    def reset_running(self):
        self.filtered(lambda doc: doc.show_reset_running_button).write({'running': False})

    @api.multi
    @api.depends('e_document_time_line_ids.date')
    def _compute_min_e_document_time_line_date(self):
        for rec in self:
            if rec.e_document_time_line_ids:
                rec.min_e_document_time_line_date = min(rec.e_document_time_line_ids.mapped('date'))

    @api.multi
    @api.depends('e_document_time_line_ids.date')
    def _compute_max_e_document_time_line_date(self):
        for rec in self:
            if rec.e_document_time_line_ids:
                rec.max_e_document_time_line_date = max(rec.e_document_time_line_ids.mapped('date'))

    @api.multi
    @api.depends('float_1', 'date_from', 'template_id', 'struct', 'du_input_type', 'date_5', 'date_3', 'darbo_grafikas',
                 'fixed_attendance_ids', 'etatas', 'du_input_type', 'employee_id2', 'struct', 'work_norm')
    def _compute_show_wage_is_mma_warning(self):
        template_date_mapping = {
            self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template').id: 'date_5',
            self.env.ref('e_document.isakymas_del_priemimo_i_darba_template').id: 'date_from',
            self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id: 'date_3',
        }
        documents = self.filtered(lambda doc: doc.template_id.id in template_date_mapping.keys() and
                                              doc.state in ['draft', 'confirm'])
        for doc in documents:
            date_field = template_date_mapping.get(doc.template_id.id)
            date = doc[date_field]
            if doc.du_input_type == 'neto':
                bruto = doc.wage_bruto
            else:
                bruto = doc.float_1
            if date and bruto:
                if not doc.struct or doc.struct.upper() == 'MEN':
                    mma_tax_field = 'mma'
                else:
                    mma_tax_field = 'min_hourly_rate'
                taxes = self.env['hr.contract'].with_context(date=date).sudo().get_payroll_tax_rates([mma_tax_field])
                etatas = doc.etatas_computed or doc.etatas or \
                         doc.employee_id2.sudo().with_context(date=date).appointment_id.schedule_template_id.etatas or \
                         1.0
                mma = taxes[mma_tax_field] * etatas if mma_tax_field == 'mma' else taxes[mma_tax_field]
                if tools.float_compare(mma, bruto, precision_digits=2) == 0:
                    doc.show_wage_is_mma_warning = True

    @api.one
    @api.depends('company_id')
    def _compute_company_code(self):
        self.company_code = self.env.user.sudo().company_id.partner_id.kodas

    @api.depends('extra_text')
    def _compute_extra_text_html(self):
        for rec in self.filtered(lambda a: a.extra_text):
            extra_text = ''
            single_line = '''<p>{0}</p>'''
            for line in rec.extra_text.split('\n'):
                extra_text += single_line.format(line)
            rec.extra_text_html = extra_text

    @api.one
    @api.depends('company_id')
    def _compute_company_address(self):
        company_partner = self.env.user.sudo().company_id.partner_id
        if company_partner:
            self.company_address = ', '.join(a for a in [company_partner.street, company_partner.city] if a)
        else:
            self.company_address = ''

    @api.one
    @api.depends('employee_id1', 'employee_id1.identification_id', 'employee_id2', 'employee_id2.identification_id')
    def _compute_employee_identification_id(self):
        identification_id = ''
        employee = self.employee_id1 if self.document_type == 'prasymas' else self.employee_id2
        if employee and (self.env.user.is_hr_manager() or self.env.user.is_premium_manager() or
                         self.env.user.is_free_manager() or
                         self.env.user.has_group('robo_basic.group_robo_edocument_manager')):
            identification_id = str(employee.sudo().identification_id or '')
        self.employee_identification_id = identification_id

    @api.one
    @api.depends('employee_id1', 'employee_id1.identification_id', 'employee_id2', 'employee_id2.street')
    def _compute_employee_street(self):
        street = ''
        employee = self.employee_id1 if self.document_type == 'prasymas' else self.employee_id2
        if employee and (self.env.user.is_hr_manager() or self.env.user.is_premium_manager() or
                         self.env.user.is_free_manager() or
                         self.env.user.has_group('robo_basic.group_robo_edocument_manager')):
            street = str(employee.sudo().street or '')
        self.employee_street = street

    @api.depends('user_ids')
    def _compute_multi_user_state(self):
        """
        Computes the state for documents that are signed by multiple users
        Field 'multi_user_state' is used only in the filter for now, this compute method is not triggered
        :return: None
        """
        state_mapping = {
            'draft': 'none',
            'cancel': 'none',
            'confirm': 'pending',
            'e_signed': 'signed'
        }
        SignedUsers = self.env['signed.users']
        current_user = self.env.user
        for rec in self:
            if rec.user_ids:
                signed_user = SignedUsers.search([('document_id', '=', rec.id), ('user_id', '=', current_user.id)])
                if not signed_user:
                    rec.multi_user_state = 'none'
                else:
                    rec.multi_user_state = signed_user.state
            else:
                rec.multi_user_state = state_mapping[rec.state]

    @api.one
    def _holiday_request_banner(self):
        company = self.sudo().env.user.company_id
        is_request = self.document_type == 'prasymas'
        send_manager = self.template_id.send_manager
        is_manager = company.vadovas.user_id.id == self.env.user.id
        department_manager_must_approve = self.politika_atostogu_suteikimas == 'department'
        not_approved_yet = self.sudo().approve_status == 'waiting_approval'

        is_delegate = is_department_delegate = False
        if not is_manager:
            user_employees = self.env.user.employee_ids
            if user_employees:
                user_employee = user_employees[0]
                today = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                department_id = self.employee_id1.department_id.id if is_request else False
                if department_id:
                    department_delegate_date = self.date_document or today
                    is_department_delegate = user_employee[0].is_department_delegate_at_date(department_id,
                                                                                             department_delegate_date)
                is_signable_by_delegate = self.is_signable_by_delegate()
                if is_signable_by_delegate:
                    delegate_date = self.reikia_pasirasyti_iki or today
                    is_delegate = user_employee[0].is_delegate_at_date(delegate_date)

        if is_request and send_manager and department_manager_must_approve and \
                (is_manager or is_delegate or is_department_delegate) and not_approved_yet:
            self.holiday_request_banner = True
        else:
            self.holiday_request_banner = False

    @api.multi
    @api.depends('date_from', 'date_to', 'employee_id1', 'employee_id2')
    def _compute_negative_holiday_banner(self):
        templates = [
            self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template').id,
            self.env.ref('e_document.prasymas_del_kasmetiniu_atostogu_template').id,
        ]
        for rec in self:
            if rec.template_id.id in templates and rec.date_from and rec.date_to:
                holidays_in_advance = rec.sudo().calculate_negative_holidays()[1]
                if self.env.user.company_id.accumulated_days_policy == 'allow':
                    if holidays_in_advance > 0:
                        rec.negative_holiday_banner = True
                else:
                    rec.negative_holiday_banner = False

    @api.multi
    @api.depends('employee_id1', 'employee_id2', 'date_from', 'date_to')
    def _compute_holiday_days_text(self):
        for rec in self:
            text = ''
            employee = rec.employee_id1 if rec.document_type == 'prasymas' else rec.employee_id2
            date_from, date_to = rec.date_from, rec.date_to
            if not employee or not date_from or not date_to:
                rec.holiday_days_text = text
                continue

            num_days = 0.0
            use_calendar_days = False

            appointments = self.env['hr.contract.appointment'].search([
                ('employee_id', '=', employee.id),
                ('date_start', '<=', date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', date_from)
            ])
            contracts = appointments.sudo().mapped('contract_id')
            if contracts:
                use_calendar_days = any(app.leaves_accumulation_type == 'calendar_days' for app in appointments)
                if use_calendar_days:
                    leaves_context = {
                        'force_use_schedule_template': True, 'do_not_use_ziniarastis': True,
                        'calculating_holidays': True
                    }
                else:
                    leaves_context = {'calculating_preliminary_holiday_duration': True}

                num_days = 0.0
                for contract in contracts:
                    date_from = max(contract.date_start, date_from)
                    date_to = min(contract.date_end or date_to, date_to)
                    num_days += contract.with_context(leaves_context).get_num_work_days(date_from, date_to)

            if tools.float_is_zero(num_days, precision_digits=2):
                num_days = self.env['hr.payroll'].sudo().with_context(
                    include_weekends=True
                ).standard_work_time_period_data(date_from, date_to).get('days', 0.0)

            if not tools.float_is_zero(num_days, precision_digits=2):
                if use_calendar_days:
                    if int(num_days) % 10 == 0 or (10 < int(num_days) % 100 < 20):
                        text = _('kalendorinių dienų')
                    elif int(num_days) % 10 == 1:
                        text = _('kalendorinę dieną')
                    else:
                        text = _('kalendorines dienas')
                else:
                    if int(num_days) % 10 == 0 or (10 < int(num_days) % 100 < 20):
                        text = _('darbo dienų')
                    elif int(num_days) % 10 == 1:
                        text = _('darbo dieną')
                    else:
                        text = _('darbo dienas')

            if not tools.float_is_zero(num_days, precision_digits=2):
                text = ' ({0} {1})'.format(int(num_days), text)
            rec.holiday_days_text = text

    @api.onchange('document_type', 'date_document', 'date_3', 'employee_id1', 'employee_id2')
    def get_selection_1(self):
        if self.enable_advance_setup:
            employee_id = self.employee_id2 if self.document_type == 'isakymas' else self.employee_id1
            if employee_id:
                appointment_date = self.date_3 if self.document_type == 'isakymas' and self.date_3 else self.date_document
                active_appointment = employee_id.with_context(date=appointment_date).appointment_id
                if active_appointment:
                    self.selection_1 = 'twice_per_month' if active_appointment.avansu_politika == 'fixed_sum' else 'once_per_month'

    @api.one
    def _inverse_check_attached_signed_document(self):
        if not self.env.user.is_accountant():
            raise exceptions.UserError(_('Negalite keisti prisegto pasirašyto failo, nes nesate buhalteris'))
        return True

    @api.multi
    @api.depends('document_type', 'employee_id1', 'employee_id2', 'template_id', 'e_document_line_ids.employee_id2',
                 'business_trip_employee_line_ids.employee_id', 'qualification_order_employee_lines')
    def _compute_related_employee_ids(self):
        bonus_doc = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template', raise_if_not_found=False)
        business_trip_doc = self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template',
                                         raise_if_not_found=False)
        cancellation_templates = [
            self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template'),
            self.env.ref('e_document.isakymas_del_susitarimo_nutraukimo_template')
        ]
        for rec in self:
            is_bonus_doc = bonus_doc and rec.template_id.id == bonus_doc.id
            is_trip_doc = business_trip_doc and rec.template_id.id == business_trip_doc.id
            is_qualification_doc = rec.is_qualification_improvement_doc()
            if is_bonus_doc:
                lines = rec.get_document_lines()
                rec.related_employee_ids = lines.mapped('employee_id2')
            elif is_trip_doc:
                rec.related_employee_ids = rec.business_trip_employee_line_ids.mapped('employee_id')
            elif is_qualification_doc:
                rec.related_employee_ids = rec.qualification_order_employee_lines.mapped('employee_id')
            elif rec.template_id in cancellation_templates:
                rec.related_employee_ids = (rec.cancel_id and rec.cancel_id.related_employee_ids) or rec.employee_id2
            elif rec.document_type == 'prasymas':
                rec.related_employee_ids = rec.employee_id1
            else:
                rec.related_employee_ids = rec.employee_id2

    def _search_related_employee_ids(self, operator, value):
        if operator != 'ilike':
            return [(0, '=', 1)]

        # Find the employee ids
        if isinstance(value, list):
            employee_ids = []
            for val in value:
                employee_ids += self.env['hr.employee'].with_context(active_test=False).sudo().search([
                    ('name', 'ilike', val),
                ]).mapped('id')
        else:
            employee_ids = self.env['hr.employee'].with_context(active_test=False).sudo().search([
                ('name', 'ilike', value),
            ]).mapped('id')
        if not employee_ids:
            return [(0, '=', 1)]

        document_ids = list()

        # Find cancelling documents
        cancel_template_ids = [
            self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template').id,
            self.env.ref('e_document.isakymas_del_susitarimo_nutraukimo_template').id,
        ]
        document_ids += self.env['e.document'].sudo().search([
            ('template_id', 'in', cancel_template_ids),
            ('cancel_id.employee_id2', 'in', employee_ids)
        ]).ids

        # Generate mapping for documents with document lines
        line_template_map = [
            {
                'template': self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template', False),
                'line_model': 'e.document.line',
                'employee_field': 'employee_id2',
            },
            {
                'template': self.env.ref('omnisend.isakymas_del_priedo_skyrimo_grupei_template', False),
                'line_model': 'omnisend.e.document.line',
                'employee_field': 'employee_id',
            },
            {
                'template': self.env.ref('e_document.isakymas_del_kvalifikacijos_tobulinimo_template', False),
                'line_model': 'e.document.qualification.order.employee.lines',
                'employee_field': 'employee_id',
                'document_relation': 'document_id',
            },
            {
                'template': self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template', False),
                'line_model': 'e.document.business.trip.employee.line',
                'employee_field': 'employee_id',
            },
        ]

        # Find documents based on employee set in document lines
        for line_template_data in line_template_map:
            template = line_template_data['template']
            if not template:
                continue
            document_relation = line_template_data.get('document_relation', 'e_document_id')
            full_template_relation = document_relation + '.template_id'
            line_model = line_template_data['line_model']
            document_ids += self.env[line_model].sudo().search([
                (full_template_relation, '=', template.id),
                (line_template_data['employee_field'], 'in', employee_ids)
            ]).mapped(document_relation).ids

        # Find other documents
        document_ids += self.env['e.document'].sudo().search([
            ('id', 'not in', document_ids),
            '|',
            '&',
            ('document_type', '=', 'prasymas'),
            ('employee_id1', 'in', employee_ids),
            '&',
            ('document_type', '!=', 'prasymas'),
            ('employee_id2', 'in', employee_ids)
        ]).ids

        document_ids = list(set(document_ids))
        return [('id', 'in', document_ids)]

    def _search_multi_user_state(self, operator, value):
        SignedUsers = self.env['signed.users']
        EDocument = self.env['e.document']
        current_user = self.env.user
        if operator == '=' and value == 'pending':
            doc_ids = SignedUsers.search([('user_id', '=', current_user.id), ('state', '=', 'pending')]).\
                mapped('document_id.id')
            doc_ids += EDocument.search([('state', '=', 'confirm'), ('user_ids', '=', False)]).ids
            return [('id', 'in', list(set(doc_ids)))]
        if operator == '=' and value == 'signed':
            doc_ids = SignedUsers.search([('user_id', '=', current_user.id), ('state', '=', 'signed')]). \
                mapped('document_id.id')
            doc_ids += EDocument.search([('state', '=', 'e_signed'), ('user_ids', '=', False)]).ids
            return [('id', 'in', list(set(doc_ids)))]
        return [('multi_user_state', operator, value)]

    @api.onchange('num_children', 'num_extra_days')
    def onchange_children(self):
        if self.num_children in ['1', '2'] and self.num_extra_days == '2':
            return {'warning': {'title': _('Įspėjimas'),
                                'message': _(
                                    'Negalite pasirinkti dviejų poilsio dienų jei auginate mažiau nei tris vaikus.')}}
        elif self.num_children == '1_under_12' and self.num_extra_days != '1':
            return {'warning': {'title': _('Įspėjimas'),
                                'message': _('Auginant vieną vaiką iki 12m. gali būti suteikiama tik viena poilsio '
                                             'diena kartą per 3 mėnesius.')}}

    @api.multi
    @api.constrains('num_extra_days')
    def constrains_children(self):
        for rec in self:
            if rec.num_children in ['1', '2'] and rec.num_extra_days == '2':
                raise exceptions.ValidationError(
                    _('Negalite pasirinkti dviejų poilsio dienų jei auginate mažiau nei tris vaikus.')
                )
            elif rec.num_children == '1_under_12' and rec.num_extra_days != '1':
                raise exceptions.ValidationError(
                    _('Auginant vieną vaiką iki 12m. gali būti suteikiama tik viena poilsio diena kartą per 3 mėnesius.')
                )

    @api.multi
    @api.constrains('enable_advance_setup', 'advance_amount', 'selection_1', 'document_type')
    def constrains_advance(self):
        for rec in self:
            if rec.enable_advance_setup and rec.document_type == 'isakymas' and \
                    rec.selection_1 == 'twice_per_month' and tools.float_compare(rec.advance_amount, 0, 2) <= 0:
                raise exceptions.UserError(_('Nurodytas avansas negali būti nulinis!\n'))

    @api.depends('employee_id2', 'date_3')
    def _compute_contract_id(self):
        for rec in self:
            if rec.employee_id2 and rec.date_3 and rec.employee_data_is_accessible():
                employee_contracts = rec.employee_id2.sudo().contract_ids.sorted(key='date_start', reverse=True)
                contract = employee_contracts.filtered(
                    lambda c: c.date_start <= rec.date_3 and (not c.date_end or c.date_end >= rec.date_3)).id
                # if not contract:
                #     contract = employee_contracts[0].id if employee_contracts else False
                rec.contract_id_computed = contract

    @api.multi
    @api.depends('contract_id_computed', 'date_3')
    def _compute_appointment_id(self):
        for rec in self:
            if rec.contract_id_computed and rec.date_3 and rec.employee_data_is_accessible():
                rec.appointment_id_computed = rec.contract_id_computed.with_context(date=rec.date_3).sudo().appointment_id.id

    @api.multi
    @api.constrains('bonus_input_type', 'bonus_type_selection')
    def _check_bonus_input_type_for_specific_bonus_types(self):
        priedo_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_template')
        priedo_grupei_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        for rec in self:
            is_priedo_doc = rec.template_id == priedo_template or rec.template_id == priedo_grupei_template
            if rec.bonus_input_type == 'neto' and rec.bonus_type_selection not in ['1men', 'ne_vdu'] and is_priedo_doc:
                raise exceptions.ValidationError(_(
                    'Negalima skirti priedo pagal NETO sumą už ilgesnį nei vieno mėnesio laikotarpį, dėl galimų netikslingų paskaičiavimų'))

    @api.onchange('bonus_input_type', 'bonus_type_selection')
    def _onchange_bonus_input_type_for_specific_bonus_types(self):
        priedo_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_template')
        priedo_grupei_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        is_priedo_doc = self.template_id == priedo_template or self.template_id == priedo_grupei_template
        if self.bonus_type_selection not in ['1men', 'ne_vdu'] and is_priedo_doc:
            self.bonus_input_type = 'bruto'

    @api.multi
    def get_formview_id(self):
        view_ref = self._context.get('form_view_ref', False)
        if view_ref:
            view_id = self.env.ref(view_ref, raise_if_not_found=False)
            if not view_id:
                view_id = self.env.ref(self._module + '.' + view_ref, raise_if_not_found=False)
            if view_id:
                return view_id.id
        else:
            rec = self[0]
            return rec.sudo().template_id.view_id.id
        return False

    @api.multi
    @api.constrains('darbo_grafikas', 'fixed_attendance_ids', 'etatas', 'weekly_work_hours', 'struct', 'work_norm')
    def _check_schedule_hours_less_than_work_hours(self):
        bypass = self._context.get('bypass_weekly_hours_mismatch_schedule')
        for rec in self:
            if rec.darbo_grafikas not in ['fixed', 'suskaidytos']:
                schedule_amount = sum(l.hour_to - l.hour_from for l in rec.fixed_attendance_ids)
                if not bypass and float_compare(schedule_amount, rec.weekly_work_hours_computed, precision_digits=2) > 0:
                    raise exceptions.UserError(
                        _('''Grafiko darbo laikas turi būti mažesnis arba lygus nustatytam darbo laikui pagal etatą, darbo laiko normą arba valandų skaičių per savaitę.
                        Pakeiskite darbo grafiką arba kitus darbo laiko nustatymus.''')
                    )

    @api.one
    @api.depends('employee_id2', 'struct', 'du_input_type')
    def get_current_salary(self):
        current_salary = 0.0
        if self.employee_id2 and (
                self.env.user.is_hr_manager() or self.env.user.is_premium_manager() or self.env.user.is_free_manager()):
            current_day = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            contract_id = self.sudo().env['hr.contract'].search([('employee_id', '=', self.employee_id2.id),
                                                                 ('date_start', '<', current_day), '|',
                                                                 ('date_end', '=', False),
                                                                 ('date_end', '>=', current_day)])
            if contract_id:
                appointment_id = contract_id.get_active_appointment()
                if appointment_id and self.state == 'e_signed':
                    appointment_id = self.env['hr.contract.appointment'].search(
                        [('employee_id', '=', appointment_id.employee_id.id),
                         ('date_end', '<', appointment_id.date_start)],
                        order='date_end desc', limit=1)
                if appointment_id:
                    if self.struct == 'MEN' and self.du_input_type != 'bruto':
                        current_salary = appointment_id.neto_monthly
                    elif self.struct == 'VAL':
                        current_salary = appointment_id.hypothetical_hourly_wage
                    else:
                        current_salary = appointment_id.wage
        self.current_salary = current_salary

    @api.model
    def server_action_download(self):
        action = self.env.ref('e_document.server_action_download_f')
        if action:
            action.create_action()

    @api.multi
    def download_multiple_pdfs(self):
        def format_file_name(name_values, file=None):
            file_name_values = [str(file_name_value) for file_name_value in name_values if file_name_value]
            file_name = ' '.join(file_name_values)
            if '.' not in file_name[:4]:
                if file:
                    mime = magic.Magic(mime=True)
                    mimetype = mime.from_buffer(file.decode('base64'))
                    extension = mimetypes.guess_extension(mimetype)
                else:
                    extension = '.pdf'
                file_name += extension
            file_name = file_name.replace("/", "")
            return file_name.decode('utf-8')

        DOCUMENT_LIMIT = 200  # Number of documents that can be downloaded in a single archive
        DOCUMENT_SIZE_LIMIT = 20  # Maximum size of the archive (in MB)

        files = []
        current_file_size = 0
        for rec in self.filtered(lambda d: d.generated_document):
            if len(files) > DOCUMENT_LIMIT or \
                    tools.float_compare(current_file_size, DOCUMENT_SIZE_LIMIT, precision_digits=2) > 0:
                break

            doc = rec.generated_document
            if self._context.get('force_no_mark'):
                result, fmt = self.env['ir.actions.report.xml'].with_context(
                    force_paperformat=self.paperformat_id, no_mark=True).render_report(rec._ids,
                                                                                       'e_document.general_print',
                                                                                       data=None)
                if fmt == 'pdf':
                    doc = result.encode('base64')
            if not doc:
                continue

            file_name_values = [
                rec.name or '',
                _('Nr. {}').format(rec.document_number) if rec.document_number and rec.document_number != '-' else None,
                rec.employee_id2.name or rec.employee_id1.name or '',
                rec.date_from_display or '',
                rec.date_to_display if rec.date_from_display != rec.date_to_display else '',
                rec.create_date if not rec.date_from_display and not rec.date_to_display else ''
            ]
            file_name = format_file_name(file_name_values, doc)
            files.append((file_name, doc))
            current_file_size += doc.decode('base64').__sizeof__() / 1024.0 / 1024.0  # P3:DivOK

            if rec.attached_signed_document:
                doc = rec.attached_signed_document
                file_name = rec.attached_signed_document_filename
                if not file_name:
                    file_name_values = [_('Attached signed document')] + file_name_values
                    file_name = format_file_name(file_name_values, doc)
                files.append((file_name, doc))
                current_file_size += doc.decode('base64').__sizeof__() / 1024.0 / 1024.0  # P3:DivOK

        if not files:
            raise exceptions.UserError(_('There are no files that can be downloaded.'))

        mem_zip = BytesIO()

        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.writestr(f[0], f[1].decode('base64'))

        company = self.env.user.company_id
        filename = _('[{}] RoboLabs e-Dokumentai {}').format(
            self.env.cr.dbname,
            datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        ) + '.zip'
        attach_id = self.env['ir.attachment'].sudo().create({
            'res_model': 'res.company',
            'res_id': company.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': mem_zip.getvalue().encode('base64'),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=res.company&res_id=%s&attach_id=%s' % (company.id, attach_id.id),
            'target': 'current',
        }

    @api.multi
    def action_download(self):
        if len(self) > 1:
            return self.download_multiple_pdfs()
        for rec in self:
            if rec.generated_document:
                doc = rec.generated_document
                if self._context.get('force_no_mark'):
                    result, fmt = self.env['ir.actions.report.xml'].with_context(
                        force_paperformat=self.paperformat_id, no_mark=True).render_report(rec._ids,
                                                                                           'e_document.general_print',
                                                                                           data=None)
                    if fmt == 'pdf':
                        doc = result.encode('base64')
                attach_id = self.env['ir.attachment'].create({
                    'res_model': 'e.document',
                    'res_id': rec.id,
                    'type': 'binary',
                    'name': rec.file_name,
                    'datas_fname': rec.file_name,
                    'datas': doc,
                })
                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/binary/download?res_model=e.document&res_id=%s&attach_id=%s' % (
                        rec.id, attach_id.id),
                    'target': 'current',
                }

    @api.multi
    def action_download_signing_summary(self):
        for rec in self:
            result, fmt = self.env['ir.actions.report.xml'].with_context(
                force_paperformat=self.paperformat_id, no_mark=True).render_report(rec._ids,
                                                                                   'e_document.signing_summary',
                                                                                   data=None)
            if fmt == 'pdf':
                doc = result.encode('base64')
            attach_id = self.env['ir.attachment'].create({
                'res_model': 'e.document',
                'res_id': rec.id,
                'type': 'binary',
                'name': 'dokumentas.pdf',
                'datas_fname': 'dokumentas.pdf',
                'datas': doc,
            })
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/binary/download?res_model=e.document&res_id=%s&attach_id=%s' % (rec.id, attach_id.id),
                'target': 'self',
            }

    @api.multi
    def inform_users(self, users):
        partner_ids = set()
        partner_ids.update(users.mapped('partner_id.id'))
        partner_ids = list(partner_ids)
        for rec in self:
            doc_name = rec.name or rec.name_force or _('Dokumentas')
            try:
                doc_url = rec._get_document_url()
                if doc_url:
                    doc_name = '<a href=%s>%s</a>' % (doc_url, doc_name)
            except:
                pass
            msg = dict(body=_('Laukiantis pasirašymo dokumentas "%s".') % doc_name,
                       subject=_('Dokumentas pasirašymui'), priority='high', front_message=True,
                       rec_model='e.document', rec_id=rec.id,
                       view_id=self.env.ref('e_document.general_document_view').id)
            msg['partner_ids'] = partner_ids
            rec.robo_message_post(**msg)

    @api.one
    @api.depends('template_id')
    def _compute_extra_fields_visible(self):
        self.extra_fields_visible = self.env.user.has_group('e_document.e_document_group_extra_fields')

    @api.one
    @api.depends('darbo_grafikas')
    def _darbo_grafikas_string(self):
        self.darbo_grafikas_string = dict(self._fields['darbo_grafikas'].selection).get(self.darbo_grafikas) or _(
            'Nekintančio darbo laiko režimas')

    @api.one
    @api.depends('template_id', 'darbo_grafikas', 'fixed_attendance_ids')
    def _weekly_work_days(self):
        days = 5
        du_templates = [
            self.env.ref('e_document.isakymas_del_priemimo_i_darba_template').id
        ]
        if self.template_id.id in du_templates:
            if self.darbo_grafikas in ['fixed', 'suskaidytos']:
                days = len(set(self.fixed_attendance_ids.mapped('dayofweek')))
        self.weekly_work_days_computed = days

    @api.multi
    def check_dates_of_prasymas_isakymas_to_be_the_same(self):
        self.ensure_one()
        source_document = self.search([('record_id', '=', self.id), ('record_model', '=', 'e.document')], limit=1)
        this_document_dates = []
        prasymas_document_dates = []

        def get_dates_from_documents_for_check():
            # TODO ADD MODE IF NECESSARY
            mamadienio_isakymas = self.env.ref('e_document.isakymas_del_mamadienio_/_tevadienio_suteikimo_template').id
            mamadienio_prasymas = self.env.ref('e_document.prasymas_del_mamadienio_/_tevadienio_suteikimo_template').id

            kvalifikacijos_isakymas = self.env.ref('e_document.isakymas_del_kvalifikacijos_kelimo_template').id
            kvalifikacijos_prasymas = self.env.ref('e_document.prasymas_del_kvalifikacijos_kelimo_template').id

            nutraukimo_isakymas = self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template').id
            nutraukimo_prasymas = self.env.ref('e_document.prasymas_del_darbo_sutarties_nutraukimo_template').id

            date_from_date_to_isakymai = [
                self.env.ref('e_document.isakymas_del_nestumo_ir_gimdymo_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_papildomu_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_nemokamu_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_leidimo_neatvykti_i_darba_template').id,
                self.env.ref('e_document.isakymas_del_3_menesiu_atostogu_vaikui_priziureti_suteikimo_template').id,
                self.env.ref('e_document.isakymas_del_kurybiniu_atostogu_suteikimo_template').id,
                self.env.ref('e_document.isakymas_del_mokymosi_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_komandiruotes_template').id,
                self.env.ref(
                    'e_document.isakymas_del_mokymosi_atostogu_dalyvauti_neformaliojo_suaugusiuju_svietimo_programose_template').id,
                self.env.ref('e_document.isakymas_del_papildomu_atostogu_template').id,
                self.env.ref('e_document.isakymas_del_tevystes_atostogu_suteikimo_template').id,
                self.env.ref('e_document.isakymas_del_neatvykimo_i_darba_darbdaviui_leidus_template').id
            ]

            date_from_date_to_prasymai = [
                self.env.ref('e_document.prasymas_del_nestumo_ir_gimdymo_atostogu_template').id,
                self.env.ref('e_document.prasymas_del_kasmetiniu_atostogu_template').id,
                self.env.ref('e_document.prasymas_del_papildomu_atostogu_template').id,
                self.env.ref('e_document.prasymas_del_nemokamu_atostogu_suteikimo_template').id,
                self.env.ref('e_document.prasymas_del_vaiko_prieziuros_atostogu_suteikimo_template').id,
                self.env.ref('e_document.prasymas_leisti_neatvykti_i_darba_template').id,
                self.env.ref('e_document.prasymas_suteikti_3_menesiu_atostogas_vaikui_priziureti_template').id,
                self.env.ref('e_document.prasymas_suteikti_kurybines_atostogas_template').id,
                self.env.ref('e_document.prasymas_suteikti_mokymosi_atostogas_template').id,
                self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template').id,
                self.env.ref(
                    'e_document.prasymas_suteikti_mokymosi_atostogas_dalyvauti_neformaliojo_suaugusiuju_svietimo_programose_template').id,
                self.env.ref('e_document.prasymas_del_papildomu_atostogu_template').id,
                self.env.ref('e_document.prasymas_suteikti_tevystes_atostogas_template').id,
            ]

            self_tmpl_id = self.template_id.id
            src_tmpl_id = source_document.template_id.id
            if self_tmpl_id == mamadienio_isakymas and src_tmpl_id == mamadienio_prasymas:
                if self.date_4 == source_document.date_2:
                    this_document_dates.append(self.date_4)
                else:
                    this_document_dates.append(self.date_3)
                prasymas_document_dates.append(source_document.date_2)
            elif self_tmpl_id in date_from_date_to_isakymai and src_tmpl_id in date_from_date_to_prasymai:
                this_document_dates.append(self.date_from)
                this_document_dates.append(self.date_to)
                prasymas_document_dates.append(source_document.date_from)
                prasymas_document_dates.append(source_document.date_to)
            elif self_tmpl_id == kvalifikacijos_isakymas and src_tmpl_id == kvalifikacijos_prasymas:
                this_document_dates.append(self.date_3)
                prasymas_document_dates.append(source_document.date_3)
            elif self_tmpl_id == nutraukimo_isakymas and src_tmpl_id == nutraukimo_prasymas:
                this_document_dates.append(self.date_1)
                prasymas_document_dates.append(source_document.date_1)

        if source_document:
            record_template_id = source_document.template_id.id
        else:
            record_template_id = None

        if record_template_id:
            get_dates_from_documents_for_check()
            for i in range(0, len(this_document_dates)):
                if this_document_dates[i] and prasymas_document_dates[i] and this_document_dates[i] != \
                        prasymas_document_dates[i]:
                    return False
        return True

    @api.one
    @api.depends('failed_workflow')
    def do_display_warning_decorator(self):
        if self.failed_workflow and self.env.user.is_accountant():
            self.display_warning_decorator = True
        else:
            self.display_warning_decorator = False

    @api.onchange('fixed_attendance_ids')
    def set_schedule_as_custom(self):
        if self.fixed_schedule_template != 'custom':
            line_amount = len(self.fixed_attendance_ids)
            start_hours = list(set(self.fixed_attendance_ids.mapped('hour_from')))
            end_hours = list(set(self.fixed_attendance_ids.mapped('hour_to')))
            days_match = set(self.fixed_attendance_ids.mapped('dayofweek')) == set(['0', '1', '2', '3', '4'])

            template_exists = False
            if days_match:
                if len(start_hours) == 1 and len(end_hours) == 1:
                    if float_compare(start_hours[0], 8.0, precision_digits=2) == 0 and any(
                            float_compare(hour, end_hours[0], precision_digits=2) == 0 for hour in
                            [14.0, 12.0, 10.0]) and line_amount == 5:
                        template_exists = True
                elif len(start_hours) == 2 and len(end_hours) == 2:
                    start_hours_match = (any(
                        float_compare(hour, start_hours[0], precision_digits=2) == 0 for hour in [8.0, 13.0]) and any(
                        float_compare(hour, start_hours[1], precision_digits=2) == 0 for hour in [8.0, 13.0])) or (any(
                        float_compare(hour, start_hours[0], precision_digits=2) == 0 for hour in [9.0, 13.0]) and any(
                        float_compare(hour, start_hours[1], precision_digits=2) == 0 for hour in [9.0, 13.0]))
                    end_hours_match = (any(
                        float_compare(hour, end_hours[0], precision_digits=2) == 0 for hour in [12.0, 17.0]) and any(
                        float_compare(hour, end_hours[1], precision_digits=2) == 0 for hour in [12.0, 17.0])) or (any(
                        float_compare(hour, end_hours[0], precision_digits=2) == 0 for hour in [12.0, 18.0]) and any(
                        float_compare(hour, end_hours[1], precision_digits=2) == 0 for hour in [12.0, 18.0]))
                    if start_hours_match and end_hours_match and line_amount == 10:
                        template_exists = True
            if not template_exists:
                self.fixed_schedule_template = 'custom'

    @api.multi
    @api.constrains('weekly_work_hours')
    def sane_number_of_weekly_hours(self):
        for rec in self:
            max_hrs = 40.0 if not rec.darbo_grafikas == 'sumine' else 52.0
            if not max_hrs >= rec.weekly_work_hours > 0:
                raise exceptions.UserError(_('Valandų per savaitę skaičius turi būti tarp 0 ir %s') % max_hrs)

    @api.multi
    @api.constrains('date_from', 'date_to', 'date_5', 'date_6')
    def date_constrains(self):
        business_trip_doc_ids = [
            self.env.ref('e_document.isakymas_del_komandiruotes_template').id,
            self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template').id,
        ]
        du_doc_id = self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template').id
        for rec in self:
            if rec.template_id.id in business_trip_doc_ids:
                if rec.date_from and rec.date_to:
                    date_from_dt = datetime.strptime(rec.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_to_dt = datetime.strptime(rec.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if (date_to_dt - date_from_dt).days < 0:
                        raise exceptions.ValidationError(
                            _('Data nuo negali būti vėlesnė už datą iki.')
                        )
            if rec.template_id.id == du_doc_id:
                if rec.date_5 and rec.date_6:
                    date_from_dt = datetime.strptime(rec.date_5, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_to_dt = datetime.strptime(rec.date_6, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_from_dt >= date_to_dt:
                        raise exceptions.ValidationError(
                            _('Sutarties pabaiga turi būti vėlesnė už sutarties pradžią.')
                        )

    @api.one
    @api.depends('darbo_grafikas', 'fixed_attendance_ids', 'etatas', 'weekly_work_hours', 'struct')
    def _weekly_work_hours_computed(self):
        if self.darbo_grafikas not in ['fixed', 'suskaidytos']:
            base = self.etatas * 40.0 * self.work_norm
        else:
            # Regular compute method does not work correctly here at this point (?due to newid objects?)
            line_time_total = sum(
                [a.hour_to - a.hour_from if a.hour_from and a.hour_to else 0.0 for a in self.fixed_attendance_ids])
            base = line_time_total
        weekly_work_hours = base
        self.weekly_work_hours_computed = round(weekly_work_hours, 2)

    @api.onchange('employee_id2')
    def get_sumine_appointment_values(self):
        if self.template_id.id == self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template').id:
            self.job_id4 = self.employee_id2.job_id
        elif self.template_id.id == self.env.ref('e_document.isakymas_del_priemimo_i_darba_template').id:
            self.work_norm = self.sudo().employee_id2.job_id.work_norm if self.sudo().employee_id2 else 1.0

    @api.one
    @api.depends('darbo_grafikas')
    def _get_show_values(self):
        self.show_weekly_work_hours = False
        self.show_fixed_attendance_lines = True
        self.show_etatas_computed = self.darbo_grafikas in ['fixed', 'suskaidytos']
        self.show_weekly_work_hours_computed = self.darbo_grafikas in ['fixed', 'suskaidytos', 'lankstus']
        self.show_etatas = self.darbo_grafikas in ['sumine', 'lankstus', 'individualus']

    @api.onchange('darbo_grafikas', 'etatas', 'weekly_work_hours', 'struct', 'work_norm')
    def _update_schedule_template(self):
        if self.darbo_grafikas not in ['fixed', 'suskaidytos']:
            schedule_amount = sum(l.hour_to - l.hour_from for l in self.fixed_attendance_ids)
            if float_compare(schedule_amount, self.weekly_work_hours_computed, precision_digits=2) > 0:
                self.fixed_schedule_template = 'custom'

    @api.onchange('fixed_schedule_template')
    def set_schedule_template(self):
        if self.fixed_schedule_template != 'custom':
            if self.fixed_schedule_template == '8_hrs_5_days':
                hour_from = 8.0
                hour_to = 12.0
                hour_from_1 = 13.0
                hour_to_1 = 17.0
            elif self.fixed_schedule_template == '8_hrs_5_days_from_9':
                hour_from = 9.0
                hour_to = 12.0
                hour_from_1 = 13.0
                hour_to_1 = 18.0
            elif self.fixed_schedule_template == '6_hrs_5_days':
                hour_from = 8.0
                hour_to = 14.0
            elif self.fixed_schedule_template == '4_hrs_5_days':
                hour_from = 8.0
                hour_to = 12.0
            elif self.fixed_schedule_template == '2_hrs_5_days':
                hour_from = 8.0
                hour_to = 10.0
            else:
                hour_from = 8.0
                hour_to = 12.0
                hour_from_1 = 13.0
                hour_to_1 = 17.0

            ids = []
            if self.fixed_schedule_template in ['6_hrs_5_days', '4_hrs_5_days', '2_hrs_5_days']:
                for i in range(0, 5):
                    ids.append((0, 0, {
                        'hour_from': hour_from,
                        'hour_to': hour_to,
                        'dayofweek': str(i)
                    }))
            else:
                for i in range(0, 5):
                    ids.append((0, 0, {
                        'hour_from': hour_from,
                        'hour_to': hour_to,
                        'dayofweek': str(i)
                    }))
                    ids.append((0, 0, {
                        'hour_from': hour_from_1,
                        'hour_to': hour_to_1,
                        'dayofweek': str(i)
                    }))
            self.write({'fixed_attendance_ids': [(5,)] + ids})

    @api.onchange('date_document', 'date_from', 'date_1', 'date_2', 'date_to')
    def date_checks(self):
        def _strp(date):
            return datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)

        if self.template_id.id == self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template').id \
                and self.date_document and self.date_1:
            date_dt = datetime.strptime(self.date_document, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_now = datetime.utcnow()
            if date_now > date_dt:
                date_dt = date_now
            date_dt_to = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            if (date_dt - date_dt_to).days > 0:
                return {'warning': {'title': _('Įspėjimas'),
                                    'message': _('Įsakymo data turi būti ne vėlesnė kaip atleidimo diena.')}}

        if self.template_id.id in [self.env.ref('e_document.isakymas_del_komandiruotes_template').id,
                                   self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template').id]:
            if self.date_from and self.date_to:
                date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
                if (date_to_dt - date_from_dt).days < 0:
                    return {'warning': {'title': _('Įspėjimas'),
                                        'message': _('Data nuo negali būti vėlesnė už datą iki.')}}

        fatherly_holiday_request_template = self.env.ref('e_document.prasymas_suteikti_tevystes_atostogas_template').id
        fatherly_holiday_order_template = self.env.ref(
            'e_document.isakymas_del_tevystes_atostogu_suteikimo_template').id
        if self.template_id.id in [fatherly_holiday_order_template, fatherly_holiday_request_template]:
            if self.date_from and self.date_to:
                duration = (_strp(self.date_to) - _strp(self.date_from)).days + 1
                if duration > 30:
                    return {'warning': {'title': _('Įspėjimas'),
                                        'message': _('Tėvystės atostogų trukmė negali viršyti 30 dienų')}}

    @api.constrains('float_1', 'work_norm', 'etatas')
    def du_constrains(self):
        self.check_mma_constraint()

    @api.one
    def check_mma_constraint(self):
        ext_id_date_mapping = {
            'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template': self.date_3,
            'e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template': self.date_5,
            'e_document.isakymas_del_priemimo_i_darba_template': self.date_from,
        }
        # Ref those external ids to templates
        template_date_mapping = {}
        for (ext_id, date) in iteritems(ext_id_date_mapping):
            template_date_mapping.update({self.env.ref(ext_id, raise_if_not_found=False): date})

        if self.template_id in template_date_mapping:
            # We don't allow setting NET salary for hourly structure
            if self.du_input_type == 'bruto' or self.struct != 'MEN':
                bruto_wage = self.float_1
            else:
                bruto_wage = self.sudo().wage_bruto
                if tools.float_is_zero(bruto_wage, precision_digits=2): return
            minimum_wage_field = 'mma' if self.struct == 'MEN' else 'min_hourly_rate'
            date_to_use = template_date_mapping.get(self.template_id) or \
                          datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            mma = self.env['hr.contract'].with_context(date=date_to_use).sudo().get_payroll_tax_rates([minimum_wage_field])
            mma = mma[minimum_wage_field]
            if self.struct == 'MEN':
                etatas = self.etatas if self.darbo_grafikas not in ['fixed', 'suskaidytos'] else self.etatas_computed
                salary_change_template = self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template')
                if self.template_id == salary_change_template:
                    appointment = self.sudo().employee_id2.with_context(date=date_to_use).appointment_id
                    etatas = appointment.schedule_template_id.etatas or 1.0
                mma *= etatas
            mma = round(mma, 2)
            if float_compare(bruto_wage, mma, precision_digits=2) == -1:
                raise exceptions.UserError(_('Minimalus darbo užmokestis nustatytam etatui yra per mažas!\n Minimalus '
                                             'darbo užmokestis: %s') % mma)

    @api.multi
    @api.constrains('etatas')
    def etatas_values_1_0(self):
        for rec in self:
            if rec.darbo_grafikas not in ['fixed', 'suskaidytos'] and rec.struct == 'MEN':
                if not (1.5 >= rec.etatas > 0.0) or float_is_zero(rec.etatas, precision_digits=2):
                    raise exceptions.UserError(_('Nustatyta netinkama etato dalis, etatas turi būti tarp 0 ir 1.5'))

    @api.one
    @api.depends('darbo_grafikas', 'fixed_attendance_ids', 'etatas', 'du_input_type', 'employee_id2', 'struct',
                 'work_norm')
    def compute_etatas(self):
        if self.darbo_grafikas in ['fixed', 'suskaidytos']:
            etatas = sum(line.hour_to - line.hour_from for line in self.fixed_attendance_ids) / 40.0  # P3:DivOK
            if not tools.float_is_zero(self.work_norm, precision_digits=2):
                etatas /= self.work_norm  # P3:DivOK
        else:
            etatas = self.etatas
        self.etatas_computed = round(etatas, 5)
        self.current_salary_recalculated = self.current_salary * round(etatas, 5)

    @api.onchange('date_from', 'date_to')
    def _get_holiday_dates(self):
        text = ""
        self.holiday_dates = text
        if self.date_from and self.date_to:
            date = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            holidays = self.env['sistema.iseigines'].search(
                [('date', '<=', self.date_to), ('date', '>=', self.date_from)])
            while date <= date_to:
                holiday = holidays.filtered(
                    lambda r: r['date'] == date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) and True or False
                if holiday or date.weekday() in [5, 6]:
                    if len(text) != 0:
                        text += ', '
                    text += str(date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))
                date = date + relativedelta(days=1)
            self.holiday_dates = text

    @api.one
    @api.depends('date_from', 'date_to')
    def _dates_contain_weekends(self):
        self.dates_contain_weekend = False
        if self.date_from and self.date_to:
            date = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            holidays = self.env['sistema.iseigines'].search(
                [('date', '<=', self.date_to), ('date', '>=', self.date_from)])
            while date <= date_to:
                holiday = holidays.filtered(
                    lambda r: r['date'] == date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) and True or False
                if holiday or date.weekday() in [5, 6]:
                    self.dates_contain_weekend = True
                    break
                date = date + relativedelta(days=1)

    @api.depends('business_trip_worked_on_weekends', 'dates_contain_weekend', 'employee_id2', 'date_from', 'date_to')
    def _show_extra_komandiruotes_text(self):
        order_template = self.env.ref('e_document.isakymas_del_komandiruotes_template', False)
        request_template = self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template', False)
        for rec in self:
            rec.extra_business_trip_weekend_text = ""
            if rec.template_id == order_template:
                if rec.dates_contain_weekend and rec.business_trip_worked_on_weekends == 'true' and rec.employee_id2:
                    name = rec.employee_id2.display_name
                    name_ko = rec.linksnis(name, 'ko')
                    name_ka = rec.linksnis(name, 'ka')
                    rec.extra_business_trip_weekend_text = "Esant darbuotojo " + name_ko + " sutikimui/prašymui, skiriu " + name_ka + " dirbti poilsio dienomis (" + rec.holiday_dates + "). "
            elif rec.template_id == request_template:
                if rec.dates_contain_weekend and rec.business_trip_worked_on_weekends == 'true':
                    rec.extra_business_trip_weekend_text = "Prašau leisti dirbti poilsio dienomis (" + rec.holiday_dates + ")"

    @api.one
    @api.depends('employee_id2', 'e_document_line_ids')
    def do_show_annotation(self):
        if self.template_id.id == self.env.ref('e_document.isakymas_del_komandiruotes_template').id:
            if self.employee_id2.id == self.env.user.company_id.vadovas.id:
                self.show_annotation = True
            else:
                self.show_annotation = False
        elif self.template_id.id == self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template').id:
            employee_ids = self.e_document_line_ids.mapped('employee_id2')
            if self.env.user.company_id.vadovas.id in employee_ids.ids:
                self.show_annotation = True
            else:
                self.show_annotation = False
        else:
            self.show_annotation = False

    @api.depends('template_id')
    def _compute_do_show_user(self):
        create_others = self.env.ref('robo_basic.group_robo_create_on_behalf')
        if create_others.id in self.env.user.groups_id.ids:
            for rec in self:
                rec.show_user = True

    @api.depends('darbo_rusis')
    def _terminuota_sutartis(self):
        for rec in self.filtered(lambda d: d.darbo_rusis in
                                           ['terminuota', 'laikina_terminuota', 'pameistrystes', 'projektinio_darbo']):
            rec.terminuota_sutartis = True

    @api.one
    def _signed_multiple(self):
        sign_line_id = self.user_ids.filtered(lambda r: r.user_id.id == self.env.user.id)
        if sign_line_id and sign_line_id.state == 'signed':
            self.signed_multiple = True

    @api.depends('locked')
    def _hide_view(self):
        is_accountant =  self.env.user.is_accountant()
        for rec in self:
            if rec.locked and not is_accountant:
                rec.hide_view = True
            else:
                rec.hide_view = False

    @api.depends('employee_id1')
    def _show_cancel_request(self):
        for rec in self:
            if rec.employee_id1.user_id.id == self.env.user.id:
                rec.show_cancel_request = True
            else:
                rec.show_cancel_request = False

    @api.one
    def _allow_approve(self):
        user = self.env.user
        is_request = self.document_type == 'prasymas'
        user_employees = user.employee_ids
        employee = self.employee_id1 if is_request else False
        is_delegate = is_department_delegate = False
        is_signable_by_delegate = self.is_signable_by_delegate()
        if user_employees:
            user_employee = user_employees[0]
            today = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            delegate_date = self.reikia_pasirasyti_iki or today
            is_delegate = user_employee.is_delegate_at_date(delegate_date)
            department_id = employee.department_id.id if employee else False
            if department_id:
                department_delegate_date = self.date_document or today
                is_department_delegate = user_employee.is_department_delegate_at_date(department_id,
                                                                                      department_delegate_date)

        document_employee_is_user = employee.id in user_employees.ids if user_employees and employee else False
        # Check user rights
        is_allowed = (is_delegate and is_signable_by_delegate) or \
                     (not is_delegate and ((employee and (employee.department_id.manager_id.user_id == self.env.user
                                                          or is_department_delegate)) or self.env.user.is_manager()
                                           or (self.env.user.is_hr_manager() and not document_employee_is_user)))
        if is_request and self.template_id.send_manager and self.politika_atostogu_suteikimas == 'department' and \
                not self.rejected and self.state == 'e_signed' and is_allowed:
            self.allow_approve = True
        else:
            self.allow_approve = False

    @api.one
    def _allow_reject(self):
        is_request = self.document_type == 'prasymas'
        user_employees = self.env.user.employee_ids
        employee = self.employee_id1 if is_request else False
        is_delegate = is_department_delegate = False
        is_signable_by_delegate = self.is_signable_by_delegate()
        if user_employees:
            user_employee = user_employees[0]
            today = datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            delegate_date = self.reikia_pasirasyti_iki or today
            is_delegate = user_employee.is_delegate_at_date(delegate_date)
            department_id = employee.department_id.id if employee else False
            if department_id:
                department_delegate_date = self.date_document or today
                is_department_delegate = user_employee.is_department_delegate_at_date(department_id,
                                                                                      department_delegate_date)

        document_employee_is_user = employee.id in user_employees.ids if user_employees and employee else False
        # Check user rights
        is_allowed = (is_delegate and is_signable_by_delegate) or \
                     (not is_delegate and ((employee and (employee.department_id.manager_id.user_id == self.env.user
                                                          or is_department_delegate)) or self.env.user.is_manager()
                                           or (self.env.user.is_hr_manager() and not document_employee_is_user)))
        if is_request and self.template_id.send_manager and self.politika_atostogu_suteikimas == 'department' \
                and self.state == 'e_signed' and not self.rejected and is_allowed:
            related_order = self.get_related_order()
            if related_order and related_order.state == 'e_signed':
                self.allow_reject = False
            else:
                self.allow_reject = True
        else:
            self.allow_reject = False

    @api.one
    @api.depends('cancel_id')
    def _cancel_data(self):
        if self.cancel_id:
            self.cancel_name = self.cancel_id.template_id.name
            self.cancel_date = self.cancel_id.date_signed
            self.cancel_number = self.cancel_id.document_number
            try:
                root = etree.fromstring(self.cancel_id.final_document, parser=etree.XMLParser(recover=True))
                if type(root) != etree._Element:
                    self.cancel_body = str()
                else:
                    elem = root.xpath("//div[@id = 'body']")
                    if not elem:
                        elem = root.xpath("//div[@style = 'padding-left: 20px;']")
                    if elem:
                        self.cancel_body = ''.join(list(elem[0].itertext()))
            except etree.XMLSyntaxError:
                self.cancel_body = str()

    @api.depends('company_id')
    def _apskaitos_politika(self):
        company_id = self.env.user.sudo().company_id
        for rec in self:
            rec.politika_atostoginiai = company_id.politika_atostoginiai
            rec.politika_atostogu_suteikimas = company_id.politika_atostogu_suteikimas
            rec.holiday_policy_inform_manager = company_id.holiday_policy_inform_manager

    @api.multi
    @api.depends('document_type', 'employee_id1', 'employee_id2',
                 'business_trip_employee_line_ids.employee_id', 'e_document_line_ids', 'template_id')
    def _doc_partner_id(self):
        cancellation_templates = [
            self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template'),
            self.env.ref('e_document.isakymas_del_susitarimo_nutraukimo_template')
        ]
        free_form_document_template = self.env.ref('e_document.laisvos_formos_dokumentas_template')
        business_trip_document_template = self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template')
        business_trip_group_document_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        asset_lease_template = self.env.ref('e_document.asset_lease_agreement_template', False)
        for rec in self:
            if rec.document_type == 'prasymas' or rec.template_id == free_form_document_template:
                rec.doc_partner_id = rec.employee_id1.address_home_id.id
            else:
                if rec.template_id == business_trip_document_template and rec.business_trip_employee_line_ids and \
                        len(rec.business_trip_employee_line_ids) == 1:
                    rec.doc_partner_id = rec.business_trip_employee_line_ids.employee_id.address_home_id.id
                elif rec.template_id == business_trip_group_document_template:
                    lines = rec.get_document_lines()
                    if lines and len(lines) == 1:
                        rec.doc_partner_id = lines.employee_id2.address_home_id.id
                    elif rec.doc_partner_id:
                        rec.doc_partner_id = None
                elif rec.template_id in cancellation_templates:
                    related_employees = (rec.cancel_id and rec.cancel_id.related_employee_ids) or rec.employee_id2
                    if related_employees and len(related_employees) > 1:
                        related_employee = None
                    else:
                        related_employee = related_employees[0]
                    rec.doc_partner_id = related_employee and related_employee.address_home_id.id
                elif asset_lease_template and rec.template_id == asset_lease_template:
                    pass
                else:
                    rec.doc_partner_id = rec.employee_id2.address_home_id.id

    @api.multi
    @api.depends('template_id', 'date_from', 'date_time_from', 'date_1', 'date_2', 'date_3', 'date_4', 'date_5',
                 'document_type', 'state')
    def _compute_reikia_pasirasyti_iki(self):
        for rec in self:
            if rec.document_type != 'isakymas':
                continue
            if rec.state == 'cancel':
                rec.reikia_pasirasyti_iki = False
                continue
            date_lim_for_signing_field_name = rec.template_id.date_lim_for_signing_field_name
            if date_lim_for_signing_field_name:
                if date_lim_for_signing_field_name == '_use_immediate_date':
                    pass
                else:
                    rec.reikia_pasirasyti_iki = rec._prev_work_day(rec[rec.template_id.date_lim_for_signing_field_name])
            else:
                if rec.template_id.id == rec.env.ref('e_document.isakymas_del_poilsio_dienos_perkelimo_template').id:
                    rec.reikia_pasirasyti_iki = min(rec['date_1'], rec['date_2'])
                elif rec.template_id.id == rec.env.ref(
                        'e_document.isakymas_del_mamadienio_/_tevadienio_suteikimo_template'
                ).id:
                    rec.reikia_pasirasyti_iki = min(rec['date_3'], rec['date_4']) if rec['num_extra_days'] == '2' else rec['date_3']

            if not rec.reikia_pasirasyti_iki:
                rec.reikia_pasirasyti_iki = datetime.utcnow()

            rec.env['e.document.delegate'].sudo().search([
                ('date_start', '<=', rec.reikia_pasirasyti_iki),
                ('date_stop', '>=', rec.reikia_pasirasyti_iki)
            ]).mapped('employee_id.user_id')._compute_delegated_document_ids()

    @api.onchange('country_allowance_id', 'template_id', 'num_calendar_days', 'date_from', 'date_to', 'int_1',
                  'employee_id2')
    def set_dienpinigiu_norma(self):
        if self._context.get('percentage', False):  # prevent endless onchange triggering
            if self.template_id.id == self.env.ref('e_document.isakymas_del_komandiruotes_template').id:
                self._num_calendar_days()
                if self.int_1 < 50:
                    if self.num_calendar_days == 1 and self.country_allowance_id.id == self.env.ref(
                            'l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False).id:
                        self.int_1 = 0
                    else:
                        self.int_1 = 50
                elif 200 >= self.int_1 > 100:
                    if self.employee_id2.id != self.env.user.company_id.vadovas.id:
                        self.int_1 = 100
                elif self.int_1 > 200:
                    if self.employee_id2.id != self.env.user.company_id.vadovas.id:
                        self.int_1 = 100
                    else:
                        self.int_1 = 200
                norma = self.int_1 / 100.0  # P3:DivOK

                if not self.num_calendar_days == 1 or not self.country_allowance_id.id == self.env.ref(
                        'l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False).id:
                    if tools.float_compare(norma, 0.5, precision_digits=2) == -1:
                        norma = 1.0
                        self.int_1 = 100
                self.float_1 = tools.float_round(
                    self.country_allowance_id.get_amount(self.date_from, self.date_to) * norma, precision_digits=2)

            elif self.country_allowance_id and self.template_id.id in [
                self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template').id,
                self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template').id
            ]:
                if self.e_document_line_ids:
                    self.set_dienpinigiu_norma()
                if self.business_trip_employee_line_ids:
                    for line in self.business_trip_employee_line_ids:
                        line._onchange_allowance_percentage_or_employee_id()

    @api.onchange('float_1')
    def allowance_limiter(self):
        if self.template_id.id == self.env.ref(
                'e_document.isakymas_del_komandiruotes_template').id and self.country_allowance_id:
            if self._context.get('norm', False):  # prevent endless onchange triggering
                country_allowance_amount = self.country_allowance_id.get_amount(self.date_from, self.date_to)
                mid_norm = tools.float_round(country_allowance_amount * 1, precision_digits=2)
                min_norm = tools.float_round(country_allowance_amount * 0.5, precision_digits=2)
                max_norm = tools.float_round(country_allowance_amount * 2, precision_digits=2)
                is_ceo = True if self.employee_id2.id == self.env.user.company_id.vadovas.id else False
                max_possible = 200 if is_ceo else 100

                self._num_calendar_days()
                if self.num_calendar_days == 1 and self.country_allowance_id.id == \
                        self.env.ref('l10n_lt_payroll.country_allowance_lt', raise_if_not_found=False).id:
                    min_possible = 0
                else:
                    min_possible = 50
                try:
                    per_percent = mid_norm // 100   # P3:DivOK
                    percentage = self.float_1 // per_percent  # P3:DivOK

                    if self.float_1 > max_norm and is_ceo:
                        self.int_1 = max_possible
                        self.set_dienpinigiu_norma()
                    elif self.float_1 > mid_norm and not is_ceo:
                        self.int_1 = max_possible
                        self.set_dienpinigiu_norma()
                    elif self.float_1 <= min_norm:
                        self.int_1 = min_possible
                        self.set_dienpinigiu_norma()
                    else:
                        self.int_1 = int(percentage)
                        self.set_dienpinigiu_norma()
                except ZeroDivisionError:
                    self.int_1 = 0
                    self.float_1 = 0
                    self.set_dienpinigiu_norma()

    @api.onchange('date_1', 'date_3')
    def onch_set_first_month_date(self):
        if self.template_id.id == self.env.ref(
                'e_document.prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_template').id and self.date_1:
            self.date_1 = (datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        elif self.template_id.id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_template').id and self.date_3:
            self.date_3 = (datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        elif self.template_id.id == self.env.ref(
                'e_document.isakymas_del_priedo_skyrimo_grupei_template').id and self.date_3:
            self.date_3 = (datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.onchange('date_1', 'bonus_type_selection')
    def onch_set_premijos_datos(self):
        if self.template_id.id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_template').id or \
                self.template_id.id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template').id:
            if self.date_1 and self.bonus_type_selection:
                date_1_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_1_rel_delta = relativedelta(day=1)
                if self.bonus_type_selection == '1men':
                    date_2_rel_delta = relativedelta(day=31)
                    date_3_rel_delta = relativedelta(day=1)
                elif self.bonus_type_selection == '3men':
                    date_2_rel_delta = relativedelta(months=2, day=31)
                    date_3_rel_delta = relativedelta(months=2, day=1)
                else:
                    return
                self.date_1 = (date_1_dt + date_1_rel_delta).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                self.date_2 = (date_1_dt + date_2_rel_delta).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                self.date_3 = (date_1_dt + date_3_rel_delta).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def find_template_finish_date(self, templates, date_field):
        self.ensure_one()
        for template_name in templates:
            full_name = 'e_document.'+template_name
            template = self.env.ref(full_name, raise_if_not_found=False)
            if template and self.template_id.id == template.id:
                self.reikia_pasirasyti_iki = self._prev_work_day(self[date_field])
                return True
        return False

    def _prev_work_day(self, date):
        if not date:
            return False

        prev_day_index = 1
        date = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        work_days = [0, 1, 2, 3, 4]

        while prev_day_index < 365:  # max one year celebration...
            prev_day_index += 1

            date -= timedelta(days=1)

            if date.weekday() not in work_days:
                continue

            holidays = self.env['sistema.iseigines'].search(
                [('date', '=', date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))])
            if holidays:
                continue

            return date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.one
    @api.depends('template_id', 'float_2', 'float_1', 'npd_type', 'selection_nedarbingumas', 'int_1', 'date_from',
                 'selection_bool_1', 'sodra_papildomai_type', 'darbo_rusis', 'du_input_type', 'vaikus_augina',
                 'selection_bool_2', 'date_5', 'bool_1')  # employee_id2
    def _compute_payroll(self):
        contract_term_change_template = self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template')
        employment_template = self.env.ref('e_document.isakymas_del_priemimo_i_darba_template')
        salary_change_template = self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template')
        is_an_applicable_template = self.template_id in [
            contract_term_change_template, employment_template, salary_change_template
        ]

        if self.employee_data_is_accessible() and is_an_applicable_template and self.struct == 'MEN':
            is_salygu_pakeitimo_doc = self.template_id == contract_term_change_template
            is_employment_document = self.template_id == employment_template
            is_salary_change_document = self.template_id == salary_change_template

            # Compute date
            date_to_use = self.date_5
            if self.template_id == employment_template:
                date_to_use = self.date_from
            elif is_salygu_pakeitimo_doc:
                date_to_use = date_to_use or self.date_3

            # Find out the forced NPD
            force_npd = self.float_2 if self.npd_type == 'manual' else None
            disability = None
            if self.npd_type == 'auto' and self.selection_bool_2 == 'true':
                disability = self.selection_nedarbingumas

            is_terminated_contract = self.darbo_rusis in ['terminuota', 'pameistrystes', 'projektinio_darbo']
            is_foreign_resident = is_employment_document and self.bool_1

            contract = None

            # Find if provides additional SoDra contributions
            if is_salary_change_document:
                # Additional SoDra from computed appointment
                additional_sodra_type = self.compute_bool_1 == 'true' and self.compute_sodra_papildomai_type
            elif is_salygu_pakeitimo_doc:
                # Additional SoDra from last appointment
                last_appointment = self.env['hr.contract.appointment'].sudo().search([
                    ('employee_id', '=', self.employee_id2.id),
                    ('date_start', '<', date_to_use)
                ], order='date_start desc', limit=1)
                last_appointment = last_appointment[0] if last_appointment else False
                additional_sodra_type = last_appointment and last_appointment.sodra_papildomai and \
                                        last_appointment.sodra_papildomai_type
                contract = last_appointment.contract_id if last_appointment else None
            else:
                # Additional SoDra set on document
                additional_sodra_type = self.selection_bool_1 == 'true' and self.sodra_papildomai_type

            if self.du_input_type == 'bruto':
                gross_amount = self.float_1
                if not gross_amount:
                    gross_amount = 0.0
            else:
                net_amount = self.float_1
                if not net_amount:
                    net_amount = 0.0
                gross_amount = self.env['hr.payroll'].convert_net_income_to_gross(
                    net_amount, date=date_to_use, forced_tax_free_income=force_npd,
                    voluntary_pension=additional_sodra_type, is_foreign_resident=is_foreign_resident,
                    disability=disability, contract=contract
                )
                gross_amount = tools.float_round(gross_amount, precision_digits=2)

            payroll_data = self.env['hr.payroll'].sudo().get_payroll_values(
                date=date_to_use, bruto=gross_amount, forced_tax_free_income=force_npd,
                voluntary_pension=additional_sodra_type, disability=disability, is_fixed_term=is_terminated_contract,
                is_foreign_resident=is_foreign_resident, contract=contract,
            )

            def preprocess_amount(amount):
                return "{:.2f}".format(tools.float_round(amount, precision_digits=2))

            self.atlyginimo_lentele = self.env['ir.qweb'].sudo().render('e_document.SalaryCalculationTable', {
                'currency_symbol': self.env.user.company_id.currency_id.symbol or '€',
                'gross_salary': preprocess_amount(gross_amount),
                'untaxable_amount': preprocess_amount(payroll_data.get('npd', 0.0)),
                'income_tax': preprocess_amount(payroll_data.get('gpm', 0.0)),
                'health_insurance': preprocess_amount(payroll_data.get('employee_health_tax', 0.0)),
                'pension_insurance': preprocess_amount(payroll_data.get('employee_pension_tax', 0.0)),
                'voluntary_sodra': preprocess_amount(payroll_data.get('voluntary_sodra', 0.0)),
                'net_amount': preprocess_amount(payroll_data.get('neto', 0.0)),
                'employer_taxes': preprocess_amount(payroll_data.get('darbdavio_sodra', 0.0)),
                'workplace_cost': preprocess_amount(payroll_data.get('workplace_costs', 0.0)),
            })

            self.wage_bruto = gross_amount
        else:
            self.wage_bruto = tools.float_round(self.float_1, precision_rounding=0.01)

    @api.multi
    def get_required_form_fields(self):
        """
        Returns a dict of fields that are required
        for specific eDoc template form view
        :return: {'field_name': 'field_string'...}
        """
        self.ensure_one()
        required_fields = {}
        user = self.env.user
        for view in self.mapped('template_id.view_id'):
            try:
                arch = view.arch
                arch_data = etree.fromstring(arch)
                view_required_field_arch_fields = arch_data.findall('''.//field[@required]''')
                view_required_fields = {}
                for view_required_field in view_required_field_arch_fields:
                    invisible_attribute = view_required_field.get('invisible', False)
                    is_invisible = invisible_attribute in [True, 1] or \
                                   (
                                           isinstance(invisible_attribute, (basestring, unicode)) and
                                           invisible_attribute.lower() in ['true', '1']
                                   )
                    if is_invisible:
                        continue
                    groups = view_required_field.get('groups', '')
                    if not groups:
                        has_group = True
                    else:
                        has_group = False
                        group_identifiers = [x.replace(' ', '') for x in groups.split(',')]
                        for group_identifier in group_identifiers:
                            try:
                                has_group = user.has_group(group_identifier)
                            except:
                                has_group = True  # Makes the field required
                                break
                            if has_group:
                                break
                    if has_group:
                        view_required_fields = {x.get('name'): x.get('string') for x in view_required_fields}
                required_fields.update(view_required_fields)
            except:
                pass
        return required_fields

    @api.multi
    def check_required_form_fields(self):
        """
        Checks whether any field that is required
        in the form view for this specific eDoc template.
        Since some actions can be done from a tree, these
        'required' constraints might be skipped otherwise
        :return: None
        """

        batch_errors = str()
        for rec in self:
            required_form_view_fields = rec.get_required_form_fields()
            if required_form_view_fields:
                doc_errors = str()
                # Check for required fields for specific template
                for field, name in required_form_view_fields.items():
                    if not rec[field]:
                        doc_errors += _('Neįvestas privalomas laukas {}!\n').format(name)

                # Append errors to the main error string
                if doc_errors:
                    # Form header, if document has an employee associated with it
                    # append the name for easier distinction
                    header = _('Dokumentas - {}. {}')
                    if rec.employee_id1.name or rec.employee_id2.name:
                        header = header.format(rec.name, _(' Darbuotojas - {}. \n').format(
                            rec.employee_id1.name or rec.employee_id2.name))
                    else:
                        header = header.format(rec.name, '\n')
                    # Append doc lever errors to batch errors
                    batch_errors += '{}\n'.format(header + doc_errors)

        # Raise an error for whole batch
        if batch_errors:
            raise exceptions.UserError(_('Nepavyko suformuoti šių dokumentų: \n\n') + batch_errors)

    @api.multi
    def toggle_skip_constraints(self):
        if self.user_has_groups('robo_basic.group_robo_premium_accountant'):
            for rec in self:
                rec.skip_constraints = not rec.skip_constraints

    @api.multi
    def toggle_skip_constraints_confirm(self):
        if self.user_has_groups('robo_basic.group_robo_premium_accountant'):
            for rec in self:
                rec.skip_constraints_confirm = not rec.skip_constraints_confirm

    @api.onchange('darbo_rusis')
    def onchange_darbo_rusis(self):
        if self.darbo_rusis not in ['terminuota', 'laikina_terminuota', 'pameistrystes',
                                    'projektinio_darbo']:
            self.date_6 = False

    @api.onchange('acc_number')
    def onchange_acc_number(self):
        self.acc_number = sanitize_account_number(self.acc_number)

    @api.onchange('dk_nutraukimo_straipsnis')
    def onchange_dk_nutraukimo_straipsnis(self):
        if self.dk_nutraukimo_straipsnis:
            self.text_4 = self.dk_nutraukimo_straipsnis.straipsnis
            self.text_2 = self.dk_nutraukimo_straipsnis.dalis
            self.dk_detalizacija = self.dk_nutraukimo_straipsnis.detalizavimas

    @api.depends('employee_id2')
    def _compute_surname(self):
        for rec in self.filtered('employee_id2'):
            rec.surname = rec.employee_id2.get_split_name().get('last_name')

    @api.depends('generated_document')
    def _generated_document_download(self):
        for rec in self.filtered('generated_document'):
            rec.generated_document_download = rec.generated_document

    @api.depends('employee_id1')
    def _compute_job_id_1(self):
        for rec in self:
            rec.job_id1 = rec.employee_id1.sudo().job_id.id

    @api.depends('employee_id2')
    def _compute_job_id_2(self):
        for rec in self:
            rec.job_id2 = rec.employee_id2.sudo().job_id.id

    @api.multi
    def _set_num_work_days(self):
        """
        Dummy method, without it num_work_days always computes
        """
        pass

    @api.multi
    def _set_job_id_2(self):
        """
        Dummy method, without it job_id2 always computes, even when employee_id2.job_id is 0
        """
        pass

    @api.depends('employee_id3')
    def _compute_job_id_3(self):
        for rec in self:
            rec.job_id3 = rec.employee_id3.sudo().job_id.id

    @api.multi
    @api.depends('e_document_line_ids', 'bonus_input_type', 'employee_id1', 'employee_id2', 'date_from', 'int_1')
    def _compute_text_1(self):
        order_holiday_extension_template = self.env.ref('e_document.order_holiday_extension_template', raise_if_not_found=False)
        request_holiday_extension_template = self.env.ref('e_document.request_holiday_extension_template', raise_if_not_found=False)
        for rec in self:
            if rec.template_id == self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template'):
                compute_text_1 = '''<br>Siunčiami darbuotojai:
                                        <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                                        <tr style="border:1px solid black;">
                                        <td style="border:1px solid black;"><b>Vardas pavardė</b></td>
                                        <td style="border:1px solid black;"><b>Dienpinigių suma, EUR</b></td>
                                        </td></tr>'''
                for line in rec.e_document_line_ids:
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

            elif rec.template_id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template'):
                document_lines = rec.get_document_lines()
                if not document_lines:
                    raise exceptions.ValidationError(_('At least one employee is required for the order of bonus document'))
                if len(document_lines) > 1:
                    compute_text_1 = '''<br>Priedas skiriamas šiems darbuotojams:
                                            <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                                            <tr style="border:1px solid black;">
                                            <td style="border:1px solid black;"><b>Vardas pavardė</b></td>
                                            <td style="border:1px solid black;"><b>Priedo dydis ({0}), EUR</b></td>
                                            </td></tr>'''.format(rec.bonus_input_type)
                    for line in rec.e_document_line_ids:
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
            elif rec.template_id in [order_holiday_extension_template, request_holiday_extension_template]:
                try:
                    employee = rec.employee_id1 if rec.template_id == request_holiday_extension_template else \
                        rec.employee_id2
                    date_appointment = rec.date_from or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    additional_days = rec.int_1 or 0
                    main_leaves, additional_leaves = employee.sudo().with_context(
                        date=date_appointment).appointment_id.get_employee_yearly_leaves()
                    leaves_sum = main_leaves + additional_leaves + additional_days

                    compute_text_1 = _('''
                    Currently {} has <b>{}</b> main leaves per year and <b>{}</b> additional leaves per year.
                    With the additional <b>{}</b> requested with this document, if the order is signed successfully, the 
                    employee will have a total of <b>{}</b> leaves per year starting from {}.
                    ''').format(
                        employee.name_related, main_leaves, additional_leaves, additional_days, leaves_sum,
                        rec.date_from)
                    rec.compute_text_1 = compute_text_1
                except Exception:
                    rec.compute_text_1 = str()

    @api.depends('employee_id1')
    def _compute_department_id(self):
        for rec in self:
            rec.department_id = rec.employee_id1.sudo().department_id.id

    @api.multi
    @api.depends('company_id', 'signed_user_id')
    def _compute_manager_id(self):
        for rec in self:
            if rec.signed_user_id and rec.signed_user_id.employee_ids.filtered(lambda x: x.active) \
                    and rec.document_type in ['isakymas']:
                manager_id = rec.signed_user_id.employee_ids.filtered(lambda x: x.active)[0].id
            else:
                manager_id = rec.company_id.sudo().vadovas.id
            rec.manager_id = manager_id

    @api.depends('template_id', 'name_force')
    def _compute_name(self):
        for rec in self:
            if rec.name_force:
                rec.name = rec.name_force
            elif rec.template_id:
                rec.name = rec.template_id.name
            else:
                rec.name = _('Dokumentas')

    @staticmethod
    def linksnis(words, mano_linksnis):
        kokie_linksniai = {
            'ko': linksniuoti.kas_to_ko,
            'kam': linksniuoti.kas_to_kam,
            'ka': linksniuoti.kas_to_ka,
            'kuo': linksniuoti.kas_to_kuo,
            'kur': linksniuoti.kas_to_kur,
            'sauksm': linksniuoti.kas_to_sauksm,
        }
        if mano_linksnis in kokie_linksniai:
            return kokie_linksniai[mano_linksnis](words)
        return words

    @staticmethod
    def days_string_based_on_number(number):
        number = int(number)
        if number % 10 == 0 or 10 < number % 100 < 20:
            return 'dienų'
        elif number % 10 == 1:
            return 'dieną'
        else:
            return 'dienas'

    @staticmethod
    def format_float_to_hours(fhours):
        if not isinstance(fhours, (int, float)):
            try:
                fhours = float(fhours)
            except:
                return "00:00"
        ihours = int(fhours)
        return "%02d:%02d" % (ihours, (fhours - ihours) * 60)

    @staticmethod
    def format_float_to_hours_and_minutes(fhours):
        if not isinstance(fhours, (int, float)):
            try:
                fhours = float(fhours)
            except:
                return _("00h 00m")
        ihours = int(fhours)
        return "%02dh %02dm" % (ihours, (fhours - ihours) * 60)

    @staticmethod
    def parse_schedule_lines_for_printing(lines):
        if bool(lines) and not isinstance(lines, unicode):
            lines_to_show = lines.filtered(lambda l: l.id)
            if not lines_to_show:
                lines_to_show = lines
            return lines_to_show
        else:
            return [
                {'dayofweek': 0, 'hour_from': 8, 'hour_to': 12},
                {'dayofweek': 0, 'hour_from': 13, 'hour_to': 17},
                {'dayofweek': 1, 'hour_from': 8, 'hour_to': 12},
                {'dayofweek': 1, 'hour_from': 13, 'hour_to': 17},
                {'dayofweek': 2, 'hour_from': 8, 'hour_to': 12},
                {'dayofweek': 2, 'hour_from': 13, 'hour_to': 17},
                {'dayofweek': 3, 'hour_from': 8, 'hour_to': 12},
                {'dayofweek': 3, 'hour_from': 13, 'hour_to': 17},
                {'dayofweek': 4, 'hour_from': 8, 'hour_to': 12},
                {'dayofweek': 4, 'hour_from': 13, 'hour_to': 17},
            ]
        # I have no idea whats going on with these writes on onchange methods, so we need to filter all newobjects.

    @staticmethod
    def get_weekday_string(week_day):
        week_day = str(week_day)
        week_days = {
            '0': 'Pirmadienis',
            '1': 'Antradienis',
            '2': 'Trečiadienis',
            '3': 'Ketvirtadienis',
            '4': 'Penktadienis',
            '5': 'Šeštadienis',
            '6': 'Sekmadienis'
        }
        return week_days.get(week_day, 'Pirmadienis')

    def get_related_order(self):
        if self.document_type == 'prasymas' and self.record_model == 'e.document':
            related_document = self.env['e.document'].sudo().search([('id', '=', self.record_id)], limit=1)
            if related_document and related_document.document_type == 'isakymas':
                return related_document
        return False

    @api.multi
    def cancel_order(self):
        self.ensure_one()
        if self.document_type == 'isakymas' and self.state == 'e_signed':
            template_id = self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template')
            employee_id = self.signed_user_id.sudo().employee_ids.filtered(lambda x: x.active)[0].id \
                if self.signed_user_id.employee_ids.filtered(lambda x: x.active) \
                else self.env.user.sudo().company_id.vadovas.id
            cancel_id = self.create({
                'document_type': 'isakymas',
                'template_id': template_id.id,
                'employee_id2': employee_id,
                'cancel_id': self.id,
                'date_4': datetime.now(),  # reikia pasirašyti iki date_4
            })
            ctx = dict(self._context)
            ctx['robo_header'] = {}
            return {
                'name': _('eDokumentai'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'e.document',
                'view_id': template_id.view_id.id,
                'res_id': cancel_id.id,
                'context': ctx,
            }

    @api.multi
    def cancel_holiday(self):
        self.ensure_one()
        employee = self.employee_id1
        if employee.user_id and self.env.user.id != employee.user_id.id:
            raise exceptions.UserError(_('Negalima atšaukti atostogų prašymo.'))
        if self.record_model != 'e.document' or not self.record_id:
            raise exceptions.UserError(_('Negalima atšaukti atostogų prašymo. Kreipkitės į sistemos administratorių.'))
        if self.document_type == 'prasymas' and self.state == 'e_signed' and self.susijes_isakymas_pasirasytas:
            template = self.env.ref('e_document.prasymas_del_kasmetiniu_atostogu_atsaukimo_template')
            cancel_document = self.with_context(e_document_view_type='rigid').create({
                'document_type': 'prasymas',
                'template_id': template.id,
                'employee_id1': employee.id,
                'cancel_id': self.record_id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'date_document': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
            })
            ctx = dict(self._context)
            ctx['robo_header'] = {}
            return {
                'name': _('eDokumentai'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'e.document',
                'view_id': template.view_id.id,
                'res_id': cancel_document.id,
                'context': ctx,
            }

    @api.multi
    def open_cancel_id(self):
        self.ensure_one()
        if self.cancel_id:
            ctx = dict(self._context)
            ctx['robo_header'] = {}
            return {
                'name': _('eDokumentai'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'e.document',
                'view_id': self.cancel_id.template_id.view_id.id,
                'res_id': self.cancel_id.id,
                'context': ctx,
            }

    @api.multi
    def open_cancelled_ids(self):
        self.ensure_one()
        if self.cancelled_ids:
            ctx = dict(self._context)
            ctx['robo_header'] = {}
            return {
                'name': _('eDokumentai'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'e.document',
                'view_id': self.cancelled_ids[0].template_id.view_id.id,
                'res_id': self.cancelled_ids[0].id,
                'context': ctx,
            }

    @api.multi
    def cancel_request(self):
        self.ensure_one()
        if self.state == 'e_signed' and not self.susijes_isakymas_pasirasytas:
            # if self.employee_id1.user_id.id != self.env.user.id:
            #     raise exceptions.Warning(_('Negalima atšaukti ne savo prašymų.'))
            order_id = self.sudo().browse(self.record_id)
            if order_id and order_id.state != 'e_signed':
                order_id.active = False
                self.sudo().write({'state': 'cancel'})
                return
            elif not order_id and not self.susijes_isakymas_pasirasytas:
                self.sudo().write({'state': 'cancel'})
                return
        raise exceptions.Warning(_('Negalima atšaukti vadovo patvirtintų prašymų.'))

    @api.model
    def create(self, vals):
        self.check_access_rights('create')
        if 'user_id' not in vals:
            vals['user_id'] = self.env.user.id
        res = super(EDocument, self.sudo()).create(vals)
        res.sudo(user=self.env.user.id).check_access_rule('create')
        res.sudo()._compute_dates_display()
        return res

    @api.multi
    def unlink(self):
        if self.env.uid == tools.SUPERUSER_ID and self._context.get('unlink_from_script', False):
            return super(EDocument, self).unlink()
        if any(doc.state == 'e_signed' for doc in self):
            raise exceptions.UserError(_('Negalima ištrinti pasirašytų dokumentų.'))
        if any(doc.document_type == 'isakymas' for doc in self):
            raise exceptions.UserError(_('Negalima ištrinti dokumentų.'))
        return super(EDocument, self).unlink()

    @api.multi
    def write(self, vals):
        for rec in self:
            # for line in rec.fixed_attendance_ids.filtered(lambda l: not l.e_document):
            #     line.write({'e_document': rec.id})
            bypass = len(vals) == 1 and (isinstance(vals.get('expense_state_approval', False), str)
                                         or 'last_message_sent' in vals)
            if not rec.sudo().active and type(rec.id) == int and not self.env.user._is_admin():
                raise exceptions.Warning(_('Negalima keisti suarchyvuotų dokumentų.'))
            if rec.state == 'e_signed' and not self.env.user._is_admin() and not bypass:
                raise exceptions.Warning(_('Negalima keisti pasirašytų dokumentų.'))
            if 'cancel_id' in vals and not self.env.user._is_admin():
                vals.pop('cancel_id')
            if rec.template_id.send_manager and vals.get('state') == 'cancel' and rec.document_type == 'prasymas' and \
                    self.env.user.sudo().company_id.politika_atostogu_suteikimas == 'department':
                vals['approve_status'] = 'rejected'
        if self.env.user.has_group('e_document.group_robo_business_trip_user') and \
                any(x.business_trip_document for x in self):
            res = super(EDocument, self.sudo()).write(vals)
        else:
            res = super(EDocument, self).write(vals)
        self.sudo()._compute_dates_display()
        return res

    @api.model
    def default_get(self, default_get_fields):
        res = super(EDocument, self).default_get(default_get_fields)

        user = self.env.user
        employee = user.employee_ids and user.employee_ids[0] or False

        # Set basic document data
        res['employee_id1'] = employee.id if employee else False
        res['vieta'] = user.sudo().company_id.partner_id.city
        res['company_id'] = user.company_id.id

        # Determine the e-document template
        template_external_id = self._context.get('rec_template_id')
        template = None
        if template_external_id:
            template = self.sudo().env.ref('e_document.' + template_external_id, False)
        if not template:
            # Template could not be determined so no other actions regarding template rendering should be taken
            return res

        # Document specific data
        if template == self.env.ref('e_document.isakymas_del_kasos_darbo_organizavimo_template') and \
                'employee_id3' in default_get_fields:
            res['employee_id3'] = user.company_id.vadovas.id

        # Get work norm
        if employee:
            res['work_norm'] = employee.job_id.work_norm

        # Parse template text
        template_text = template.template
        if template_text:
            # Replace specific ISO characters with symbols
            template_text = template_text.replace('&lt;', '<').replace('&gt;', '>')

        parsed_template_text = jinja2.Environment().parse(template_text)  # Parse template
        variables = meta.find_undeclared_variables(parsed_template_text)  # Get undeclared variables

        data = {}  # Additional methods and placeholders that can be used for Jinja template rendering
        data.update(LINKSNIAI_FUNC)  # Add cases to data

        additional_variables = self._get_additional_variables()

        # Add placeholders to variables
        for variable in variables:
            if variable in LINKSNIAI_FUNC:
                continue  # Don't set placeholders for case variables

            # Determine if a placeholder should be used.
            use_placeholder = True
            try:
                field_type = self._fields.get(variable, object)
                if isinstance(field_type, OdooOne2manyField):
                    use_placeholder = False
            except KeyError:
                pass
            if not use_placeholder:
                continue

            data[variable] = additional_variables.get('placeholder', '')

        # Add additional variables so that they can be used when rendering the template
        for variable_name, variable_function in iteritems(additional_variables):
            if variable_name in variables:
                data[variable_name] = variable_function

        # Get template and render it
        jinja_template = jinja2.Environment().from_string(template_text)
        final_result = jinja_template.render(**data)
        res.update({'final_document': final_result})
        return res

    @api.multi
    def _get_additional_variables(self):
        # Generate gray squares for each variable so that when the template text is previewed - the user knows
        # a value will be set in these places when he saves the document
        placeholder_style = 'background-color: #8394a1; width: 75px; display: inline-block; height: 17px; opacity: 0.2;'
        variable_placeholder = '''<span style="{0}"></span>'''.format(placeholder_style)

        return {
            'format_float_to_hours': self.format_float_to_hours,
            'format_float_to_hours_and_minutes': self.format_float_to_hours_and_minutes,
            'get_weekday_string': self.get_weekday_string,
            'parse_schedule_lines_for_printing': self.parse_schedule_lines_for_printing,
            'days_string_based_on_number': self.days_string_based_on_number,
            'num_calendar_days': self.num_calendar_days,
            'date_string': self.date_string,
            'len': len,
            'sum': sum,
            'e_document_line_ids': self.e_document_line_ids,
            'date_to_string': self.env['e.document.template'].date_to_string,
            'e_document_time_line_ids': self.e_document_time_line_ids,
            'placeholder': variable_placeholder,
        }

    @api.one
    def set_final_document(self):
        if self._context.get('do_not_update', False):  # use for scripts that fix new fields
            return False
        if not self._context.get('force_set_document_lang'):
            self = self.with_context(lang='lt_LT')
        template_rec = self.sudo().template_id
        template = template_rec.template
        if template:
            template = template.replace('&lt;', '<').replace('&gt;', '>')
        parsed_template = jinja2.Environment().parse(template)
        variables = meta.find_undeclared_variables(parsed_template)
        data = {}
        is_temp_job_template = self.template_id == self.env.ref(
            'e_document.isakymas_del_paskyrimo_laikinai_eiti_pareigas_template', raise_if_not_found=False)
        employee_gender = False

        downtime_template = self.env.ref('e_document.isakymas_del_prastovos_skelbimo_template',
                                         raise_if_not_found=False)
        is_downtime_document = self.template_id == downtime_template
        parse_selection_fields = not is_downtime_document

        python_vars = {
            'len': len,
            'range': range,
            'min': min,
            'float_is_zero': float_is_zero,
            'float': float
        }
        variable_python_methods = [var for var in variables if var in python_vars.keys()]
        for variable in variable_python_methods:
            data[variable] = python_vars.get(variable)
        linksniai_vars = [var for var in variables if var in LINKSNIAI_FUNC]
        variables_to_parse = list(set(variables) - set(variable_python_methods) - set(linksniai_vars))

        additional_variables = self._get_additional_variables()

        for variable in variables_to_parse:
            try:
                variable = variable.replace('__sv__', '')
                try:
                    value = getattr(self.sudo(), variable)
                except AttributeError:
                    if variable in additional_variables:
                        value = additional_variables.get(variable)
                    else:
                        continue  # Variable is from the template itself and not the document
                if is_temp_job_template and variable == 'employee_id3' and value and value.sudo().gender and \
                        (value.sudo().gender == 'male' or value.sudo().gender == 'female'):
                    employee_gender = value.sudo().gender
                variable_type = self._fields.get(variable, object)
                if isinstance(value, models.BaseModel) and variable not in ['fixed_attendance_ids', 'e_document_line_ids', 'e_document_time_line_ids']:
                    if len(value) == 0:
                        value = ''
                    else:
                        if variable in ['downtime_employee_lines', 'downtime_come_to_work_times']:
                            value = value.sudo()
                            if variable == 'downtime_come_to_work_times':
                                value = value.filtered(lambda v: v.id)
                        else:
                            if employee_gender and variable == 'job_id2' and value:
                                value.ensure_one()
                                if employee_gender == 'male' and value.sudo().male_name:
                                    value = value.sudo().male_name
                                elif employee_gender == 'female' and value.sudo().female_name:
                                    value = value.sudo().female_name
                                else:
                                    value = value.sudo().name
                            else:
                                if not isinstance(variable_type, fields.One2many):
                                    value.ensure_one()
                                    value = value.sudo().name
                if value is False:  # FIXME: do we want to actually test if value _is_ False, or make sure we have empty string? Here, if value is set to 0, it will not be converted to string
                    value = ''
                if isinstance(variable_type, fields.Many2one):
                    tzone = self._context.get('tz')
                    if timezone:
                        try:
                            diff = datetime.now(timezone(tzone)) - datetime.utcnow()
                            value_dt = datetime.strptime(value, tools.DEFAULT_SERVER_DATETIME_FORMAT) + diff
                            value = value_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                        except:
                            pass
                elif isinstance(variable_type, fields.Selection) and parse_selection_fields:
                    selection_dict = dict(self.with_context(lang='lt_LT').fields_get(allfields=[variable])[variable]['selection'])
                    # Add the original value to the data so it's accessible by calling the variable with the suffix
                    # '__sv__' (selection value)
                    data[variable + '__sv__'] = value
                    value = selection_dict.get(value, '')
                elif isinstance(variable_type, fields.Float):
                    if isinstance(value, float):
                        format_string = '%0.2f'
                        # Quick patch, maybe check trailing 0's,determine based on size or always keep 3.
                        if tools.float_compare(value, round(value, 2), precision_digits=4) != 0:
                            format_string = '%0.3f'
                        value = format_string % value
                data[variable] = value
            except NameError:
                raise exceptions.Warning(_('Neteisingi duomenys'))
        # try:
        #     data['extra_text'] = utils.escape(data['extra_text'])
        # except:
        #     pass
        data.update(LINKSNIAI_FUNC)
        if template:
            final_result = jinja2.Environment().from_string(template).render(**data)
            self.final_document = final_result

    @api.multi
    def create_pdf(self):
        self.ensure_one()
        report_name = 'e_document.general_print'
        result, fmt = self.env['ir.actions.report.xml'].with_context(
            force_paperformat=self.paperformat_id).render_report(self._ids, report_name, data=None)
        if fmt == 'pdf':
            self.generated_document = result.encode('base64')
        else:
            self.generated_document = False

    @api.multi
    def execute_confirm_workflow(self):
        """
        Method to execute additional functions on confirm
        """
        self.execute_confirm_workflow_update_values()
        self.execute_confirm_workflow_check_values()
        self.sudo().execute_confirm_check_holiday_intersect()

    @api.multi
    def execute_confirm_workflow_update_values(self):
        def set_first_day_of_month(date):
            if date:
                date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_dt.day != 1:
                    date = (date_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            return date

        for rec in self:
            if rec.template_id == self.env.ref(
                    'e_document.prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_template'):
                rec.date_1 = set_first_day_of_month(rec.date_1)

            elif rec.template_id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_template'):
                rec.date_3 = set_first_day_of_month(rec.date_3)

            elif rec.template_id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template'):
                rec.date_3 = set_first_day_of_month(rec.date_3)

            elif rec.template_id == self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template'):
                rec.compute_bool_1_stored = rec.compute_bool_1
                rec.sodra_papildomai_type_stored = rec.compute_sodra_papildomai_type

    @api.multi
    def execute_confirm_workflow_check_values(self):
        templates_with_fix_attendance_ids = [self.env.ref('e_document.internship_order_template', False),
                                             self.env.ref(
                                                 'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template',
                                                 False),
                                             self.env.ref('e_document.isakymas_del_priemimo_i_darba_template', False)]
        templates_with_e_document_time_line_ids = [
            self.env.ref('e_document.dynamic_workplace_compensation_order_template', False),
            self.env.ref('e_document.unpaid_free_time_order_template', False),
            self.env.ref('e_document.overtime_order_template', False),
            self.env.ref('e_document.unpaid_free_time_request_template', False),
            self.env.ref('e_document.overtime_request_template', False)]
        for rec in self:
            if rec.sudo().skip_constraints_confirm:
                _logger.info('Value check before confirmation was skipped for document %s: %s' % (self.id, self.name))
                continue
            if rec.template_id in templates_with_fix_attendance_ids:
                check_time_overlap(rec.fixed_attendance_ids)
            elif rec.template_id in templates_with_e_document_time_line_ids:
                check_time_overlap(rec.e_document_time_line_ids)
            if rec.template_id == self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template'):
                rec.check_valid_allowance_date()
                rec.check_e_document_line_ids()
            elif rec.template_id == self.env.ref('e_document.prasymas_del_tarnybines_komandiruotes_template') or \
                    rec.template_id == self.env.ref('e_document.isakymas_del_komandiruotes_template'):
                rec.check_valid_allowance_date()
            elif rec.template_id == self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template', False):
                contract = self.env['hr.contract'].search_count([('employee_id', '=', self.employee_id2.id),
                                                                 ('date_start', '<=', self.date_5)])
                if not contract:
                    raise exceptions.UserError(
                        _('Darbuotojas %s neturi validaus kontrakto šiai datai. Pirmiausia priimkite jį į darbą.')
                        % rec.employee_id2.name
                    )
            elif rec.template_id == self.env.ref('e_document.prasymas_del_darbo_uzmokescio_pervedimo_i_banko_saskaita_template'):
                validate_iban(rec.acc_number)
            elif rec.template_id in [
                self.env.ref('e_document.prasymas_del_vaiko_prieziuros_atostogu_suteikimo_template'),
                self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template'),
                self.env.ref('e_document.prasymas_suteikti_tevystes_atostogas_template'),
                self.env.ref('e_document.isakymas_del_tevystes_atostogu_suteikimo_template')
            ]:
                rec.check_valid_parental_leave_dates()


    @api.multi
    def execute_confirm_check_holiday_intersect(self):
        rest_type = self.env.ref('hr_holidays.holiday_status_P', raise_if_not_found=False)
        rest_type_id = rest_type and rest_type.id or False

        holiday_request_template_ids = self.get_holidays_templates_ids()
        holiday_order_template_ids = self.get_holidays_order_templates_ids()
        template_ids = holiday_request_template_ids + holiday_order_template_ids

        for rec in self.filtered(lambda r: r.template_id.id in template_ids):
            if rec.sudo().skip_constraints_confirm:
                _logger.info('Holiday overlap check was skipped for document %s: %s' % (self.id, self.name))
                continue

            holidays = self.env['hr.holidays'].search([('employee_id', '=', rec.employee_id2.id),
                                                       ('holiday_status_id', '!=', rest_type_id),
                                                       ('state', 'not in', ['cancel', 'refuse']),
                                                       ('date_from_date_format', '<=', rec.date_to),
                                                       ('date_to_date_format', '>=', rec.date_from)])
            other_day_holidays = holidays.filtered(
                lambda r: r['date_from_date_format'] != rec.date_from or r['date_to_date_format'] != rec.date_to)
            employee_has_taken_free_time_off = self.employee_has_taken_free_time_off(
                rec.employee_id2, rec.date_from, rec.date_to
            )
            if other_day_holidays or employee_has_taken_free_time_off:
                raise exceptions.Warning(_('Negalima turėti persidengiančių neatvykimo įrašų. Įrašas persidengia '
                                           'darbuotojui {}').format(linksniuoti.kas_to_kam(rec.employee_id2.name)))

            if rec.template_id.id in holiday_request_template_ids and not rec.not_check_holidays:
                if not rec.check_intersecting_holidays(rec.employee_id1.id,
                                                       rec.date_from, rec.date_to,
                                                       holiday_request_template_ids):
                    raise exceptions.ValidationError(_('Jūsų prašymas kirstųsi su jau esančiu atostogų/komandiruočių '
                                                       'prašymu ir/ar darbuotojo neatvykimu.'))

    @api.one
    def check_valid_allowance_date(self):
        valid_dates = self.country_allowance_id.line_ids.filtered(
            lambda r: (not r.date_from or r.date_from <= self.date_to)
                      and (not r.date_to or r.date_to >= self.date_from)
        )
        if not valid_dates:
            raise exceptions.Warning(_('Nerastos normos %s laikotarpiui %s - %s')
                                     % (self.country_allowance_id.name, self.date_from, self.date_to))

    @api.multi
    def check_valid_parental_leave_dates(self):
        self.ensure_one()
        parental_leave_templates = [
            self.env.ref('e_document.prasymas_del_vaiko_prieziuros_atostogu_suteikimo_template'),
            self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template')]
        is_parental_leave = True if self.template_id in parental_leave_templates else False
        year_limit = 3 if is_parental_leave else 1

        date_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_to = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_child_birthdate = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_lim_after_child_birthdate = date_child_birthdate + relativedelta(years=year_limit)

        if not is_parental_leave and (date_to - date_from).days > 29:
            raise exceptions.ValidationError(_('The duration of the leave may not exceed 30 days'))
        if date_to > date_lim_after_child_birthdate:
            limit_string = _('three years') if is_parental_leave else _('one year')
            raise exceptions.ValidationError(
                _('End date of the leave must not be later than {} after the childbirth ({})').format(
                    limit_string, date_lim_after_child_birthdate.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)))

    @api.one
    def check_e_document_line_ids(self):
        if not self.e_document_line_ids:
            raise exceptions.Warning(_('Įveskite bent vieną darbuotoją.'))
        elif self.e_document_line_ids:
            employee_ids = self.e_document_line_ids.mapped('employee_id2')
            if len(employee_ids) != len(self.e_document_line_ids):
                raise exceptions.Warning(_('Įvesti darbuotojai kartojasi'))

    @api.multi
    def check_dates_not_past(self):
        spec_docs = [
            self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template').id,
            self.env.ref('e_document.isakymas_del_priemimo_i_darba_template').id,
            self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template').id,
            self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template').id
        ]

        priedo_docs = [
            self.env.ref('e_document.isakymas_del_priedo_skyrimo_template').id,
            self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template').id
        ]

        date_now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        allow_historical_forming = self.sudo().env.user.company_id.e_documents_allow_historic_signing
        allow_historical_forming_spec = self.sudo().env.user.company_id.e_documents_allow_historic_signing_spec

        for doc in self:
            if doc.sudo().skip_constraints_confirm:
                _logger.info(_('Praleistas formavimo datų tikrinimas dokumentui %s: %s') % (doc.id, doc.name))
                continue

            template = doc.template_id.id
            doc._compute_dates_display()
            is_historic = doc.date_from_display and doc.date_from_display < date_now
            is_special_doc = template in spec_docs
            is_priedo_doc = template in priedo_docs

            if (is_historic and not is_priedo_doc) and \
                    ((not allow_historical_forming_spec and is_special_doc) or
                     (not allow_historical_forming and not is_special_doc)):
                raise exceptions.ValidationError(_(
                    'Negalite formuoti el. dokumentų praeities data. Informuokite buhalterį parašydami žinutę dokumento apačioje.'))

    @api.model
    def create_action_multi_confirm(self):
        action = self.env.ref('e_document.action_multi_confirm')
        if action:
            action.create_action()

    @api.model
    def create_action_multi_sign(self):
        action = self.env.ref('e_document.action_multi_sign')
        if action:
            action.create_action()

    @api.multi
    def confirm(self):
        docs = self.filtered(lambda d: d.state == 'draft')
        # Check whether all fields that are required in the form view
        # are actually filled (Relevant on tree view multi actions)
        docs.check_required_form_fields()
        if not self.env.user.is_accountant():
            docs.check_dates_not_past()
        for rec in docs:
            rec.execute_confirm_workflow()
            if not rec.uploaded_document:
                rec.create_pdf()
            rec.state = 'confirm'

    @api.model
    def calc_date_from(self, date, hour=8, minute=0):
        if hour >= 24:
            hour, minute = 23, 59
        local, utc = datetime.now(), datetime.utcnow()
        diff = utc - local
        local_time = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=hour, minute=minute)
        utc_time = local_time + diff
        return utc_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def calc_date_to(self, date, hour=16, minute=0):
        if hour >= 24:
            hour, minute = 23, 59
        local, utc = datetime.now(), datetime.utcnow()
        diff = utc - local
        local_time = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(hour=hour, minute=minute)
        utc_time = local_time + diff
        return utc_time.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @api.model
    def get_compensation_days(self, date_from, date_to, employee_id):
        employee = self.env['hr.employee'].browse(employee_id)
        days_to_compensate = 0
        if date_from and date_to:
            date = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            holidays = self.env['sistema.iseigines'].search(
                [('date', '<=', date_to), ('date', '>=', date_from)])
            while date <= date_to_dt:
                holiday = holidays.filtered(
                    lambda r: r['date'] == date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) and True or False
                if holiday or date.weekday() in [5, 6]:  # TODO Maybe based on schedule?
                    days_to_compensate += 1
                date = date + relativedelta(days=1)
        date_to_dt = (datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
            tools.DEFAULT_SERVER_DATE_FORMAT)
        holidays = self.env['hr.holidays'].search([('date_from', '>=', date_to_dt), ('employee_id', '=', employee_id)])
        dates = []
        date = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)
        darbo_grafikas = employee.with_context(date=date_from).contract_id.appointment_id.schedule_template_id
        free_days = ['5', '6']
        if darbo_grafikas and darbo_grafikas.fixed_attendance_ids and len(darbo_grafikas.fixed_attendance_ids) != 0:
            schedule_work_days = darbo_grafikas.fixed_attendance_ids.mapped('dayofweek')
            free_days = list(set(['0', '1', '2', '3', '4', '5', '6']) - set(schedule_work_days))
        while days_to_compensate > 0:
            _date = date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            _next_date = (date + relativedelta(days=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            holiday = holidays.filtered(lambda r: (r['date_from'] <= _date <= r['date_to'])
                                                  or (r['date_from'] <= _next_date <= r['date_to'])
                                                  or (r['date_from'] >= _date and r['date_to'] <= _next_date))
            iseigines = self.env['sistema.iseigines'].search([('date', '=', date)])
            if not holiday and str(date.weekday()) not in free_days and not iseigines:
                dates.append(_date)
                days_to_compensate -= 1
            date += relativedelta(days=1)
        date_start = False
        date_end = False
        dates_dict = {}
        dates.sort()
        for date in dates:
            if not date_start:
                date_start = date
            if not date_end:
                date_end = date
            date_end_dt = datetime.strptime(date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            diff = (date_dt - date_end_dt).days
            if diff > 1:
                date_start = date
                date_end = date
            else:
                date_end = date
            dates_dict[date_start] = date_end
        return dates_dict

    @api.model
    def get_num_of_compensation_days(self, date_from, date_to):
        days_to_compensate = 0
        if date_from and date_to:
            date = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            holidays = self.env['sistema.iseigines'].search(
                [('date', '<=', date_to), ('date', '>=', date_from)])
            while date <= date_to_dt:
                holiday = holidays.filtered(
                    lambda r: r['date'] == date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) and True or False
                if holiday or date.weekday() in [5, 6]:
                    days_to_compensate += 1
                date = date + relativedelta(days=1)
        return days_to_compensate

    @api.multi
    def workflow_execution(self):
        self.ensure_one()
        eval_context = {
            'obj': self.sudo(),
            'datetime': datetime,
            'env': self.sudo().env,
            'relativedelta': relativedelta,
            'tools': tools,
        }
        locals = {}
        if self.sudo().template_id.python_code:
            if not self._context.get('simulate'):
                self.sudo()._set_document_number()
            safe_eval(self.sudo().template_id.python_code, eval_context, locals, mode='exec', nocopy=True)

    @api.multi
    def _set_document_number(self):
        self.ensure_one()
        document_number = False
        if self.document_type == 'isakymas':
            document_number = self.env['ir.sequence'].next_by_code('ISAKYMAS')
        elif self.document_type == 'agreement':
            document_number = self.env['ir.sequence'].next_by_code('SUTARTIS')
        if document_number:
            self.write({'document_number': document_number})

    @api.multi
    def set_related_prasymai_isakymas_signed(self):
        for rec in self:
            prasymai = self.env['e.document'].search([('record_model', '=', 'e.document'), ('record_id', '=', rec.id)])
            if prasymai:
                prasymai.write({'susijes_isakymas_pasirasytas': True})
                for prasymas in prasymai:
                    msg = {
                        'body': _('Jūsų prašymą patvirtino direktorius.'),
                        'subject': _('Patvirtintas prašymas'),
                        'priority': 'high',
                        'front_message': True,
                        'rec_model': 'e.document',
                        'rec_id': prasymas.id,
                        'view_id': prasymas.view_id.id or False,
                    }
                    partner_ids = prasymas.mapped('employee_id1.user_id.partner_id.id')
                    if partner_ids:
                        msg['partner_ids'] = partner_ids
                    prasymas.robo_message_post(**msg)
            if rec.view_type == 'free' and rec.document_type == 'prasymas':
                msg = {
                    'body': _('Patvirtintas laisvos formas prašymas.'),
                    'subject': _('Patvirtintas prašymas'),
                    'priority': 'medium',
                    'front_message': True,
                    'rec_model': 'e.document',
                    'rec_id': rec.id,
                    'view_id': rec.view_id.id or False,
                    'partner_ids': self.env['hr.employee'].search([('robo_access', '=', True),
                                                                   ('robo_group', '=', 'manager')]).mapped(
                        'user_id.partner_id.id')
                }
                rec.robo_message_post(**msg)

    @api.one
    def _set_document_link(self):
        if self.record_model == 'e.document' and self.record_id:
            isakymas = self.sudo().browse(self.record_id)
            isakymas.inform_ceo_about_order_waiting_for_signature()

    @api.multi
    def get_partners_to_inform_about_orders_waiting_for_signature(self):
        self.ensure_one()

        partner_ids = set()

        # Main mail channel
        mail_channel = self.env.ref('e_document.orders_waiting_for_signature_mail_channel', raise_if_not_found=False)
        if not mail_channel:
            # Add CEO as partner to inform since mail channel does not exist
            ceo_employee = self.env.user.sudo().company_id.vadovas
            ceo_partner = ceo_employee.user_id.partner_id or ceo_employee.address_home_id
            if ceo_partner:
                partner_ids.add(ceo_partner.id)
        else:
            # Add mail channel subscribers as partners
            allowed_partner_id_list = mail_channel.sudo().mapped('group_public_id.users.partner_id.id')
            channel_partner_ids = mail_channel.sudo().mapped('channel_partner_ids')
            partner_ids.update(
                channel_partner_ids.filtered(lambda p: p.id in allowed_partner_id_list or not p.user_ids).mapped('id')
            )

        # Include e.document.delegates
        date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        delegate_ids = self.sudo().env['e.document.delegate'].search([('date_start', '<=', date),
                                                                      ('date_stop', '>=', date)])
        partner_ids.update(delegate_ids.sudo().mapped('employee_id.user_id.partner_id.id'))

        partner_ids = list(partner_ids)
        return partner_ids

    @api.multi
    def get_document_link_tag(self):
        """ Generate HTML string tag to link to the document """
        self.ensure_one()
        template_name = self.template_id.name or ''
        try:
            doc_url = self._get_document_url()
            if doc_url:
                return '<a href=%s>%s</a>' % (doc_url, template_name)
        except Exception as e:
            return template_name

    @api.multi
    def inform_ceo_about_order_waiting_for_signature(self):
        """ Inform the CEO and related partners of an order waiting for their signature """
        for rec in self:
            # Generate message body
            document_link_tag = rec.get_document_link_tag()
            body = _('Naujas laukiantis pasirašymo įsakymas "%s"') % document_link_tag
            if rec.employee_id2:
                body += ' {}'.format(linksniuoti.kas_to_kam(rec.employee_id2.name))
            body += '.'

            # Generate message subject
            subject = _('Naujas įsakymas')
            company_name = str(self.env.user.company_id.name)
            if company_name:
                subject += ' ({})'.format(company_name)

            # Form message
            msg = {
                'body': body,
                'subject': subject,
                'priority': 'high',
                'front_message': True,
                'rec_model': 'e.document',
                'rec_id': rec.id,
                'view_id': rec.view_id.id or False,
                'partner_ids': rec.get_partners_to_inform_about_orders_waiting_for_signature()
            }

            rec.robo_message_post(**msg)

    @api.model
    def get_holidays_templates_ids(self):
        ''' Returns the IDs of request for holidays '''
        external_id_names = [
            'prasymas_del_tarnybines_komandiruotes_template',
            'prasymas_del_kasmetiniu_atostogu_template',
            'prasymas_del_nemokamu_atostogu_suteikimo_template',
            'prasymas_del_vaiko_prieziuros_atostogu_suteikimo_template',
            'prasymas_leisti_neatvykti_i_darba_template',
            'prasymas_suteikti_3_menesiu_atostogas_vaikui_priziureti_template',
            'prasymas_suteikti_kurybines_atostogas_template',
            'prasymas_suteikti_mokymosi_atostogas_template',
            'prasymas_suteikti_mokymosi_atostogas_dalyvauti_neformaliojo_suaugusiuju_svietimo_programose_template',
            'prasymas_del_papildomu_atostogu_template',
            'prasymas_del_nestumo_ir_gimdymo_atostogu_template',
            'prasymas_suteikti_tevystes_atostogas_template',
        ]

        ids = []
        for ext_id in external_id_names:
            full_ext_id = 'e_document.' + ext_id
            res_id = self.env.ref(full_ext_id, raise_if_not_found=False)
            if res_id:
                ids.append(res_id.id)
        return ids

    @api.model
    def get_holidays_order_templates_ids(self):
        """ Returns the IDs of order for holidays """
        holidays_order_template_ids = [
            self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_nemokamu_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_3_menesiu_atostogu_vaikui_priziureti_suteikimo_template').id,
            self.env.ref('e_document.isakymas_del_leidimo_neatvykti_i_darba_template').id,
            self.env.ref('e_document.isakymas_del_kurybiniu_atostogu_suteikimo_template').id,
            self.env.ref('e_document.isakymas_del_mokymosi_atostogu_template').id,
            self.env.ref(
                'e_document.isakymas_del_mokymosi_atostogu_dalyvauti_neformaliojo_suaugusiuju_svietimo_programose_template').id,
            self.env.ref('e_document.isakymas_del_papildomu_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_nestumo_ir_gimdymo_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_tevystes_atostogu_suteikimo_template').id,
            self.env.ref('e_document.isakymas_del_neatvykimo_i_darba_darbdaviui_leidus_template').id,
            self.env.ref('e_document.isakymas_del_komandiruotes_template').id,
            self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template').id,
            self.env.ref('e_document.isakymas_del_prastovos_skelbimo_template').id,
        ]
        return holidays_order_template_ids

    @api.model
    def check_intersecting_holidays(self, employee_id, date_from, date_to, holidays_template_ids):
        if date_from > date_to:
            raise exceptions.UserError(_('Neteisingas periodas.'))
        intersecting_holidays = self.env['hr.holidays'].search([('employee_id', '=', employee_id),
                                                                ('date_from_date_format', '<=', date_to),
                                                                ('date_to_date_format', '>=', date_from),
                                                                ('state', '=', 'validate')], count=True)
        if intersecting_holidays:
            return False
        if self._context.get('check_leaves_only'):
            return True
        intersecting_documents = self.env['e.document'].search([('id', '!=', self.id),
                                                                ('employee_id1', '=', employee_id),
                                                                ('state', '=', 'e_signed'),
                                                                ('template_id', 'in', holidays_template_ids),
                                                                ('rejected', '=', False),
                                                                '|',
                                                                '&',
                                                                ('date_from', '<=', date_from),
                                                                ('date_to', '>=', date_from),
                                                                '&',
                                                                ('date_from', '<=', date_to),
                                                                ('date_from', '>=', date_from),
                                                                ])
        for doc in intersecting_documents:
            # If the related order is not sign, we might block. If it is signed, the holiday record should be created
            # and caught by the previous check. If there is no holiday record, we should raise because it is a weird
            # state and accountant should check.
            if doc.record_model != 'e.document':
                continue
            record = self.env['e.document'].browse(doc.record_id).exists()
            if not record:
                return False
            if record.state in ['draft', 'confirm'] and record.document_type == 'isakymas':
                return False
            if record.record_model == 'hr.holidays' and not self.env['hr.holidays'].sudo().search_count([
                ('id', '=', record.record_id)
            ]):
                return False
        return True

    @api.multi
    def check_workflow_date_constraints(self):
        self.ensure_one()

        def _strp(date):
            return datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)

        allow_historical_signing_spec = self.sudo().env.user.company_id.e_documents_allow_historic_signing_spec
        allow_historical_signing = self.sudo().env.user.company_id.e_documents_allow_historic_signing
        template_id = self.sudo().template_id
        body = str()
        if not allow_historical_signing_spec:
            if template_id == self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template',
                                           raise_if_not_found=False):
                if self.date_document and self.date_1:
                    date_dt = datetime.strptime(self.date_document, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_now = datetime.utcnow()
                    if date_now > date_dt:
                        date_dt = date_now
                    date_dt_to = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if (date_dt - date_dt_to).days > 0:
                        body += _('Įsakymo data turi būti ne vėlesnė kaip atleidimo diena.')
            if template_id == self.env.ref('e_document.isakymas_del_priemimo_i_darba_template',
                                           raise_if_not_found=False):
                if self.date_document and self.date_from and self.date_2:
                    date_dt = datetime.strptime(self.date_document, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_now = datetime.utcnow()
                    if date_now > date_dt:
                        date_dt = date_now
                    date_dt_from = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_dt_req = datetime.strptime(self.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)

                    related_national_holidays = self.env['sistema.iseigines'].search([('date', '<=', self.date_from),
                                                                                      ('date', '>=',
                                                                                       self.date_document)]).mapped(
                        'date')
                    if date_dt > date_dt_from:
                        body += _('Įsakymo data turi būti ne vėlesnė kaip 2 d.d prieš įdarbinimo dieną.\n')
                    elif date_dt_req > date_dt:
                        body += _('Įsakymo data turi būti ne vėlesnė kaip 2 d.d prieš įdarbinimo dieną.\n')
                    else:
                        num_days = 0
                        while date_dt <= date_dt_from:
                            if date_dt.weekday() not in (5, 6) and date_dt.strftime(
                                    tools.DEFAULT_SERVER_DATE_FORMAT) not in related_national_holidays:
                                num_days += 1
                            date_dt += timedelta(days=1)
                        if num_days < 2:
                            body += _('Įsakymo data turi būti ne vėlesnė kaip 2 d.d prieš įdarbinimo dieną.\n')

            is_salygu_pakeitimo_doc = template_id == self.env.ref(
                'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template', raise_if_not_found=False)
            if is_salygu_pakeitimo_doc:
                now = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                if self.date_3 < now:
                    body += _('Įsigaliojimo data turi būti šiandienos ar velesnė data.')

        if not allow_historical_signing:
            if template_id == self.env.ref('e_document.prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_template',
                                           raise_if_not_found=False):
                if not self.date_1:
                    body += _('Nenurodyta pradžios data\n')
                else:
                    date_from_dt = datetime.strptime(self.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_from_dt <= datetime.now() + relativedelta(months=-1, day=31):
                        body += _('Negalima pasirašyti NPD prašymo ankstesne, nei einamojo mėnesio pirma diena.\n')

        if not self.check_dates_of_prasymas_isakymas_to_be_the_same():
            body += _('Skiriasi datos nustatytos prašyme, nuo datų, nustatytų šiame įsakyme.')

        fatherly_holiday_request_template = self.env.ref('e_document.prasymas_suteikti_tevystes_atostogas_template').id
        fatherly_holiday_order_template = self.env.ref(
            'e_document.isakymas_del_tevystes_atostogu_suteikimo_template').id
        if template_id.id in [fatherly_holiday_order_template, fatherly_holiday_request_template]:
            if self.date_from and self.date_to:
                duration = (_strp(self.date_to) - _strp(self.date_from)).days + 1
                if duration > 30:
                    body += _('Tėvystės atostogų trukmė negali viršyti 30 dienų')

        if template_id.id in [
            self.env.ref('e_document.isakymas_atleisti_nuo_darbo_valstybinems_(visuomeninems)_pareigoms_atlikti_template').id,
            self.env.ref('e_document.isakymas_del_3_menesiu_atostogu_vaikui_priziureti_suteikimo_template').id,
            self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_kurybiniu_atostogu_suteikimo_template').id,
            self.env.ref('e_document.isakymas_del_mokymosi_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_mokymosi_atostogu_dalyvauti_neformaliojo_suaugusiuju_svietimo_programose_template').id,
            self.env.ref('e_document.isakymas_del_nemokamu_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_nestumo_ir_gimdymo_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_papildomu_atostogu_template').id,
            self.env.ref('e_document.isakymas_del_prastovos_skelbimo_template').id,
            self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template').id,
            self.env.ref('e_document.isakymas_del_tevystes_atostogu_suteikimo_template').id,
            self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template').id,
        ]:
            if self.date_from and self.date_to:
                if self.date_from > self.date_to:
                    body += _('Data nuo negali būti vėlesnė už datą iki.')
            elif not self.date_from:
                body += _('Nenurodyta data nuo')
            elif not self.date_to:
                body += _('Nenurodyta data iki')

        return body

    @api.multi
    def check_workflow_constraints(self):
        self.ensure_one()
        template_id = self.sudo().template_id
        holidays_request_template_ids = self.get_holidays_templates_ids()
        body = str()
        holidays_order_template_ids = self.get_holidays_order_templates_ids()

        work_contract_condition_change_template = self.env.ref(
            'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template', False)
        work_relation_termination_template = self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template', False)
        salary_change_template = self.env.ref('e_document.isakymas_del_darbo_uzmokescio_pakeitimo_template', False)

        if template_id == work_relation_termination_template:
            try:
                date_end = self.employee_id2.with_context(date=self.date_1).contract_id.date_end or self.date_1
            except:
                date_end = self.date_1

            atleidimo_doc = self.env['e.document'].search_count([
                ('state', '=', 'signed'),
                ('template_id', '=', template_id.id),
                ('date_1', '=', date_end),
                ('employee_id2', '=', self.employee_id2.id)
            ])
            if atleidimo_doc:
                body += _('Egzistuoja pasirašytas įsakymas dėl darbo sutarties nutraukimo šiam darbuotojui.')

        if template_id in [self.env.ref('e_document.isakymas_del_priemimo_i_darba_template', raise_if_not_found=False),
                           work_contract_condition_change_template]:
            if self.darbo_grafikas in ['fixed', 'suskaidytos']:
                if self.fixed_attendance_ids and len(self.fixed_attendance_ids) > 0:
                    for weekday in self.fixed_attendance_ids.mapped('dayofweek'):
                        weekday_lines = self.fixed_attendance_ids.filtered(lambda r: r['dayofweek'] == weekday)
                        if len(weekday_lines) > 1:
                            weekday_lines.sorted(key=lambda r: (r['hour_from'], r['hour_to']))
                            hours_from = weekday_lines[1:].mapped('hour_from')
                            hours_to = weekday_lines[:-1].mapped('hour_to')
                            if any(h_from < h_to for h_from, h_to in zip(hours_from, hours_to)):
                                body += _("Grafiko savaitės dienų valandos negali kirstis.\n")
                else:
                    body += _('Nenurodytas grafikas\n')

            max_hours = 40.0
            if self.darbo_grafikas in ['sumine', 'individualus']:  # DK 115 straipsnis, 3 punktas.
                max_hours = 52.0 * self.etatas  # TODO THIS IS BAD, NEED DUAL CONTRACTS

            if self.weekly_work_hours_computed > max_hours:
                body += _('Negalima nustatyti grafiko, kuriame savaitės darbo '
                          'laiko norma viršija %s val. savaitę\n') % round(max_hours)

            self.check_mma_constraint()

        if template_id == salary_change_template:
            contract = self.env['hr.contract'].search([('employee_id', '=', self.employee_id2.id),
                                                       ('date_start', '<=', self.date_5)],
                                                      order='date_start desc', limit=1)
            if not contract:
                body += _('Darbuotojas %s neturi validaus kontrakto šiai datai. '
                          'Pirmiausia priimkite jį į darbą.') % self.employee_id2.name
            if contract and contract.date_start == self.date_5:
                date_before_dt = datetime.strptime(self.date_5, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)
                date_before = date_before_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                previous_contract = self.employee_id2.sudo().contract_ids.filtered(lambda c: c.date_end == date_before)
                if not previous_contract:
                    body += _(
                        'Norint pakeisti naujos darbo sutarties atlyginimą, atšaukine pradinį įsakymą ir sukurkite '
                        'naują įsakymą dėl priėmimo į darbą.\n')
            if contract.date_end and contract.date_end >= self.date_5:
                date_dt = datetime.strptime(self.date_5, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_is_first_day = date_dt == date_dt + relativedelta(day=1)
                terminated_to_non_terminated = contract.rusis == 'terminuota' and self.darbo_rusis == 'neterminuota'
                if contract.rusis != self.darbo_rusis and not terminated_to_non_terminated and not date_is_first_day:
                    body += _('Sutarties rūšį galite keisti tik nuo mėnesio pirmos dienos.\n')

            if contract.date_end and contract.date_end < self.date_5:
                body += _('Darbuotojo(-os) kontraktas baigėsi %s. Turite iš naujo įdarbinti '
                          'darbuotoją užpildydami įsakymą dėl priėmimo į darbą\n' % contract.date_end)

            if contract and self.struct != contract.struct_id.code:
                date_dt = datetime.strptime(self.date_5, tools.DEFAULT_SERVER_DATE_FORMAT)
                if date_dt != date_dt + relativedelta(day=1):
                    body += _('Atlyginimo struktūrą galite keisti tik nuo mėnesio pirmos dienos.\n')

        if template_id == self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template',
                                       raise_if_not_found=False):
            cancel_doc = self.cancel_id
            if cancel_doc.template_id == self.env.ref('e_document.isakymas_del_priemimo_i_darba_template'):
                contract = False
                if cancel_doc.record_id and cancel_doc.record_model == 'hr.contract':
                    contract = self.env['hr.contract'].browse(cancel_doc.record_id).exists()
                if not contract:
                    body += _('Employee contract not found. Please contact your accountant.')
                else:
                    payslips = self.env['hr.payslip'].search([('contract_id', '=', contract.id)], limit=1)
                    if payslips:
                        body += _(
                            'Negalite atšaukti priėmimo į darbą, nes darbuotojui jau buvo paskaičiuotas atlyginimas. '
                            'Jei manote, kad tai klaida, informuokite buhalterį parašydami žinutę dokumento apačioje'
                        )
        if template_id == self.env.ref('e_document.isakymas_del_priemimo_i_darba_template', raise_if_not_found=False):

            if tools.float_compare(self.float_1, 0, 2) <= 0:
                body += _('Nurodytas darbo užmokestis negali būti nulinis!\n')
            # TODO: maybe do something for different types of contract. Some are maybe cumulative? Here we assume full-time contracts

            domain = [('employee_id', '=', self.employee_id2.id),
                      '|',
                      ('date_end', '=', False),
                      ('date_end', '>=', self.date_from)]
            if self.date_6:  # date_6 is mapped to date_to: end of contract
                domain += [('date_start', '<=', self.date_6)]
            existing_contracts = self.env['hr.contract'].search(
                domain)  # todo: Maybe limit=1 is enough, with some adequate sorting, but not sure
            if existing_contracts:
                domain = [('record_model', '=', 'hr.contract'),
                          ('record_id', 'in', existing_contracts.ids),
                          ('state', 'in', ['e_signed'])]
                orders = self.search(domain, order='date_signed desc')
                if not orders or not all(o.rejected for o in orders):
                    body += _('Šiame periode jau yra aktyvi darbo sutartis. '
                              'Jei reikia pagalbos, informuokite buhalterį parašydami žinutę dokumento apačioje.')

        if template_id == self.env.ref('e_document.isakymas_del_komandiruotes_grupei_template',
                                       raise_if_not_found=False):
            body = str()
            if self.e_document_line_ids:
                for line in self.e_document_line_ids:
                    if tools.float_compare(line.float_1, 0, 2) <= 0 or line.int_1 == 0:
                        body += _('Dienpinigių Suma/Procentai turi būti daugiau už nulį!\n')
            if self.business_trip_worked_on_weekends == 'true':
                body += _(
                    'Privalomas darbuotojo prašymas/sutikimas dirbti poilsio dieną. Grupinė komandiruotė negalima,'
                    ' darbuotojams formuokite atskirus komandiruočių įsakymus.')

        if template_id == self.env.ref('e_document.isakymas_del_priedo_skyrimo_template', raise_if_not_found=False):
            date_payout = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
            period_to = datetime.strptime(self.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)

            confirmed_payslip = self.env['hr.payslip'].sudo().search([
                ('employee_id', '=', self.employee_id2.id),
                ('date_to', '=', (date_payout + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
                ('state', '=', 'done')
            ])

            if date_payout.year < period_to.year or (
                    date_payout.year == period_to.year and date_payout.month < period_to.month) or confirmed_payslip:
                body += _(
                    'Negalima pasirašyti priedo skyrimo, nes išmokėjimo periodas yra ankstesnis nei laikotarpio už'
                    ' kurį išmokama pabaiga arba išmokėjimo datai jau egzistuoja patvirtintas algalapis')

        if template_id == self.env.ref('e_document.isakymas_del_naudojamo_ligos_koeficiento_template',
                                       raise_if_not_found=False):
            if not 1 >= self.float_1 > 0:
                body += _('Koeficientas turi būti reikšmė tarp 0 ir 1!')

        if template_id == self.env.ref('e_document.prasymas_del_kasmetiniu_atostogu_template',
                                       raise_if_not_found=False):
            leave_days = self.sudo().employee_id1.contract_id.with_context(
                calculating_holidays=True).get_num_work_days(self.date_from, self.date_to)
            appointment_id = self.sudo().employee_id1.contract_id.with_context(date=self.date_from).appointment_id
            if leave_days == 0 and appointment_id.schedule_template_id.template_type in ['fixed']:
                body += _('Pasirinktame atostogų periode nerasta darbo dienų.')

        if template_id == self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template') or \
                template_id == self.env.ref('e_document.prasymas_del_kasmetiniu_atostogu_template'):
            body, holidays_in_advance = self.sudo().calculate_negative_holidays(body)
            if self.env.user.company_id.accumulated_days_policy == 'deny':
                if holidays_in_advance > 0:
                    body += _('''
                        Negalima pasirašyti dokumento, nes darbuotojo atostogų 
                        likutis mažesnis už nurodytą atostogų skyrimo periodą
                        ''')

        if template_id == salary_change_template:
            contract = self.env['hr.contract'].search(
                [('employee_id', '=', self.employee_id2.id), ('date_start', '<=', self.date_5), '|',
                 ('date_end', '=', False),
                 ('date_end', '>=', self.date_5)],
                order='date_start desc', limit=1)

            later_appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', contract.id),
                                                                            ('date_start', '>', self.date_5)
                                                                            ], limit=1)
            if later_appointment:
                body += _('Egzistuoja aktyvus sutarties priedas prasidedantis %s dieną, '
                          'jeigu norite pasirašyti šį dokumentą pirmiausia '
                          'atšaukite šį priedą') % later_appointment.date_start

            potential_duplicate = self.env['hr.contract.appointment'].search([('contract_id', '=', contract.id),
                                                                              ('date_start', '=', self.date_5)
                                                                              ], limit=1)
            if potential_duplicate:
                duplicate_doc = self.env['e.document'].search([
                    ('state', '=', 'signed'),
                    ('template_id', '=', salary_change_template.id),
                    ('date_5', '=', self.date_5),
                    ('employee_id2', '=', self.employee_id2.id),
                    ('id', '!=', self.id)
                ])
                if duplicate_doc:
                    body += _('Jau egzistuoja pasirašytas įsakymas dėl darbo užmokesčio keitimo tai pačiai dienai.')

        if template_id.id in holidays_order_template_ids or template_id == self.env.ref(
                'e_document.isakymas_del_komandiruotes_template'):
            if self.date_from and self.date_to and self.employee_id2:
                employee_id = self.employee_id2.id
                date_from = self.date_from
                date_to = self.date_from if self.template_id.id == self.env.ref(
                    'e_document.isakymas_del_nestumo_ir_gimdymo_atostogu_template').id else self.date_to
                # TODO should only one day that has contract be enough to form hr.holidays or all of them have to have holidays? Right now - all
                contract = self.env['hr.contract'].search([
                    ('employee_id', '=', employee_id),
                    ('date_start', '<=', date_from),
                    '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', date_to)
                ])
                if self.employee_id2.type != 'mb_narys' and not contract:
                    body += _('Darbuotojas neturi aktyvaus kontrakto nurodytam periodui')

        if template_id.id in holidays_request_template_ids and not self.not_check_holidays:
            if not self.check_intersecting_holidays(self.employee_id1.id, self.date_from, self.date_to,
                                                    holidays_request_template_ids):
                body += _(
                    'Jūsų prašymas kirstųsi su jau esančiu atostogų/komandiruočių prašymu ir/ar darbuotojo neatvykimu.')

        if template_id == self.env.ref(
                'e_document.isakymas_del_terminuotos_darbo_sutarties_pasibaigimo_ir_darbo_santykiu_tesimo_pagal_neterminuota_darbo_sutarti_template',
                raise_if_not_found=False):
            if not self.employee_id2:
                body += _('Nepasirinktas darbuotojas')
            else:
                employee_contracts = self.env['hr.contract'].search([
                    ('employee_id', '=', self.employee_id2.id)
                ])
                employee_contracts = employee_contracts.sorted(key='date_start', reverse=True)

                if not employee_contracts:
                    body += _('Darbuotojos neturi darbo sutarties')
                else:
                    last_contract = employee_contracts[0]

                    if not last_contract.date_end:
                        body += _('Paskutinė darbuotojo darbo sutartis nėra terminuota (neturi pabaigos datos)')
                    else:
                        last_possible_date_end_to_continue = (datetime.utcnow() - relativedelta(days=1)).strftime(
                            tools.DEFAULT_SERVER_DATE_FORMAT)

                        if last_contract.date_end < last_possible_date_end_to_continue:
                            body += _(
                                'Paskutinė darbuotojo darbo sutartis baigiasi anksčiau, nei vakar diena. Norint pratęsti darbo santykius su darbuotoju - pasirašykite įsakymą dėl priėmimo į darbą')

        if template_id == work_contract_condition_change_template:
            contract_id = self.contract_id_computed
            if not contract_id:
                body += _('Jūsų pasirinktai datai nepavyko nustatyti aktyvios darbuotojo sutarties. Įsakymas turėtų '
                          'įsigalioti kol dar galioja dabartinė darbuotojo sutartis')
            elif not (self.wage_being_changed or self.job_id_being_changed or self.department_id2_being_changed or
                      self.struct_id_being_changed or self.etatas_being_changed or self.work_norm_being_changed or
                      self.darbingumas_being_changed or self.schedule_type_being_changed or
                      self.schedule_times_being_changed or self.contract_end_being_changed or
                      self.contract_type_being_changed or self.advance_amount_being_changed or self.selection_1_being_changed):
                body += _('Nesikeičia darbo sutarties sąlygos.')
            else:
                later_appointment = self.env['hr.contract.appointment'].search([('contract_id', '=', contract_id.id),
                                                                                ('date_start', '>', self.date_3)
                                                                                ], limit=1)
                if later_appointment:
                    body += _('Egzistuoja aktyvus sutarties priedas prasidedantis %s dieną, '
                              'jeigu norite pasirašyti šį dokumentą pirmiausia '
                              'atšaukite šį priedą') % later_appointment.date_start

                potential_duplicate = self.env['hr.contract.appointment'].search([('contract_id', '=', contract_id.id),
                                                                                  ('date_start', '=', self.date_3)
                                                                                  ], limit=1)
                if potential_duplicate:
                    duplicate_doc = self.env['e.document'].search([
                        ('state', '=', 'signed'),
                        ('template_id', '=', work_contract_condition_change_template.id),
                        ('date_3', '=', self.date_3),
                        ('employee_id2', '=', self.employee_id2.id),
                        ('id', '!=', self.id)
                    ])
                    if duplicate_doc:
                        body += _('Jau egzistuoja pasirašytas įsakymas dėl darbo sutarties sąlygų pakeitimo.')

                    duplicate_doc = self.env['e.document'].search([
                        ('state', '=', 'signed'),
                        ('template_id', '=', salary_change_template.id),
                        ('date_5', '=', self.date_3),
                        ('employee_id2', '=', self.employee_id2.id),
                        ('id', '!=', self.id)
                    ])
                    if duplicate_doc:
                        body += _('Egzistuoja pasirašytas įsakymas dėl darbo užmokesčio keitimo tai pačiai dienai.\n'
                                  'Norėdami keisti darbo sutarties sąlygas - atšaukite įsakymą dėl darbo užmokęsčio pakeitimo')

                if tools.float_compare(self.float_1, 0, 2) <= 0:
                    body += _('Nurodytas darbo užmokestis negali būti nulinis!\n')

                if contract_id.date_start == self.date_3:
                    date_before_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(
                        days=1)
                    date_before = date_before_dt.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                    previous_contract = self.employee_id2.sudo().contract_ids.filtered(
                        lambda c: c.date_end == date_before)
                    if not previous_contract:
                        body += _(
                            'Norint pakeisti naujos darbo sutarties sąlygas, atšaukine pradinį įsakymą ir sukurkite '
                            'naują įsakymą dėl priėmimo į darbą.\n')

                if contract_id.date_end and contract_id.date_end >= self.date_3:
                    date_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                    date_is_first_day = date_dt == date_dt + relativedelta(day=1)
                    terminated_to_non_terminated = contract_id.rusis == 'terminuota' and self.darbo_rusis == 'neterminuota'
                    if contract_id.rusis != self.darbo_rusis and not terminated_to_non_terminated and not date_is_first_day:
                        body += _('Sutarties rūšį galite keisti tik nuo mėnesio pirmos dienos.\n')

                if contract_id.date_end and contract_id.date_end < self.date_3:
                    body += _('Darbuotojo(-os) kontrakto pabaigos data %s. Turite iš naujo įdarbinti '
                              'darbuotoją užpildydami įsakymą dėl priėmimo į darbą\n' % contract_id.date_end)

                if self.struct != contract_id.struct_id.code:
                    date_dt = datetime.strptime(self.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                    if date_dt != date_dt + relativedelta(day=1):
                        body += _('Atlyginimo struktūrą galite keisti tik nuo mėnesio pirmos dienos.\n')

                atleidimo_doc = self.env['e.document'].search([
                    ('state', '=', 'signed'),
                    ('template_id', '=', work_relation_termination_template.id),
                    ('date_1', '=', contract_id.date_end),
                    ('employee_id2', '=', self.employee_id2.id)
                ])
                if atleidimo_doc and self.date_6 != contract_id.date_end:
                    body += _('Egzistuoja pasirašytas įsakymas dėl darbo sutarties nutraukimo šiai darbo sutarčiai.\n'
                              'Šios darbo sutarties pabaigos datos keisti nebegalima')

                set_to_terminate = self.darbo_rusis in ['terminuota', 'laikina_terminuota', 'pameistrystes',
                                                        'projektinio_darbo']
                day_after_tomorrow = (datetime.now() + relativedelta(days=2)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                if self.date_6 and set_to_terminate and day_after_tomorrow > self.date_6 != contract_id.date_end:
                    body += _('Negalima sutrumpinti darbo sutarties daugiau, nei 2 dienos nuo šiandienos.')

                if set_to_terminate and not self.date_6:
                    body += _('Darbo sutartis pagal nurodytą darbo sutarties rūšį privalo turėti pabaigos datą')

                is_terminated = self.darbo_rusis in ['terminuota', 'laikina_terminuota', 'pameistrystes',
                                                     'projektinio_darbo']
                if self.date_6 and self.date_1:
                    if self.date_1 > self.date_6 and is_terminated:
                        body += _(
                            'Bandomajo laikotarpio pabaigos data privalo būti ankstesnė už darbo sutarties pabaigos datą')
                    if self.date_1 < contract_id.date_start:
                        body += _(
                            'Bandomajo laikotarpio pabaigos data privalo būti vėlesnė už darbo sutarties pradžios datą (%s)') % (
                                    contract_id.date_start)
                    if contract_id.trial_date_start and self.date_1 < contract_id.trial_date_start:
                        body += _(
                            'Bandomajo laikotarpio pabaigos data privalo būti vėlesnė už bandomajo laikotarpio pradžios datą (%s)') % (
                                    contract_id.trial_date_start)
                if contract_id.date_end:
                    later_contracts = self.env['hr.contract'].search([
                        ('employee_id', '=', self.employee_id2.id),
                        ('date_start', '>=', contract_id.date_end)
                    ], order='date_start asc', limit=1)
                    if later_contracts and not self.date_6:
                        body += _(
                            'Egzistuoja vėliau prasidedanti darbuotojo sutartis, todėl privaloma nustatyti darbo šios darbo sutarties pabaigos datą.\n'
                            'Sekanti darbo sutartis prasideda %s') % later_contracts.date_start
                    elif later_contracts and self.date_6 >= later_contracts.date_start:
                        body += _(
                            'Egzistuoja vėliau prasidedanti darbuotojo sutartis, todėl šios darbo sutarties pabaigos data privalo būti ankstesnė už sekančios darbo sutarties pradžios datą.\n'
                            'Sekanti darbo sutartis prasideda %s') % later_contracts.date_start

        # Check for closed slips or batches;
        bonus_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_template', raise_if_not_found=False)
        group_bonus_template = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template',
                                            raise_if_not_found=False)
        recruitment_template = self.env.ref('e_document.isakymas_del_priemimo_i_darba_template', False)
        if template_id == recruitment_template:
            has_closed_run = self.env['hr.payslip.run'].sudo().search_count([
                ('date_end', '>=', self.date_from),
                ('state', '=', 'close'),
            ])
            if has_closed_run:
                raise exceptions.ValidationError(_('You cannot sign this document because there is at least one '
                                                   'validated payslip batch after the chosen start date'))
        elif template_id in [bonus_template, group_bonus_template, salary_change_template,
                             work_contract_condition_change_template]:
            group_template = (template_id == group_bonus_template)
            if group_template:
                employee_ids, operator = self.get_document_lines().mapped('employee_id2.id'), 'in'
            else:
                employee_ids, operator = self.employee_id2.id, '='
            has_closed_slip = bool(self.env['hr.payslip'].sudo().search_count([
                ('employee_id', operator, employee_ids),
                ('date_from', '<=', self.date_3),
                ('date_to', '>=', self.date_3),
                ('state', '=', 'done')
            ]))
            if has_closed_slip:
                raise exceptions.ValidationError(_(
                    'Negalite pasirašyti šio dokumento, nes periode egzistuoja patvirtintas darbuotojo algalapis'))

        if template_id == self.env.ref('e_document.isakymas_del_atsaukimo_is_kasmetiniu_atostogu_template',
                                       raise_if_not_found=False):
            if not self.date_1:
                raise exceptions.UserError(_('Nenustatyta atostogų nutraukimo data'))
            holiday = self.env['hr.holidays'].search_count([
                ('state', '=', 'validate'),
                ('type', '=', 'remove'),
                ('employee_id', '=', self.employee_id2.id),
                ('date_to_date_format', '>=', self.date_1),
                ('date_from_date_format', '<=', self.date_1),
                ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_cl').id)
            ])
            if not holiday:
                body += _('Darbuotojas pasirinktai datai neatostogauja')

        if template_id in [
            self.env.ref('e_document.prasymas_del_vaiko_prieziuros_atostogu_suteikimo_template'),
            self.env.ref('e_document.isakymas_del_vaiko_prieziuros_atostogu_template'),
            self.env.ref('e_document.prasymas_suteikti_tevystes_atostogas_template'),
            self.env.ref('e_document.isakymas_del_tevystes_atostogu_suteikimo_template')
        ]:
            self.check_valid_parental_leave_dates()

        return body

    @api.multi
    def full_workflow_execution(self):
        self.ensure_one()
        if not self.sudo().skip_constraints:
            errors = self.sudo().check_workflow_constraints()
            errors_date = self.sudo().check_workflow_date_constraints()
            if errors or errors_date:
                body = errors_date + errors
                raise exceptions.UserError(body)
        else:
            _logger.info('Workflow check was skipped for document %s' % self.id)
        try:
            self.workflow_execution()
        except Exception as e:
            self._handle_workflow_exception(e)

    @api.multi
    def _handle_workflow_exception(self, exception):
        self.ensure_one()
        import traceback
        tests_enabled = tools.config.get('test_enable')
        message_admins = traceback.format_exc()
        try:
            message_accountants = exception.name
        except AttributeError:
            try:
                message_accountants = exception.args[0]
            except AttributeError:
                message_accountants = ''
        if not tests_enabled:
            self._cr.rollback()
        simulate = self._context.get('simulate', False)
        is_request = self.document_type == 'prasymas'
        if not self.sudo().skip_constraints and not simulate and not is_request:
            # Create or write in ticket if signing of non-request e-document fails
            ticket = self.env['client.support.ticket'].sudo().search([
                ('rec_model', '=', 'e.document'),
                ('rec_id', '=', self.id),
                ('user_id', '=', self.env.user.id),
                ('state', '=', 'open'),
            ])
            if not ticket:
                ticket = self.env['client.support.ticket'].sudo().create({
                    'rec_model': 'e.document',
                    'rec_id': self.id,
                    'user_id': self.env.user.id,
                    'reason': 'edoc',
                    'subject': _('Pasirašymas'),
                })
            ticket.sudo(self.env.user).with_context(ignore_rec_model=True).robo_message_post(
                body=_('Nepavyko pasirašyti dokumento.'),
                subject=_('Pasirašymas'),
                subtype='robo.mt_robo_front_message',
                robo_chat=True,
                content_subtype='html',
                front_message=True, message_type='notification')
        if not is_request:
            # Send email to accountant
            findir_email = self.sudo().env.user.company_id.findir.partner_id.email
            database = self._cr.dbname
            if not self.sudo().skip_constraints:
                subject = 'Nepavyko pasirašyti el. dokumento [%s]' % database
            else:
                subject = 'Nepavyko įvykdyti pasirašyto el. dokumento eigos [%s]' % database
            doc_url = self._get_document_url()
            doc_name = '<a href=%s>%s</a>' % (doc_url, self.name) if doc_url else self.name
            if not self.sudo().skip_constraints:
                message = 'Nepavyko pasirašyti dokumento %s. Jums buvo sukurta nauja užklausa.' % doc_name
            else:
                message = 'Nepavyko įvykdyti pasirašyto el. dokumento eigos %s' % doc_name
            if message_accountants:
                message += '<br/>Klaida: %s' % message_accountants
            # We always send message of non-request e-documents if workflow constraints were skipped
            # or if error message is new
            condition_1 = not self.sudo().skip_constraints and message != self.last_message_sent and findir_email
            condition_2 = self.sudo().skip_constraints and findir_email
            if condition_1 or condition_2:
                if condition_1:
                    self.last_message_sent = message
                self.env['script'].sudo().send_email(emails_to=[findir_email],
                                                     subject=subject,
                                                     body=message)
        # Create bug report
        if message_admins and not simulate:
            database = self._cr.dbname
            if not self.sudo().skip_constraints:
                subject = 'Failed to sign [%s]' % database
            else:
                subject = 'Forced sign without workflow [%s]' % database
            template = self.sudo().template_id.name
            details = 'Template: %s\n<br/>Doc id: %s' % (template, self.id)
            self.env['robo.bug'].sudo().create({
                'user_id': self.env.user.id,
                'error_message': subject + '<br/>' + details + '<br/>' + message_admins,
            })
        if not tests_enabled:
            self._cr.commit()
        if not self.sudo().skip_constraints or simulate:
            msg = _('Klaida %s ') % str(exception.args[0]) if exception.args else ''
            _logger.info('Failed to sign document: %s', msg)

            if msg != '' and (self.env.user.is_accountant() or
                              isinstance(exception, (exceptions.UserError, exceptions.ValidationError))):
                raise exceptions.UserError(msg)
            else:
                raise exceptions.UserError(_('Nepavyko pasirašyti dokumento. Informuokite buhalterį parašydami '
                                             'žinutę dokumento apačioje.'))
        else:
            # forced workflow for orders
            self.failed_workflow = True
            self._set_document_number()

    @api.multi
    def open_invite_to_sign_wizard(self):
        action = self.env.ref('e_document.action_invite_to_sign_wizard').read()[0]
        if len(self) == 1:
            user_ids = self.find_remaining_users()
            action['context'] = {'default_e_document_id': self.id, 'default_user_items': user_ids,
                                 'default_signed_user_ids': self.user_ids.mapped('user_id.id')}
        return action

    @api.multi
    def find_remaining_users(self):
        """
        Find users that are not yet included in user_ids (signed.users) of e-document and that are not system admins
        :return: A list of values for signed.users records creation
        """
        self.ensure_one()
        base_group = self.env.ref('base.group_system').id
        excluded_user_ids = self.user_ids.mapped('user_id.id')
        users = self.env['hr.employee'].search([]).mapped('user_id').filtered(lambda u: u.groups_id != base_group
                                                                              and u.id not in excluded_user_ids)
        items = []
        for user in users:
            items.append((0, 0, {
                'user_id': user.id
            }))

        return items

    @api.multi
    def action_mark_signed(self):
        self.ensure_one()
        res_id = self.env['e_document.mark_signed'].create({'e_document_id': self.id}).id
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'e_document.mark_signed',
            'res_id': res_id,
            'view_id': self.env.ref('e_document.mark_signed_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.multi
    def mark_signed(self):
        self.ensure_one()
        is_a_request = self.document_type == 'prasymas'
        if not is_a_request or self.state in ['e_signed', 'cancel']:
            raise exceptions.ValidationError(_('Netinkama dokumento būsena, kad būtų galima šį dokumentą pažymėti, '
                                               'kaip pasirašytą'))
        if not self.env.user.has_group('e_document.group_robo_mark_requests_signed'):
            raise exceptions.ValidationError(_('Neturite teisės pažymėti dokumentos, kaip pasirašytus'))
        politika_atostogu_suteikimas = self.env.user.sudo().company_id.politika_atostogu_suteikimas
        if politika_atostogu_suteikimas == 'ceo' or (
                not self.template_id.send_manager and politika_atostogu_suteikimas == 'department'):
            self.full_workflow_execution()
        self.date_signed = datetime.utcnow()
        self.sudo().write({
            'marked_as_signed': True,
            'no_mark': True,
            'signed_user_id': self.env.user.id,
        })
        self.create_pdf()
        self.sudo().state = 'e_signed'
        self.sudo().set_related_prasymai_isakymas_signed()
        self.env['e.document'].accountants_subscribe(self)
        if self.document_type == 'prasymas' and politika_atostogu_suteikimas != 'ceo' and self.template_id.send_manager:
            self.sudo().approve_status = 'waiting_approval'

        doc_name = self.display_name
        try:
            doc_url = self._get_document_url()
            if doc_url:
                doc_name = '<a href=%s>%s</a>' % (doc_url, doc_name)
        except:
            pass

        msg = {
            'body': _('Dokumentas - %s buvo pažymėtas, kaip pasirašytas. Prie šio dokumento turėjo būti prisegtas '
                      'skenuotas pasirašytas originalas. Prašome peržiūrėti šį dokumentą.') % doc_name,
            'subject': _('Prašymas buvo pažymėtas kaip pasirašytas.') + ' [%s]' % self.env.cr.dbname,
            'priority': 'high',
            'front_message': True,
            'rec_model': 'e.document',
            'rec_id': self.id,
            'view_id': self.view_id.id or False,
        }

        mail_channel = self.env.ref('e_document.mark_signed_requests_mail_channel', False)
        if mail_channel:
            # Just posts the message to the channel but should not send an email
            mail_channel.sudo().message_post(**msg)

            channel_partner_ids = mail_channel.sudo().mapped('channel_partner_ids')
            allowed_users = mail_channel.sudo().mapped('group_public_id.users')
            allowed_partner_ids = channel_partner_ids.sudo().with_context(active_test=False).filtered(
                lambda p: any(user_id in allowed_users for user_id in p.user_ids) or not p.user_ids
            )

            msg.update({
                'partner_ids': allowed_partner_ids.ids
            })
        else:
            partner_ids = self.mapped('company_id.findir.partner_id.id')
            if partner_ids:
                msg['partner_ids'] = partner_ids
        self.sudo().robo_message_post(**msg)

    @api.multi
    def mass_sign(self):
        failure_msg = _('{} {} - {}. Klaida - {}\n')
        failed_to_confirm = str()
        failed_to_sign = str()
        documents_to_sign = self.filtered(lambda x: x.state in ['draft', 'confirm'])
        documents_not_running = documents_to_sign.filtered(lambda d: d.state == 'confirm' and not d.running)
        documents_not_running.sudo().write({'running': True})
        tests_enabled = tools.config.get('test_enable')
        if not tests_enabled:
            self.env.cr.commit()
        for rec in documents_to_sign:
            if rec.state in ['draft']:
                try:
                    rec.confirm()
                    if not tests_enabled:
                        self.env.cr.commit()
                except Exception as exc:
                    failed_to_confirm += failure_msg.format(rec.name, rec.date_from_display or '',
                                                            rec.date_to_display or '', exc.args[0])
                    continue
            if rec.state in ['confirm']:
                try:
                    kwargs = {}
                    if rec.id in documents_not_running.ids:
                        kwargs['running_bypass'] = True
                    rec.sign(**kwargs)
                    if not tests_enabled:
                        self.env.cr.commit()
                except Exception as exc:
                    failed_to_sign += failure_msg.format(rec.name, rec.date_from_display or '',
                                                         rec.date_to_display or '', exc.args[0])
        err = ''
        if failed_to_confirm != '':
            err += _('Nepavyko suformuoti šių dokumentų:\n\n{}\n').format(failed_to_confirm)
        if failed_to_sign != '':
            err += _('Nepavyko pasirašyti šių dokumentų:\n\n{}').format(failed_to_sign)
        if err != '':
            if not tests_enabled:
                self.env.cr.rollback()
            documents_not_running.sudo().write({'running': False})
            if not tests_enabled:
                self.env.cr.commit()
            raise exceptions.Warning(err)

    @api.multi
    def check_user_can_sign(self, raise_if_false=True):
        """
        Check whether current user can sign the document
        :param raise_if_false: raise errors if the current user cannot sign
        :return: True / False
        """
        self.ensure_one()
        user = self.env.user
        company = user.sudo().company_id
        company_manager = company.vadovas.user_id
        is_manager = user == company_manager
        is_an_order = self.document_type == 'isakymas'
        is_a_request = self.document_type == 'prasymas'
        is_other = self.document_type == 'other'
        user_employees = user.employee_ids
        employee = False
        if is_a_request or is_other:
            employee = self.employee_id1
        elif is_an_order:
            employee = self.employee_id2
        document_employee_is_user = employee.id in user_employees.ids if user_employees and employee else False
        business_trip_bypass = self.business_trip_document and user.has_group('e_document.group_robo_business_trip_signer')
        if self.document_type in ['isakymas', 'agreement']:
            if not is_manager:
                is_signable_by_delegate = self.is_signable_by_delegate()
                if not is_signable_by_delegate:
                    if raise_if_false:
                        raise exceptions.UserError(
                            _('Tik įmonės vadovas gali pasirašyti šio tipo dokumentus.'))
                    return False
                is_delegate = False
                if self.reikia_pasirasyti_iki and user_employees:
                    is_delegate = user_employees[0].is_delegate_at_date(self.reikia_pasirasyti_iki)
                if not is_delegate and not business_trip_bypass:
                    if raise_if_false:
                        raise exceptions.UserError(
                            _('Tik įmonės vadovas ir įgalioti asmenys gali pasirašyti šio tipo dokumentus.'))
                    return False

                # holidays_order_template_ids = self.get_holidays_order_templates_ids()
                # if self.template_id.id in holidays_order_template_ids and document_employee_is_user:
                #     if raise_if_false:
                #         raise exceptions.UserError(_('Įgalioti asmenys negali pasirašyti įsakymo dėl savo atostogų.'))
                #     else:
                #         return False

        elif is_a_request or is_other:
            if not document_employee_is_user:
                if raise_if_false:
                    raise exceptions.UserError(_('Negalite pasirašyti už kitą asmenį'))
                else:
                    return False
        return True

    @api.multi
    def sign(self, **kwargs):
        self.ensure_one()
        if self.sudo().running and not kwargs.get('running_bypass'):
            _logger.info('User %s tried to sign running document %s', self.env.user.id, self.id)
            raise exceptions.Warning(_('Klaida, kažkas jau bando pasirašyti dokumentą, prašome perkrauti puslapį.'))

        if self.env.user.company_id.process_edoc_signing_as_job and not self._context.get('simulate'):
            self.sudo().write({'running': True})
            self._cr.commit()
            kwargs['running_bypass'] = True
            self.with_delay(channel='root.e_document', eta=5, max_retries=1)._sign(**kwargs)
        else:
            self._sign(**kwargs)

    @job
    def _sign(self, **kwargs):
        # Ensure document state
        if self.state in ['e_signed', 'cancel']:
            return

        if not self._context.get('simulate', False):
            # Set the document as running
            self.sudo().write({'running': True})
            # Commit the transaction before executing the workflow to set the running state
            if not tools.config.get('test_enable'):
                self.env.cr.commit()

        if self.user_ids:
            # Completely different process with multiple users
            self._execute_multi_user_sign_workflow(**kwargs)
        else:
            self._execute_regular_sign_workflow(**kwargs)

    @api.multi
    def _execute_multi_user_sign_workflow(self, **kwargs):
        self.ensure_one()

        # Get sign parameters
        simulate = self._context.get('simulate', False)
        tests_enabled = tools.config.get('test_enable')

        # Get company and document parameters
        user = self.env.user
        company = user.company_id.sudo()
        template = self.template_id
        is_signable_by_delegate = not template or (template.is_signable_by_delegate and
                                                   template not in company.manager_restricted_document_templates)
        company_manager_user = company.vadovas.user_id

        # Generate a new cursor for signing the document or use existing cursor if tests are running
        new_cr = self.pool.cursor() if not tests_enabled else self._cr
        new_env = api.Environment(new_cr, self.env.user.id, {'lang': 'lt_LT'})
        doc = new_env['e.document'].browse(self.id)

        workflow_exception = None
        try:
            lines_waiting_for_signature = doc.sudo().user_ids.filtered(lambda r: r.state != 'signed')
            if simulate and lines_waiting_for_signature:
                user = lines_waiting_for_signature[0].user_id
                doc = doc.sudo(user.id)
            user_lines_waiting_for_signature = lines_waiting_for_signature.filtered(lambda r: r.user_id == user)
            no_one_has_signed = 'signed' not in doc.sudo().user_ids.mapped('state')
            if user_lines_waiting_for_signature:
                if no_one_has_signed:
                    try:
                        doc.execute_first_sign_workflow()
                    except Exception as e:
                        doc._handle_workflow_exception(e)

                if lines_waiting_for_signature == user_lines_waiting_for_signature or simulate:
                    # Only waiting for signature from the user - execute last signature workflow
                    try:
                        errors = doc.sudo().check_workflow_constraints()
                        if errors:
                            raise exceptions.UserError(errors)
                        doc.execute_last_sign_workflow()
                    except Exception as e:
                        doc._handle_workflow_exception(e)
                    else:
                        if not simulate and doc.document_type == 'agreement':  # TODO why is the agreement type checked?
                            doc.sudo()._set_document_number()
                            doc.sudo().set_final_document()
                            doc.create_pdf()
                if not simulate:
                    user_lines_waiting_for_signature.sudo().sign(user_id=user.id)
                    if not tests_enabled:
                        new_cr.commit()
                return
            elif doc.user_id == user and not doc.sudo().user_ids.filtered(lambda r: r.user_id == user):
                # User is not in the list of users but is set as the user who should sign the document
                new_env['signed.users'].sudo().create({
                    'state': 'signed',
                    'user_id': user.id,
                    'document_id': doc.id,
                    'signed_by_delegate': False,
                    'date': datetime.utcnow(),
                })
                if no_one_has_signed:
                    try:
                        doc.execute_first_sign_workflow()
                    except Exception as e:
                        doc._handle_workflow_exception(e)

            # Execute delegate signing
            if is_signable_by_delegate and not simulate:
                manager_not_signed = doc.user_ids.filtered(lambda r: r.state != 'signed' and
                                                                     r.user_id == company_manager_user)
                doc_date = doc.reikia_pasirasyti_iki or datetime.today().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                is_delegate = any(employee.is_delegate_at_date(doc_date) for employee in user.employee_ids)
                if manager_not_signed and is_delegate:
                    manager_not_signed.sudo().sign(user_id=user.id, delegate=True)

            if not tests_enabled and not simulate:
                new_cr.commit()
        except Exception as e:
            workflow_exception = e
            if not tests_enabled:
                new_cr.rollback()
        finally:
            if not tests_enabled:
                new_cr.close()
            if not simulate:
                if not tests_enabled:
                    self.env.cr.commit()
                self.sudo().write({'running': False})
                if not tests_enabled:
                    self.env.cr.commit()
            if workflow_exception is not None:
                raise workflow_exception
            return

    @api.multi
    def _should_execute_sign_workflow_as_sudo(self):
        self.ensure_one()
        execute_with_sudo = False
        if self.business_trip_document and self.env.user.has_group('e_document.group_robo_business_trip_signer'):
            execute_with_sudo = True
        return execute_with_sudo

    @api.multi
    def _execute_regular_sign_workflow(self, **kwargs):
        self.ensure_one()

        # Get sign parameters
        simulate = self._context.get('simulate', False)
        tests_enabled = tools.config.get('test_enable')

        # Determine basic document data
        is_an_order = self.document_type == 'isakymas'
        execute_as_sudo = self._should_execute_sign_workflow_as_sudo()

        # Get other parameters
        user = self.env.user
        validation_required_from = user.sudo().company_id.politika_atostogu_suteikimas
        should_execute_workflow = is_an_order or validation_required_from == 'ceo' or \
                                  (not self.template_id.send_manager and validation_required_from == 'department')

        # Check basic document constraints (if the signing is not being simulated)
        if not simulate:
            try:
                self.check_user_can_sign()
            except:
                self.env.cr.rollback()
                self.sudo().write({'running': False})
                self.env.cr.commit()
                raise
            self.sudo().write({'running': True})
            # Commit the transaction before executing the workflow to set the running state
            if not tests_enabled:
                self.env.cr.commit()

        # Generate a new cursor for signing the document or use existing cursor if tests are running
        new_cr = self.pool.cursor() if not tests_enabled else self._cr
        new_env = api.Environment(new_cr, user.id, self.env.context)
        doc = new_env['e.document'].browse(self.id)

        workflow_exception = None

        try:
            # Check if the workflow should be executed
            if should_execute_workflow:
                if execute_as_sudo:
                    doc.sudo().full_workflow_execution()
                else:
                    doc.full_workflow_execution()

            # After running the workflow in "simulate" mode rollback all the changes and don't do anything else
            if simulate:
                if not tests_enabled:
                    new_cr.rollback()
                return False

            # Update document data after signing
            doc.date_signed = datetime.utcnow()
            doc.sudo().signed_user_id = user.id
            doc.sudo().set_final_document()  # Explicitly re-generate document with signed_user_id
            doc.create_pdf()
            doc.write({'state': 'e_signed'})
            doc.sudo().set_related_prasymai_isakymas_signed()
            doc.request_confirmation_workflow()
            doc.inform_about_signing_the_document()
            doc.send_ticket_order_signed_for_past_date()
            doc.inform_about_fixed_term_exceeded_constraints()

            if not tests_enabled:
                new_cr.commit()
        except Exception as e:
            workflow_exception = e
            if not tests_enabled:
                new_cr.rollback()
        finally:
            if not tests_enabled:
                new_cr.close()
            if not simulate:
                if not tests_enabled:
                    self.env.cr.commit()
                self.sudo().write({'running': False})
                if not tests_enabled:
                    self.env.cr.commit()
            if workflow_exception is not None:
                raise workflow_exception

    @api.multi
    def execute_last_sign_workflow(self):
        return False

    @api.multi
    def execute_first_sign_workflow(self):
        return False

    @api.multi
    def request_confirmation_workflow(self):
        holiday_confirmation_policy = self.env.user.sudo().company_id.politika_atostogu_suteikimas
        if holiday_confirmation_policy != 'ceo':
            user_employee_ids = self.env.user.employee_ids.ids
            company_name = self.env.user.company_id.name

            docs = self.filtered(lambda d: d.document_type == 'prasymas' and d.template_id.send_manager)
            for rec in docs:
                rec.sudo().approve_status = 'waiting_approval'
                rec.try_auto_approve()

                department = rec.employee_id1.department_id
                department_manager_delegate = department.sudo().department_delegate_ids.\
                    filtered(lambda x: x.date_start <= rec.date_document <= x.date_stop)
                department_manager = department_manager_delegate[0].employee_id if department_manager_delegate \
                    else department.manager_id
                if department_manager and department_manager.id not in user_employee_ids:
                    user_is_not_the_department_manager = True
                else:
                    user_is_not_the_department_manager = False

                if rec.holiday_policy_inform_manager and user_is_not_the_department_manager:
                    partner = department_manager.address_home_id or department_manager.user_id.partner_id
                    if partner:
                        try:
                            doc_url = rec._get_document_url()
                            if doc_url:
                                doc_link_html = '<a href=%s>%s</a>' % (doc_url, rec.name)
                            else:
                                doc_link_html = rec.name or ''
                        except:
                            doc_link_html = rec.name or ''
                        body_str = _('Pasirašytas darbuotojo(-os) %s dokumentas -  %s, '
                                     'laukiama jūsų patvirtinimo. %s') % (rec.employee_id1.name or '',
                                                                          doc_link_html.lower(),
                                                                          company_name)
                        msg = {
                            'body': body_str,
                            'subject': _('Pasirašytas prašymas, laukiama jūsų patvirtinimo'),
                            'priority': 'high',
                            'front_message': True,
                            'rec_model': 'e.document',
                            'rec_id': rec.id,
                            'view_id': rec.view_id.id or False,
                            'partner_ids': partner.ids
                        }
                        rec.robo_message_post(**msg)

    @api.multi
    def inform_about_signing_the_document(self):
        annual_leave_template = self.env.ref('e_document.isakymas_del_kasmetiniu_atostogu_template')
        cancel_template_ids = [
            self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template').id,
            self.env.ref('e_document.isakymas_del_susitarimo_nutraukimo_template').id,
        ]

        for rec in self:
            all_doc_channels = self.env['mail.channel']
            if rec.document_type == 'prasymas':
                channel = self.env.ref('e_document.requests_mail_channel', raise_if_not_found=False)
                if channel:
                    all_doc_channels |= channel
            if rec.document_type == 'isakymas':
                channel = self.env.ref('e_document.orders_mail_channel', raise_if_not_found=False)
                if channel:
                    all_doc_channels |= channel
            all_doc_channels |= rec.template_id.sudo().sign_mail_channel_ids

            type_str = dict(rec._fields.get('document_type', False)._description_selection(self.env)).get(
                rec.document_type, '').lower()

            document_subject = _('Pasirašytas {0}').format(type_str)
            number_string = ''
            if rec.document_number and rec.document_number != '-':
                number_string = ' Nr. {0}'.format(rec.document_number)
                document_subject += number_string
            document_subject += ' ({0})'.format(self.env.user.company_id.name)

            document_body = _('Pasirašytas {0}').format((self.name or '').lower())
            if rec.document_number and rec.document_number != '-':
                document_body += _(', dokumento numeris - {0}.').format(rec.document_number)
            if rec.template_id.id in cancel_template_ids and rec.cancel_id.document_number and rec.cancel_id.document_number != '-':
                document_body += _(' Panaikinto dokumento numeris - {0}.').format(rec.cancel_id.document_number)
            if rec.related_employee_ids:
                names = ', '.join(rec.related_employee_ids.mapped('name'))
                document_body += _(' Darbuotojas(-ai) - {0}.').format(names)

            msg = {
                'body': document_body,
                'subject': document_subject,
                'message_type': 'comment',
                'subtype': 'mail.mt_comment'
            }
            if rec.generated_document:
                file_name = '{0}{1} ({2})'.format(
                    type_str.capitalize(),
                    number_string,
                    self.env.user.company_id.name
                )

                attach_id = self.with_context(default_type='binary').env['ir.attachment'].create({
                    'res_model': 'e.document',
                    'res_id': rec.id,
                    'type': 'binary',
                    'name': file_name + '.pdf',
                    'datas_fname': file_name + '.pdf',
                    'datas': rec.generated_document,
                })
                msg['attachment_ids'] = [attach_id.id]

            for doc_mail_channel in all_doc_channels:
                # Just posts the message to the channel but should not send an email
                doc_mail_channel.sudo().message_post(**msg)

            channel_partner_ids = all_doc_channels.sudo().mapped('channel_partner_ids')
            allowed_users = all_doc_channels.sudo().mapped('group_public_id.users')
            channel_partner_user_ids = channel_partner_ids.mapped('user_ids')
            partner_user_ids = channel_partner_user_ids.sudo().filtered(lambda u: not u.is_accountant() and u in allowed_users or
                                                                                  u.main_accountant or
                                                                                  u.substitute_accountant)

            msg_partner_ids = channel_partner_ids.filtered(lambda p: (any(
                p_user.id in partner_user_ids.ids for p_user in
                p.user_ids) or not p.user_ids) and not p.mokesciu_institucija)

            # Other conditions to force inform the accountant
            inform_accountant = False
            if rec.template_id.id == annual_leave_template.id and rec.politika_atostoginiai == 'rinktis' and \
                    rec.atostoginiu_ismokejimas == 'pries':
                inform_accountant = True

            if inform_accountant:
                msg_partner_ids |= rec.company_id.findir.partner_id

            msg.update({
                'priority': 'high',
                'front_message': True,
                'rec_model': 'e.document',
                'rec_id': rec.id,
                'view_id': rec.view_id.id or False,
                'partner_ids': msg_partner_ids.ids
            })
            rec.with_context(default_type='binary').robo_message_post(**msg)

    @api.multi
    def send_ticket_order_signed_for_past_date(self):
        """
        Method to inform accountant (by sending a ticket) about an order that was signed for a past date;
        """
        for rec in self.filtered(lambda d: d.document_type == 'isakymas'):
            date_document = rec.date_document

            date_from = rec.cancel_id.date_from_display if rec.cancel_id else rec.date_from_display
            if not date_from or date_from >= date_document:
                continue
            payslip_run = self.env['hr.payslip.run'].sudo().search([
                ('date_start', '<=', date_from),
                ('date_end', '>=', date_from),
            ])
            if not payslip_run or payslip_run.state != 'close':
                continue
            subject = _('Order was signed for a past date')
            body = _('Order "{0}" (#{1}) was signed for a past date').format(rec.name, rec.document_number)
            try:
                rec.create_internal_ticket(subject, body)
            except Exception as exc:
                message = 'Failed to create a ticket informing that an order was signed for a past date.' \
                          '\nError: {}'.format(str(exc.args))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })

    @api.multi
    def inform_about_fixed_term_exceeded_constraints(self):
        """
        Method to send a ticket to accountants if fixed-term work relation exceeds the boundaries as described in the
        following article of DK: http://www.infolex.lt/ta/368200:str68;
        """
        self.ensure_one()
        templates = [
            self.env.ref('e_document.isakymas_del_priemimo_i_darba_template'),
            self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template'),
        ]
        if self.template_id not in templates or self.darbo_rusis != 'terminuota' or not self.date_6:
            return

        # Find fixed term contracts of the employee, sort them by date DESC
        fixed_term_contracts = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id2.id),
            ('rusis', '=', 'terminuota'),
        ]).sorted(key='date_start', reverse=True)
        if not fixed_term_contracts:
            return

        month_limit_successive_contracts = 2
        year_limit_different_work_functions = 5
        year_limit_constant_work_functions = 2

        consecutive_contracts = fixed_term_contracts[0]
        for index, contract in enumerate(fixed_term_contracts):
            if contract == fixed_term_contracts[0]:
                continue
            newer_contract_date_start = datetime.strptime(fixed_term_contracts[index-1].date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
            contract_date_end = datetime.strptime(contract.date_end, tools.DEFAULT_SERVER_DATE_FORMAT)
            if contract_date_end + relativedelta(months=month_limit_successive_contracts) >= newer_contract_date_start:
                consecutive_contracts |= contract
            else:
                break

        # Fixed term consecutive period
        start_date = datetime.strptime(consecutive_contracts[-1].date_start, tools.DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(self.date_6, tools.DEFAULT_SERVER_DATE_FORMAT)

        send_message = False
        exceeded_years = False
        if start_date+relativedelta(years=year_limit_different_work_functions) < end_date:
            exceeded_years = year_limit_different_work_functions
            send_message = True
        elif start_date+relativedelta(years=year_limit_constant_work_functions) < end_date:
            exceeded_years = year_limit_constant_work_functions
            send_message = True
        if not send_message:
            return

        subject = _('Consecutive fixed term contracts exceeded the limits')
        body = _('Consecutive fixed-term contracts extending work relation with employee {} has exceeded {} years. '
                 'Make sure that the contract does not turn into an indefinite duration one because of the '
                 'constraints').format(self.employee_id2.name_related, exceeded_years, )
        try:
            self.create_internal_ticket(subject, body)
        except Exception as exc:
            self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)

    @api.multi
    def simulate_signing(self):
        tests_enabled = tools.config.get('test_enable')
        try:
            self.with_context(simulate=True).sign()
        except Exception as exc:
            if not tests_enabled:
                self.env.cr.rollback()
            raise exceptions.Warning(
                _('Nenumatyta klaida, klaidos pranešimas: %s') % str(exc.args[0]) if exc.args else '')
        if not tests_enabled:
            self.env.cr.rollback()
        raise exceptions.Warning(_('Dokumentas paruoštas pasirašymui'))

    @api.multi
    def check_skip_leave_creation(self):
        self.ensure_one()
        type1 = self.env.ref('hr_holidays.holiday_status_TA')
        type2 = self.env.ref('hr_holidays.holiday_status_VP')
        existing_holidays = self.env['hr.holidays'].search([
            ('type', '=', 'remove'),
            ('state', 'not in', ['cancel', 'refuse']),
            ('holiday_status_id', 'in', [type1.id, type2.id]),
            ('employee_id', '=', self.employee_id2.id),
            ('date_to', '>=', self.date_from),
            ('date_from', '<=', self.date_to),
        ])
        doc_number_exists = any(existing_holidays.mapped('numeris'))
        count = len(existing_holidays)
        return count > 0 and not doc_number_exists

    @api.multi
    def try_auto_approve(self):
        if self.env.user.sudo().company_id.politika_atostogu_suteikimas == 'ceo' \
                or not self.employee_id1.department_id.manager_id \
                or self.employee_id1.department_id.manager_id.id in self.env.user.employee_ids.ids:
            self.with_context(auto_approve=True).action_approve()

    @api.multi
    def action_approve(self):
        for rec in self:
            if rec.state != 'e_signed':
                raise exceptions.Warning(_('Galima patvirtinti tik pasirašytus dokumentus.'))
            if rec.allow_approve:
                rec.sudo().write({'approve_status': 'approved'})
                rec.full_workflow_execution()
                robo_front = not self._context.get('auto_approve')
                msg = {
                    'body': _('Jūsų prašymas buvo patvirtintas skyriaus vadovo.'),
                    'subject': _('Patvirtintas prašymas'),
                    'priority': 'high',
                    'front_message': robo_front,
                    'rec_model': 'e.document',
                    'rec_id': rec.id,
                    'view_id': rec.view_id.id or False,
                }
                partner_ids = rec.sudo().mapped('employee_id1.user_id.partner_id.id')
                if partner_ids:
                    msg['partner_ids'] = partner_ids
                rec.robo_message_post(**msg)

    @api.multi
    def action_reject(self):
        for rec in self:
            if rec.state != 'e_signed' or rec.document_type != 'prasymas':
                raise exceptions.Warning(_('Galima atmesti tik pasirašytus prašymus.'))
            if rec.allow_reject:
                rec.sudo().write({'approve_status': 'rejected', 'rejected': True})
                msg = {
                    'body': _('Jūsų prašymas buvo atmestas.'),
                    'subject': _('Atmestas prašymas'),
                    'priority': 'high',
                    'front_message': True,
                    'rec_model': 'e.document',
                    'rec_id': rec.id,
                    'view_id': rec.view_id.id or False,
                }
                partner_ids = rec.sudo().mapped('employee_id1.user_id.partner_id.id')
                if partner_ids:
                    msg['partner_ids'] = partner_ids
                rec.robo_message_post(**msg)

    @api.multi
    def create_internal_ticket(self, subject, body):
        """ Create an internal accounting ticket relating to the edoc """
        self.ensure_one()
        ticket_obj = self.sudo()._get_ticket_rpc_object()
        vals = {
            'ticket_dbname': self.env.cr.dbname,
            'ticket_model_name': self._name,
            'ticket_record_id': self.id,
            'name': subject,
            'ticket_user_login': self.env.user.login,
            'ticket_user_name': self.env.user.name,
            'description': body,
            'ticket_type': 'accounting',
            'user_posted': self.env.user.name,
            'client_ticket_type': 'edoc',
        }

        res = ticket_obj.create_ticket(**vals)

        if not res:
            raise exceptions.UserError('The distant method did not create the ticket.')
        return True

    @api.multi
    def warn_about_missing_cancel_workflow(self):
        """ Inform accountant when an edoc is cancelled with no specific cancel workflow """
        self.ensure_one()
        findir_email = self.sudo().env.user.company_id.findir.partner_id.email
        database = self._cr.dbname
        subject = 'Dokumentas buvo atšauktas [%s]' % database
        if findir_email:
            doc_url = self._get_document_url()
            doc_name = '<a href=%s>%s</a>' % (doc_url, self.name) if doc_url else self.cancel_id.name
            message = 'Dokumentas %s buvo atšauktas. Gali būti, kad reikia atstatyti šiuos pakeitimus. Turėjo būti sukurtas ticketas.' % doc_name

            self.env['script'].sudo().send_email(emails_to=[findir_email],
                                                 subject=subject,
                                                 body=message)
        try:
            body = """
                Dokumentas %s (%s) buvo atšauktas. Gali būti, kad reikia atstatyti šiuos pakeitimus rankiniu būdu.
                """ % (self.document_number, self.template_id.name)
            self.create_internal_ticket(subject, body)
        except Exception as exc:
            self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)

    @api.model
    def _create_cancel_workflow_failed_ticket_creation_bug(self, rec_id, exc):
        message = 'Failed to create cancel workflow ticket for EDoc ID {}\n' \
                  'Exception: {}'.format(self.id, str(exc.args))
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': message,
        })

    @api.multi
    def execute_cancel_workflow(self):
        """ Actions to execute when signing an order of cancellation """
        """ On specific template file, overload method with:
        @api.multi
        def execute_cancel_workflow(self):
            self.ensure_one()
            template = self.env.ref(_your_document_template, False)
            if self.cancel_id and self.cancel_id.template_id == template:
                # Your cancel workflow
            else:
                super(EDocument, self).execute_cancel_workflow()
         
         """
        self.ensure_one()
        holidays_template_ext_ids = ['e_document.isakymas_del_kasmetiniu_atostogu_template',
                                     'e_document.isakymas_del_nemokamu_atostogu_template',
                                     'e_document.isakymas_del_komandiruotes_template',
                                     'e_document.isakymas_del_tarnybines_komandiruotes_template',
                                     'e_document.isakymas_del_papildomu_atostogu_template']
        bonus_template_ext_id = 'e_document.isakymas_del_priedo_skyrimo_template'
        bonus_template_id = self.env.ref(bonus_template_ext_id)
        holidays_template_ids = map(lambda ext_id: self.env.ref(ext_id).id, holidays_template_ext_ids)
        user_id = self._context.get('uid')
        user = self.env['res.users'].browse(user_id) if user_id else None
        if self.cancel_id and self.cancel_id.template_id.id in holidays_template_ids:
            record_model = self.cancel_id.record_model
            record_id = self.cancel_id.record_id
            related_documents = self.env['e.document'].search([
                ('record_id', '=', record_id),
                ('record_model', '=', record_model)
            ])
            # Unlink holiday record if there's only a single related document or if all of them have been rejected
            unlink_holiday_record = len(related_documents) == 1 or all(related_documents.mapped('rejected'))
            if record_model and record_id:
                holidays_id = self.env[record_model].browse(record_id).exists()
                if not holidays_id:
                    try:
                        subject = 'Atostogų įrašas nerastas'
                        body = _("""
                                Pasirašytas atostogų įsakymas buvo atšauktas, bet negalėjome ištrinti atostogų įrašo.
                                Įtariame, kad jis jau buvo ištrintas ranka. 
                                Įsitikinkite, kad tokio pačio įrašo tikrai nėra.
                            """)
                        self.create_internal_ticket(subject, body)
                    except Exception as exc:
                        self._create_cancel_workflow_failed_ticket_creation_bug(self.id, exc)
                elif holidays_id.state == 'validate' and holidays_id.date_from:
                    period_line_ids = self.env['ziniarastis.period.line'].search([
                        ('employee_id', '=', holidays_id.employee_id.id),
                        ('date_from', '<=', holidays_id.date_from),
                        ('date_to', '>=', holidays_id.date_from)], limit=1)
                    if period_line_ids and period_line_ids[0].period_state == 'done':
                        raise exceptions.Warning(_('Įsakymo patvirtinti negalima, nes atlyginimai jau buvo '
                                                   'paskaičiuoti. Informuokite buhalterį '
                                                   'parašydami žinutę dokumento apačioje.'))
                    if unlink_holiday_record:
                        holidays_id.action_refuse()
                        holidays_id.action_draft()
                        holidays_id.unlink()
                elif holidays_id.state != 'validate' and holidays_id.date_from and unlink_holiday_record:
                    holidays_id.action_draft()
                    holidays_id.unlink()

            if self.cancel_id.template_id.id == self.env.ref('e_document.isakymas_del_komandiruotes_template').id:
                if self.cancel_id.business_trip_worked_on_weekends == 'true' and self.cancel_id.compensate_employee_business_trip_holidays == 'free_days':
                    related_free_days_after_business_trip = self.env['hr.holidays'].search(
                        [('numeris', '=', self.cancel_id.document_number),
                         ('holiday_status_id', '=', self.env.ref('hr_holidays.holiday_status_V').id)])
                    for free_day in related_free_days_after_business_trip:
                        if free_day.state == 'validate' and free_day.date_from:
                            period_line_ids = self.env['ziniarastis.period.line'].search([
                                ('employee_id', '=', free_day.employee_id.id),
                                ('date_from', '<=', free_day.date_from),
                                ('date_to', '>=', free_day.date_from)], limit=1)
                            if period_line_ids and period_line_ids[0].period_state == 'done':
                                raise exceptions.Warning(_('Įsakymo patvirtinti negalima, nes atlyginimai '
                                                           'jau buvo paskaičiuoti. Informuokite buhalterį '
                                                           'parašydami žinutę dokumento apačioje.'))
                            free_day.action_refuse()
                            free_day.action_draft()
                            free_day.unlink()
                        elif free_day.state != 'validate' and free_day.date_from:
                            free_day.action_draft()
                            free_day.unlink()
                elif self.cancel_id.business_trip_worked_on_weekends == 'true' and self.cancel_id.compensate_employee_business_trip_holidays != 'free_days' and self.cancel_id.holiday_fix_id:
                    self.cancel_id.holiday_fix_id.unlink()
            return True

        if self.cancel_id and self.cancel_id.template_id == bonus_template_id:
            try:
                record_model = self.cancel_id.record_model
                record_id = self.cancel_id.record_id
                if record_model and record_id:
                    bonus_rec = self.env[record_model].browse(record_id)
                    payslip = self.env['hr.payslip'].search([('employee_id', '=', bonus_rec.employee_id.id),
                                                             ('date_to', '=', bonus_rec.payment_date_to)], limit=1)
                    if not payslip or payslip.state != 'done':
                        bonus_rec.action_cancel()
                        bonus_rec.unlink()
                    else:
                        raise exceptions.ValidationError(
                            _('Negalima pasirašyti įsakymo, nes algalapis jau patvirtintas'))
            except Exception as exc:
                raise exceptions.UserError(
                    _('Nepavyko atšaukti priedo, greičiausiai dėl to, kad darbuotojo %s algalapis priedo '
                      'periodui jau patvirtintas. Priedą reikia panaikinti rankiniu būdu.') % self.cancel_id.employee_id2.name)
            return True

        if self.cancel_id and self.cancel_id.template_id == self.env.ref(
                'e_document.isakymas_del_priedo_skyrimo_grupei_template'):
            cancel_doc = self.cancel_id
            err_msgs = []
            period_from = cancel_doc.date_1
            period_to = cancel_doc.date_2
            period_pay = cancel_doc.date_3
            period_pay_dt = datetime.strptime(period_pay, tools.DEFAULT_SERVER_DATE_FORMAT)
            pay_from = (period_pay_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            pay_to = (period_pay_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            employee_lines = cancel_doc.get_document_lines()
            employee_ids = employee_lines.mapped('employee_id2')
            bonus_recs = self.env['hr.employee.bonus'].search([
                ('employee_id', 'in', employee_ids.mapped('id')),
                ('for_date_from', '=', period_from),
                ('for_date_to', '=', period_to),
                ('payment_date_from', '=', pay_from),
                ('payment_date_from', '=', pay_from),
                ('payment_date_to', '=', pay_to),
                ('payment_date_from', '=', pay_from),
                ('bonus_type', '=', cancel_doc.bonus_type_selection),
                ('related_document', '=', cancel_doc.id)
            ])
            bonus_recs |= self.env['hr.employee.bonus'].browse(cancel_doc.parse_record_ids())
            bonus_recs |= self.env['hr.employee.bonus'].browse(cancel_doc.record_id)
            slips = self.env['hr.payslip'].search([
                ('employee_id', 'in', employee_ids.mapped('id')),
                ('date_from', '=', pay_from),
                ('date_to', '=', pay_to)
            ])

            for empl_line in employee_lines:
                empl_id = empl_line.employee_id2.id
                empl_bonus_recs = bonus_recs.filtered(lambda b: tools.float_compare(b.amount, empl_line.float_1,
                                                                                    precision_digits=2) == 0 and b.employee_id.id == empl_id)
                if not empl_bonus_recs:
                    err_msgs.append((empl_id, 'no_bonus_rec'))
                    continue
                empl_slips = slips.filtered(lambda s: s.employee_id.id == empl_id)
                if any(slip.state != 'draft' for slip in empl_slips):
                    err_msgs.append((empl_id, 'some_slips_not_draft'))
                    continue
                try:
                    for empl_bonus_rec in empl_bonus_recs:
                        empl_bonus_rec.action_cancel()
                        bonus_recs = bonus_recs.filtered(lambda b: b.id != empl_bonus_rec.id)
                        empl_bonus_rec.unlink()
                except:
                    err_msgs.append((empl_id, 'failed_to_cancel'))

            if err_msgs:
                if user and not user.is_accountant():
                    raise exceptions.UserError(_('failed to sign the document. Please contact the company\'s accountant.'))
                msg_body = ''
                err_cats = [err_tuple[1] for err_tuple in err_msgs]
                err_cat_name_id_mapping = {
                    'no_bonus_rec': _('Nerasti priedų įrašai šiems darbuotojams:'),
                    'some_slips_not_draft': _('Šių darbuotojų algalapiai nėra juodraščio būsenos:'),
                    'failed_to_cancel': _(
                        'Nepavyko atšaukti priedo įrašo dėl nežinomų priežaščių šiems darbuotojams:'),
                }
                for err_cat in set(err_cats):
                    err_cat_employee_ids = [err_tuple[0] for err_tuple in err_msgs if err_tuple[1] == err_cat]
                    err_cat_employee_names = self.env['hr.employee'].browse(err_cat_employee_ids).mapped('name')
                    if msg_body != '':
                        msg_body += '\n'
                    err_cat_name = err_cat_name_id_mapping.get(err_cat, 'Nenumatytos problemos:')
                    msg_body += err_cat_name + '\n\n'
                    for empl_name in err_cat_employee_names:
                        msg_body += empl_name + '\n'
                is_document_for_group = True if len(employee_lines) > 1 else False
                if is_document_for_group:
                    intro = _('It was not possible to cancel the order of bonus for group (Company {}). '
                              'You will need to adjust bonuses by hand. '
                              'Error messages:').format(str(self.env.user.company_id.name))
                else:
                    intro = _('It was not possible to cancel the order of bonus for an employee (Company {}). '
                              'Error messages:').format(str(self.env.user.company_id.name))
                msg_body = intro + '\n\n' + msg_body
                raise exceptions.UserError(msg_body)
            return True

        if self.cancel_id:
            self.cancel_id.warn_about_missing_cancel_workflow()

    @api.multi
    def esign(self):
        raise exceptions.UserError(_('Ši operacija yra negalima'))
        self.workflow_execution()
        # todo: iSign API
        self.date_signed = datetime.utcnow()
        self.sudo().signed_user_id = self.env.user.id
        self.write({'state': 'e_signed'})
        self.sudo().set_related_prasymai_isakymas_signed()
        for rec in self:
            self.env['e.document'].accountants_subscribe(rec)  # todo check execution

    @api.multi
    def cancel(self):
        for rec in self:
            if rec.state not in ['draft', 'confirm']:
                raise exceptions.Warning(_('Negalima atšaukti pasirašyto dokumento.'))
            if rec.sudo().user_ids and not self.env.user.is_manager() and not (self.env.user.has_group(
                    'robo_basic.group_robo_create_on_behalf') and rec.user_id.id == self.env.user.id):
                raise exceptions.UserError(_('Tik vadovas arba asmuo sukūręs šį dokumentą gali jį atšaukti.'))
        self.write({'state': 'cancel', 'cancel_uid': self.env.uid})

    @api.multi
    def set_draft(self):
        for rec in self:
            if rec.state not in ['draft', 'confirm']:
                raise exceptions.Warning(_('Negalima atšaukti pasirašyto dokumento.'))
        self.write({'state': 'draft'})

    @api.multi
    def action_copy(self):
        res = self.copy()
        return {
            'name': _('El. dokumentai'),
            'view_mode': 'form',
            'view_id': res.template_id.view_id.id,
            'view_type': 'form',
            'res_model': 'e.document',
            'res_id': res.id,
            'type': 'ir.actions.act_window',
            'context': dict(self._context),
            'flags': {'initial_mode': 'edit'},
        }

    @api.multi
    def copy(self, default=None):
        if not self.template_id.allow_copy:
            raise exceptions.UserError(_('Negalima kopijuoti dokumento.'))
        return super(EDocument, self).copy(default=default)

    @api.one
    @api.depends('date_from', 'date_to')
    def _num_calendar_days(self):
        if self.date_from and self.date_to and self.date_to >= self.date_from:
            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
            num_days = (date_to_dt - date_from_dt).days + 1
            employee = self._context.get('employee')
            if self.is_business_trip_doc() and employee:
                employee_lines = self.business_trip_employee_line_ids.filtered(lambda l: l.employee_id == employee)
                dont_pay_allowance_days = len(employee_lines.mapped('extra_worked_day_ids').filtered(lambda l: not l.pay_allowance))
                num_days = max(0, num_days-dont_pay_allowance_days)
            self.num_calendar_days = num_days
        else:
            self.num_calendar_days = 0

    @api.one
    @api.depends('date_from', 'date_to')
    def _num_work_days(self):
        employee_id = self.employee_id1 if self.document_type == 'prasymas' else self.employee_id2
        if self.date_from and self.date_to and self.date_to >= self.date_from and employee_id:
            contracts_for_period = self.sudo().env['hr.contract'].search([
                ('employee_id', '=', employee_id.id),
                ('date_start', '<=', self.date_to),
                '|',
                ('date_end', '=', False),
                ('date_end', '>=', self.date_from)
            ])
            num_days = 0
            appointment = contracts_for_period.mapped('appointment_id')
            # TODO Do it properly (maybe a method that computes the day string instead of doing it
            #  inside the document)
            if len(appointment) != 1 or appointment.leaves_accumulation_type != 'calendar_days':
                for contract in contracts_for_period:
                    num_days += contract.sudo().get_num_work_days(self.date_from, self.date_to)
            self.num_work_days = num_days
        else:
            self.num_work_days = 0

    @api.one
    @api.depends('template_id.view_id', 'force_view_id')
    def _view_id(self):
        if self.force_view_id:
            self.view_id = self.force_view_id.id
        else:
            self.view_id = self.template_id.view_id.id

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        result = super(EDocument, self).fields_view_get(view_id, view_type, toolbar=toolbar, submenu=submenu)
        if view_type == 'multiple_form_tree':
            politika_atostogu_suteikimas = self.env.user.sudo().company_id.politika_atostogu_suteikimas
            if politika_atostogu_suteikimas == 'ceo':
                doc = etree.XML(result['arch'])
                if doc.xpath("//field[@name='approve_status']"):
                    node = doc.xpath("//field[@name='approve_status']")[0]
                    doc.remove(node)
                    result['arch'] = etree.tostring(doc)
        return result

    # @api.multi
    # def parseit(self):
    #     self.ensure_one()
    #     template = self.sudo().template_id.template
    #     # template = test_template
    #     parsed_template = jinja2.Environment().parse(template)
    #     variables = meta.find_undeclared_variables(parsed_template)
    #     data = {}
    #     for variable in variables:
    #         try:
    #             value = getattr(self.sudo(), variable)
    #             if isinstance(value, models.BaseModel):
    #                 if len(value) == 0:
    #                     value = ''
    #                 else:
    #                     value.ensure_one()
    #                     value = value.name
    #             if value is False:
    #                 value = ''
    #             data[variable] = value
    #         except NameError:
    #             raise exceptions.Warning(_('Neteisingi duomenys'))
    #     final_result = jinja2.Environment().from_string(template).render(**data)
    #     self.final_document = final_result

    @api.model
    def _reset_ir_doc_sequence(self):
        doc_sequence = self.env['ir.sequence'].search([('code', '=', 'e.document.name.sequence')])
        if doc_sequence:
            doc_sequence.write({'number_next': 1})

    @api.multi
    def open_related_record(self):
        self.ensure_one()
        if not self.record_model or not self.record_id:
            raise exceptions.UserError(_('Nėra susijusių dokumentų.'))
        if self.record_model == 'e.document':
            return {}
        if self.env.user.is_accountant() and self.record_model and self.record_id:
            record_model = self.record_model
            record_id = self.record_id
        else:
            return {}
        return {
            'name': _('Susijęs dokumentas'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': record_model,
            'res_id': record_id,
            'view_id': False,
        }

    @api.multi
    def open_related_document(self):
        self.ensure_one()
        source_document = self.search([('record_id', '=', self.id), ('record_model', '=', 'e.document')], limit=1)
        if not self.env.user.is_manager() and not self.env.user.has_group('robo_basic.group_robo_edocument_manager'):
            return {}
        if source_document:
            record_id = source_document.id
            view_id = source_document.sudo().template_id.view_id.id
        else:
            if self.record_model != 'e.document' or not self.record_id:
                raise exceptions.Warning(_('Nėra susijusių įrašų'))
            record_id = self.record_id
            record = self.env['e.document'].browse(record_id)
            view_id = record.sudo().template_id.view_id.id

        return {
            'name': _('Susijęs dokumentas'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'e.document',
            'res_id': record_id,
            'view_id': view_id,
        }

    @api.multi
    def set_link_to_record(self, record):
        for rec in self:
            rec.write({
                'record_model': record._inherit or record._name,
                'record_id': record.id
            })

    @api.multi
    def inform_about_creation(self, record, reason=_('automatiškai sukurtas')):
        base_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        for rec in self:
            fragment = {
                'view_type': u'form',
                'model': u'e.document',
                'id': rec.id
            }
            view_id = rec.template_id.view_id.id
            action_id = self.env['ir.actions.act_window'].search([('view_id', '=', view_id)], limit=1)
            if view_id:
                if action_id:
                    url = urljoin(
                        base_url,
                        '/web#' + werkzeug.url_encode(fragment) + '&view_id=%s&action_id=%s' % (view_id, action_id.id)
                    )
                else:
                    url = urljoin(base_url, '/web#' + werkzeug.url_encode(fragment) + '&view_id=%s' % view_id)
            else:
                url = urljoin(base_url, '/web#' + werkzeug.url_encode(fragment))
            name_link = (u'<a href="{}">' + rec.name + u'</a>').format(url)
            msg = _('Šis įrašas buvo %s pagal dokumentą %s') % (reason, name_link)
            record.message_post(body=msg, subtype='mt_comment')

    @api.model
    def get_accountant_ids(self):
        prem_acc_group_id = self.env.ref('robo_basic.group_robo_premium_accountant').id
        admin_group_id = self.env.ref('base.group_system').id
        users = self.env['res.users'].search([('groups_id', 'in', prem_acc_group_id),
                                              ('groups_id', 'not in', admin_group_id)])
        return users.mapped('partner_id.id')

    @api.model
    def accountants_subscribe(self, record, partner_ids=None):
        if not partner_ids:
            partner_ids = self.env.user.company_id.findir.partner_id.ids
        record.message_subscribe(partner_ids=partner_ids)

    @api.model
    def get_needaction_count(self):
        employee_id = self.env.user.employee_ids and self.env.user.employee_ids[0].id or False
        if employee_id:
            if self.env.user.is_manager():
                where = "(e.employee_id1 = %s OR e.employee_id1 is NULL) AND e.state='confirm' " % employee_id
            else:
                if self.env['hr.department'].search([('manager_id.user_id', '=', self.env.user.id)], count=True):
                    employee_ids = self.env['hr.employee'].sudo().search(
                        [('employee_id.department_id.manager_id.user_id', '=', self.env.user.id)]).ids
                    where = "(e.employee_id1 = %s AND e.state='confirm') OR (e.state='e_signed' AND e.approve_status = 'waiting_approval' AND e.employee_id1 IN (%s) and e.document_type = 'prasymas') " % (
                        employee_id, employee_ids and ','.join(map(str, employee_ids)) or 'null')
                else:
                    where = "e.employee_id1 = %s AND e.state='confirm' " % employee_id

            sql = """SELECT count(id) as needaction_count
                    FROM e_document e
                    WHERE %s """ % where

            self.env.cr.execute(sql)
            return self.env.cr.fetchone()[0]
        return 0

    @api.model
    def _needaction_domain_get(self):
        pending_document_ids = self.env['signed.users'].search([('state', '=', 'pending'),
                                                                ('user_id', '=', self.env.user.id)]).mapped(
            'document_id.id')
        other_request_ids = self.search([('document_type', '=', 'prasymas'),
                                         ('employee_id1.department_id.manager_id.user_id', '!=', self.env.user.id),
                                         '|',
                                         ('approve_status', '=', 'waiting_approval'),
                                         ('state', 'in', ('confirm', 'draft')),
                                         '|',
                                         ('employee_id1.user_id', '=', False),
                                         ('employee_id1.user_id', '!=', self.env.user.id)]).ids
        is_department_manager = self.env['hr.department'].search_count([('manager_id.user_id', '=', self.env.user.id)])
        is_department_delegate = self.env['e.document.department.delegate'].sudo().search_count([
            ('employee_id.user_id', '=', self.env.user.id)])
        employment_request_template = \
            self.env.ref('e_document.prasymas_del_priemimo_i_darba_ir_atlyginimo_mokejimo_template')
        if self.env.user.sudo().company_id.politika_atostogu_suteikimas == 'department' and \
                not self.env.user.is_manager() and not self.env.user.is_hr_manager() and \
                (is_department_manager or is_department_delegate):
            return [
                '|',
                    '|',
                        '&',
                            ('state', '=', 'confirm'),
                            '|',
                                ('id', 'in', pending_document_ids),
                                '&',
                                    ('user_id', '=', self.env.user.id),
                                    ('user_ids', '=', False),
                        '&',
                            '&',
                                '&',
                                    ('state', '=', 'e_signed'),
                                    ('approve_status', '=', 'waiting_approval'),
                                ('document_type', '=', 'prasymas'),
                            ('template_id.send_manager', '=', True),
                    '&',  # Add employment requests to counter.
                        '&',
                            ('state', '=', 'draft'),
                            ('employee_id1', 'in', self.env.user.employee_ids.ids),
                        ('template_id', '=', employment_request_template.id),
            ]
        elif self.env.user.sudo().company_id.politika_atostogu_suteikimas == 'department' and \
                (self.env.user.is_manager() or self.env.user.is_hr_manager()):
            return [
                '|',
                    '&',
                        '|',
                            '&',
                                '|',
                                    ('user_ids', '=', False),
                                    ('id', 'in', pending_document_ids),
                                ('state', 'in', ('confirm', 'draft')),
                            ('approve_status', '=', 'waiting_approval'),
                        ('id', 'not in', other_request_ids),
                    '&',  # Add employment requests to counter.
                        '&',
                            ('state', '=', 'draft'),
                            ('employee_id1', 'in', self.env.user.employee_ids.ids),
                        ('template_id', '=', employment_request_template.id),
            ]
        else:
            return [
                '|',
                    '|',
                        '|',
                            '&',
                                ('approve_status', '=', 'waiting_approval'),
                                ('user_id', '=', self.env.user.id),
                            '&',
                                ('state', '=', 'confirm'),
                                '|',
                                    ('id', 'in', pending_document_ids),
                                    '&',
                                        ('user_id', '=', self.env.user.id),
                                        ('user_ids', '=', False),
                        '&',
                            '&',
                                ('state', 'in', ('confirm', 'draft')),
                                ('document_type', '=', 'isakymas'),
                            ('user_ids', '=', False),
                    '&',  # Add employment requests to counter.
                        '&',
                            ('state', '=', 'draft'),
                            ('employee_id1', 'in', self.env.user.employee_ids.ids),
                        ('template_id', '=', employment_request_template.id),
            ]

    def _search_current_user_department_delegate(self, operator, value):
        if operator == '=' and value is True:
            EDocument = self
            user = self.env.user
            document_ids = []
            if user.sudo().company_id.politika_atostogu_suteikimas == 'department' \
                    and not user.is_manager() and not user.is_hr_manager():
                department_delegates = self.env['e.document.department.delegate'].sudo().search(
                    [('employee_id.user_id', '=', user.id)])
                for delegate in department_delegates:
                    document_ids += EDocument.search([('date_document', '>=', delegate.date_start),
                                              ('date_document', '<=', delegate.date_stop),
                                              ('document_type', '=', 'prasymas'),
                                              ('template_id.send_manager', '=', True),
                                              ('employee_id1.department_id', '=', delegate.department_id.id)]).ids
            return [('id', 'in', list(set(document_ids)))]
        return [('current_user_department_delegate', operator, value)]

    @api.multi
    def _compute_current_user_department_delegate(self):
        """
        Field 'current_user_department_delegate' is used only in the filter for now, this compute method is not triggered
        :return: None
        """
        pass

    @api.model
    def open_badge_action(self):
        if self.env.user.sudo().company_id.politika_atostogu_suteikimas == 'department' and \
                not self.env.user.is_manager() and not self.env.user.is_hr_manager() and \
                self.env['hr.department'].search_count([
                    ('manager_id.user_id', '=', self.env.user.id)]):
            action = self.env.ref('e_document.e_document_action_badge2').read()[0]
        elif self.env.user.sudo().company_id.politika_atostogu_suteikimas == 'department' and \
                (self.env.user.is_manager() or self.env.user.is_hr_manager()):
            action = self.env.ref('e_document.e_document_action_badge3').read()[0]
        else:
            action = self.env.ref('e_document.e_document_action_badge1').read()[0]
        return action

    @api.multi
    def _date_from_display(self):
        template_bonus = self.env.ref('e_document.isakymas_del_priedo_skyrimo_template')
        template_bonus_group = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        template_bonus_periodic = self.env.ref('e_document.isakymas_del_periodinio_priedo_skyrimo_template')
        template_contract_condition_change = self.env.ref(
            'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template')
        template_overtime_order = self.env.ref('e_document.overtime_order_template')
        template_overtime_request = self.env.ref('e_document.overtime_request_template')
        for rec in self:
            date_from = False
            if (rec.template_id == template_bonus or rec.template_id == template_bonus_group) and rec.date_3:
                date_from_dt = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_from = (date_from_dt + relativedelta(day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            elif rec.template_id == template_bonus_periodic and rec.date_1:
                date_from = datetime.strptime(rec.date_1, tools.DEFAULT_SERVER_DATE_FORMAT)
            elif rec.template_id == template_contract_condition_change and rec.date_3:
                date_from = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
            elif rec.template_id in [template_overtime_order, template_overtime_request]:
                dates = list(set(rec.e_document_time_line_ids.mapped('date')))
                date_from = dates[0] if len(dates) == 1 else False
            elif rec.document_type == 'isakymas' and rec.text_10 == 'avansine_apyskaita.report_cashbalance_template':
                date_from = rec.date_from
            else:
                date_from_field = rec.sudo().template_id.date_from_field_name or 'date_signed'
                if date_from_field:
                    date_from = rec[date_from_field]
                    if date_from:
                        date_from = date_from[:10]
            rec.date_from_display = date_from

    @api.multi
    def _date_to_display(self):
        template_bonus = self.env.ref('e_document.isakymas_del_priedo_skyrimo_template')
        template_bonus_group = self.env.ref('e_document.isakymas_del_priedo_skyrimo_grupei_template')
        template_bonus_periodic = self.env.ref('e_document.isakymas_del_periodinio_priedo_skyrimo_template')
        template_contract_condition_change = self.env.ref(
            'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template')
        template_overtime_order = self.env.ref('e_document.overtime_order_template')
        template_overtime_request = self.env.ref('e_document.overtime_request_template')
        for rec in self:
            date_to = False
            if (rec.template_id == template_bonus or rec.template_id == template_bonus_group) and rec.date_3:
                date_from_dt = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
                date_to = (date_from_dt + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            elif rec.template_id == template_bonus_periodic and rec.date_2:
                date_to = datetime.strptime(rec.date_2, tools.DEFAULT_SERVER_DATE_FORMAT)
            elif rec.template_id == template_contract_condition_change and rec.date_3:
                date_to = datetime.strptime(rec.date_3, tools.DEFAULT_SERVER_DATE_FORMAT)
            elif rec.template_id in [template_overtime_order, template_overtime_request]:
                dates = list(set(rec.e_document_time_line_ids.mapped('date')))
                date_to = dates[0] if len(dates) == 1 else False
            elif rec.document_type == 'isakymas' and rec.text_10 == 'avansine_apyskaita.report_cashbalance_template':
                date_to = rec.date_to
            else:
                date_to_field = rec.sudo().template_id.date_to_field_name or 'date_signed'
                if date_to_field:
                    date_to = rec[date_to_field]
                    if date_to:
                        date_to = date_to[:10]
                if not date_to and rec.date_from_display:
                    date_to = rec.date_from_display
            rec.date_to_display = date_to

    @api.multi  # triggered on write and create, so no api.depends()
    def _compute_dates_display(self):
        if not self._context.get('dates_display_computed'):
            for rec in self:
                rec.with_context(dates_display_computed=True)._date_from_display()
                rec.with_context(dates_display_computed=True)._date_to_display()

    @api.model
    def compute_all_dates_display(self):
        docs = self.search([])
        docs._date_from_display()
        docs._date_to_display()

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        fields2 = fields and fields[:] or None
        extra_fields = ['state', 'signed_multiple']
        for f in extra_fields:
            if fields and (f not in fields):
                fields2.append(f)
        result = super(EDocument, self).read(fields=fields2, load=load)
        try:
            for r in result:
                if r['signed_multiple']:
                    r['state'] = 'e_signed'
        except:
            pass
        return result

    @api.multi
    def _get_document_url(self):
        """
        Returns URL to directly open E-Document record
        :return: url: direct URL to document as a str
        """
        self.ensure_one()
        fragment = {
            'view_type': u'form',
            'model': u'e.document',
            'id': self.id,
            'view_id': self.view_id.id,
        }
        action = self.env.ref('e_document.e_document_action', False)
        if action:
            fragment.update(action=action.id)
        robo_menu_id = self.env.ref('e_document.e_document_root', False)
        if robo_menu_id:
            fragment.update(robo_menu_id=robo_menu_id.id, menu_id=robo_menu_id.id)
        base_url = self.sudo().env['ir.config_parameter'].get_param('web.base.url')
        url = urljoin(base_url, '/web#' + werkzeug.url_encode(fragment))
        return url

    @api.multi
    def calculate_negative_holidays(self, body=''):
        """
        Calculate the amount of holidays in advance, based on the holiday dates in the request.
        :param body: message for the user, if something fails
        :return: body, holidays_in_advance
        """
        self.ensure_one()

        date_from, date_to = self.date_from, self.date_to
        if not date_from or not date_to:
            return body, None

        employee = self.employee_id2
        if not employee:
            employee = self.employee_id1

        contract = employee.with_context(date=date_from).contract_id or \
                   employee.with_context(date=date_to).contract_id

        appointment = contract.with_context(date=date_from).appointment_id or \
                      contract.with_context(date=date_to).appointment_id

        if not appointment:
            body += _('Pagal nurodytas datas neegzistuoja darbuotojo darbo sutarties priedas')
            return body, None

        regular_schedule = appointment.schedule_template_id.template_type in ['fixed', 'suskaidytos']

        # Get holiday duration based on schedule template values and not on the actual planned schedule or existing
        # time sheets
        leaves_context = {
            'calculating_holidays': True, 'force_use_schedule_template': True, 'do_not_use_ziniarastis': True
        }

        leave_days = contract.with_context(leaves_context).get_num_work_days(date_from, date_to)

        if tools.float_is_zero(leave_days, precision_digits=2) and regular_schedule:
            body += _('Pasirinktame atostogų periode nerasta darbo dienų.')
        remaining_leaves = employee.with_context(date=date_from)._compute_employee_remaining_leaves(date_from)
        holidays_in_advance = float_compare(leave_days, remaining_leaves, precision_digits=2)

        return body, holidays_in_advance

    @api.multi
    def is_signable_by_delegate(self):
        """
        Check if document may be signed by a delegate according to company settings
        :return: True/False
        """
        self.ensure_one()
        company = self.sudo().env.user.company_id
        user = self.env.user
        cancel_template_ids = [
            self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template', False),
            self.env.ref('e_document.isakymas_del_susitarimo_nutraukimo_template', False),
        ]

        is_cancel_order = self.template_id in cancel_template_ids
        # If it is a cancel order, the cancellable document should be checked instead
        document = self.cancel_id if is_cancel_order else self
        template = document.template_id
        is_request = document.document_type == 'prasymas'
        is_order = document.document_type == 'isakymas'
        is_other = document.document_type == 'other'
        is_signable_by_delegate = not template or (template.is_signable_by_delegate and template
                                                   not in company.manager_restricted_document_templates)
        user_employees = user.employee_ids
        employee = False
        if is_request or is_other:
            employee = document.employee_id1
        elif is_order:
            employee = document.employee_id2
        document_employee_is_user = employee.id in user_employees.ids if user_employees and employee else False
        is_signable_by_delegate = is_signable_by_delegate and (not document_employee_is_user or
                                                               (document_employee_is_user and
                                                                company.allow_delegate_to_sign_related_documents))
        return is_signable_by_delegate

    @api.model
    def cron_generate_docs_to_continue_term_contracts(self):
        """
        Cron method to create new documents (depending on choice on company profile) for fixed term contracts coming
        to an end.
        """
        company = self.env.user.company_id
        action = company.default_action_after_fixed_term_contract_end or 'change_type'
        duration_by_months = (company.fixed_term_contract_extension_by_months or 1) if action == 'extend' else False
        now = datetime.utcnow()
        max_end_date = now
        days_to_add = 3
        while days_to_add:
            max_end_date = (max_end_date + relativedelta(days=1))
            if max_end_date.weekday() in (5, 6):
                continue
            if self.env['sistema.iseigines'].search_count([('date', '=', max_end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT))]):
                continue
            days_to_add -= 1
        ending_contracts = self.env['hr.contract'].search([
            ('date_end', '<=', max_end_date.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
            ('date_end', '>=', now.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
            ('rusis', 'in', ('terminuota', 'laikina_terminuota', 'pameistrystes', 'projektinio_darbo'))
        ])
        nutraukimo_isakymas = self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template').id
        tesimo_isakymas = self.env.ref(
            'e_document.isakymas_del_terminuotos_darbo_sutarties_pasibaigimo_ir_darbo_santykiu_tesimo_pagal_neterminuota_darbo_sutarti_template',
            raise_if_not_found=False)
        extend_fixed_term_contract_template = self.env.ref(
            'e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template')
        domain = [nutraukimo_isakymas]
        if tesimo_isakymas is not None:
            domain.append(tesimo_isakymas.id)
        existing_e_docs = self.search([
            ('template_id', 'in', domain),
            ('employee_id2', 'in', ending_contracts.mapped('employee_id.id'))
        ])
        for contract in ending_contracts:
            if action == 'nothing':
                continue
            further_employee_contracts = self.env['hr.contract'].search([
                ('employee_id', '=', contract.employee_id.id),
                ('date_start', '>=', contract.date_end),
            ])
            if further_employee_contracts:
                continue
            related_e_docs = existing_e_docs.filtered(lambda d: d.employee_id2.id == contract.employee_id.id)
            related_nutraukimo_doc = related_e_docs.filtered(
                lambda d: d.date_1 == contract.date_end and d.template_id.id == nutraukimo_isakymas and
                          d.state != 'cancel' and not d.rejected)
            if related_nutraukimo_doc:
                continue
            related_tesimo_doc = related_e_docs.filtered(
                lambda d: (
                          (d.template_id.id == tesimo_isakymas.id and d.date_1_computed == contract.date_end) or
                          (d.template_id.id == extend_fixed_term_contract_template.id and d.date_3 == contract.date_end)
                          ) and d.state != 'cancel' and not d.rejected
            )
            if related_tesimo_doc:
                continue

            values = {
                'employee_id2': contract.employee_id.id,
                'document_type': 'isakymas',
                'record_model': 'hr.contract',
                'record_id': contract.id,
            }
            if action == 'change_type':
                values_additional = {
                    'template_id': tesimo_isakymas.id,
                }
            elif action == 'extend':
                appointment = contract.appointment_id
                fixed_attendance_ids = []
                for line in appointment.schedule_template_id.fixed_attendance_ids:
                    vals = {
                        'hour_from': line.hour_from,
                        'hour_to': line.hour_to,
                        'dayofweek': line.dayofweek
                    }
                    fixed_attendance_ids.append((0, 0, vals))

                values_additional = {
                    'employee_id': contract.employee_id.id,
                    'job_id': contract.employee_id.job_id.id,
                    'selection_bool_2': 'true' if appointment.invalidumas else 'false',
                    'selection_nedarbingumas': '0_25' if appointment.darbingumas.name == '0_25' else '30_55',
                    'work_norm': appointment.schedule_template_id.work_norm,
                    'float_1': appointment.wage,
                    'fixed_attendance_ids': [(5,)] + fixed_attendance_ids,
                    'struct': appointment.struct_id.code,
                    'template_id': extend_fixed_term_contract_template.id,
                    'darbo_rusis': 'terminuota',
                    'date_3': contract.date_end,
                    'date_6': (now+relativedelta(months=duration_by_months)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT),
                    'darbo_grafikas': appointment.schedule_template_id.template_type,
                    'du_input_type': 'bruto' if float_compare(appointment.wage, appointment.neto_monthly,
                                                              precision_digits=2) == 0 else 'neto',
                    'etatas': appointment.schedule_template_id.etatas,
                    'selection_1': 'twice_per_month' if appointment.avansu_politika else 'once_per_month',
                    'advance_amount': appointment.avansu_politika_suma if appointment.avansu_politika else 0.00,
                    'npd_type': 'auto' if appointment.use_npd else 'manual',
                }
            elif action == 'terminate':
                fixed_term_contract_termination_article = self.env['dk.nutraukimo.straipsniai'].search([
                    ('straipsnis', '=', '69'),
                    ('dalis', '=', '1')
                ], limit=1)
                values_additional = {
                    'template_id': nutraukimo_isakymas,
                    'dk_nutraukimo_straipsnis': fixed_term_contract_termination_article.id or False,
                    'date_1': contract.date_end,
                }
            values.update(values_additional)
            new_doc = self.env['e.document'].create(values)
            new_doc.confirm()

    @api.model
    def cron_remove_running_boolean(self):
        self.env['e.document'].search([('running', '=', True)]).write({'running': False})

    @api.model
    def date_string(self, date, month_linksnis, year_linksnis=False, day_linksnis=False):
        if not year_linksnis:
            year_linksnis = month_linksnis
        if not day_linksnis:
            day_linksnis = year_linksnis
        month_name_mapping = {
            1: 'Sausis',
            2: 'Vasaris',
            3: 'Kovas',
            4: 'Balandis',
            5: 'Gegužė',
            6: 'Birželis',
            7: 'Liepa',
            8: 'Rugpjūtis',
            9: 'Rugsėjis',
            10: 'Spalis',
            11: 'Lapkritis',
            12: 'Gruodis',
        }

        try:
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        except:
            return date
        month_string = LINKSNIAI_FUNC[month_linksnis](month_name_mapping[date_dt.month])
        day = str(date_dt.day)
        year_string = LINKSNIAI_FUNC[year_linksnis]('metai')
        day_string = LINKSNIAI_FUNC[day_linksnis]('diena')
        return str(date_dt.year) + ' ' + year_string + ', ' + month_string + ' ' + day + ' ' + day_string

    @api.model
    def message_post_to_mail_channel(self, subject, body, channel, rec_model='e.document', rec_id=False):
        """
        Method to post a message to a certain mail channel on E documents module
        :param subject: Subject of the message
        :param body: Message
        :param channel: Channel to post the message to
        :param rec_model: Model for the message to point to
        :param rec_id: Particular record it for the message to point to
        """
        mail_channel = self.env.ref(channel, raise_if_not_found=False)
        if not mail_channel:
            return

        channel_partner_ids = mail_channel.sudo().mapped('channel_partner_ids')

        msg = {
            'body': body,
            'subject': subject,
            'message_type': 'comment',
            'subtype': 'robo.mt_robo_front_message',
            'priority': 'high',
            'front_message': True,
            'rec_model': rec_model,
            'rec_id': rec_id,
            'partner_ids': channel_partner_ids.ids,
        }
        mail_channel.sudo().robo_message_post(**msg)

    @api.multi
    def employee_data_is_accessible(self):
        """
        Method is meant to be overridden
        :return: Indication if employee data may be accessible for the user
        """
        self.ensure_one()
        return self.env.user.is_manager() or self.env.user.is_hr_manager()

    @api.model
    def _check_employee_should_work_on_specified_days(self, employee, times=None, show_times_employee_should_work=True):
        """
        Checks if the employee should work at the given times
        :param employee: (hr.employee) Employee to check for
        :param times: (list) List of tuples with the times to check (date, time_from, time_to)
        :param show_times_employee_should_work: (bool) Show the actual times employee should work on for each date
                                                       where the times do not match
        """
        if not times:
            times = list()

        if not employee or not times or not isinstance(times, list):
            return

        dates = set([time[0] for time in times])

        appointments = self.env['hr.contract.appointment'].search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', max(dates)),
            '|',
            ('date_end', '>=', min(dates)),
            ('date_end', '=', False)
        ])

        error_messages = []

        for date in dates:
            appointment = appointments.get_active_appointment_at_date(date)
            if not appointment:
                msg = _('Should not be working on {} because an appointment could not be found for the date').format(
                    date
                )
                error_messages.append(msg)
            schedule_template = appointment.schedule_template_id
            template_type = schedule_template.template_type
            if template_type in ['sumine', 'individualus']:
                continue  # Employee works flexible schedule so theoretically each day can be a work day.

            # Get work times. The times are fixed attendance lines merged together
            fixed_attendances = schedule_template._get_regular_work_times([date]).get(
                schedule_template.id, {}
            ).get(date, dict())
            fixed_attendances = fixed_attendances.get('night_lines', []) + fixed_attendances.get('day_lines', [])
            scheduled_times = [(x[0], x[1]) for x in fixed_attendances]

            requested_times = [time for time in times if time[0] == date]

            has_scheduled_time = all(
                any(
                    tools.float_compare(d_t[0], r_t[1], precision_digits=2) <= 0 and
                    tools.float_compare(r_t[2], d_t[1], precision_digits=2) <= 0
                    for d_t in scheduled_times
                ) for r_t in requested_times
            )

            if not has_scheduled_time:
                date_error_message = _('Can not set times {} for date {} because they do not match the scheduled '
                                       'times.').format(
                    ', '.join(
                        '{}-{}'.format(self.format_float_to_hours(x[1]), self.format_float_to_hours(x[2]))
                        for x in requested_times
                    ),
                    date
                )
                if show_times_employee_should_work and scheduled_times:
                    date_error_message += _('The scheduled times for the date are: {}.').format(
                        ', '.join(
                            '{}-{}'.format(self.format_float_to_hours(x[0]), self.format_float_to_hours(x[1]))
                            for x in scheduled_times
                        )
                    )
                error_messages.append(date_error_message)

        if error_messages:
            raise exceptions.ValidationError('\n'.join(error_messages))

    @api.multi
    def find_related_records(self):
        self.ensure_one()
        record_model = self.record_model
        if not record_model:
            return
        record_ids = self.parse_record_ids()
        if self.record_id:
            record_ids.append(self.record_id)
        if not record_ids:
            return
        try:
            records = self.env[record_model].browse(record_ids).exists()
        except:
            records = None
        return records

    @api.multi
    def raise_no_related_records_found_error(self):
        """To be executed in workflow execution to raise error and send a message to an accountant"""
        self.ensure_one()
        document_name = self.name or self.name_force or _('Document ID:{}').format(self.id)
        document_cancellation_template = self.env.ref('e_document.isakymas_del_ankstesnio_vadovo_isakymo_panaikinimo_template')
        if self.template_id == document_cancellation_template and self.cancel_id:
            canceled_document = self.cancel_id
            document_name += ' - ' + canceled_document.name or canceled_document.name_force or \
                             _('Document ID:{}').format(canceled_document.id)
        # Raise MissingError instead of UserError or ValidationError so that the message is not shown to the client.
        raise exceptions.MissingError(
            _('The related records for the document "{}" could not be found. Either they were not created or they have '
              'already been deleted. Please make sure the related records do not exist and allow signing the document '
              'without checking the constraints. If you find that records still exist please contact support at '
              'support@robolabs.lt').format(document_name)
        )

    @api.multi
    def switch_contract_type_change_document(self):
        """
        Method to switch between EDoc templates that can be used to change contract type;
        Current template will get archived, the other one - unarchived/created.
        :return: form view of the template user is switching to
        """
        mapper = {
            'extend': self.env.ref('e_document.isakymas_del_darbo_sutarties_salygu_pakeitimo_template'),
            'change_type': self.env.ref('e_document.isakymas_del_terminuotos_darbo_sutarties_pasibaigimo_ir_darbo_santykiu_tesimo_pagal_neterminuota_darbo_sutarti_template'),
            'terminate': self.env.ref('e_document.isakymas_del_atleidimo_is_darbo_template'),
        }
        current_template = self._context.get('current')
        records = self.filtered(lambda t: t.template_id == mapper.get(current_template))
        return records.mapped('employee_id2').action_after_fixed_term_contract_end()

    @api.multi
    def add_all_employees_as_to_document_lines(self):
        self.ensure_one()
        if self.template_id == self.env.ref('e_document.isakymas_del_tarnybines_komandiruotes_template'):
            lines = self.business_trip_employee_line_ids
            employee_field_name = 'employee_id'
            base_line_vals = {'allowance_amount': 0.0, 'e_document_id': self.id}
        else:
            employee_field_name = 'employee_id2'
            lines = self.get_document_lines()
            base_line_vals = {'e_document_id': self.id}
        existing_employees = lines.mapped(employee_field_name)
        missing_employees = self.find_missing_employees(existing_employees)
        for missing_employee in missing_employees:
            line_vals = base_line_vals.copy()
            line_vals[employee_field_name] = missing_employee.id
            lines.create(line_vals)

    @api.multi
    def find_missing_employees(self, existing_employees, ):
        date = self.date_document
        appointments = self.env['hr.contract.appointment'].sudo().search([
            ('employee_id', 'not in', existing_employees.ids),
            ('date_start', '<=', date),
            '|', ('date_end', '=', False), ('date_end', '>=', date)
        ])
        missing_employees = appointments.mapped('employee_id')
        return missing_employees

    @api.model
    def create_confirm_all_documents_action(self):
        action = self.env.ref('e_document.create_confirm_all_documents_action')
        if action:
            action.create_action()

    @api.model
    def create_reject_all_documents_action(self):
        action = self.env.ref('e_document.create_reject_all_documents_action')
        if action:
            action.create_action()
