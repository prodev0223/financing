# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import _, api, exceptions, fields, models


class SignedUsers(models.Model):
    _name = 'signed.users'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', string='Asmuo', required=True)
    date = fields.Datetime(string='Pasirašymo laikas')
    state = fields.Selection([('pending', 'Laukia pasirašymo'),
                              ('signed', 'Pasirašyta')], string='Būsena',
                             default='pending')
    document_id = fields.Many2one('e.document', string='Dokumentas')
    signed_by_delegate = fields.Boolean(string='Pasirašė įgaliotinis', default=False)

    @api.constrains('user_id', 'document_id')
    def _check_no_duplicate_user(self):
        for rec in self:
            if self.search_count([('user_id', '=', rec.user_id.id), ('document_id', '=', rec.document_id.id)]) > 1:
                raise exceptions.ValidationError(_('Kvietimai negali kartotis.'))

    @api.multi
    def sign(self, user_id, delegate=False):
        if not self.env.user.has_group('base.group_system'):
            return
        self.ensure_one()
        if not user_id:
            raise exceptions.ValidationError(_('Nenurodytas vartotojas.'))
        if delegate and self.user_id.id != user_id:
            if self.env['signed.users'].search([('document_id', '=', self.document_id.id), ('user_id', '=', user_id)]):
                raise exceptions.ValidationError(_('Įgaliotiniams nėra leidžiama pasirašyti vietoje vadovo, jeigu jie '
                                                   'yra taip pat pakviesti pasirašyti.'))
        self.write({
            'state': 'signed',
            'signed_by_delegate': True if delegate and self.user_id.id != user_id else False,
            'date': datetime.utcnow()
        })
        if delegate and self.user_id.id != user_id:
            self.env['signed.users'].create({
                'state': 'signed',
                'user_id': user_id,
                'document_id': self.document_id.id,
                'signed_by_delegate': False,
                'date': datetime.utcnow(),
            })
        if len(self.document_id.user_ids.filtered(lambda r: r.state == 'signed')) == len(self.document_id.user_ids)\
                and not self.document_id.invite_to_sign_new_users:
            self.document_id.write({
                'state': 'e_signed',
                'date_signed': datetime.utcnow(),
            })


SignedUsers()
