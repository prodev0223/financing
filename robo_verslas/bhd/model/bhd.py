# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, exceptions, tools
from odoo.tools.misc import xlwt
import xlrd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import base64
import StringIO
import logging
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    margin = fields.Float(string='Antkainis (%)', readonly=True, states={'draft': [('readonly', False)]})

    @api.multi
    def add_margin(self):
        self.ensure_one()
        margin = self.margin
        for line in self.order_line:
            line.with_context(triggered_field='price_unit')._onchange_human()
            line.set_price_margin(margin)

    @api.multi
    def action_invoice_create(self, grouped=False, final=False):
        invoice_ids = super(SaleOrder, self).action_invoice_create(grouped=grouped, final=final)
        for invoice in self.env['account.invoice'].browse(invoice_ids):
            margins = invoice.mapped('sale_ids.margin')
            if margins:
                invoice.write({'margin': margins[0]})
        return invoice_ids

    @api.multi
    def action_product_list_export_excel(self):
        self.ensure_one()
        self._cr.execute('''SELECT prod.default_code AS code, SUM(product_uom_qty) AS qty 
                            FROM sale_order_line line
                            LEFT JOIN product_product prod ON prod.id = line.product_id
                            WHERE line.order_id = %s
                            GROUP BY prod.id''', (self.id,))
        data = self._cr.fetchall()

        if not data:
            raise exceptions.UserError(_('Nėra užsakymo eilučių, kurias būtų galima eksportuoti'))

        workbook = xlwt.Workbook(encoding='utf-8')
        worksheet = workbook.add_sheet(_('Produktų sąrašas'))

        row = 0
        for code, qty in data:
            worksheet.write(row, 0, code)
            worksheet.write(row, 1, qty)
            row += 1

        f = StringIO.StringIO()
        workbook.save(f)
        base64_file = f.getvalue().encode('base64')

        filename = '%s produktų sąrašas.xls' % self.name or ''
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'sale.order',
            'res_id': self.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=sale.order&res_id=%s&attach_id=%s' % (self.id, attach_id.id),
            'target': 'self',
        }


SaleOrder()


#antkainis, marža
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.multi
    def get_price_with_margin(self, margin=0.0):
        self.ensure_one()
        move_ids = self.mapped('procurement_ids.move_ids')
        if not move_ids or len(move_ids) == len(move_ids.filtered(lambda r: r.state == 'cancel')) or move_ids.filtered(lambda r: r.state not in ['assigned', 'done', 'cancel']):
            raise exceptions.UserError(_('Ne visi susiję važtaraščiai yra rezervuoti/perduoti. Pirmiau rezervuokite ir tik tuomet bus galima pridėti antkainį.'))
        all_quants = self.env['stock.quant']
        quant_ids = move_ids.mapped('quant_ids')
        reserved_quant_ids = move_ids.mapped('reserved_quant_ids')
        all_quants |= quant_ids
        all_quants |= reserved_quant_ids
        if not all_quants:
            raise exceptions.UserError(_('%s produktas neturi atsargų') % (self.product_id.name))
        all_cost = sum(all_quants.mapped(lambda r: r.qty*r.cost))
        all_qty = sum(all_quants.mapped('qty'))
        average_cost = all_cost / all_qty
        price = average_cost * (1.0 + margin / 100.0)
        return price

    @api.multi
    def set_price_margin(self, margin=0.0):
        self.ensure_one()
        if self.product_uom_qty:
            self.price_unit = self.get_price_with_margin(margin)


SaleOrderLine()


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    code = fields.Char('Trumpinis', required=True, size=20, help="")


StockWarehouse()


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    show_force_incoming = fields.Boolean(compute='_show_force_incoming')

    @api.one
    @api.depends('location_id')
    def _show_force_incoming(self):
        if self.location_id.usage == 'supplier':
            self.show_force_incoming = True
        else:
            self.show_force_incoming = False

    @api.multi
    def force_incoming_shipping(self):
        """
        Prepares forcing of picking do_transfer action without tracking SN.
        On exception, try again without unlinking pack_operation_ids
        :return: None
        """
        self.ensure_one()
        try:
            self.force_incoming_shipping_exec()
        except Exception as exc:
            self.env.cr.rollback()
            _logger.info('BHD: Force incoming shipping exception %s' % exc.args[0] if exc.args else str())
            self.force_incoming_shipping_exec(unlink_packs=False)

    @api.multi
    def force_incoming_shipping_exec(self, unlink_packs=True):
        """
        Forces picking do_transfer action without tracking SN.
        :param unlink_packs: indicates whether pack_operation_ids
                should be unlinked before transferring (bool)
        :return: None
        """
        product_tracking = {}
        for pick in self:
            if unlink_packs:
                pick.pack_operation_ids.unlink()
            for line in pick.move_lines:
                if line.product_id.tracking != 'none':
                    product_tracking[line.product_id.id] = line.product_id.tracking
                    line.product_id.write({'tracking': 'none'})
            pick.do_transfer()
        for product in self.env['product.product'].browse(product_tracking.keys()):
            product.write({'tracking': product_tracking[product.id]})

    def open_lot_import_wizard(self):
        self.ensure_one()
        return {
            'name': _("Importuoti SN"),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.picking.lot.import.wizard',
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': {'picking_id': self.id}
        }


