# -*- coding: utf-8 -*-

from odoo import models, api, tools, exceptions, _
import base64
from lxml import etree
from dateutil.parser import parse
from ... import amazon_tools as at

"""
!! IMPORTANT -- File is unfinished and code will not be used at the moment
"""


class AmazonXMLParsers(models.AbstractModel):
    """
    Abstract model that contains Amazon XML parsers.
    Passed XML is parsed and data is prepared
    for corresponding object creation
    """
    _name = 'amazon.xml.parsers'

    @api.model
    def get_value(self, node, element, expected_type=None):
        """
        Fetch value from the node using passed xpath_string.
        :param node: parent node that is being searched
        :param element: xpath string
        :param expected_type: test
        :return: node text or None
        """
        element_value = 0.0 if expected_type is float else str()
        if node:
            found_node = node.find(element)
            try:
                element_value = found_node.text
                if expected_type is float:
                    element_value = float(element_value)
            except (ValueError, AttributeError):
                pass
        return element_value

    @api.model
    def parse_date(self, date_str):
        parsed_date = str()
        if isinstance(date_str, basestring):
            parsed_date = parse(date_str).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return parsed_date

    @api.model
    def parse_orders_xml(self, xml_base64):
        """
        Parse Amazon orders XML file and arrange data in a structure
        that is ready to-be-passed to corresponding object creation
        :param xml_base64: Amazon XML base64 (str)
        :return: List of amazon.order value dicts ([{}, {}])
        """
        def add_spec_line(line_name, line_type, line_total, line_tax=0.0):
            """Inner method to add special order lines"""
            line_vals = {
                'ext_line_name': line_name,
                'amount_tax': line_tax,
                'line_amount': line_total,
                'line_type': line_type,
            }
            order_lines_inner.append((0, 0, line_vals))

        data = base64.b64decode(xml_base64)
        try:
            root = etree.fromstring(data, parser=etree.XMLParser(recover=True))
        except etree.XMLSyntaxError:
            raise exceptions.ValidationError(_('Netinkamas failo formatas.'))

        if type(root) != etree._Element:
            raise exceptions.ValidationError(_('Netinkamas failo formatas.'))

        order_list = []
        base_root = root.find('.//Message//SettlementReport')

        total_order_nodes = [(x, False) for x in base_root.findall('Order')]
        total_order_nodes += [(x, True) for x in base_root.findall('Refund')]

        total_xml_amount = self.get_value(base_root.find('SettlementData'), 'TotalAmount', float)
        total_calculated_amount = 0.0

        for order_node, is_refund in total_order_nodes:
            of_node = order_node.find('Fulfillment')
            order_id = self.get_value(order_node, 'AmazonOrderID')

            order_lines = []
            order_values = {
                'order_id': order_id,
                'merchant_order_id': self.get_value(order_node, 'MerchantOrderID'),
                'shipment_id': self.get_value(order_node, 'ShipmentID'),
                'marketplace_name': self.get_value(order_node, 'MarketplaceName'),
                'fulfillment_code':  self.get_value(of_node, 'MerchantFulfillmentID'),
                'order_time': self.parse_date(self.get_value(of_node, 'PostedDate')),
                'amazon_order_line_ids': order_lines
            }
            item_nodes = of_node.findall('AdjustedItem' if is_refund else 'Item')
            for item_node in item_nodes:
                order_lines_inner = []
                price_node = item_node.find('ItemPriceAdjustments' if is_refund else 'ItemPrice')
                price_component_nodes = price_node.findall('Component')

                base_values = {
                    at.MAIN_COMPONENT_NAME: 0.0,
                    at.MAIN_COMPONENT_TAX_NAME: 0.0,
                    at.SHIPPING_COMPONENT_NAME: 0.0,
                    at.SHIPPING_COMPONENT_TAX_NAME: 0.0
                }
                for price_component_node in price_component_nodes:
                    component_type = self.get_value(price_component_node, 'Type')
                    if component_type not in at.PRICE_COMPONENTS:
                        raise exceptions.ValidationError(
                            _('Unidentified price component - {}. Order ID - {}').format(component_type, order_id))
                    base_values[component_type] += self.get_value(price_component_node, 'Amount', float)

                if not tools.float_is_zero(base_values[at.MAIN_COMPONENT_NAME], precision_digits=2):
                    vals = {
                        'ext_line_name': at.MAIN_COMPONENT_NAME,
                        'ext_product_code': self.get_value(item_node, 'AmazonOrderItemCode'),
                        'sku_product_code': self.get_value(item_node, 'SKU'),
                        'quantity': self.get_value(item_node, 'Quantity'),
                        'amount_tax': base_values[at.MAIN_COMPONENT_TAX_NAME],
                        'line_amount': base_values[at.MAIN_COMPONENT_NAME],
                        'line_type': 'principal',
                    }
                    order_lines_inner.append((0, 0, vals))

                if not tools.float_is_zero(base_values[at.SHIPPING_COMPONENT_NAME], precision_digits=2):
                    add_spec_line(
                        at.SHIPPING_COMPONENT_NAME, 'shipping',
                        base_values[at.SHIPPING_COMPONENT_NAME],
                        base_values[at.SHIPPING_COMPONENT_TAX_NAME])

                item_fees_node = item_node.find('ItemFeeAdjustments' if is_refund else 'ItemFees')
                fee_nodes = item_fees_node.findall('Fee')
                for fee_node in fee_nodes:
                    amount = self.get_value(fee_node, 'Amount', float)
                    add_spec_line(self.get_value(fee_node, 'Type'), 'fees', amount)
                    total_calculated_amount += amount

                promotion_nodes = item_node.findall('PromotionAdjustment' if is_refund else 'Promotion')
                for promotion_node in promotion_nodes:
                    amount = self.get_value(promotion_node, 'Amount', float)
                    add_spec_line(self.get_value(promotion_node, 'MerchantPromotionID'), 'promotion', amount)
                    total_calculated_amount += amount

                total_calculated_amount += base_values[at.MAIN_COMPONENT_NAME]
                order_lines += order_lines_inner
            order_list.append(order_values)

        return order_list


AmazonXMLParsers()
