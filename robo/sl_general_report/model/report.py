# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class FinancialReport(models.Model):

    _inherit = 'account.financial.report'

    code = fields.Char(string='Kodas', translate=True)
    excluded_account_ids = fields.Many2many('account.account', string='Praleidžiamos sąskaitos')
    template_row = fields.Integer(string='Šablono eilutė')
    template_col = fields.Integer(string='Šablono stulpelis')
    label = fields.Boolean(string='Antraštė', default=False)
    report_type = fields.Char(string='Tipas')
    activity_form = fields.Selection([('uab', 'Uždaroji akcinė bendrovė'),
                                      ('mb', 'Mažoji bendrija'),
                                      ('vsi', 'Viešoji įstaiga')],
                                     string='Veiklos forma', readonly=True)
    formula = fields.Char(string='Excel formulė')
    formula_prev = fields.Char(string='Praėjusio laikotarpio Excel formulė')

    ultimate_parent_id = fields.Many2one(
        'account.financial.report', string='Ataskaita', compute='_compute_ultimate_parent_id', store=True)

    # Fields used only on balance reports
    balance_line_side = fields.Selection([('upper', 'Viršutinė'),
                                          ('lower', 'Apatinė')],
                                         string='Eilutės pozicija balanso ataskaitoje')
    balance_leveling_line = fields.Boolean(string='Išlyginamoji balanso eilutė')

    @api.multi
    @api.constrains('balance_line_side')
    def _check_balance_line_side(self):
        """
        Constraints //
        If report type is BL, line side should be specified
        :return: None
        """
        failed_lines = self.filtered(lambda x: x.report_type == 'BL' and not x.balance_line_side)
        if failed_lines:
            error_message = _(
                'Balanso eilutės privalo turėti pažymėtą poziciją. Nerasta pozicija šioms eilutėms: \n {}').format(
                '\n'.join(failed_lines.mapped('name')))
            raise exceptions.ValidationError(error_message)

    @api.multi
    @api.constrains('balance_leveling_line')
    def _check_balance_leveling_line(self):
        """
        Constraints //
        Only one leveling line per ultimate parent must be present
        :return: None
        """
        for rec in self.filtered(lambda x: x.balance_leveling_line):
            # Leveling line can not have a formula
            if rec.formula or rec.formula_prev:
                raise exceptions.ValidationError(_('Išlyginamoji eilutė negali būti suminė'))

            # Check whether the leveling line already exists on the same report and on the same side
            duplicate = self.env['account.financial.report'].search(
                    [('id', '!=', rec.id),
                     ('balance_line_side', '=', rec.balance_line_side),
                     ('ultimate_parent_id', '=', rec.ultimate_parent_id.id),
                     ('balance_leveling_line', '=', rec.balance_leveling_line)], limit=1)
            if duplicate:
                raise exceptions.ValidationError(_('Ši ataskaita jau turi išlyginamąją eilutę - %s') % duplicate.name)

    @api.multi
    @api.depends('parent_id')
    def _compute_ultimate_parent_id(self):
        """
        Compute //
        Compute ultimate parent ID for the report
        :return: None
        """
        for rec in self:
            parent = rec
            while parent.parent_id:
                parent = parent.parent_id
            rec.ultimate_parent_id = parent

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, '{}: {}'.format(rec.name, (rec.activity_form or str()).upper())) for rec in self]