StockPicking()


class StockPickingImportWizard(models.TransientModel):

    _name = 'stock.picking.lot.import.wizard'

    def default_picking_id(self):
        return self._context.get('picking_id')

    picking_id = fields.Many2one('stock.picking', required=True, string='Važtaraštis', default=default_picking_id)
    data = fields.Binary(string='SN failas', required=True)

    @api.multi
    def scan_serials(self):
        serials = []
        try:
            book = xlrd.open_workbook(file_contents=self.data.decode('base64'))
            sheet = book.sheet_by_index(0)
            row = 0
            lot_col = 0
            barcode_col = 0
            for r in xrange(sheet.nrows):
                cell = sheet.cell_value(r, 0)
                if cell == u'SKU':
                    row = r
                    break
            for c in xrange(sheet.ncols):
                cell = sheet.cell_value(row + 1, c)
                if cell and u'Lot' in cell or u'Partij' in cell:
                    lot_col = c
                    break
            for c in xrange(sheet.ncols):
                cell = sheet.cell_value(row, c)
                if cell and u'SKU' == cell:
                    barcode_col = c
                    break
            for r in xrange(row + 1, sheet.nrows):
                cell = sheet.cell_value(r, barcode_col)
                if cell:
                    barcode = cell
                else:
                    barcode = False
                cell = sheet.cell_value(r - 1, lot_col)
                if cell:
                    lot = cell
                else:
                    lot = False
                if barcode and lot:
                    serials.append((barcode, lot))
        except:
            raise exceptions.UserError(_('Nurodytas netinkamas failo formatas'))
        product_obj = self.env['product.product']
        picking_id = self.picking_id
        # picking_id.pack_operation_product_ids.mapped('pack_lot_ids').unlink()
        for barcode, lot in serials:
            product_id = product_obj.search(['|', ('default_code', '=', barcode), ('barcode', '=', barcode)])
            if len(product_id) > 1:
                raise exceptions.Warning(_('Rasti keli produktai tuo pačiu kodu %s.') % barcode)
            if product_id and lot:
                if picking_id.pack_operation_product_ids.filtered(lambda r: r.product_id.id == product_id.id):
                    line = picking_id.pack_operation_product_ids.filtered(lambda r: r.product_id.id == product_id.id)[0]
                    line.on_barcode_scanned(lot)
                    if line.scan_status not in [1, 2]:
                        raise exceptions.UserError(
                            _('Nepavyko priskirti SN (%s):\n%s') % (lot, line.scan_status_text))
                    line.qty_done += 1


StockPickingImportWizard()


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    mistake_type = fields.Selection(selection_add=[('force_cancel', 'Atšaukti (be SN)')])

    @api.multi
    def _create_returns(self):
        if self.mistake_type == 'force_cancel':
            product_tracking = {}
            picking = self.env['stock.picking'].browse(self.env.context.get('active_id'))
            for stock_move in picking.move_lines.filtered(lambda m: m.has_tracking != 'none'):
                product_tracking[stock_move.product_id.id] = stock_move.product_id.tracking
                stock_move.product_id.write({
                    'tracking': 'none'
                })

            res = super(StockReturnPicking, self)._create_returns()

            for k, v in product_tracking.items():
                self.env['product.product'].browse(k).write({'tracking': v})

            return res

        return super(StockReturnPicking, self)._create_returns()


StockReturnPicking()


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    @api.multi
    def produce_simplified_force(self):
        self.ensure_one()
        old_settings = {}
        for move in self.move_raw_ids.filtered(lambda x: x.product_id.tracking != 'none' and x.state not in ('done', 'cancel')):
            rounding = move.product_uom.rounding
            if tools.float_compare(move.quantity_done, move.product_uom_qty, precision_rounding=rounding) != 0:
                old_settings[move.product_id.id] = move.product_id.tracking
                move.product_id.write({'tracking': 'none'})
        for move in self.move_finished_ids.filtered(lambda x: x.product_id.tracking != 'none' and x.state not in ('done', 'cancel')):
            rounding = move.product_uom.rounding
            if tools.float_compare(move.quantity_done, move.product_uom_qty, precision_rounding=rounding) != 0:
                old_settings[move.product_id.id] = move.product_id.tracking
                move.product_id.write({'tracking': 'none'})
        self.produce_simplified()
        for k, v in old_settings.items():
            self.env['product.product'].browse(k).write({'tracking': v})


