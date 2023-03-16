# -*- coding: utf-8 -*-
from odoo import models, fields, _, tools, api, exceptions
from datetime import datetime


class AccountAssetAsset(models.Model):
    _inherit = 'account.asset.asset'

    likvidacine_verte = fields.Float(compute='_likvidacine_verte')
    likvidavimo_data = fields.Char(string='Likvidavimo data', compute='_change_likvidavimo_data') #used to be stored

    ivedimas_id = fields.Many2one('eksploatacijos.aktas', default=False, string='Įvedimo į eksploataciją aktas')
    isvedimas_id = fields.Many2one('eksploatacijos.aktas', default=False, string='Išvedimo iš eksploatacijos aktas')
    show_ivedimas = fields.Boolean(compute='_show_ivedimas')
    show_isvedimas = fields.Boolean(compute='_show_isvedimas')

    @api.depends('ivedimas_id')
    def _show_ivedimas(self):
        for rec in self.filtered('ivedimas_id'):
            rec.show_ivedimas = True

    @api.depends('isvedimas_id')
    def _show_isvedimas(self):
        for rec in self.filtered('isvedimas_id'):
            rec.show_isvedimas = True

    @api.depends('state')
    def _change_likvidavimo_data(self):
        for rec in self:
            if rec.state == 'close':
                date = rec.writeoff_move_id and rec.writeoff_move_id.date or rec.date_close
                if not date and rec.isvedimas_id:
                    date = rec.isvedimas_id.name
                rec.likvidavimo_data = date
            elif rec.state == 'open' and rec.isvedimas_id:
                rec.likvidavimo_data = rec.isvedimas_id.name
            elif rec.state == 'open' and rec.depreciation_line_ids: #Does it make sense? Assets should not be in state open
                rec.likvidavimo_data = rec.depreciation_line_ids[-1].depreciation_date
            else:
                rec.likvidavimo_data = False

    @api.depends('value_residual', 'salvage_value')
    def _likvidacine_verte(self):
        for rec in self:
            rec.likvidacine_verte = rec.value_residual + rec.salvage_value

    @api.multi
    def validate(self):
        res = super(AccountAssetAsset, self).validate()
        for asset in self:
            if asset.ivedimas_id or asset.date and self.env.user.company_id.operation_act_creation != 'auto':
                continue
            committees = self.env['alignment.committee'].sudo().search(
                [('state', '=', 'valid'), ('type', '=', 'asset')],
                order='date DESC'
            ).with_context(active_test=True).filtered('is_valid')
            if not committees:
                continue
            act = self.env['eksploatacijos.aktas'].with_context(automatic_creation=True).create({
                'name': asset.date,
                'komisija': committees[0].id,
                'tipas': 'in',
                'introduced_asset_ids': [(4, asset.id)],
            })
            act.invite()
        return res

    @api.multi
    def write_off(self, closing_expense_account_id, closing_date=None):
        self.ensure_one()
        if self.isvedimas_id:
            # If we want to enforce aligned operation act (maybe with company setting), uncomment:
            # if not self.isvedimas_id.state != 'aligned':
            #     raise exceptions.UserError(_('The operation act has not been validated'))
            if closing_date and closing_date != self.isvedimas_id.name:
                raise exceptions.UserError(
                    _('Ilgalaikis turtas %s negali būti nurašytas kitai datai, nei nurodyta eksploatacijos akte (%s)')
                    % (self.code, self.isvedimas_id.name))
            else:
                closing_date = self.isvedimas_id.name
        super(AccountAssetAsset, self).write_off(closing_expense_account_id, closing_date)
        if not self.isvedimas_id and self.env.user.company_id.operation_act_creation == 'auto':
            committees = self.env['alignment.committee'].sudo().search(
                [('state', '=', 'valid'), ('type', '=', 'asset')], order='date DESC')
            if committees:
                act = self.env['eksploatacijos.aktas'].with_context(automatic_creation=True).create({
                    'name': self.date_close,
                    'komisija': committees[0].id,
                    'tipas': 'out',
                    'withdrawn_asset_ids': [(4, self.id)],
                })
                if len(committees) == 1:
                    act.invite()

    @api.model
    def _check_for_preexisting_act_for_asset(self, act_type):
        assets = self.env['account.asset.asset'].browse(self._context.get('active_ids', False))
        act_field = 'ivedimas_id' if act_type == 'in' else 'isvedimas_id'
        return assets.mapped(act_field)

    @api.multi
    def create_operation_act(self, act_type='in'):
        if not self.env.context.get('active_ids'):
            raise exceptions.UserError(_('Pasirinkite bent vieną ilgalaikį turtą'))

        if not self.env['alignment.committee'].search_count([('state', '=', 'valid'), ('type', '=', 'asset')]):
            raise exceptions.UserError(_('Pirma sukurkite komisiją!'))

        if act_type == 'in':
            view_id = self.env.ref('eksploatacijos_aktas.operation_act_wizard_in_view_form').id,
        else:
            view_id = self.env.ref('eksploatacijos_aktas.operation_act_wizard_out_view_form').id,

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'operation.act.wizard',
            'context': dict(self.env.context or {}, **{'default_act_type': act_type}),
            'view_mode': 'form',
            'view_type': 'form',
            'view_id': view_id,
            'target': 'new',
        }

    @api.multi
    def create_exploitation_act(self):
        self.ensure_one()
        operation_act_type = self.env.context.get('act_type', 'in')
        return self.with_context(active_ids=self.ids).create_operation_act(operation_act_type)


AccountAssetAsset()
