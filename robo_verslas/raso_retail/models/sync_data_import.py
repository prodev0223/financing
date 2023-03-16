# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, exceptions, _
from lxml import etree, objectify
from lxml.etree import tostring
from itertools import chain
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pyodbc
from pyodbc import OperationalError
from xml.etree.ElementTree import tostring
import pytz


class SyncDataImport(models.Model):
    _name = 'sync.data.import'

    data_type = fields.Selection([('0', 'ShopList'),
                                  ('1', 'Partners'),
                                  ('2', 'GoodsGroups'),
                                  ('3', 'Goods'),
                                  ('4', 'GoodsPrices'),
                                  ('5', 'Discounts'),
                                  ('6', 'GroupDiscounts'),
                                  ('7', 'GoodsPricesTerm')], required=True)

    ext_import_id = fields.Integer(string='Išorinis importo ID')
    full_sync = fields.Boolean(default=False)
    data_provider = fields.Char(string='Tiekėjas')
    sync_data = fields.Text(string='Perduodami duomenys')
    group_id = fields.Integer(string='Grupės identifikatorius')
    group_no = fields.Integer(string='Grupės numeris')
    group_state = fields.Integer(string='Grupės būsena')
    status = fields.Char(string='Būsena')
    rec_date = fields.Date(string='Įrašo data')
    edit_date = fields.Date(string='Keitimo data')

    shop_ids = fields.Many2many('raso.shoplist')
    partner_ids = fields.Many2many('res.partner')
    category_ids = fields.Many2many('product.category')
    product_ids = fields.Many2many('product.template')
    prices_ids = fields.Many2many('product.template.prices')
    discount_ids = fields.Many2many('product.template.discounts')
    group_discount_ids = fields.Many2many('product.category.discounts')

    revision_ids = fields.One2many('data.import.revisions', 'data_import_id')

    @api.multi
    def import_data(self, args):
        """
        Import object data in XML format to external Raso Retail server and fetch the response status
        :param args: arguments expected in a query - data_type/provider/XML file (list)
        :return: None
        """
        self.ensure_one()

        # Get external cursor and database name
        db = self.sudo().env['ir.config_parameter'].get_param('raso_db')
        cursor = self.env['raso.export.wizard'].get_cursor()

        sql = "EXEC [" + db + "].[ie].[usp_SyncDataImport_i] @DataType=?, @DataProvider=?, @SyncData=?"
        cursor.execute(sql, args)
        import_id = [dict(zip(zip(*cursor.description)[0], row)) for row in cursor.fetchall()][0]
        if import_id:
            self.write({
                'ext_import_id': import_id['SyncDataImportId'],
                'status': '0',
            })
            cursor.commit()
        else:
            raise exceptions.UserError(_('Operacija nepavyko! Negautas importavimo identifikatorius'))

    @api.multi
    def write_vals(self, revision_ids, document):
        self.ensure_one()
        self.write({
            'revision_ids': revision_ids,
            'data_provider': 'RIVILE',
            'sync_data': document,
            'rec_date': datetime.now(pytz.timezone('Europe/Vilnius')).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
            'edit_date': datetime.now(pytz.timezone('Europe/Vilnius')).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
        })

    @api.one
    def format_xml(self):

        def set_node(node, key, value, type_of=None, empty_node=True):
            type_of = str if type_of is None else type_of
            if not value and (not empty_node or type_of == str):
                return False
            el = etree.Element(key)
            if type_of == bool:
                value = '1' if value else '0'
            if isinstance(value, (float, int)) and not isinstance(value, bool):
                value = str(value)
            if value:
                el.text = value
            else:
                el.text = ''
            setattr(node, key, el)

        def format_datetime(value='', nullable=False):
            if nullable and not value:
                return False
            if not value:
                value = datetime.now(pytz.timezone('Europe/Vilnius')).strftime('%Y-%m-%dT%H:%M:%S.000')
            else:
                value = datetime.strptime(value,
                                          tools.DEFAULT_SERVER_DATETIME_FORMAT).strftime('%Y-%m-%dT%H:%M:%S.000')
            return value

        revision_ids = []
        if self.data_type == '0':
            records = self.shop_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                                        <ShopListSync FullSync="1">
                                        </ShopListSync>'''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                        <ShopListSync>
                        </ShopListSync>'''
            root = objectify.fromstring(xml)
            for shop in records:
                shop_list = objectify.Element("ShopList")
                set_node(shop_list, 'ShopNo', shop.shop_no)
                set_node(shop_list, 'ShopName', shop.shop_name)
                set_node(shop_list, 'Address', shop.address)
                set_node(shop_list, 'City', shop.city)
                set_node(shop_list, 'Level', shop.level, type_of=bool)
                set_node(shop_list, 'IPAddress', shop.ip_address)
                set_node(shop_list, 'SCOAddress', shop.sco_address)
                set_node(shop_list, 'Remarks', shop.remarks)
                set_node(shop_list, 'Enabled', '1')
                root.append(shop_list)
                revision_vals = {
                    'revision_number': shop.revision_number,
                    'res_id': shop.id,
                    'res_model': 'raso.shoplist'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        elif self.data_type == '1':
            records = self.partner_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                                        <PartnersSync FullSync="1">
                                        </PartnersSync>
                                        '''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                        <PartnersSync>
                        </PartnersSync>
                        '''
            root = objectify.fromstring(xml)
            revision_ids = []
            for partner in records:
                partners = objectify.Element("Partners")
                set_node(partners, 'Code', partner.kodas)
                set_node(partners, 'Name', partner.name)
                set_node(partners, 'Address', partner.street)
                set_node(partners, 'VATCode', partner.vat)
                set_node(partners, 'Enabled', '1')
                root.append(partners)
                revision_vals = {
                    'revision_number': partner.revision_number,
                    'res_id': partner.id,
                    'res_model': 'res.partner'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        elif self.data_type == '2':
            records = self.category_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                         <GoodsGroupsSync FullSync="1">
                         </GoodsGroupsSync>'''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                         <GoodsGroupsSync>
                         </GoodsGroupsSync>
                        '''
            root = objectify.fromstring(xml)
            for goods_group in records:
                if not goods_group.code:
                    raise exceptions.UserError('Paduotas įrašas %s neturi grupės kodo!' % goods_group.name)
                goods_groups = objectify.Element("GoodsGroups")
                set_node(goods_groups, 'Code', goods_group.code)
                set_node(goods_groups, 'ParentCode', goods_group.parent_code)
                set_node(goods_groups, 'Name', goods_group.name)
                set_node(goods_groups, 'Level', goods_group.level)
                set_node(goods_groups, 'Age', goods_group.age)
                set_node(goods_groups, 'Refundable', goods_group.refundable, type_of=bool)
                set_node(goods_groups, 'Enabled', '1')
                set_node(goods_groups, 'EditDate', format_datetime())
                root.append(goods_groups)
                revision_vals = {
                    'revision_number': goods_group.revision_number,
                    'res_id': goods_group.id,
                    'res_model': 'product.category'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        elif self.data_type == '3':
            records = self.product_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                                       <GoodsSync FullSync="1">
                                       </GoodsSync>
                                       '''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                        <GoodsSync>
                        </GoodsSync>
                        '''
            root = objectify.fromstring(xml)
            for good in records:
                goods = objectify.Element("Goods")
                if not good.barcode:
                    raise exceptions.UserError('Paduotas įrašas %s neturi barkodo!' % good.name)
                set_node(goods, 'Code', good.barcode)
                set_node(goods, 'VCode', good.id)
                set_node(goods, 'Name', good.name)
                set_node(goods, 'MinPrice', good.min_price)
                set_node(goods, 'MaxPrice', good.max_price)
                set_node(goods, 'VatCode', good.vat_code)
                set_node(goods, 'DepNo', good.dep_no)
                set_node(goods, 'Unit', good.uom_id.name)
                set_node(goods, 'ExtraQty', good.extra_qty)
                set_node(goods, 'ExtraCode', good.extra_code)
                set_node(goods, 'ExtraInfo', good.group_code)
                set_node(goods, 'SDate', format_datetime(value=good.s_date, nullable=True))
                set_node(goods, 'SNumber', good.s_number)
                set_node(goods, 'Text', good.text)
                set_node(goods, 'Age', good.age, type_of=bool)
                set_node(goods, 'Refundable', good.refundable, type_of=bool)
                set_node(goods, 'CommentRequired', good.comment_required, type_of=bool)
                set_node(goods, 'IsWeighing', good.is_weighing, type_of=bool)
                set_node(goods, 'SCALE', good.scale, type_of=bool)
                set_node(goods, 'USEUP', good.use_up, type_of=bool)
                set_node(goods, 'SupplierCode', good.supplier_code)
                set_node(goods, 'SupplierName', good.supplier_name)
                set_node(goods, 'DiscountStatus', good.discount_status)
                set_node(goods, 'DiscPointsStatus', good.disc_points_status)
                set_node(goods, 'StartTime', format_datetime(value=good.start_time, nullable=True))
                set_node(goods, 'EndTime', format_datetime(value=good.end_time, nullable=True))
                set_node(goods, 'Enabled', '1')
                set_node(goods, 'EditDate', format_datetime())
                root.append(goods)
                revision_vals = {
                    'revision_number': good.revision_number,
                    'res_id': good.id,
                    'res_model': 'product.template'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        elif self.data_type == '4' or self.data_type == '7':
            records = self.prices_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                                        <GoodsPricesSync FullSync="1">
                                        </GoodsPricesSync>
                                        '''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                        <GoodsPricesSync>
                        </GoodsPricesSync>
                        '''
            root = objectify.fromstring(xml)
            for p_price in records:
                goods_prices = objectify.Element("GoodsPrices")
                if not p_price.product_id.barcode:
                    raise exceptions.UserError(_('Paduotas įrašas %s neturi barkodo!') % p_price.name)
                set_node(goods_prices, 'GoodsCode', p_price.product_id.barcode)
                set_node(goods_prices, 'ShopNo', p_price.shop_id.shop_no, type_of=int)
                set_node(goods_prices, 'PriceNo', p_price.id, type_of=int)
                set_node(goods_prices, 'Qty', p_price.qty)
                set_node(goods_prices, 'Price', p_price.price)
                set_node(goods_prices, 'DateFrom', format_datetime(value=p_price.date_from, nullable=True))
                set_node(goods_prices, 'DateTo', format_datetime(value=p_price.date_to, nullable=True))
                set_node(goods_prices, 'Enabled', '1')
                set_node(goods_prices, 'EditDate', format_datetime())
                root.append(goods_prices)
                revision_vals = {
                    'revision_number': p_price.revision_number,
                    'res_id': p_price.id,
                    'res_model': 'product.template.prices'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        elif self.data_type == '5':
            records = self.discount_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                                        <DiscountsSync FullSync = "1">
                                        </DiscountsSync>
                                        '''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                        <DiscountsSync>
                        </DiscountsSync>
                        '''
            root = objectify.fromstring(xml)
            for discount in records:
                discounts = objectify.Element("Discounts")
                set_node(discounts, 'ID', discount.id)
                set_node(discounts, 'StoreCode', discount.shop_id.shop_no, type_of=int)
                set_node(discounts, 'ProductCode', discount.product_id.barcode)
                set_node(discounts, 'Name', discount.name)
                set_node(discounts, 'Status', discount.status)
                set_node(discounts, 'Quantity', discount.quantity)
                set_node(discounts, 'Price', discount.price)
                set_node(discounts, 'DiscountAmount', discount.discount_amount)
                set_node(discounts, 'Amount', discount.amount)
                set_node(discounts, 'Weekdays', discount.weekdays)
                set_node(discounts, 'StartsAt', format_datetime(value=discount.starts_at, nullable=True))
                set_node(discounts, 'EndsAt', format_datetime(value=discount.ends_at, nullable=True))
                set_node(discounts, 'CardRequired', discount.card_required, type_of=bool)
                set_node(discounts, 'AppliesToProduct', discount.applies_to_product, type_of=bool)
                set_node(discounts, 'DiscountFromProduct', discount.discount_from_product, type_of=bool)
                set_node(discounts, 'Type', discount.type)
                set_node(discounts, 'AID', discount.aid)
                set_node(discounts, 'Enabled', '1')
                set_node(discounts, 'EditDate', format_datetime())

                root.append(discounts)
                revision_vals = {
                    'revision_number': discount.revision_number,
                    'res_id': discount.id,
                    'res_model': 'product.template.discounts'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        elif self.data_type == '6':
            records = self.group_discount_ids
            if not records:
                return
            if self.full_sync:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                                    <GDiscountsSync FullSync = "1">
                                    </GDiscountsSync>
                                    '''
            else:
                xml = '''<?xml version="1.0" encoding="UTF-8"?>
                        <GDiscountsSync>
                        </GDiscountsSync>
                        '''
            root = objectify.fromstring(xml)
            for discount in records:
                g_discounts = objectify.Element("GDiscounts")
                set_node(g_discounts, 'ID', discount.id)
                set_node(g_discounts, 'StoreCode', discount.shop_id.shop_no, type_of=int)
                set_node(g_discounts, 'ExtraInfo', discount.category_id.code)
                set_node(g_discounts, 'SumFrom', discount.sum_from, type_of=int)
                set_node(g_discounts, 'SumTo', discount.sum_to, type_of=int)
                set_node(g_discounts, 'Name', discount.name)
                set_node(g_discounts, 'Discount', discount.discount, type_of=int)
                set_node(g_discounts, 'Status', discount.status)
                set_node(g_discounts, 'DiscountForGroups', discount.discount_for_groups, type_of=bool)
                set_node(g_discounts, 'BasedOnTime', discount.based_on_time, type_of=bool)
                set_node(g_discounts, 'SaleForbidden', discount.sale_forbidden, type_of=bool)
                set_node(g_discounts, 'CardRequired', discount.card_required, type_of=bool)
                set_node(g_discounts, 'DicType', 'P')
                set_node(g_discounts, 'Weekdays', discount.weekdays)
                set_node(g_discounts, 'StartsAt', format_datetime(value=discount.starts_at, nullable=True))
                set_node(g_discounts, 'EndsAt', format_datetime(value=discount.ends_at, nullable=True))
                set_node(g_discounts, 'Enabled', '1')
                set_node(g_discounts, 'EditDate', format_datetime())

                root.append(g_discounts)
                revision_vals = {
                    'revision_number': discount.revision_number,
                    'res_id': discount.id,
                    'res_model': 'product.category.discounts'
                }
                revision_ids.append((0, 0, revision_vals))
            objectify.deannotate(root)
            etree.cleanup_namespaces(root)
            if not self._context.get('download', False):
                self.write_vals(revision_ids, etree.tostring(root, xml_declaration=True, encoding='utf-8'))
                self.import_data([self.data_type, self.data_provider, self.sync_data])
            else:
                self.sync_data = etree.tostring(root, xml_declaration=True)

        else:
            raise exceptions.ValidationError(_('Unrecognized data type'))
        if self._context.get('download', False):
            attach_vals = {
                'res_model': 'sync.data.import',
                'name': self.data_type + '.xml',
                'datas_fname': self.data_type + '.xml',
                'res_id': self.id,
                'type': 'binary',
                'datas': self.sync_data.encode('base64'),
            }
            return self.env['ir.attachment'].sudo().create(attach_vals)
        else:
            self.cron_update_import_status()

    @api.model
    def cron_update_import_status(self):
        """
        Fetch status of exported objects and write it to corresponding objects.
        Possible response statuses - accepted(1)/rejected(3)
        :return: None
        """
        # Don't run updater which runs every 10 minutes at night,
        # so it does not intersect with other cron-jobs
        if not 3 < datetime.utcnow().hour < 20:
            return
        # Collect imports of statuses - not imported (0) / waiting (2) / rejected (3)
        import_ids = self.env['sync.data.import'].search([('status', 'in', ['0', '2', '3'])])
        if import_ids:
            db = self.sudo().env['ir.config_parameter'].get_param('raso_db')
            cursor = self.env['raso.export.wizard'].get_cursor(raise_exception=False)
            # We do not raise exception here, since cron runs every 10 mins
            # so it can spam us really quickly. If there's a longer-term problem
            # other cron-jobs will detect it
            if not cursor:
                return

            for import_id in import_ids:
                sql = "EXEC [" + db + "].[ie].[usp_SyncDataImport_v] @SyncDataImportId = %s" % import_id.ext_import_id
                cursor.execute(sql)
                res = [{column_name: value for column_name, value
                        in zip(zip(*cursor.description)[0], row)} for row in cursor.fetchall()]
                if res:
                    status = res[0].get('Status', 3)
                else:
                    status = 3
                import_id.write({'status': str(status)})
            import_ids.recompute_update_state()

    @api.multi
    def recompute_update_state(self):
        for rec in self:
            if rec.data_type in ['0']:
                rec.shop_ids._need_to_update()
            if rec.data_type in ['1']:
                rec.partner_ids._need_to_update()
            if rec.data_type in ['2']:
                rec.category_ids._need_to_update()
            if rec.data_type in ['3']:
                rec.product_ids._need_to_update()
            if rec.data_type in ['4']:
                rec.prices_ids._need_to_update()
            if rec.data_type in ['5']:
                rec.discount_ids._need_to_update()
            if rec.data_type in ['6']:
                rec.group_discount_ids._need_to_update()

    @api.model
    def cron_full_sync(self):
        product_ids = self.env['product.template'].search([('imported_ids', '!=', False)])
        product_ids.with_context(full_sync=True, force=True).import_products()

    @api.model
    def full_sync_products(self):
        product_ids = self.env['product.template'].search([('imported_ids', '!=', False), ('active', '=', True)])
        product_ids.with_context(full_sync=True, force=True, skip_children=True).import_products()


SyncDataImport()
