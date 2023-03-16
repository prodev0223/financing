# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import _, api, exceptions, fields, models, tools
import pytz


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def default_get(self, fields_list):
        res = super(ResUsers, self).default_get(fields_list)
        if self.env.user.company_id.require_2fa:
            res['enable_2fa'] = True
        return res

    def _default_action(self):
        return self.env.ref('robo.open_robo_vadovas_client_action').id or False

    action_id = fields.Many2one('ir.actions.actions', defaulf=_default_action)
    forecast_budget_line_ids = fields.One2many('forecast.budget.line', 'user_id', string='Prognozės biudžeto eilutės')
    project_involvement = fields.One2many('project.involvement', 'user_id', string="Projektų sąryšiai")
    inform_comments = fields.Boolean(string='Receive an email when messages are left on documents', default=True)
    cash_register_journal_ids = fields.Many2many('account.journal', 'res_users_account_journal_rel',
                                                 string='Leidžiami kasos aparatų žurnalai',
                                                 domain=[('code', '!=', 'KVIT'), ('code', 'not like', 'CSH'),
                                                         ('type', '=', 'cash')],
                                                 groups='robo_basic.group_robo_premium_manager')
    active = fields.Boolean(inverse='_set_active')

    def __init__(self, pool, cr):
        init_res = super(ResUsers, self).__init__(pool, cr)
        type(self).SELF_WRITEABLE_FIELDS = list(self.SELF_WRITEABLE_FIELDS)
        type(self).SELF_WRITEABLE_FIELDS.extend(['inform_comments'])
        type(self).SELF_WRITEABLE_FIELDS = list(set(type(self).SELF_WRITEABLE_FIELDS))
        type(self).SELF_READABLE_FIELDS = list(self.SELF_READABLE_FIELDS)
        type(self).SELF_READABLE_FIELDS.extend(['inform_comments'])
        type(self).SELF_READABLE_FIELDS = list(set(type(self).SELF_READABLE_FIELDS))
        return init_res

    @api.constrains('enable_2fa')
    def _check_2fa_is_not_required(self):
        """ Prevent disabling 2FA if it is required in the company settings """
        if not self._context.get('changing_global_2fa_policy'):
            if any(u.company_id.require_2fa and not u.enable_2fa for u in self):
                raise exceptions.ValidationError(_('2FA is required by the company policy. You cannot disable it'))

    @api.multi
    def write(self, vals):
        if vals.get('active') and self.env.user.company_id.require_2fa:
            vals['enable_2fa'] = True
        return super(ResUsers, self).write(vals)

    @api.model
    def set_default_actions(self):
        action_id = self.env.ref('robo.open_robo_vadovas_client_action').id or False
        if action_id:
            self.search([]).write({'action_id': action_id})

    @api.multi
    def get_current_timestamp(self):
        """
        Get current timestamp based on timezone settings
        :return: Current user timestamp (str)
        """
        self.ensure_one()
        now = datetime.utcnow()
        tz_name = self.env.context.get('tz') or self.tz or 'Europe/Vilnius'
        if tz_name:
            user_tz = pytz.timezone(tz_name)
            now = pytz.utc.localize(now).astimezone(user_tz)
        return now.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @api.multi
    def _set_active(self):
        for rec in self:
            msg = {
                'body': _('User: {}, related to this partner has been {}').format(
                    rec.name, _('activated') if rec.active else _('deactivated')),
            }
            rec.partner_id.robo_message_post(**msg)


ResUsers()
