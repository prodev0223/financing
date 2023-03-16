# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, exceptions, fields, models, tools


class ClientSupportTicket(models.Model):
    _name = 'client.support.ticket'
    _inherit = ['mail.thread']

    _order = 'message_last_post DESC'

    # TODO: add some date fields?
    # TODO: add other categories and pass them to internal
    number = fields.Char(string='Numeris', readonly=True)
    subject = fields.Char(string='Tema', readonly=True)
    last_person = fields.Char(string='Paskutinis atsakęs', readonly=True,
                              default=lambda self: self.env.user.partner_id and self.env.user.partner_id.name or _(
                                  'ROBO'))
    state = fields.Selection([('open', 'Sprendžiama'),
                              ('closed', 'Uždaryta')], default='open', string='Būsena', readonly=True)

    reason = fields.Selection([('invoice', 'Sąskaitos faktūros'),
                               ('payment', 'Mokėjimai'),
                               ('payroll', 'Darbo užmokestis'),
                               ('edoc', 'El. dokumentai'),
                               ('it', 'Sistemos sutrikimai'),
                               ('other', 'Kita')], string='Kategorija', required=True, readonly=True)

    rec_model = fields.Char(string='Susijęs objektas', groups='base.group_system')
    rec_id = fields.Integer(string='Susijusio objekto ID', groups='base.group_system')
    user_id = fields.Many2one('res.users', string='Naudotojas', default=lambda self: self.env.user)
    message_last_post = fields.Datetime(readonly=True)
    allow_posting_widget = fields.Boolean(string='Leisti vartotojui rašyti žinutes',
                                          compute='_compute_allow_posting_widget')

    goto_button_visible = fields.Boolean(compute='_compute_goto_button_visible')

    @api.one
    @api.depends('state')
    def _compute_allow_posting_widget(self):
        if self.state == 'open' or self.env.user.is_accountant():
            self.allow_posting_widget = True

    @api.depends('rec_model', 'rec_id')
    def _compute_goto_button_visible(self):
        for rec in self:
            rec.goto_button_visible = True if rec.sudo().rec_model and rec.sudo().rec_id else False

    @api.model
    def create(self, vals):
        res = super(ClientSupportTicket, self).create(vals)
        if res.sudo().rec_id and res.sudo().rec_model:
            res.message_post(body=_('Sukurta iš modelio: %s ID: %s')
                                  % (res.sudo().rec_model, res.sudo().rec_id))
        self._cr.commit()  # ROBO: we must commit, otherwise internal system cannot find the record
        return res

    @api.multi
    def name_get(self):
        return [(rec.id, rec.number or self.subject or self.reason) for rec in self]

    @api.multi
    @api.returns('self', lambda value: value.id)
    def robo_message_post(self, **kwargs):
        self.ensure_one()
        if self.state == 'closed' and not self.env.user.is_accountant():
            raise exceptions.UserError(_('Negalima palikti komentarų uždarytoje užklausoje.'))
        if kwargs.get('subtype') == 'robo.mt_robo_front_message':
            self.write({'last_person': self.env.user.partner_id and self.env.user.partner_id.name or _('ROBO'),
                        'message_last_post': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
        if self.sudo().rec_id and self.sudo().rec_model:
            kwargs.update({'rec_id': self.sudo().rec_id, 'rec_model': self.sudo().rec_model})
        else:
            kwargs.update({'rec_id': self.id, 'rec_model': 'client.support.ticket'})
        if kwargs.get('ticket_close'):
            self.write({'state': 'closed'})
        kwargs.update({'client_ticket_type': self.reason})
        res = super(ClientSupportTicket, self).robo_message_post(**kwargs)
        if not self.env.context.get('ignore_rec_model') and kwargs.get(
                'subtype') == 'robo.mt_robo_front_message' and self.sudo().rec_id and self.sudo().rec_model:
            rec = self.env[self.sudo().rec_model].browse(self.sudo().rec_id)
            if rec.exists():
                rec.with_context(update_record_from_ticket=True).robo_message_post(**kwargs)
        return res

    # ROBO: we must move this part before commit
    # @api.multi
    # @api.returns('self', lambda value: value.id)
    # def message_post(self, **kwargs):
    #     if kwargs.get('subtype') == 'robo.mt_robo_front_message':
    #         self.write({'last_person': self.env.user.partner_id and self.env.user.partner_id.name or _('Robo Platforma'),
    #                     'message_last_post': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)})
    #     return super(ClientSupportTicket, self).message_post(**kwargs)

    @api.multi
    def close_ticket(self):
        """ Close ticket on user's request """
        self.ensure_one()
        if self.state == 'closed':
            raise exceptions.UserError(_('Užklausa jau uždaryta'))
        if not self.env.user.is_manager() and not self.user_id == self.env.user:
            raise exceptions.UserError(_('Negalite uždaryti šios užklausos, nes ji priklauso kitam vartotojui.'))
        self.write({
            'state': 'closed',
            'last_person': self.env.user.partner_id and self.env.user.partner_id.name or _('ROBO'),
            'message_last_post': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        })
        self.sudo().robo_message_post(body=_('%s uždarė užklausą') % self.env.user.partner_id.name,
                                      robo_chat=True, client_message=True, ticket_close=True, front_message='True')

    @api.multi
    def reopen_ticket(self):
        """ Re-open ticket on user's request """
        self.ensure_one()
        if self.state == 'open':
            raise exceptions.UserError(_('Užklausa jau atidaryta'))
        if not self.env.user.is_manager() and not self.user_id == self.env.user:
            raise exceptions.UserError(_('Negalite atidaryti šios užklausos, nes ji priklauso kitam vartotojui.'))
        domain = [('rec_id', '=', self.sudo().rec_id),
                  ('rec_model', '=', self.sudo().rec_model),
                  ('state', '=', 'open'),
                  ('user_id', '=', self.user_id.id),
                  ('id', '!=', self.id)]
        existing_tickets = self.env['client.support.ticket'].sudo().search(domain)
        if existing_tickets:
            raise exceptions.UserError(
                _('Negalite atidaryti užklausos, nes jau yra atvira užklausa su tuo pačiu dokumentu.'))
        self.write({
            'state': 'open',
            'last_person': self.env.user.partner_id and self.env.user.partner_id.name or _('ROBO'),
            'message_last_post': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        })
        self.sudo().robo_message_post(body=_('%s atidarė užklausą') % self.env.user.partner_id.name, robo_chat=True,
                                      client_message=True, ticket_close=False, front_message='True', ticket_reopen=True)

    @api.multi
    def open_linked_record(self):
        """ Open the view of the record associated with the ticket, if any."""
        self.ensure_one()
        res_id = self.sudo().rec_id
        res_model = self.sudo().rec_model
        if res_id and res_model:
            rec = self.env[res_model].browse(res_id)
            action = rec.get_formview_action()
            if action:
                return action
            return {
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': res_model,
                'res_id': res_id,
                'robo_front': True,
                'type': 'ir.actions.act_window',
                'target': 'current',
                'context': {'robo_header': {},
                            'robo_menu_id': self.env.ref('robo.menu_start').id}
            }
        else:
            return {'type': 'ir.actions.do_nothing'}
