# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import models, api, fields, _, tools
from six import iterkeys


class StockProductionLot(models.Model):
    _inherit = 'stock.production.lot'

    @api.multi
    def _post_manual_create(self):
        for rec in self:
            expiry_dates = rec._get_dates()
            rec.write(expiry_dates)
        return

    @api.multi
    def _update_expiry_dates(self, overwrite=False):
        for rec in self:
            expiry_dates = rec._get_dates()
            if not overwrite:
                keys_to_remove = []
                for key in iterkeys(expiry_dates):
                    if rec[key]:
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    expiry_dates.pop(key, None)
            rec.write(expiry_dates)
        return


StockProductionLot()


class StockPackOpExt(models.Model):
    _inherit = 'stock.pack.operation'

    removal_date = fields.Datetime(string='Produkto galiojimo data', groups='stock.group_production_lot')
    use_removal_date = fields.Boolean(string='Naudoti produkto galiojimo datą')

    @api.onchange('barcode')
    def onchange_barcode(self):
        if (self.barcode and not self.use_removal_date) or (self.barcode and self.use_removal_date and self.removal_date):
            self.on_barcode_scanned(self.barcode)
            self.barcode = ''

    def create_lot(self, barcode):
        cdate = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        if self.use_removal_date:
            self.sudo()._cr.execute(
                u'''INSERT INTO stock_production_lot (create_date, write_date, create_uid, write_uid, name, product_id, removal_date) VALUES ('%s', '%s', %s, %s, '%s', %s, '%s')''' %
                (cdate, cdate, self._uid, self._uid, barcode, self.product_id.id, self.removal_date))
        else:
            self.sudo()._cr.execute(
                u'''INSERT INTO stock_production_lot (create_date, write_date, create_uid, write_uid, name, product_id) VALUES ('%s', '%s', %s, %s, '%s', %s)''' %
                (cdate, cdate, self._uid, self._uid, barcode, self.product_id.id))

        new_serial = self.env['stock.production.lot'].search([('name', '=', barcode),
                                                              ('product_id', '=', self.product_id.id)
                                                              ], limit=1)
        vals = {'lot_id': new_serial.id,
                'qty_todo': 1,
                'qty': 1,
                'lot_name': new_serial.name,
                'removal_date': self.removal_date}

        self.pack_lot_ids |= self.pack_lot_ids.new(vals)
        self.scan_status_text = _('Naujas SN <%s> pridėtas.') % new_serial.name
        self.scan_status = 2

    @api.multi
    def save(self):
        for rec in self:
            for lot in rec.pack_lot_ids:
                if lot.lot_name:
                    lot.lot_id.write({'removal_date': lot.removal_date, 'name': lot.lot_name})
        return super(StockPackOpExt, self).save()


StockPackOpExt()


class PackOperationLot(models.Model):
    _inherit = 'stock.pack.operation.lot'

    removal_date = fields.Datetime(string='Produkto galiojimo data', groups='stock.group_production_lot')


PackOperationLot()


