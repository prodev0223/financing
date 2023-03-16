# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

import base64
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
from datetime import datetime

from odoo import api, exceptions, fields, models, _


class XmlDeclaration(models.TransientModel):
    """
    Intrastat XML Declaration
    """
    _name = "l10n_lt_intrastat_xml.xml_decl"
    _description = 'Intrastat XML'

    def _default_get_month(self):
        return fields.Date.from_string(fields.Date.context_today(self)).strftime('%m')

    def _default_get_year(self):
        return fields.Date.from_string(fields.Date.context_today(self)).strftime('%Y')

    name = fields.Char(string='Dokumentas', default='intrastat.xml')
    month = fields.Selection([('01', 'Sausis'), ('02', 'Vasaris'), ('03', 'Kovas'),
                               ('04', 'Balandis'), ('05', 'Gegužė'), ('06', 'Birželis'), ('07', 'Liepa'),
                               ('08', 'Rugpjūtis'), ('09', 'Rugsėjis'), ('10', 'Spalis'),
                               ('11', 'Lapkritis'), ('12', 'Gruodis')], string='Mėnuo', required=True, default=_default_get_month)
    year = fields.Char(size=4, required=True, default=_default_get_year, string='Metai')
    company_id = fields.Many2one('res.company', string='Įmonė', required=True, default=lambda self: self.env.user.company_id)
    decl_type = fields.Selection([('import', 'Atvežimai'), ('export', 'Išvežimai')], string='Tipas', default='import', required=True)
    file_save = fields.Binary(string='Intrastat dokumentas', readonly=True)
    state = fields.Selection([('draft', 'Juodraštis'), ('download', 'Atsisiųsti')], default='draft')
    skip_secondary_uom = fields.Boolean(string='Praleisti antrinio matavimo vieneto spausdinimą')

    @api.model
    def _company_warning(self, translated_msg):
        """ Raise a error with custom message, asking user to configure company settings """
        raise exceptions.RedirectWarning(
            translated_msg, self.env.ref('robo.action_robo_company_settings').id, _('Eiti į įmonės nustatymus'))

    @api.multi
    def create_xml(self):
        self.ensure_one()
        company = self.company_id
        if not (company.partner_id and company.partner_id.country_id and
                company.partner_id.country_id.id):
            self._company_warning(_('Nenustatyta įmonės valstybė.'))
        if not company.company_registry:
            self._company_warning(_('Nenustatytas įmonės kodas.'))
        if len(self.year) != 4:
            raise exceptions.Warning(_('Neteisingas metų formatas.'))
        if not company.phone and not company.fax:
            raise exceptions.Warning(_('Nenurodytas įmonės kontaktinis telefono numeris.'))
        if not company.email:
            raise exceptions.UserError(_('Nenurodytas įmonės kontaktinis el. pašto adresas.'))
        intrastat_code_obj = self.env['report.intrastat.code']

        #Create root declaration
        decl = ET.Element('INSTAT')
        decl.set('xmlns', "http://www.w3.org/2001/XMLSchema-instance")

        #Basic data
        date_dt = datetime.now()
        Envelope = ET.SubElement(decl, 'Envelope')
        envelopeId = ET.SubElement(Envelope, 'envelopeId')
        envelopeId.text = date_dt.strftime('%Y%m%d%H%M%S')
        DateTime = ET.SubElement(Envelope, 'DateTime')
        date = ET.SubElement(DateTime, 'date')
        time = ET.SubElement(DateTime, 'time')
        date.text = date_dt.strftime('%Y-%m-%d')
        time.text = date_dt.strftime('%H:%M:%S')
        Party = ET.SubElement(Envelope, 'Party')
        Party.set('partyType', 'CC')
        Party.set('partyRole', 'receiver')
        partyName = ET.SubElement(Party, 'partyName')
        partyName.text = 'Muitinės departamentas'
        PartyId = ET.SubElement(Party, 'partyId')
        PartyId.text = 'MM39'
        Party2 = ET.SubElement(Envelope, 'Party')
        Party2.set('partyType', 'PSI')
        Party2.set('partyRole', 'sender')
        partyName2 = ET.SubElement(Party2, 'partyName')
        partyName2.text = company.name
        PartyId2 = ET.SubElement(Party2, 'partyId')
        PartyId2.text = company.vat[2:]
        Address = ET.SubElement(Party2, 'Address')
        Address_actual = ET.SubElement(Address, 'adresas')

        Address_actual.text = company.partner_id.with_context(skip_name=True).contact_address_line
        phoneNumber = ET.SubElement(Address, 'phoneNumber')
        phoneNumber.text = (company.phone or company.fax or '').strip()
        ET.SubElement(Address, 'e-mail').text = company.email.strip()
        findir = company.sudo().findir
        contact_person_phone = (findir.work_phone or findir.partner_id.phone or findir.partner_id.mobile or '').strip()
        if not contact_person_phone or not findir.email:
            raise exceptions.UserError(_('Nenurodyti buhalterio kontaktiniai duomenys (tel. nr. ir el. pašto adresas)'))
        contactPerson = ET.SubElement(Party2, 'ContactPerson')
        contactPersonName = ET.SubElement(contactPerson, 'contactPersonName')
        contactPersonName.text = findir.name
        ET.SubElement(contactPerson, 'phoneNumber').text = contact_person_phone
        ET.SubElement(contactPerson, 'e-mail').text = findir.email
        softwareUsed = ET.SubElement(Envelope, 'softwareUsed')
        softwareUsed.text = 'ROBO'

        #Declarations
        domain = [('code', '!=', self.company_id.partner_id.country_id.code or 'LT'),
                  ('month', '=', self.month),
                  ('name', '=', self.year),
                  ('intrastat_id', '!=', False),
                  ('type', '=', self.decl_type),
                  ]
        fields = ['month', 'code', 'name', 'intrastat_id', 'weight', 'value', 'supply_units', 'type',
                  'kilmes_salis', 'transaction_code', 'delivery_terms', 'product_description', 'intrastat_description', 'partner_vat']
        groupby = ['intrastat_id', 'code', 'type', 'kilmes_salis', 'transaction_code', 'delivery_terms', 'product_description', 'intrastat_description', 'partner_vat']
        data = self.env['report.intrastat'].read_group(domain, fields, groupby, lazy=False)
        if not data:
            if self._context.get('manual_call', False):
                raise exceptions.Warning(_('Pasirinktam periodui nėra duomenų.'))
            return False
        decl_num = 1
        Declaration = ET.SubElement(Envelope, 'Declaration')
        declaration_id = ET.SubElement(Declaration, 'declarationId')
        declaration_id.text = unicode(decl_num)
        declaration_datetime = ET.SubElement(Declaration, 'DateTime')
        declaration_date = ET.SubElement(declaration_datetime, 'date')
        declaration_date.text = date_dt.strftime('%Y-%m-%d')
        declaration_time = ET.SubElement(declaration_datetime, 'time')
        declaration_time.text = date_dt.strftime('%H:%M:%S')
        referencePeriod = ET.SubElement(Declaration, 'referencePeriod')
        referencePeriod.text = self.year + '-' + self.month
        Function = ET.SubElement(Declaration, 'Function')
        functionCode = ET.SubElement(Function, 'functionCode')
        functionCode.text = 'O'
        flowCode = ET.SubElement(Declaration, 'flowCode')
        flowCode.text = 'A' if self.decl_type == 'import' else 'D'
        currencyCode = ET.SubElement(Declaration, 'currencyCode')
        currencyCode.text = 'EUR'
        PSIId = ET.SubElement(Declaration, 'PSIId')
        PSIId.text = company.vat[2:]
        item_num = 1
        total_invoiced = 0.0
        for line in data:
            country_code = line['code']
            intrastat_id = line['intrastat_id'][0]
            intrastat_id = intrastat_code_obj.browse(intrastat_id).exists()
            if not intrastat_id:
                continue
            weight = line['weight'] or 0.0
            value = line['value']
            if value < 1.0:
                value = 1.0
            total_invoiced += round(value)
            supply_units = line['supply_units']
            kilmes_salis = line['kilmes_salis']
            transaction_code = line['transaction_code']
            delivery_terms = line['delivery_terms']
            product_description = line['product_description']
            intrastat_description = line['intrastat_description']
            partner_vat = line['partner_vat']

            Item = ET.SubElement(Declaration, 'Item')
            itemNumber = ET.SubElement(Item, 'itemNumber')
            itemNumber.text = unicode(item_num)
            CN8 = ET.SubElement(Item, 'CN8')
            CN8Code = ET.SubElement(CN8, 'CN8Code')
            CN8Code.text = intrastat_id.name[:8]
            if supply_units and not self.skip_secondary_uom:
                SUCode = ET.SubElement(CN8, 'SUCode')
                SUCode.text = 'NAR'
            goodsDescription = ET.SubElement(Item, 'goodsDescription')
            if intrastat_description:
                goods_description = intrastat_description
            elif product_description:
                goods_description = product_description
            else:
                goods_description = ''
            if goods_description:
                goods_description = goods_description[:100]
            else:
                goods_description = u'Prekės'
            goodsDescription.text = goods_description
            MSConsDestCode = ET.SubElement(Item, 'MSConsDestCode')
            MSConsDestCode.text = country_code
            countryOfOriginCode = ET.SubElement(Item, 'countryOfOriginCode')
            if kilmes_salis and self.decl_type == 'import':
                if country_code != kilmes_salis and kilmes_salis == 'LT':
                    countryOfOriginCode.text = country_code
                else:
                    countryOfOriginCode.text = kilmes_salis
            elif kilmes_salis and self.year >= 2022:
                countryOfOriginCode.text = kilmes_salis
            netMass = ET.SubElement(Item, 'netMass')
            # if not weight and supply_units:
            #     netMass.text = unicode('%.3f' % round(supply_units, 3)).replace('.', '')
            # else:
            #     netMass.text = unicode('%.3f' % round(weight, 3)).replace('.', '')
            netMass.text = unicode('%.3f' % round(weight, 3)).replace('.', '')
            if supply_units and not self.skip_secondary_uom:
                quantityInSU = ET.SubElement(Item, 'quantityInSU')
                quantityInSU.text = unicode('%.3f' % round(supply_units, 3)).replace('.', '')
            invoicedAmount = ET.SubElement(Item, 'invoicedAmount')
            invoicedAmount.text = unicode('%d' % round(value))
            statisticalValue = ET.SubElement(Item, 'statisticalValue')
            statisticalValue.text = unicode('%d' % round(value))
            if self.decl_type == 'export':
                partnerId = ET.SubElement(Item, 'partnerId')
                partnerId.text = unicode(partner_vat or 'QV999999999999')
            NatureOfTransaction = ET.SubElement(Item, 'NatureOfTransaction')
            natureOfTransactionACode = ET.SubElement(NatureOfTransaction, 'natureOfTransactionACode')
            natureOfTransactionBCode = ET.SubElement(NatureOfTransaction, 'natureOfTransactionBCode')
            natureOfTransactionACode.text = transaction_code
            natureOfTransactionBCode.text = '1'
            modeOfTransportCode = ET.SubElement(Item, 'modeOfTransportCode')
            modeOfTransportCode.text = company.default_intrastat_transport or '3'
            DeliveryTerms = ET.SubElement(Item, 'DeliveryTerms')
            TODCode = ET.SubElement(DeliveryTerms, 'TODCode')
            TODCode.text = delivery_terms or 'EXW'
            item_num += 1

        totalInvoicedAmount = ET.SubElement(Declaration, 'totalInvoicedAmount')
        totalInvoicedAmount.text = unicode('%d' % round(total_invoiced))
        totalStatisticalAmount = ET.SubElement(Declaration, 'totalStatisticalValue')
        totalStatisticalAmount.text = unicode('%d' % round(total_invoiced))
        totalNumberDetailedLines = ET.SubElement(Declaration, 'totalNumberDetailedLines')
        totalNumberDetailedLines.text = unicode(item_num-1)
        numberOfDeclarations = ET.SubElement(Envelope, 'numberOfDeclarations')
        numberOfDeclarations.text = unicode(decl_num)

        #Get xml string with declaration
        data_file = ET.tostring(decl, encoding='ISO-8859-13', method='xml')
        data_file = parseString(data_file).toprettyxml(encoding='ISO-8859-13')

        #change state of the wizard
        self.write({'name': 'intrastat_%s%s.xml' % (self.year, self.month),
                    'file_save': base64.encodestring(data_file),
                    'state': 'download'})
        return {
            'name': _('Parsisiųsti'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_lt_intrastat_xml.xml_decl',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': self.id,
        }
