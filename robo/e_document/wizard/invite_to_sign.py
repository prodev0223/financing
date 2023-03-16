# -*- coding: utf-8 -*-
from odoo import _, api, exceptions, fields, models


class EDocumentInviteToSign(models.TransientModel):
    _name = 'invite.to.sign.wizard'

    e_document_id = fields.Many2one('e.document', 'Dokumentas', required=True, ondelete='cascade')
    user_items = fields.One2many('invite.to.sign.wizard.line', 'wizard_id')
    signed_user_ids = fields.Many2many('res.users')
    user_ids = fields.Many2many('res.users', compute='_compute_user_ids')

    @api.multi
    @api.depends('user_items.user_id')
    def _compute_user_ids(self):
        admins = self.env['res.users'].search(
            [('groups_id', 'in', self.env.ref('robo_basic.group_robo_premium_accountant').id)])
        user_employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
        users = self.env.user if not user_employee else self.env['res.users']
        for rec in self:
            users |= rec.mapped('user_items.user_id') | admins
            rec.user_ids = users.ids

    @api.multi
    def invite_to_sign(self):
        self.ensure_one()
        if not self.user_items:
            raise exceptions.UserError(_('Pasirinkite bent vieną darbuotoją'))
        if not self.e_document_id:
            raise exceptions.UserError(_('Nepasirinktas dokumentas'))

        for rec in self.user_items:
            self.sudo().env['signed.users'].create({
                'document_id': self.e_document_id.id,
                'user_id': rec.user_id.id,
            })

        users = self.user_items.mapped('user_id')
        self.e_document_id.inform_users(users)


EDocumentInviteToSign()


class EDocumentInviteToSignLine(models.TransientModel):
    _name = 'invite.to.sign.wizard.line'

    @api.model
    def get_domain(self):
        user_ids = self.env['hr.employee'].search([]).mapped('user_id.id')
        return [('groups_id', 'not in', self.env.ref('base.group_system').id), ('id', 'in', user_ids)]

    user_id = fields.Many2one('res.users', string='Pakviesti pasirašyti', required=True, domain=get_domain)
    wizard_id = fields.Many2one('invite.to.sign.wizard')


EDocumentInviteToSignLine()