MrpProduction()


class MrpUnbuid(models.Model):
    _inherit = 'mrp.unbuild'

    @api.multi
    def action_unbuild(self):
        self.ensure_one()
        product_tracking = {}
        for produce_move in self.produce_line_ids:
            if produce_move.has_tracking != 'none':
                product_tracking[produce_move.product_id.id] = produce_move.product_id.tracking
                produce_move.product_id.write({
                    'tracking': 'none'
                })
        for consume_move in self.consume_line_ids:
            if consume_move.has_tracking != 'none':
                product_tracking[consume_move.product_id.id] = consume_move.product_id.tracking
                consume_move.product_id.write({
                    'tracking': 'none'
                })
        super(MrpUnbuid, self).action_unbuild()
        for k, v in product_tracking.items():
            self.env['product.product'].browse(k).write({'tracking': v})

    @api.multi
    def reserve_force(self):
        self.ensure_one()
        product_tracking = {}
        if self.produce_line_ids:
            for produce_move in self.produce_line_ids:
                if produce_move.has_tracking != 'none':
                    product_tracking[produce_move.product_id.id] = produce_move.product_id.tracking
                    produce_move.product_id.write({
                        'tracking': 'none'
                    })
        elif self.product_id.tracking != 'none':
            product_tracking[self.product_id.id] = self.product_id.tracking
            self.product_id.write({
                'tracking': 'none'
            })
        self.reserve()
        for k, v in product_tracking.items():
            self.env['product.product'].browse(k).write({'tracking': v})


MrpUnbuid()


class EpsonReport(models.TransientModel):
    _name = 'epson.report'

    def default_date_from(self):
        date = datetime.utcnow()
        return datetime(date.year, date.month, 1).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def default_date_to(self):
        return (datetime.utcnow() + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    date_from = fields.Date(string='Nuo', required=True, default=default_date_from)
    date_to = fields.Date(string='Iki', required=True, default=default_date_to)

    @api.multi
    def generate(self):

        class Tabula:

            def __init__(self):
                self.result = u''

            def add_col(self, el, add_tab=True):
                self.result += unicode(el)
                if add_tab:
                    self.result += u'\t'

            def end_line(self):
                self.result += u'\n'

            def give_result(self):
                return self.result

        self.ensure_one()

        def c_strip(string):
            s_strip = string or str()
            return s_strip.strip().replace(' ', '')

        res = Tabula()
        if self.date_from > self.date_to:
            raise exceptions.UserError(_('Neteisingos datos.'))
        domain = [('state', 'in', ['open', 'paid']), ('type', '=', 'out_invoice'),
                  ('date', '>=', self.date_from), ('date', '<=', self.date_to),
                  '|', '|', '|', '|',
                  ('product_id.default_code', '=like', 'C13%'),
                  ('product_id.default_code', '=like', 'C31%'),
                  ('product_id.default_code', '=like', 'C32%'),
                  ('product_id.default_code', '=like', 'C33%'),
                  ('product_id.default_code', '=like', 'C43%')]
        fields = ['product_id', 'partner_id', 'product_qty', 'price_total']
        groupby = ['partner_id', 'product_id']
        data = self.env['account.invoice.report'].read_group(domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=False)
        product_obj = self.env['product.product']
        partner_obj = self.env['res.partner']
        if not data:
            return False
        for line in data:
            product_id = line['product_id'][0]
            partner_id = line['partner_id'][0]
            product_qty = int(round(line['product_qty']))
            price_total = line['price_total']
            partner = partner_obj.browse(partner_id)
            product = product_obj.browse(product_id)

            country_code = partner.country_id and partner.country_id.code or 'LT'
            res.add_col('0000208328')
            res.add_col(datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT).strftime('%d/%m/%y'))
            res.add_col('F')
            res.add_col(country_code)
            vat_code = c_strip(partner.vat)
            res.add_col(vat_code)
            partner_code = c_strip(partner.kodas)
            res.add_col(partner_code)

            # Check if partner name is no longer than 40 symbols
            partner_name = line['partner_id'][1]
            if len(partner_name) > 40:
                # Format it like this so the string cut looks nicer
                partner_name = '{}...'.format(partner_name[:37])
            res.add_col(partner_name)

            res.add_col(c_strip(product.default_code))
            res.add_col(product_qty)
            res.add_col('%0.2f' % price_total)
            res.add_col('EUR')
            res.add_col('NIV', add_tab=False)
            res.end_line()

        result = res.give_result()
        base64_file = base64.b64encode(result)
        filename = 'epson-%s.txt' % datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        company_id = self.env.user.sudo().company_id.id
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'res.company',
            'res_id': company_id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=res.company&res_id=%s&attach_id=%s' % (company_id, attach_id.id),
            'target': 'self',
        }


EpsonReport()
