# -*- coding: utf-8 -*-

from odoo import models, fields, exceptions, _, api


class ScoroTax(models.Model):
    _name = 'scoro.tax'

    vat_name = fields.Char(string='PVM pavadinimas')
    vat_code = fields.Char(string='PVM kodas')
    vat_code_id = fields.Integer(string='PVM kodo ID')
    vat_percent = fields.Float(string='Procentas', inverse='_vat_percent')
    tax_id = fields.Many2one('account.tax', string='Susijęs mokestis')
    vat_type = fields.Selection([('sale', 'Pardavimai'), ('purchase', 'Pirkimai')],
                                string='Mokesčio tipas', requred=True)
    force_eu_partners = fields.Boolean(compute='_compute_force_eu_partners')

    @api.multi
    @api.depends('tax_id')
    def _compute_force_eu_partners(self):
        """
        If tax_id.code is PVM15, force this tax to scoro invoices if partner is from EU/ES
        :return: None
        """
        for rec in self:
            rec.force_eu_partners = True if rec.tax_id and rec.tax_id.code in ['PVM15'] else False

    @api.multi
    def write(self, vals):
        if 'tax_id' not in vals or ('tax_id' in vals and len(vals) > 1):
            if not self.env.user.has_group('base.group_system'):
                raise exceptions.Warning(_('Tik administratorius gali koreguoti mokesčius'))
        return super(ScoroTax, self).write(vals)

    @api.one
    def _vat_percent(self):
        self.tax_id = self.env['account.tax'].search([('amount', '=', self.vat_percent),
                                                      ('type_tax_use', '=', self.vat_type),
                                                      ('price_include', '=', False)], limit=1).id

    @api.multi
    def recompute_taxes(self):
        self.env['scoro.invoice.line'].search([]).recompute_taxes()

    @api.multi
    def name_get(self):
        return [(rec.id, rec.tax_id.code if rec.tax_id else _('Mokesčiai')) for rec in self]



ScoroTax()
