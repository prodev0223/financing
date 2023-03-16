# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class RKeeperSaleLineModifier(models.Model):
    _name = 'r.keeper.sale.line.modifier'
    _description = '''
    Model that stores rKeeper sale modifier records,
    they are used for customized sale BOMs.
    '''

    doc_date = fields.Date(string='Dokumento data')
    doc_number = fields.Char(string='Dokumento numeris', inverse='_set_related_sale_line')
    product_code = fields.Char(string='Modifikuojamo produkto kodas', inverse='_set_related_sale_line')
    modifier_code = fields.Char(string='Modifikatoriaus kodas')
    pos_code = fields.Char(string='Kasos aparato kodas')

    modified_quantity = fields.Float(string='Modifikuojamas kiekis')
    r_keeper_modifier_id = fields.Many2one('r.keeper.modifier', string='Modifikatorius')
    r_keeper_sale_line_id = fields.Many2one('r.keeper.sale.line', string='Pardavimo eilutė')

    @api.multi
    def _set_related_sale_line(self):
        """Get related sale based on doc number and product code"""
        for rec in self:
            if rec.doc_number and rec.product_code:
                sale_line = self.env['r.keeper.sale.line'].search(
                    [('doc_number', '=', rec.doc_number),
                     ('product_code', '=', rec.product_code),
                     ('pos_code', '=', rec.pos_code)]
                )
                if len(sale_line) != 1:
                    raise exceptions.ValidationError(
                        _('Duomenų faile nerastas susijęs produktas. Modifikatoriaus kodas - {}. '
                          'Produkto kodas - {}').format(rec.modifier_code, rec.product_code)
                    )
                rec.r_keeper_sale_line_id = sale_line
