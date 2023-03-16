# -*- encoding: utf-8 -*-
from datetime import datetime
from odoo import models, fields, api, _, tools, exceptions

DEFAULT_WRITEOFF_ACCOUNT_CODE = '652'


class OperationActWizard(models.TransientModel):
    _name = 'operation.act.wizard'
    _description = 'Wizard to create operation acts for assets'

    def _default_committee_id(self):
        return self.env['alignment.committee'].search([('state', '=', 'valid'), ('type', '=', 'asset')],
                                                      order='date DESC', limit=1)

    def _default_date(self):
        return datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    @api.model
    def default_get(self, fields_list):
        res = super(OperationActWizard, self).default_get(fields_list)
        if 'asset_ids' in fields_list:
            res['asset_ids'] = self.env.context.get('active_ids')
        return res

    act_type = fields.Selection([('in', 'Įvedimas'),
                                 ('out', 'Išvedimas')], default='in', required=True, string='Tipas')
    committee_id = fields.Many2one('alignment.committee', string='Komisija', required=True,
                                   default=_default_committee_id)
    committee_member_ids = fields.Many2many('hr.employee', string='Komisijos nariai',
                                            related='committee_id.employee_ids', readonly=True)
    asset_ids = fields.Many2many('account.asset.asset', string='Turtai')
    date = fields.Date(string='Akto data', default=_default_date)

    @api.multi
    def _find_preexisting_act_for_assets(self):
        """ Finds acts already created for assets """
        self.ensure_one()
        act_field = 'ivedimas_id' if self.act_type == 'in' else 'isvedimas_id'
        return self.asset_ids.mapped(act_field)

    @api.multi
    def create_operation_act(self):
        """ Create the act according to settings """
        self.ensure_one()
        if self._find_preexisting_act_for_assets():
            raise exceptions.ValidationError(_('Bent vienas ilgalaikis turtas jau turi eksploatacijos aktą.'))
        use_sudo = self.env.user.has_group('ilgalaikis_turtas.group_asset_manager')
        if use_sudo and not self.env.user.has_group('base.group_system'):
            for asset in self.asset_ids:
                asset.message_post('Creating exploitation act')
            self = self.sudo()

        # if self.act_type == 'out' and any(self.mapped('asset_ids.written_off_or_sold')):  #TODO: for now, only loose constraints
        #     raise exceptions.UserError(
        #         _('Kai kuris ilgalaikis turtas jau buvo nurašytas arba parduotas. Išvedimo aktą galima kurti tik turtui su būsena "Einamasis"'))

        # if self.act_type == 'in' and any(asset.state != 'draft' for asset in self.asset_ids):  #TODO: for now, only loose constraints
        #     raise exceptions.UserError(
        #         _('Įvedimo aktą galima kurti tik "Juodraštis" būsenos turtui'))

        act_id = self.env['eksploatacijos.aktas'].create({
            'name': self.date,
            'komisija': self.committee_id.id,
            'tipas': self.act_type,
            'introduced_asset_ids': [(6, 0, self.asset_ids.ids)] if self.act_type == 'in' else False,
            'withdrawn_asset_ids': [(6, 0, self.asset_ids.ids)] if self.act_type == 'out' else False,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'eksploatacijos.aktas',
            'view_mode': 'form',
            'view_type': 'form',
            'views': [(False, 'form')],
            'res_id': act_id.id,
            'view_id': self.env.ref('eksploatacijos_aktas.eksploatacijos_aktas_view').id,
        }


OperationActWizard()
