# -*- coding: utf-8 -*-
import os
from datetime import datetime
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, tostring
from lxml import etree

from odoo import models, fields, api, tools, exceptions
from odoo.tools.translate import _
from ..e_vmi_tools import xml_validator


class StockPickingIvaz(models.Model):
    _inherit = 'stock.picking'

    exported_to_vaz = fields.Boolean(string='Eksportuota į i.VAZ')

    @api.model
    def create_export_ivaz_action(self):
        action = self.env.ref('e_ataskaitos.export_stock_picking_ivaz_action')
        if action:
            action.create_action()

    @api.model
    def export_to_i_vaz_wizard(self):
        pickings_wrong_state = self.filtered(lambda r: r.state in ['draft', 'cancel'])
        if pickings_wrong_state:
            raise exceptions.UserError(_("Nesirinkite važtaraščio su būsena 'Juodraštis' arba 'Atšauktas'."))

        pickings_wrong_min_date = self.filtered(lambda r: not r.min_date)
        if pickings_wrong_min_date:
            raise exceptions.UserError(
                _("Nesirinkite važtaraščio, kuriame nėra užpildytas laukelis 'Suplanuota data'."))

        pickings_not_internal_usage = self.filtered(lambda r: r.location_id.usage != 'internal')
        if pickings_not_internal_usage:
            raise exceptions.UserError(_("Pasirinkote važtaraštį, kuris nėra skirtas eksportuoti i.VAZ."))

        ctx = self._context.copy()
        ctx.update({'picking_ids': self.mapped('id')})
        return {
            'context': ctx,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.picking.export.wizard',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }


class ExportPickingLine(models.TransientModel):
    _name = 'picking.export.line'

    company_id = fields.Many2one('res.company', string='Kompanija')
    scheduled_date = fields.Date(string='Suplanuota data')
    name = fields.Char(string='Numeris')
    partner_id = fields.Many2one('res.partner', string='Partneris')
    exported_to_vaz = fields.Boolean(string='Eksportuota į i.VAZ')
    picking_id = fields.Many2one('stock.picking', string='Važtaraštis')
    transport_doc_type = fields.Selection(
        [('transportdoc', 'Važtaraštis'), ('e_transport_doc', 'Elektroninis važtaraštis')],
        string='Dokumento tipas', required=True)


class StockPickingExportWizard(models.TransientModel):
    _name = 'stock.picking.export.wizard'

    def _picking_export_lines(self):
        line_ids = []
        if self._context.get('picking_ids', False):
            pickings_ids = self._context.get('picking_ids', False)

            pickings = self.env['stock.picking'].browse(pickings_ids).filtered(
                lambda r: r.state not in ['draft', 'cancel'] and r.min_date
                          and r.location_id.usage in ['internal'])
            for picking in pickings:
                vals = {'company_id': picking.company_id.id,
                        'scheduled_date': picking.min_date,
                        'name': picking.name,
                        'partner_id': picking.partner_id.id,
                        'exported_to_vaz': picking.exported_to_vaz,
                        'picking_id': picking.id,
                        'transport_doc_type': 'e_transport_doc'}
                line = self.env['picking.export.line'].create(vals)
                line_ids.append(line.id)

        return [(6, 0, line_ids)]

    export_type = fields.Selection([('full', 'Visi'), ('not_exported', 'Neeksportuota'), ('exported', 'Ekskportuota')],
                                   string='Filtras', default='full')
    picking_export_lines = fields.Many2many('picking.export.line', string='Eksportuojami važtaraščiai',
                                            default=_picking_export_lines, required=True)
    picking_export_lines_filtered = fields.Many2many('picking.export.line', string='Eksportuojami važtaraščiai',
                                                     required=True)
    transport_doc_type = fields.Selection(
        [('transportdoc', 'Važtaraštis'), ('e_transport_doc', 'Elektroninis važtaraštis')], string='Dokumento tipas',
        default='e_transport_doc', required=True)
    filter_by_warehouse = fields.Selection([('exclude_same', 'Pašalinti judėjimus tame pačiame sandėlyje'),
                                            ('not_exclude_same', 'Nepašalinti judėjimų tame pačiame sandėlyje')],
                                           string='Filtruoti pagal sandėlį',
                                           default='not_exclude_same', required=True)

    @api.onchange('export_type', 'filter_by_warehouse')
    def picking_export_lines_filtered_onchange(self):
        line_ids = []
        if self.export_type:
            if self.export_type == 'not_exported':
                # line_ids = []
                line_ids = self.picking_export_lines.filtered(lambda r: r.exported_to_vaz == False)

            elif self.export_type == 'exported':
                line_ids = self.picking_export_lines.filtered(lambda r: r.exported_to_vaz)
                # self.picking_export_lines_filtered = [(6, 0, line_ids.mapped('id'))]
            elif self.export_type == 'full':
                line_ids = self.picking_export_lines
        else:
            line_ids = self.picking_export_lines
        if self.filter_by_warehouse:
            if self.filter_by_warehouse == 'exclude_same':
                line_ids = line_ids.filtered(lambda
                                                 r: r.picking_id.location_id.warehouse_id.id != r.picking_id.location_dest_id.warehouse_id.id)  # [(6, 0, line_ids.mapped('id'))]

        self.picking_export_lines_filtered = [(6, 0, line_ids.mapped('id'))]

    @api.onchange('transport_doc_type')
    def transport_doc_type_onchange(self):
        if self.transport_doc_type:
            for line in self.picking_export_lines_filtered:
                line.transport_doc_type = self.transport_doc_type
            for line in self.picking_export_lines:
                line.transport_doc_type = self.transport_doc_type

    @api.multi
    def generate_ivaz(self):
        if not self.picking_export_lines_filtered:
            raise exceptions.UserError(_('Nepasirinkote važtaraščių eksportui.'))

        xml = Element('iVAZFile')
        xml.attrib['xmlns:xsi'] = 'http://www.w3.org/2001/XMLSchema-instance'
        xml.attrib['xmlns'] = 'http://www.vmi.lt/cms/imas/ivaz'

        SubElement(xml, 'FileDescription')
        SubElement(xml[0], 'FileVersion')
        xml[0][0].text = 'iVAZ1.3.3'
        SubElement(xml[0], 'FileDateCreated')
        xml[0][1].text = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')  # tools.DEFAULT_SERVER_DATE_FORMAT
        SubElement(xml[0], 'SoftwareCompanyName')
        xml[0][2].text = 'UAB Robolabs'
        SubElement(xml[0], 'SoftwareName')
        xml[0][3].text = 'Robo'
        SubElement(xml[0], 'SoftwareVersion')
        xml[0][4].text = '1.0'
        SubElement(xml[0], 'CreatorRegistrationNumber')
        xml[0][5].text = self.env.user.company_id.partner_id.kodas

        transport_pick_ids = self.picking_export_lines_filtered.filtered(
            lambda r: r.transport_doc_type == 'transportdoc').mapped('picking_id')
        etransport_pick_ids = self.picking_export_lines_filtered.filtered(
            lambda r: r.transport_doc_type == 'e_transport_doc').mapped('picking_id')

        if etransport_pick_ids:
            SubElement(xml, 'eTransportDocuments')
            # pick_ids = self.picking_export_lines_filtered.mapped('picking_id')
            for pick in etransport_pick_ids:
                self.set_consignation_information(xml, pick, 'eTransportDocument')

        if transport_pick_ids:
            SubElement(xml, 'TransportDocuments')
            for pick in transport_pick_ids:
                self.set_consignation_information(xml, pick, 'TransportDocument')

        u = tostring(xml, encoding="UTF-8")
        u = etree.fromstring(u)
        u = etree.tostring(u, encoding="UTF-8", xml_declaration=True)
        file = parseString(u).toprettyxml(encoding='UTF-8')

        if not xml_validator(file, xsd_file=os.path.abspath(os.path.join(os.path.dirname(__file__), '..',
                                                                         'xsd_schemas')) + '/ivaz_xsd_1_3_3.xsd'):
            raise exceptions.Warning(_('Failed to generate iVAZ xml file'))

        pick_ids = self.picking_export_lines_filtered.mapped('picking_id')
        for pick in pick_ids:
            pick.exported_to_vaz = True

        attach_vals = {'res_model': 'res.company',
                       'name': 'iVAZ' + '.xml',
                       'datas_fname': 'iVaz' + '.xml',
                       'res_id': self.env.user.company_id.id,
                       'type': 'binary',
                       'datas': file.encode('base64')}

        self.env['ir.attachment'].sudo().create(attach_vals)

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ivaz.download',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'view_id': self.env.ref('e_ataskaitos.stock_picking_ivaz_download').id,
            'context': {'file': file.encode('utf8').encode('base64')},
        }

    def set_product_info(self, products, pick):
        '''products: Etree element'''
        if not pick.pack_operation_ids:
            for idx, pick_line in enumerate(pick.move_lines):
                product = SubElement(products, 'Product')
                SubElement(product, 'ProductLineNumber')
                product[0].text = str(idx + 1)

                SubElement(product, 'Quantity')
                product[1].text = "%.2f" % pick_line.product_uom_qty

                SubElement(product, 'UnitOfMeasure')
                product[2].text = pick_line.product_uom.name

                SubElement(product, 'ProductCode')
                if not pick_line.product_id.default_code:
                    raise exceptions.Warning(_('Produktas %s neturi kodo') % pick_line.product_id.name)
                product[3].text = pick_line.product_id.default_code

                SubElement(product, 'ProductDescription')
                product[4].text = pick_line.product_id.name
        else:
            for idx, pick_line in enumerate(pick.pack_operation_ids):
                if pick_line.product_id:
                    product = SubElement(products, 'Product')
                    SubElement(product, 'ProductLineNumber')
                    product[0].text = str(idx + 1)

                    SubElement(product, 'Quantity')
                    product[1].text = "%.2f" % pick_line.product_qty

                    SubElement(product, 'UnitOfMeasure')
                    product[2].text = pick_line.product_uom_id.name

                    SubElement(product, 'ProductCode')
                    if not pick_line.product_id.default_code:
                        raise exceptions.Warning(_('Produktas %s neturi kodo') % pick_line.product_id.name)
                    product[3].text = pick_line.product_id.default_code

                    SubElement(product, 'ProductDescription')
                    product[4].text = pick_line.product_id.name
                else:
                    for pack_prod in pick_line.package_id.quant_ids:
                        if pack_prod.qty <= 0:
                            continue
                        product = SubElement(products, 'Product')
                        SubElement(product, 'ProductLineNumber')
                        product[0].text = str(idx + 1)

                        SubElement(product, 'Quantity')
                        product[1].text = "%.2f" % pack_prod.qty

                        SubElement(product, 'UnitOfMeasure')
                        product[2].text = pack_prod.product_uom_id.name

                        SubElement(product, 'ProductCode')
                        product[3].text = pack_prod.lot_id.name

                        SubElement(product, 'ProductDescription')
                        product[4].text = pack_prod.product_id.name

    def set_consignation_information(self, xml, pick, type):
        self.check_required_fields(pick)
        if type == 'eTransportDocument':
            idx = 1
        else:
            idx = 2
        pick_el = SubElement(xml[idx], type)
        el = SubElement(pick_el, 'TransportDocumentUID')
        SubElement(el, 'LocalTransportDocumentUID')
        el[0].text = str(pick.id)

        SubElement(pick_el, 'LocalTransportDocumentNumber')
        pick_el[1].text = pick.name

        date = pick.create_date if pick.create_date else pick.min_date
        date_creation = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
        SubElement(pick_el, 'LocalTransportDocumentDate')
        pick_el[2].text = date_creation.date().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

        consignee_obj = pick.location_id.company_id
        address = '%(street)s%(city)s%(zip)s%(country_name)s' % {'street': consignee_obj.street,
                                                                 'city': ', ' + consignee_obj.city if consignee_obj.city else '',
                                                                 'zip': ', ' + consignee_obj.zip if consignee_obj.zip else '',
                                                                 'country_name': ', ' + consignee_obj.country_id.name if consignee_obj.country_id.name else ''}
        if not address:
            raise exceptions.Warning(_('Nenurodytas siuntėjo adresas (%s)') % pick.name)
        place_of_issue = SubElement(pick_el, 'PlaceOfIssueTransportDocument')
        SubElement(place_of_issue, 'FullAddress')
        place_of_issue[0].text = address

        date_scheduled = datetime.strptime(pick.min_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
        SubElement(pick_el, 'TimeOfDispatch')
        pick_el[4].text = date_scheduled.strftime('%Y-%m-%dT%H:%M:%S')

        consignor = SubElement(pick_el, 'Consignor')

        SubElement(consignor, 'RegistrationNumber')
        consignor[0].text = pick.location_id.company_id.partner_id.kodas

        SubElement(consignor, 'Name')
        consignor[1].text = pick.location_id.company_id.name

        consignor_address = SubElement(consignor, 'Address')
        consignor_address_unstructured = SubElement(consignor_address, 'FullAddress')

        consignor_address_unstructured.text = address

        if pick.location_id.company_id.email:
            SubElement(consignor, 'ContactInformation')
            consignor[3].text = pick.location_id.company_id.email

        consignee = SubElement(pick_el, 'Consignee')

        SubElement(consignee, 'RegistrationNumber')
        consignee[0].text = pick.customer_code

        SubElement(consignee, 'Name')
        consignee[1].text = pick.customer_name

        consignee_address = SubElement(consignee, 'Address')
        consignee_address_unstructured = SubElement(consignee_address, 'FullAddress')
        address = '%(street)s%(city)s%(zip)s%(country_name)s' % {
            'street': pick.customer_street if pick.customer_street else '',
            'city': ', ' + pick.customer_city if pick.customer_city else '',
            'zip': ', ' + pick.customer_zip if pick.customer_zip else '',
            'country_name': ', ' + pick.customer_country if pick.customer_country else ''}
        if not address:
            raise exceptions.Warning(_('Nenurodytas gavėjo adresas (%s)') % pick.name)
        consignee_address_unstructured.text = address

        if pick.customer_email:
            SubElement(consignee, 'ContactInformation')
            consignee[3].text = pick.customer_email

        transporter = SubElement(pick_el, 'Transporter')

        SubElement(transporter, 'RegistrationNumber')
        if not pick.partner_id_carrier.kodas:
            raise exceptions.Warning(_('Nenurodytas vežėjo kompanijos kodas (%s)') % pick.name)
        transporter[0].text = pick.partner_id_carrier.kodas

        SubElement(transporter, 'Name')
        transporter[1].text = pick.partner_id_carrier.name

        transporter_address = SubElement(transporter, 'TransporterAddress')
        transporter_address_unstructured = SubElement(transporter_address, 'FullAddress')
        address = '%(street)s%(city)s%(zip)s%(country_name)s' % {
            'street': pick.partner_id_carrier.street if pick.partner_id_carrier.street else '',
            'city': ', ' + pick.partner_id_carrier.city if pick.partner_id_carrier.city else '',
            'zip': ', ' + pick.partner_id_carrier.zip if pick.partner_id_carrier.zip else '',
            'country_name': ', ' + pick.partner_id_carrier.country_id.name if pick.partner_id_carrier.country_id.name else ''}
        if not address:
            raise exceptions.Warning(_('Nenurodytas vežėjo adresas (%s)') % pick.name)
        transporter_address_unstructured.text = address

        if pick.partner_id_carrier.email:
            SubElement(transporter, 'ContactInformation')
            transporter[3].text = pick.partner_id_carrier.email

        transport_means = SubElement(transporter, 'TransportMeans')
        transport_mean = SubElement(transport_means, 'TransportMean')
        SubElement(transport_mean, 'IdentityOfTransportUnits')
        transport_mean[0].text = pick.transport_id.license_plate

        SubElement(transport_mean, 'MarqueModelTransportUnits')
        transport_mean[1].text = pick.transport_id.model

        ship_from = SubElement(pick_el, 'ShipFrom')
        SubElement(ship_from, 'LoadAddress')
        load_address = SubElement(ship_from[0], 'FullAddress')

        warehouse_adress = pick.warehouse_address_id
        address = '%(street)s%(city)s%(zip)s%(country_name)s' % {
            'street': warehouse_adress.street if warehouse_adress.street else '',
            'city': ', ' + warehouse_adress.city if warehouse_adress.city else '',
            'zip': ', ' + warehouse_adress.zip if warehouse_adress.zip else '',
            'country_name': ', ' + warehouse_adress.country_id.name if warehouse_adress.country_id.name else ''}
        if not address:
            raise exceptions.Warning(_('Nenurodytas išsiuntimo lokacijos adresas (%s)') % pick.name)
        load_address.text = address

        transporter[0].text = pick.partner_id_carrier.kodas

        ship_to = SubElement(pick_el, 'ShipTo')
        SubElement(ship_to, 'UnloadAddress')
        unload_address = SubElement(ship_to[0], 'FullAddress')

        address = '%(street)s%(city)s%(zip)s%(country_name)s' % {
            'street': pick.partner_id.street if pick.partner_id.street else '',
            'city': ', ' + pick.partner_id.city if pick.partner_id.city else '',
            'zip': ', ' + pick.partner_id.zip if pick.partner_id.zip else '',
            'country_name': ', ' + pick.partner_id.country_id.name if pick.partner_id.country_id.name else ''}
        if not address:
            raise exceptions.Warning(_('Nenurodytas gavėjo adresas (%s)') % pick.name)
        unload_address.text = address

        delivery_data = SubElement(pick_el, 'DeliveryData')
        products = SubElement(delivery_data, 'Products')
        self.set_product_info(products, pick)

        if pick.pack_operation_pack_ids:
            packages = SubElement(delivery_data, 'Packages')
            for pack in pick.pack_operation_pack_ids:
                package = SubElement(packages, 'Package')
                SubElement(package, 'KindOfPackagesCode')
                package[0].text = pack.package_id.name

                SubElement(package, 'NumberOfPackages')
                package[1].text = "%.f" % pack.qty_done

        if type == 'eTransportDocument':
            complementary = SubElement(pick_el, 'ComplementaryTransportInformation')
            payments = SubElement(complementary, 'PaymentsForDelivery')
            payment = SubElement(payments, 'PaymentForDelivery')
            SubElement(payment, 'PaymentValue')
            payment[0].text = "0.00"

    def check_required_fields(self, picking_id):
        if not picking_id.name:
            raise exceptions.UserError(_('Važtaraštis neturi priskirto unikalaus pavadinimo.'))
        if not picking_id.create_date or not picking_id.min_date:
            raise exceptions.UserError(_(
                "Važtaraštis '%s' neturi užpildytų laukelių 'Suplanuota data' arba 'Sukūrimo data'." % picking_id.name))
        if not picking_id.location_id or not picking_id.location_id.sudo().company_id or not picking_id.location_id.sudo().company_id.partner_id:
            raise exceptions.UserError(_("Važtaraštis '%s' neturi priskirto 'Siuntėjo'") % picking_id.name)
        if not picking_id.location_id.sudo().company_id.partner_id.kodas:
            raise exceptions.UserError(_("Siuntėjas neturi priskirto 'Įmonės kodo' ('%s').") % picking_id.name)
        if not picking_id.location_id.sudo().company_id.partner_id.name:
            raise exceptions.UserError(_("Siuntėjas neturi priskirto 'Pavadinimo' ('%s').") % picking_id.name)
        if not picking_id.customer_code:
            raise exceptions.UserError(_("Gavėjas neturi priskirto 'Įmonės kodo' ('%s').") % picking_id.name)
        if not picking_id.customer_name:
            raise exceptions.UserError(_("Gavėjas neturi priskirto 'Įmonės pavadinimo' ('%s').") % picking_id.name)
        if not picking_id.partner_id_carrier and not picking_id.location_id.sudo().company_id:
            raise exceptions.UserError(_("Važtaraštyje '%s' nepasirinkta 'Pervežimo kompanija'.") % picking_id.name)
        if not picking_id.partner_id_carrier.name and not picking_id.location_id.sudo().company_id.name:
            raise exceptions.UserError(_("Nenurodytas pervežimo kompanijos 'Pavadinimas' ('%s').") % picking_id.name)
        if not picking_id.partner_id_carrier.sudo().kodas and not picking_id.location_id.sudo().company_id.partner_id.kodas:
            raise exceptions.UserError(_("Nenurodytas pervežimo kompanijos 'Įmonės kodas' ('%s').") % picking_id.name)
        if not picking_id.transport_id.license_plate:
            raise exceptions.UserError(
                _("Važtaraštis '%s' neturi priskirto 'Transporto'.") % picking_id.name)
        if datetime.strptime(picking_id.min_date, tools.DEFAULT_SERVER_DATETIME_FORMAT) < datetime.utcnow():
            raise exceptions.Warning(_('Išsiuntimo laikas jau praėjo. Pakeiskite suplanuotą datą.'))


StockPickingExportWizard()


class IVAZDownload(models.TransientModel):
    _name = 'ivaz.download'

    @api.multi
    def auto_load(self):
        if 'file' in self._context.keys():
            return self._context['file']
        else:
            return ''

    def _file_name(self):
        return 'iVAZ.xml'

    file = fields.Binary(string='Ataskaitos dokumentas', readonly=True, default=auto_load)
    file_name = fields.Char(string='Failo pavadinimas', default=_file_name)


IVAZDownload()
