# -*- coding: utf-8 -*-
from odoo import fields, models, api


class ResCompany(models.Model):
    
    _inherit = 'res.company'

    def _get_default_revaluation_gain_account_id(self):
        acc = self.env['account.account'].search([('code', '=', '5803')], limit=1)
        return acc.id if acc else False

    def _get_default_revaluation_loss_account_id(self):
        acc = self.env['account.account'].search([('code', '=', '6803')], limit=1)
        return acc.id if acc else False

    revaluation_loss_account_id = fields.Many2one('account.account', 'Revaluation loss account',
                                                  domain=[('internal_type', '=', 'other')],
                                                  default=_get_default_revaluation_loss_account_id)
    revaluation_gain_account_id = fields.Many2one('account.account', 'Revaluation gain account',
                                                  domain=[('internal_type', '=', 'other')],
                                                  default=_get_default_revaluation_gain_account_id)
    revaluation_analytic_account_id = fields.Many2one('account.analytic.account', 'Revaluation Analytic account')
    provision_bs_loss_account_id = fields.Many2one('account.account', 'Provision B.S loss account',
                                                   domain=[('internal_type', '=', 'other')])
    provision_bs_gain_account_id = fields.Many2one('account.account', 'Provision B.S gain account',
                                                   domain=[('internal_type', '=', 'other')])
    provision_pl_loss_account_id = fields.Many2one('account.account', 'Provision P&L loss account',
                                                   domain=[('internal_type', '=', 'other')])
    provision_pl_gain_account_id = fields.Many2one('account.account', 'Provision P&L gain account',
                                                   domain=[('internal_type', '=', 'other')])
    default_currency_reval_journal_id = fields.Many2one('account.journal', 'Currency gain & loss Default Journal',
                                                        domain=[('type', '=', 'general')],
                                                        related='currency_exchange_journal_id', store=True)
    reversable_revaluations = fields.Boolean('Reversable Revaluations', help="Revaluations entries will be created"
                                                                             " as \"To Be Reversed\".", default=True)

ResCompany()


class AccountConfigSetings(models.TransientModel):

    _inherit = 'account.config.settings'

    revaluation_loss_account_id = fields.Many2one('account.account', 'Revaluation loss account',
                                                  related='company_id.revaluation_loss_account_id',
                                                  domain=[('internal_type', '=', 'other')])
    revaluation_gain_account_id = fields.Many2one('account.account', 'Revaluation gain account',
                                                  related='company_id.revaluation_gain_account_id',
                                                  domain=[('internal_type', '=', 'other')])
    revaluation_analytic_account_id = fields.Many2one('account.analytic.account', 'Revaluation Analytic account',
                                                      related='company_id.revaluation_analytic_account_id')
    provision_bs_loss_account_id = fields.Many2one('account.account', 'Provision B.S loss account',
                                                   related='company_id.provision_bs_loss_account_id',
                                                   domain=[('internal_type', '=', 'other')])
    provision_bs_gain_account_id = fields.Many2one('account.account', 'Provision B.S gain account',
                                                   related='company_id.provision_bs_gain_account_id',
                                                   domain=[('internal_type', '=', 'other')])
    provision_pl_loss_account_id = fields.Many2one('account.account', 'Provision P&L loss account',
                                                   related='company_id.provision_pl_loss_account_id',
                                                   domain=[('internal_type', '=', 'other')])
    provision_pl_gain_account_id = fields.Many2one('account.account', 'Provision P&L gain account',
                                                   related='company_id.provision_pl_gain_account_id',
                                                   domain=[('internal_type', '=', 'other')])
    default_currency_reval_journal_id = fields.Many2one('account.journal', 'Currency gain & loss Default Journal',
                                                        related='company_id.default_currency_reval_journal_id',
                                                        domain=[('type', '=', 'general')])
    reversable_revaluations = fields.Boolean('Reversable Revaluations', related='company_id.reversable_revaluations',
                                             help="Revaluations entries will be created as \"To Be Reversed\".",
                                             default=True)
