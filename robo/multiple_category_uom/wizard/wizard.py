# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, exceptions
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
from lxml import etree, objectify
from xml.dom.minidom import parse, parseString
from lxml.etree import XMLSyntaxError
from odoo.tools.translate import _
from datetime import datetime
import calendar
import os


class StockPickingExportWizard(models.TransientModel):
    _inherit = 'stock.picking.export.wizard'

    def set_product_info(self, products, pick):
        '''products: Etree element'''
        for idx, pick_line in enumerate(pick.move_lines):
            product = SubElement(products, 'Product')
            SubElement(product, 'ProductLineNumber')
            product[0].text = str(idx + 1)

            if pick_line.secondary_uom_id:
                qty = pick_line.secondary_uom_qty
                uom_name = pick_line.secondary_uom_id.name
            else:
                qty = pick_line.product_uom_qty
                uom_name = pick_line.product_uom.name

            SubElement(product, 'Quantity')
            product[1].text = "%.2f" % qty

            SubElement(product, 'UnitOfMeasure')
            product[2].text = uom_name
            SubElement(product, 'ProductCode')
            if not pick_line.product_id.default_code:
                raise exceptions.Warning(_('Produktas %s neturi kodo') % pick_line.product_id.name)
            product[3].text = pick_line.product_id.default_code

            SubElement(product, 'ProductDescription')
            product[4].text = pick_line.product_id.name


StockPickingExportWizard()
