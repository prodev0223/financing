# -*- coding: utf-8 -*-
# (c) 2021 Robolabs
import datetime
from odoo import api, fields, models, _, exceptions, tools
from dateutil.relativedelta import relativedelta
import base64
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString
from lxml import etree, objectify
from lxml.etree import XMLSyntaxError
import os
from sys import platform
import math
import xlwt
import StringIO

PACKAGE_CATEGORY_MAPPING = {
    'pirmine': 'CL138:1:2014-01-01',
    'antrine': 'CL138:2:2014-01-01',
    'tretine': 'CL138:3:2014-01-01',
    'nenurodoma': 'CL138:0:2014-01-01'
}

PACKAGE_ORIGIN_MAPPING = {
    'supplier': 'CL140:1:2017-02-22',
    'production': 'CL140:2:2017-02-22',
    'reverse': 'CL140:3:2017-02-22',  # Reverse supply type is not used for now, if set, it should be skipped in journal
}

PRODUCT_TYPES_ENTRY_ID_MAP = {
    'apmokestinamasGaminys': '1',
    'alyvosGaminys': '2',
    'elektronineIranga': '3',
    'transportoPriemone': '4',
    'prekinisVienetas': '5',
    # ('baterija', 'Baterija'),  # todo: ADD
}


def getQuarterStart(dt=datetime.datetime.utcnow()):
    return datetime.date(dt.year, (dt.month - 1) // 3 * 3 + 1, 1)


def xml_validator(some_xml_string, xsd_file='/path/to/my_schema_file.xsd'):
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True
    except XMLSyntaxError as exc:
        raise exceptions.ValidationError(_('Nepavyko sugeneruoti failo: %s') % exc.message)


def get_activity_type(pack_dir, partner_type=''):
    if pack_dir == 'out_kt':
        return 'CL118:EV:2016-12-07'
    elif partner_type == 'mazmenine':
        return 'CL118:MP:2016-12-07'
    elif partner_type == 'didmenine':
        return 'CL118:DP:2016-12-07'
    elif partner_type == 'nuotoline':
        return 'CL118:NP:2016-12-07'
    elif partner_type == 'tretieji':
        return 'CL118:ET:2016-12-07'
    return None


class GPAISReport(models.TransientModel):
    _name = "gpais.wizard"

    def _date_to_default(self):
        return getQuarterStart(datetime.datetime.utcnow()) + relativedelta(months=2, day=31)

    def _date_from_default(self):
        return getQuarterStart(datetime.datetime.utcnow())

    date_from = fields.Date(string="Periodas nuo", required=True, default=_date_from_default)
    date_to = fields.Date(string="Periodas iki", required=True, default=_date_to_default)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.user.company_id)
    file_save = fields.Binary(string='XML dokumentas', readonly=True)
    name = fields.Char(string='Pavadinimas')
    state = fields.Selection([('draft', 'Juodraštis'), ('download', 'Atsisiųsti')], default='draft')
    xml_type = fields.Selection([('products', 'Produktai'), ('journal', 'Žurnalas')],
                                string='Kokią informaciją norite pateikti?')
    show_warning = fields.Boolean(default=False)
    warning_msg = fields.Text(readonly=True)

    @api.multi
    def name_get(self):
        return [(rec.id, _('GPAIS ataskaita')) for rec in self]

    @api.onchange('xml_type', 'date_from', 'date_to')
    def _onchange_settings_reset(self):
        self.state = 'draft'
        self.name = False
        self.warning_msg = False
        self.show_warning = False

    @api.multi
    def _refresh_products(self):
        self.ensure_one()
        moves = self.env['stock.move'].search([('date', '>=', self.date_from),
                                       ('product_id.product_tmpl_id.gpais_product_type', '!=', False),
                                       ('product_id.product_tmpl_id.gpais_product_code', '=', False),])
        moves.mapped('product_id.product_tmpl_id').set_gpais_product_code()

    @api.multi
    def download_products(self):
        self.ensure_one()
        if not (self.env.user.has_group('stock.group_stock_manager') or self.env.user.is_accountant()):
            raise exceptions.AccessError(_('Neturite pakankamai teisių.'))

        if self._context.get('upload') and self.name and self.file_save:
            data_file = base64.decodestring(self.file_save)
            self.env.user.upload_gpais_xml(data_file, xml_type='products')
            return {
                'name': _('Parsisiųsti'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'gpais.wizard',
                'type': 'ir.actions.act_window',
                'target': 'main',
                'res_id': self.id,
            }

        # Find new products that have not been updated but been moved
        self._refresh_products()

        # Create root declaration
        xml = ET.Element('produktuSarasas')
        xml.set('xmlns', "urn:x-gpais:vvs:produktai")
        xml.set('xmlns:gpais', "urn:x-gpais:bendra")
        xml.set('xmlns:kls', "urn:x-gpais:kls")
        subjektas = ET.SubElement(xml, 'subjektas')
        subjektas.set('kodas', self.env.user.sudo().company_id.company_registry)
        produktai = ET.SubElement(xml, 'produktai')
        missing_product_names = []
        products_missing_weight = []
        packages_missing_weight = []
        batteries_missing_weight = []
        warnings = []
        self.warning_msg = False
        self.show_warning = False

        ###########################
        # GET PRODUCT INFORMATION #
        ###########################

        product_ids = self.env['product.template'].sudo().with_context(active_test=False).search([
            ('gpais_product_type', '!=', False),
            ('gpais_use_forced_product_code', '=', False),
            ('type', '=', 'product'),
            '|',
            ('package_update_date', '>=', self.date_from),
            ('gpais_info_update_date', '>=', self.date_from),
        ])

        registracijos_ids = {ptype: product_ids.get_gpais_registracijos_id(ptype)
                             for ptype in PRODUCT_TYPES_ENTRY_ID_MAP.keys()}
        register_dates = {ptype: product_ids.get_gpais_register_date_from(ptype)
                          for ptype in PRODUCT_TYPES_ENTRY_ID_MAP.keys()}
        skip_misregistered_elements = self.env.user.company_id.sudo().gpais_skip_misregistered_elements
        for product_id in product_ids:
            gpais_product_type = product_id.gpais_product_type
            registracijos_id = registracijos_ids[gpais_product_type]
            if not registracijos_id:
                raise exceptions.UserError(
                    _('Eikite į kompanijos nustatymus ir nurodykite GPAIS identifikacinius numerius.'))

            if not product_id.gpais_product_code:
                product_id.set_gpais_product_code()
                if not product_id.gpais_product_code:
                    missing_product_names.append(product_id.name)
                    continue

            date_to_market_min = register_dates[gpais_product_type]

            if not date_to_market_min and not product_id.date_to_market_from:
                raise exceptions.UserError(_('Nėra GPAIS registracijos datos ir produktas neturi informacijos apie tiekimo rinka pradžią.'))

            if not product_id.check_veiklos_budas(None, skip_activity=True):
                warnings.append('%s (%s)' % (product_id.name, product_id.gpais_product_code))
                if skip_misregistered_elements:
                    continue

            element = ET.SubElement(produktai, gpais_product_type)

            ET.SubElement(element, 'registracijosId').text = str(registracijos_id)

            ET.SubElement(element, 'kodas').text = product_id.gpais_product_code

            ET.SubElement(element, 'pavadinimas').text = product_id.name[:100] or ''

            product_weight = round(product_id.weight / 1000.0, 6)
            if tools.float_is_zero(product_weight, precision_digits=6):
                products_missing_weight.append(product_id.display_name)
            ET.SubElement(element, 'svoris').text = '%.6f' % product_weight

            ET.SubElement(element, 'pradetaTiektiNuo').text = \
                max(date_to_market_min, product_id.date_to_market_from).split(' ')[0]

            if product_id.date_to_market_until:
                ET.SubElement(element, 'tiektaIki').text = product_id.date_to_market_until.split(' ')[0]

            gaminioPakuotes = False
            date_to_market_min = max([register_dates['prekinisVienetas'], product_id.date_to_market_from])
            if gpais_product_type != 'transportoPriemone':
                packages_to_check = product_id.product_package_default_ids.filtered(lambda p: not p.date_to or
                                                                                              p.date_to >= date_to_market_min)
                packages_to_report = self.env['product.package.default']
                for package in packages_to_check:
                    if not package.package_id.check_veiklos_budas(None, skip_activity=True):
                        warnings.append(_('Pakuotė %s (produktas %s (%s))')
                                        % (package.package_id.name, product_id.name, product_id.gpais_product_code))
                        if skip_misregistered_elements:
                            continue
                    packages_to_report += package
                if packages_to_report and gpais_product_type == 'prekinisVienetas':
                    gaminioPakuotes = ET.SubElement(element, 'pakuotes')
                elif packages_to_report:
                    gaminioPakuotes = ET.SubElement(element, 'gaminioPakuotes')
                for package_default_id in packages_to_report:
                    package_id = package_default_id.package_id
                    if gpais_product_type == 'prekinisVienetas':
                        gaminioPakuote = ET.SubElement(gaminioPakuotes, 'pvPakuote')
                    else:
                        gaminioPakuote = ET.SubElement(gaminioPakuotes, 'gaminioPakuote')

                    ET.SubElement(gaminioPakuote, 'pavadinimas').text = package_id.name

                    ET.SubElement(gaminioPakuote, 'kategorija').text = PACKAGE_CATEGORY_MAPPING[package_id.package_category]

                    ET.SubElement(gaminioPakuote, 'rusis').text = 'CL130:' + package_id.rusis + ':2000-01-01'

                    ET.SubElement(gaminioPakuote, 'kiekisPakuoteje').text = '%d' % round(package_default_id.qty_in_pack)

                    ET.SubElement(gaminioPakuote, 'perdirbama').text = 'true' if package_id.recycling_type == 'perdirbama' else 'false'

                    ET.SubElement(gaminioPakuote, 'vienkartine').text = 'true' if package_id.use_type == 'vienkartine' else 'false'

                    package_weight = tools.float_round(package_id.weight / 1000.0, precision_digits=6)
                    if tools.float_is_zero(package_weight, precision_digits=6):
                        # If package weight is set to some very small value, we round it up to 1g (but only if it is actually set to something)
                        package_weight = tools.float_round(package_id.weight / 1000.0, precision_digits=6, rounding_method='UP')
                        if tools.float_is_zero(package_weight, precision_digits=6):
                            packages_missing_weight.append(_("%s, pakuotė %s") % (product_id.display_name, package_id.display_name))
                    ET.SubElement(gaminioPakuote, 'svoris').text = '%.6f' % package_weight

                    ET.SubElement(gaminioPakuote, 'pradetaTiektiNuo').text = \
                        max(date_to_market_min, package_default_id.date_from).split(' ')[0]

                    if package_default_id.date_to:
                        ET.SubElement(gaminioPakuote, 'tiektaIki').text = package_default_id.date_to.split(' ')[0]

                    if gpais_product_type != 'prekinisVienetas':
                        pakuociu_registracijos_id = self.env.user.sudo().company_id.gpais_registras_pakuotes
                        if not pakuociu_registracijos_id:
                            raise exceptions.UserError(_('Nenurodytas GPAIS pakuočių identifikacinis numeris. Eikite į '
                                                         'kompanijos nustatymus ir užpildykite trūkstamą informaciją.'))
                        ET.SubElement(gaminioPakuote, 'registracijosId').text = str(pakuociu_registracijos_id)

            if gpais_product_type == 'prekinisVienetas' and product_id.uzstatine_pakuote_ids:
                if not gaminioPakuotes:
                    gaminioPakuotes = ET.SubElement(element, 'pakuotes')
                for uzstatine_id in product_id.uzstatine_pakuote_ids:
                    if uzstatine_id.use_type == 'vienkartine':
                        uzstatine = ET.SubElement(gaminioPakuotes, 'vienkartineUzstatinePakuote')
                    else:
                        uzstatine = ET.SubElement(gaminioPakuotes, 'daugkartineUzstatinePakuote')

                    ET.SubElement(uzstatine, 'pakuociuSkaicius').text = str(uzstatine_id.qty)

                    ET.SubElement(uzstatine, 'pradetaTiektiNuo').text = \
                        max(date_to_market_min, product_id.date_to_market_from, uzstatine_id.date_from).split(' ')[0]

                    if uzstatine_id.end_date: #TODO: maybe check with product_template.date_to_market_until
                        ET.SubElement(uzstatine, 'tiektaIki').text = uzstatine_id.end_date

                    if uzstatine_id.use_type == 'vienkartine':
                        ET.SubElement(uzstatine, 'organizacijosKodas').text = uzstatine_id.org_code

                    ET.SubElement(uzstatine, 'pakuotesKodas').text = uzstatine_id.code

            if gpais_product_type == 'elektronineIranga':
                if product_id.gpais_buitine_iranga:
                    ET.SubElement(element, 'buitineIranga').text = 'true'
                else:
                    ET.SubElement(element, 'buitineIranga').text = 'false'

            if gpais_product_type != 'prekinisVienetas':
                ET.SubElement(element, 'klasifikacija').text = product_id.klasifikacija.code

        ###########################
        # GET BATTERY INFORMATION #
        ###########################

        battery_ids = self.env['product.template'].sudo().with_context(active_test=False).search([
            ('battery_update_date', '>=', self.date_from),
            ('gpais_product_type', '!=', False),
            ('type', '=', 'product'),
            ('product_battery_line_ids', '!=', False)
        ]).mapped('product_battery_line_ids.battery_id')

        bateriju_registracijos_id = self.env.user.sudo().company_id.gpais_registras_baterijos
        min_battery_date = self.env.user.sudo().company_id.gpais_registras_baterijos_data
        if battery_ids and not bateriju_registracijos_id:
            raise exceptions.UserError(_('Nenurodytas GPAIS baterijų identifikacinis numeris. Eikite į '
                                         'kompanijos nustatymus ir užpildykite trūkstamus duomenis.'))

        for battery in battery_ids:
            if not battery.check_veiklos_budas(None, skip_activity=True):
                warnings.append(_('Baterija: %s (Kodas: %s)') % (battery.name, battery.code or '-'))
                if skip_misregistered_elements:
                    continue
            element = ET.SubElement(produktai, 'baterija')
            ET.SubElement(element, 'registracijosId').text = str(bateriju_registracijos_id)

            ET.SubElement(element, 'kodas').text = battery.code or 'BT'

            ET.SubElement(element, 'pavadinimas').text = battery.name or ''

            battery_weight = round(battery.weight / 1000.0, 6)
            if tools.float_is_zero(battery_weight, precision_digits=6):
                batteries_missing_weight.append(_("baterija %s") % battery.name)
            ET.SubElement(element, 'svoris').text = '%.6f' % battery_weight

            ET.SubElement(element, 'pradetaTiektiNuo').text = \
                max(min_battery_date, battery.date_to_market_from).split(' ')[0]

            ET.SubElement(element, 'baterijosRusis').text = battery.rusis

            ET.SubElement(element, 'chemineSudetis').text = battery.chemine_sudetis.code

            ET.SubElement(element, 'imontuota').text = 'true' if battery.imontuota else 'false'

            ET.SubElement(element, 'klasifikacija').text = battery.klasifikacija.code

        errors = ''
        missing_product_names = list(set(missing_product_names))
        if missing_product_names:
            errors += _('\nŠiems produktams nenurodyti vidiniai numeriai: \n%s'
                        ) % '\n'.join(map(str, missing_product_names))
        if products_missing_weight:
            errors += _('\nŠiems produktams nenurodytas svoris: \n%s') % '\n'.join(products_missing_weight)
        if packages_missing_weight:
            errors += _('\nŠioms pakuotėms nenurodytas svoris: \n%s') % '\n'.join(packages_missing_weight)
        if batteries_missing_weight:
            errors += _('\nŠioms baterijoms nenurodytas svoris: \n%s') % '\n'.join(batteries_missing_weight)

        if errors:
            raise exceptions.UserError(errors)

        if not len(xml):
            raise exceptions.UserError(_('Nėra duomenų.'))

        if warnings:
            self.show_warning = True
            if skip_misregistered_elements:
                warning_first_line = _('Šių produktų konfigūracija neatitinka įmonės GPAIS registracijos nustatymų. Konfigūracijos neatitinkantys produktai buvo praleisti:\n')
            else:
                warning_first_line = _('Šių produktų konfigūracija neatitinka įmonės GPAIS registracijos nustatymų:\n')
            self.warning_msg = warning_first_line + '\n'.join(warnings)

        # Get xml string in correct encoding
        data_file = ET.tostring(xml, encoding='UTF-8', method='xml')
        data_file = parseString(data_file).toprettyxml(encoding='UTF-8')

        if platform == 'win32':
            sep = '\\'
        else:
            sep = '/'
        # todo: fix validation with several schema files
        if not xml_validator(data_file, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'data')) + sep + 'gpais-vvs-produktai.xsd'):
            raise exceptions.Warning(_('Nepavyko sugeneruoti XML. Trūksta duomenų.'))

        # change state of the wizard
        self.write({
            'name': ('gpais_produktai_%s_%s.xml' % (self.date_from, self.date_to)).replace('-', '_'),
            'file_save': base64.encodestring(data_file),
            'state': 'download',
        })

        # upload
        if self._context.get('upload'):
            self.env.user.upload_gpais_xml(data_file, xml_type='products')

        return {
            'name': _('Parsisiųsti'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'gpais.wizard',
            'type': 'ir.actions.act_window',
            'target': 'main',
            'res_id': self.id,
        }

    def generate_journal_excel(self):
        self.ensure_one()
        recordset = self.get_journal_entries()

        workbook = xlwt.Workbook(encoding='utf-8')
        worksheet = workbook.add_sheet(_('GPAIS journal'))
        header = [_('Picking'), _('Origin'), _('Date and time'), _('GPAIS product code'),
                  _('Quantity'), _('Weight, kg'), _('Supply date'), _('Supply type'), _('Activity type')]
        header_bold_brd = xlwt.easyxf("font: bold on; borders: left thin, right thin, bottom thin ")
        col = 0
        for val in header:
            worksheet.write(0, col, val, header_bold_brd)
            worksheet.col(col).width = 256 * 20
            col += 1
        for row, record in enumerate(recordset, 1):
            worksheet.write(row, 0, record.get('picking_name'))
            worksheet.write(row, 1, record.get('picking_origin'))
            worksheet.write(row, 2, record.get('date'))
            worksheet.write(row, 3, record.get('product_code'))
            worksheet.write(row, 4, record.get('quantity'))
            worksheet.write(row, 5, record.get('product_weight'))
            worksheet.write(row, 6, record.get('supply_date'))
            worksheet.write(row, 7, record.get('supply_type'))
            worksheet.write(row, 8, record.get('activity_type'))

        worksheet.set_panes_frozen(True)
        worksheet.set_horz_split_pos(1)
        f = StringIO.StringIO()
        workbook.save(f)
        base64_file = f.getvalue().encode('base64')
        file_name = (_('GPAIS_journal_' + str(self.date_from) + '__' + str(self.date_to) + '.xls')).replace('-', '_')
        attachment = self.env['ir.attachment'].create({
            'res_model': 'gpais.wizard',
            'res_id': self.id,
            'type': 'binary',
            'name': file_name,
            'datas_fname': file_name,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=gpais.wizard&res_id=%s&attach_id=%s' % (
                self[0].id, attachment.id),
            'target': 'self',
        }

    @api.multi
    def get_journal_entries(self):

        def check_market_period(product, move_date):
            if (product.date_to_market_from <= move_date or not product.date_to_market_from) \
                    and (move_date <= product.date_to_market_until or not product.date_to_market_until):
                return ''
            return _('Žurnalo įrašo data %s nepatenka į produkto %s tiekimo į rinką periodą [%s - %s].\n') \
                   % (min_date, product_id.default_code, product_id.date_to_market_from or '',
                      product_id.date_to_market_until or '')

        if not (self.env.user.has_group('stock.group_stock_manager') or self.env.user.is_accountant()):
            raise exceptions.UserError(_('Neturite pakankamai teisių.'))

        self.ensure_one()
        StockMove = self.env['stock.move'].sudo()
        StockPicking = self.env['stock.picking']
        ResPartner = self.env['res.partner']
        self.warning_msg = False
        self.show_warning = False
        export_xls = self._context.get('export_xls')
        warnings = str()
        recordset = []

        report_package_on_reception = self.env.user.company_id.sudo().gpais_report_package_on_reception

        ###########################
        # GET PRODUCT INFORMATION #
        ###########################
        if report_package_on_reception:
            stock_moves = StockMove.search([
                ('state', '=', 'done'),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('product_id.product_tmpl_id.gpais_product_type', '!=', False),
                ('product_id.type', '=', 'product'),
                ('picking_id.package_direction', 'in', ['in_lt', 'in']),
                ('picking_id.cancel_state', '!=', 'error'),
                ('picking_id.use_default_package', '=', True),
            ]).filtered(lambda m: not any(m.mapped('product_id.product_tmpl_id.product_package_default_ids.package_id.savom_reikmem')))
            activity_type = self.env.user.sudo().company_id.gpais_default_veiklos_budas.code
        else:
            stock_moves = StockMove.search([
                ('state', '=', 'done'),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('product_id.product_tmpl_id.gpais_product_type', '!=', False),
                ('product_id.type', '=', 'product'),
                ('picking_id.package_direction', 'in', ['out_lt', 'out_kt']),
                ('picking_id.cancel_state', '!=', 'error'),
                ('picking_id.use_default_package', '=', True),
            ])

        for move in stock_moves:
            non_error_qty = sum(move.non_error_quant_ids.mapped('qty'))
            product_id = move.product_id.product_tmpl_id
            partner_id = move.partner_id
            picking_id = move.picking_id
            gpais_product_type = product_id.gpais_product_type

            if not report_package_on_reception:
                activity_type = get_activity_type(picking_id.package_direction,
                                                  partner_id and partner_id.gpais_tiekimas or '') \
                                or self.env.user.sudo().company_id.gpais_default_veiklos_budas.code \
                                or 'CL118:DP:2016-12-07'
            if not product_id.check_veiklos_budas(activity_type):
                continue

            min_date = move.date.split(' ')[0]
            warning = check_market_period(product_id, min_date)
            if warning:
                warnings += warning
                continue

            supply_type = move.guess_gpais_supply_type() or 'supplier'
            # Reverse supply type is not used for now, if set, it should be skipped
            if supply_type == 'reverse':
                warnings += _('Produkto %s kiekis %d buvo grąžintas ir negali būti pakoreguotas žurnale.\n') \
                            % (product_id.gpais_product_code, non_error_qty)
                continue

            registration = product_id.get_gpais_registracijos_id()
            if not registration:
                raise exceptions.UserError(
                    _('Eikite į kompanijos nustatymus ir nurodykite GPAIS identifikacinius numerius.'))

            quantity = ('%.2f' % non_error_qty) if gpais_product_type == 'elektronineIranga' \
                else ('%d' % math.ceil(non_error_qty))  # TODO: ROUND OR CEIL?

            if product_id.gpais_product_origin != 'guess':
                supply_type = product_id.gpais_product_origin

            # ID is int64, max value 9 223 372 036 854 775 807
            # 15 chars: 4 free
            identification = PRODUCT_TYPES_ENTRY_ID_MAP.get(gpais_product_type) + (
                    picking_id.force_gpais_entry_id and (picking_id.force_gpais_entry_id.zfill(4)[:4]
                                                         + str(move.id).zfill(3)[-3:])
                    or str(move.id).zfill(7)[-7:]) + str(product_id.id).zfill(6)[-6:] \
                        + ('1' if picking_id.force_gpais_entry_id else '0')

            record = {
                'id': identification,
                'registration': str(registration),
                'product_code': product_id.gpais_product_code,
                'supply_date': min_date,
                'supply_type': PACKAGE_ORIGIN_MAPPING[supply_type],
                'activity_type': activity_type,
                'quantity': quantity,
            }
            if export_xls:
                product_weight = round(product_id.weight / 1000.0, 6)
                record.update({
                    'picking_name': picking_id.name or str(),
                    'picking_origin': picking_id.origin or str(),
                    'product_weight': '%.6f' % product_weight,
                    'date': move.date,
                })
            recordset.append(record)

        #############################
        # GET OWN NEEDS INFORMATION #
        #############################
        stock_moves = StockMove.search([
            ('state', '=', 'done'),
            ('date', '<=', self.date_to),
            ('date', '>=', self.date_from),
            ('product_id.product_tmpl_id.gpais_product_type', '!=', False),
            ('product_id.type', '=', 'product'),
            ('picking_id.package_direction', 'in', ['in_lt', 'in']),
            ('picking_id.cancel_state', '!=', 'error'),
            ('picking_id.use_default_package', '=', True),
        ]).filtered(lambda m: any(
            m.mapped('product_id.product_tmpl_id.product_package_default_ids.package_id.savom_reikmem')))

        for move in stock_moves:
            non_error_qty = sum(move.non_error_quant_ids.mapped('qty'))
            product_id = move.product_id.product_tmpl_id
            picking_id = move.picking_id
            gpais_product_type = product_id.gpais_product_type
            registration = product_id.get_gpais_registracijos_id()
            if not registration:
                raise exceptions.UserError(
                    _('Eikite į kompanijos nustatymus ir nurodykite GPAIS identifikacinius numerius.'))

            if not product_id.check_veiklos_budas('CL118:SS:2016-12-07'):
                continue

            min_date = picking_id.min_date.split(' ')[0]
            warning = check_market_period(product_id, min_date)
            if warning:
                warnings += warning
                continue

            supply_type = move.guess_gpais_supply_type() or 'supplier'
            # Reverse supply type is not used for now, if set, it should be skipped
            if supply_type == 'reverse':
                warnings += _('Produkto %s kiekis %d buvo grąžintas ir negali būti pakoreguotas žurnale.\n') \
                            % (product_id.gpais_product_code, non_error_qty)
                continue

            quantity = ('%.2f' % non_error_qty) if gpais_product_type == 'elektronineIranga' \
                else ('%d' % math.ceil(non_error_qty))  # TODO: ROUND OR CEIL?

            if product_id.gpais_product_origin != 'guess':
                supply_type = product_id.gpais_product_origin

            # ID is int64, max value 9 223 372 036 854 775 807
            # 15 chars: 4 free
            identification = PRODUCT_TYPES_ENTRY_ID_MAP.get(gpais_product_type) + (
                    picking_id.force_gpais_entry_id and (picking_id.force_gpais_entry_id.zfill(4)[:4]
                                                         + str(move.id).zfill(3)[-3:])
                    or str(move.id).zfill(7)[-7:]) + str(product_id.id).zfill(6)[-6:] + \
                             ('1' if picking_id.force_gpais_entry_id else '0')

            record = {
                'id': identification,
                'registration': str(registration),
                'product_code': product_id.gpais_product_code,
                'supply_date': min_date,
                'supply_type': PACKAGE_ORIGIN_MAPPING[supply_type],
                'activity_type': 'CL118:SS:2016-12-07',
                'quantity': quantity,
            }
            if export_xls:
                product_weight = round(product_id.weight / 1000.0, 6)
                record.update({
                    'picking_name': picking_id.name or str(),
                    'picking_origin': picking_id.origin or str(),
                    'product_weight': '%.6f' % product_weight,
                    'date': move.date,
                })
            recordset.append(record)

        ###########################
        # GET BATTERY INFORMATION #
        ###########################
        BatteryReport = self.env['report.product.batteries']
        ProductBattery = self.env['product.battery']
        BatteryReport.refresh_materialised_product_batteries_history()
        domain = [('date', '<=', self.date_to),
                  ('date', '>=', self.date_from),
                  ('qty_of_batteries', '>', 0),
                  ('package_direction', 'in', ['out_lt', 'out_kt'])]
        field_list = ['qty_of_batteries', 'partner_id', 'product_tmpl_id', 'product_id', 'battery_id', 'picking_id',
                      'package_direction', 'move_id']
        groupby = ['product_tmpl_id', 'picking_id', 'battery_id', 'partner_id', 'package_direction', 'move_id']
        data = BatteryReport.read_group(domain, field_list, groupby, lazy=False)
        registration = self.env.user.sudo().company_id.gpais_registras_baterijos
        if data and not registration:
            raise exceptions.UserError(
                _('Eikite į kompanijos nustatymus ir nurodykite GPAIS identifikacinius numerius.'))

        for line in data:
            battery_id = ProductBattery.browse(line['battery_id'][0])
            partner_id = line.get('partner_id')
            # partner_id is not required on stock.picking and thus can be null on report.product.batteries
            if partner_id:
                partner_id = ResPartner.browse(partner_id[0])
            move_id = StockMove.browse(line['move_id'][0])
            if not move_id:
                continue
            activity_type = get_activity_type(line['package_direction'],
                                              partner_id and partner_id.gpais_tiekimas or '') \
                            or self.env.user.sudo().company_id.gpais_default_veiklos_budas.code \
                            or 'CL118:DP:2016-12-07'

            if not battery_id.check_veiklos_budas(activity_type):
                continue

            supply_type = move_id.guess_gpais_supply_type()
            # Reverse supply type is not used for now, if set, it should be skipped in journal
            if supply_type == 'reverse':
                warnings += _('Produkto %s kiekis %d buvo grąžintas ir negali būti pakoreguotas žurnale.\n') \
                            % (battery_id.code, line['qty_of_batteries'])
                continue

            supply_type = supply_type if supply_type != 'production' else 'supplier'
            picking_id = StockPicking.browse(line['picking_id'][0])
            activity_type = get_activity_type(line['package_direction'], partner_id and
                                              partner_id.gpais_tiekimas or str()) \
                            or self.env.user.sudo().company_id.gpais_default_veiklos_budas.code or 'CL118:DP:2016-12-07'
            supply_type_code = 'CL140:1:2017-02-22' if supply_type == 'supplier' else 'CL140:3:2017-02-22'

            identification = '6' + str(picking_id.force_gpais_entry_id or picking_id.id).zfill(5)[-4:] \
                             + (picking_id.force_gpais_entry_id and (picking_id.force_gpais_entry_id.zfill(4)[:4]
                                                                     + str(move.id).zfill(3)[-3:])
                                or str(move.id).zfill(7)[-7:]) + str(battery_id.id).zfill(6)[-6:] \
                             + ('1' if picking_id.force_gpais_entry_id else '0')

            record = {
                'id': identification,
                'registration': str(registration),
                'product_code': battery_id.code,
                'supply_date': picking_id.min_date.split(' ')[0],
                'supply_type': supply_type_code,
                'activity_type': activity_type,
                'quantity': str(int(math.ceil(line['qty_of_batteries']))),
            }
            if export_xls:
                product_weight = round(battery_id.weight / 1000.0, 6)
                record.update({
                    'picking_name': picking_id.name or str(),
                    'picking_origin': picking_id.origin or str(),
                    'product_weight': '%.6f' % product_weight,
                    'date': move_id.date,
                })
            recordset.append(record)

        if not len(recordset):
            raise exceptions.UserError(_('Nėra duomenų.'))

        if warnings:
            self.show_warning = True
            warning_msg = _('Kai kurie žurnalo įrašai buvo praleisti dėl šių klaidų:\n') + warnings
            self.warning_msg = warning_msg

        return recordset

    @api.multi
    def download_journal(self):
        if not (self.env.user.has_group('stock.group_stock_manager') or self.env.user.is_accountant()):
            raise exceptions.UserError(_('Neturite pakankamai teisių.'))

        if self._context.get('upload') and self.name and self.file_save:
            data_file = base64.decodestring(self.file_save)
            self.env.user.upload_gpais_xml(data_file, xml_type='journal')
            return {
                'name': _('Parsisiųsti'),
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'gpais.wizard',
                'type': 'ir.actions.act_window',
                'target': 'main',
                'res_id': self.id,
            }

        self.ensure_one()
        recordset = self.get_journal_entries()
        # prepare XML root
        xml = ET.Element('irasuSarasas')
        xml.set('xmlns', "urn:x-gpais:vvs:zurnalas")
        xml.set('xmlns:gpais', "urn:x-gpais:bendra")
        xml.set('xmlns:kls', "urn:x-gpais:kls")
        subjektas = ET.SubElement(xml, 'subjektas')
        subjektas.set('kodas', self.env.user.sudo().company_id.company_registry)
        records_element = ET.SubElement(xml, 'irasai')

        for record in recordset:
            element = ET.SubElement(records_element, 'irasas')
            element.set('id', record.get('id'))
            ET.SubElement(element, 'registracijosId').text = record.get('registration')
            ET.SubElement(element, 'produktoKodas').text = record.get('product_code')
            ET.SubElement(element, 'tiekimoRinkaiData').text = record.get('supply_date')
            ET.SubElement(element, 'gavimoBudas').text = record.get('supply_type')
            ET.SubElement(element, 'veiklosBudas').text = record.get('activity_type')
            ET.SubElement(element, 'kiekis').text = record.get('quantity')

        # Get xml string in correct encoding
        data_file = ET.tostring(xml, encoding='UTF-8', method='xml')
        data_file = parseString(data_file).toprettyxml(encoding='UTF-8')

        if platform == 'win32':
            sep = '\\'
        else:
            sep = '/'
        if not xml_validator(data_file, xsd_file=os.path.abspath(
                os.path.join(os.path.dirname(__file__), '..', 'data')) + sep + 'gpais-vvs-zurnalas.xsd'):
            raise exceptions.ValidationError(_('Nepavyko sugeneruoti XML. Trūksta duomenų.'))
        # change state of the wizard
        self.write({
            'name': str.replace('gpais_irasai_%s_%s.xml' % (self.date_from, self.date_to), '-', ''),
            'file_save': base64.encodestring(data_file),
            'state': 'download',
        })

        # upload
        if self._context.get('upload'):
            self.env.user.upload_gpais_xml(data_file, xml_type='journal')

        return {
            'name': _('Parsisiųsti'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'gpais.wizard',
            'type': 'ir.actions.act_window',
            'target': 'main',
            'res_id': self.id,
        }
