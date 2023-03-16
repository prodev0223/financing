# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DKNutraukimoStraipsniai(models.Model):
    _name = 'dk.nutraukimo.straipsniai'

    _order = 'sequence desc, straipsnis, dalis, punktas'

    straipsnis = fields.Char(string='Straipsnis')
    dalis = fields.Char(string='Dalis')
    punktas = fields.Char(string='Punktas')
    straipsnio_pav = fields.Text(string='Straipsnio pavadinimas')
    detalizavimas = fields.Text(string='Detalizavimas')
    sequence = fields.Integer(string='Sequence')
    active = fields.Boolean(string='Active', default=True)
    request = fields.Boolean(string='Įtraukti į prašymą')
    text_in_document = fields.Text(string='Text in document', compute='_text_in_document', store=True)

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            rec_name = rec.straipsnio_pav + '(%s str.)' % (rec.straipsnis or '')
            if rec.dalis:
                rec_name += ' %s dalis' % rec.dalis
            if rec.punktas:
                rec_name += ' %s pnkt.' % rec.punktas
            res.append((rec.id, rec_name))
        return res

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        if name:
            ids = self.search(
                ['|', '|', '|', ('straipsnio_pav', operator, name), ('straipsnis', operator, name),
                 ('dalis', operator, name), ('punktas', operator, name)] + args,
                limit=limit)
        else:
            ids = self.search(args, limit=limit)
        return ids.name_get()

    @api.one
    @api.depends('straipsnis', 'dalis', 'punktas')
    def _text_in_document(self):
        text_in_document = 'LR DK %s str.' % self.straipsnis
        if self.dalis:
            text_in_document += ' %s d.' % self.dalis
            if self.punktas:
                text_in_document += ' %s p.' % self.punktas
        # text_in_document += ' (%s)' % (self.straipsnio_pav or '').lower()
        self.text_in_document = text_in_document


DKNutraukimoStraipsniai()
