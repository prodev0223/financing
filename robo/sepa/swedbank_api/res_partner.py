# -*- encoding: utf-8 -*-
from odoo import fields, models, _, api, exceptions, tools
from unidecode import unidecode
from datetime import datetime
import os
from lxml import etree, objectify
from odoo.addons.sepa import api_bank_integrations as abi


class ResPartner(models.Model):

    _inherit = 'res.partner'

    def _default_monthly_limit_currency_id(self):
        return self.sudo().env.user.company_id.currency_id.id

    send_e_invoices = fields.Boolean(string='Siųsti eSąskaitas šiam partneriui',
                                     track_visibility='onchange')
    e_invoice_application_date = fields.Datetime(string='Nuo kada siųsti eSąskaitas šiam partneriui',
                                                 track_visibility='onchange')
    automated_e_invoice_payment_state = fields.Selection([('non_automated', 'Išjungta'),
                                                          ('requested_del', 'Prašymas išsiųstas (DEL)'),
                                                          ('requested_add', 'Prašymas išsiųstas (ADD)'),
                                                          ('automated', 'Įjungta')],
                                                         string='Automatinis eSąskaitų apmokėjimas',
                                                         readonly=True, default='non_automated')

    automated_payment_agreed = fields.Boolean(string='Sutikta atlikti automatinius eSąskaitų mokėjimus',
                                              track_visibility='onchange')
    res_partner_bank_e_invoice_id = fields.Many2one(
        'res.partner.bank', string='Bankas į kurį siųsti eSąskaitas',
        track_visibility='onchange', domain="[('bank_id.bic','in', %s)]" % abi.E_INVOICE_ALLOWED_BANKS
    )
    monthly_limit = fields.Float(string='Mėnesinis automatinio mokėjimo limitas')
    monthly_limit_currency_id = fields.Many2one('res.currency', string='Mėnesinio mokėjimo limito valiuta',
                                                default=_default_monthly_limit_currency_id)
    sanitized_name = fields.Char(compute='_compute_sanitized_name', store=True)
    e_invoice_service_id_display = fields.Char(
        string='eSąskaitų gavėjo ID', compute='_compute_e_invoice_service_id_display')
    e_invoice_service_id = fields.Char(string='eSąskaitų gavėjo ID', groups='robo_basic.group_robo_premium_accountant')

    # Bank export data fields
    bank_export_job_ids = fields.One2many(
        'bank.export.job', 'e_invoice_auto_payment_partner_id', string='Banko eksporto darbai',
        groups='robo_basic.group_robo_premium_manager'
    )
    has_export_job_ids = fields.Boolean(
        string='Turi susijusių eksportų',
        compute='_compute_bank_export_job_data',
        groups='robo_basic.group_robo_premium_manager',
    )

    @api.multi
    @api.depends('bank_export_job_ids')
    def _compute_bank_export_job_data(self):
        """
        Compute //
        Check whether res.partner has any related bank export jobs
        :return: None
        """
        for rec in self:
            rec.has_export_job_ids = True if rec.bank_export_job_ids else False

    @api.multi
    def _compute_e_invoice_service_id_display(self):
        """
        Compute service ID display
        based on actual field or partner ID
        """
        for rec in self:
            rec.e_invoice_service_id_display = rec.sudo().e_invoice_service_id or rec.id

    @api.multi
    @api.depends('name')
    def _compute_sanitized_name(self):
        """
        Compute //
        Sanitize res partner name so it contains only ascii letters
        :return: None
        """
        for rec in self:
            if isinstance(rec.name, unicode):
                rec.sanitized_name = unidecode(rec.name)
            elif isinstance(rec.name, str):
                rec.sanitized_name = unidecode(unicode(rec.name, encoding='utf-8'))

    @api.multi
    @api.constrains('send_e_invoices', 'kodas')
    def _check_send_e_invoices_partner_code(self):
        """Ensures that partner code is set if send_e_invoices is checked"""
        for rec in self:
            if rec.send_e_invoices and not rec.kodas:
                raise exceptions.ValidationError(
                    _('Partneriai kuriems siunčiamos eSąskaitos privalo turėti nurodytą kodą.')
                )

    @api.multi
    @api.constrains('monthly_limit', 'automated_payment_agreed')
    def constraint_res_partner_monthly_limit(self):
        for rec in self:
            if rec.automated_payment_agreed and tools.float_is_zero(rec.monthly_limit, precision_digits=2):
                raise exceptions.ValidationError(_('Turite nurodyti mėnesinį mokėjimo limitą!'))

    @api.multi
    @api.constrains('res_partner_bank_e_invoice_id', 'automated_payment_agreed')
    def constraint_res_partner_bank_e_invoice_id(self):
        for rec in self:
            if rec.automated_payment_agreed and rec.res_partner_bank_e_invoice_id.bank_id.bic \
                    not in abi.E_INVOICE_AUTOMATIC_PAYMENT_BANKS:
                raise exceptions.ValidationError(
                    _('Automatinius mokėjimus galite aktyvuoti tik Swedbank banko sąskaitai!'))

    @api.multi
    def check_automated_agreement_constraints(self):
        filtered_partners = self.env['res.partner']
        for rec in self:
            body = str()
            if tools.float_is_zero(rec.monthly_limit, precision_digits=2):
                body += 'Partneriui nenurodytas mėnesinis limitas.'
            if not rec.res_partner_bank_e_invoice_id:
                body += 'Nenurodyta banko sąskaita į kurią turi būti siunčiamos eSąskaitos.\n'
            if rec.res_partner_bank_e_invoice_id.bank_id.bic not in abi.E_INVOICE_AUTOMATIC_PAYMENT_BANKS:
                body += 'Automatinio mokėjimo sutartį galima sudaryti tik su Swedbank klientais.\n'
            if not rec.kodas:
                body += 'Partneris neturi kodo.\n'
            if not body:
                filtered_partners += rec
            else:
                body = 'Nebandyta eksportuoti partnerio automatinio eSąskaitų ' \
                       'mokėjimo sutarties dėl šių klaidų: \n' + body
                rec.message_post(body=body)
        return filtered_partners

    @api.multi
    def format_automated_payment_xml(self, operation='ADD'):
        """
        Method that is used to generate EInvoiceStandingOrderAgreementReport xml | Automated payment agreement file
        Validation file is eInvoiceStandingOrderAgreementReportLT.xsd
        :return: AutoPayment XML in str format, AutoPayment request XML in str format
        """

        def set_node(node, key, value, skip_empty=False, dt=False):
            if skip_empty and not value:
                return
            if not skip_empty and not value and not isinstance(value, tuple([int, float, long])):
                raise exceptions.Warning('Tuščia reikšmė privalomam elementui %s' % key)
            el = etree.Element(key)
            if isinstance(value, tuple([int, float, long])) and not isinstance(value, bool):
                value = str(value)
            if value:
                if dt:
                    value = value.replace(' ', 'T')
                el.text = value
            setattr(node, key, el)

        def set_tag(node, tag, value):
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                value = str(value)
            node.attrib[tag] = value
        if not self:
            return
        company_id = self.env.user.sudo().company_id
        agr_id = company_id.swed_bank_agreement_id
        db_name = self.env.cr.dbname
        file_id = self.env['ir.sequence'].next_by_code('swed.bank.e.invoice.seq') + '__' + db_name
        now_date = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        now_datetime = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        global_e_invoice_agreement_id = self.env.user.sudo().company_id.global_e_invoice_agreement_id
        if not agr_id or not global_e_invoice_agreement_id:
            raise exceptions.ValidationError(_('Nėra aktyvuota Swedbank Gateway paslauga!'))

        e_xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                                <EInvoiceStandingOrderAgreementReport 
                                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                                </EInvoiceStandingOrderAgreementReport>
                                '''
        e_root = objectify.fromstring(e_xml_template)
        set_tag(e_root, 'senderId', abi.SWED_BANK)
        set_tag(e_root, 'receiverId', 'RECEIVER')
        set_tag(e_root, 'date', now_date)
        set_tag(e_root, 'fileId', file_id)
        set_tag(e_root, 'appId', 'EAPREP')
        for rec in self:
            e_agr = objectify.Element('Agreement')
            set_tag(e_agr, 'name', 'SOA')
            set_tag(e_agr, 'sequenceId', '1')
            set_node(e_agr, 'SellerRegNumber', company_id.company_registry)
            set_node(e_agr, 'GlobalSellerContractId', global_e_invoice_agreement_id)
            set_node(e_agr, 'Action', operation)
            set_node(e_agr, 'ServiceId', str(rec.id) + '__' + self.env.cr.dbname)
            set_node(e_agr, 'PayerName', rec.name)
            set_node(e_agr, 'PayerRegNumber', rec.kodas)
            set_node(e_agr, 'PayerIBAN', rec.res_partner_bank_e_invoice_id.acc_number)
            set_node(e_agr, 'PartialDebiting', 'NO')  # todo is always no?
            if rec.monthly_limit and rec.monthly_limit_currency_id:
                monthly_limit = etree.Element('MonthLimit')
                monthly_limit.text = str(rec.monthly_limit)
                set_tag(monthly_limit, 'currency', rec.monthly_limit_currency_id.name)
                e_agr.append(monthly_limit)
            else:
                monthly_limit = etree.Element('MonthLimit')
                monthly_limit.text = str(rec.monthly_limit)
                set_tag(monthly_limit, 'currency', 'EUR')
                e_agr.append(monthly_limit)
            set_node(e_agr, 'DaysLookForFunds', 3)
            set_node(e_agr, 'PaymentDay', 'InvoiceDueDate')  # todo, other options available
            if operation in ['ADD']:
                set_node(e_agr, 'StartDate', now_date)
                set_node(e_agr, 'EndDate', now_date)
            else:
                set_node(e_agr, 'StartDate', now_date)
                set_node(e_agr, 'EndDate', now_date)
            set_node(e_agr, 'TimeStamp', now_datetime, dt=True)
            e_root.append(e_agr)

        filename = 'auto_payment_' + db_name + '__' + now_date + '.xml'
        req_filename = 'auto_payment_' + db_name + '__' + now_date + '-request.xml'

        objectify.deannotate(e_root)
        etree.cleanup_namespaces(e_root)
        payload_string_repr = etree.tostring(e_root, xml_declaration=True, encoding='utf-8')

        req_xml_template = '''<?xml version="1.0" encoding="UTF-8"?>
                                <StandingOrderAgreementIncoming>
                                </StandingOrderAgreementIncoming>
                                '''
        req_root = objectify.fromstring(req_xml_template)
        set_node(req_root, 'Filename', filename)
        set_node(req_root, 'CountryCode', 'LT')
        set_node(req_root, 'ContractId', global_e_invoice_agreement_id)
        objectify.deannotate(req_root)
        etree.cleanup_namespaces(req_root)
        req_string_repr = etree.tostring(req_root, xml_declaration=True, encoding='utf-8')
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'xsd_schemas')) + '/eInvoiceStandingOrderAgreementReportLT.xsd'
        validated, error = abi.xml_validator(payload_string_repr, path)
        if validated:
            return {
                'payload_xml': payload_string_repr,
                'payload_filename': filename,
                'req_xml': req_string_repr,
                'req_filename': req_filename,
                'file_id': file_id
            }
        else:
            body = 'SwedBank -- eInvoice Fail fail: Failed to validate ' \
                   'XML XSD schema, error message: %s' % error
            self.send_bug(body=body, subject='SwedBank eInvoice -- Failed to validate XSD')
            return {}

    def send_bug(self, body, subject):
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'subject': subject + ' [%s]' % self._cr.dbname,
            'error_message': body,
        })

    @api.multi
    def reverse_auto_payment_write(self, failed=False):
        """Method used to write the state in several cases:
           if auto-payment that is turned-on is being deleted and it failed it should be kept as automated
           if auto-payment that is turned-of is being added and it failed it should be kept as non-automated"""

        for rec in self:
            if rec.automated_e_invoice_payment_state == 'requested_add':
                rec.automated_e_invoice_payment_state = 'non_automated' if failed else 'automated'
            elif rec.automated_e_invoice_payment_state == 'requested_del':
                rec.automated_e_invoice_payment_state = 'automated' if failed else 'non_automated'


ResPartner()
