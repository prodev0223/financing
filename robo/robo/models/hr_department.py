# -*- coding: utf-8 -*-


from odoo import _, fields, models, api


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    default_cash_journal_id = fields.Many2one(
        'account.journal', string=_('Numatytasis grynųjų operacijų žurnalas'),
        domain=[('type', '=', 'cash')], groups='robo_basic.group_robo_premium_manager'
    )
    name = fields.Char(track_visibility='onchange')
    prime_cost = fields.Boolean(string='Prime cost', compute='_compute_prime_cost', inverse='_set_prime_cost',
                                store=True)

    @api.model
    def get_cost_account(self):
        return self.env['account.account'].search([('code', '=', '6001')], limit=1)

    @api.model
    def has_access_for_prime_cost(self):
        return self.env.user.is_premium_manager() or not self.env.user.is_hr_manager()

    @api.multi
    @api.depends('saskaita_debetas')
    def _compute_prime_cost(self):
        account = self.get_cost_account()
        can_compute_prime_cost = self.has_access_for_prime_cost()
        for rec in self:
            rec.prime_cost = rec.sudo().saskaita_debetas == account if can_compute_prime_cost else False

    @api.multi
    def _set_prime_cost(self):
        account = self.get_cost_account()
        if not self.has_access_for_prime_cost():
            return
        for rec in self.sudo():
            rec.saskaita_debetas = account if rec.prime_cost else False
