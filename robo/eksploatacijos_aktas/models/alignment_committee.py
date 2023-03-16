# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions


class AlignmentCommittee(models.Model):

    _name = 'alignment.committee'
    _description = 'Alignment Committee'
    _inherit = ['mail.thread']

    _order = 'date DESC'

    name = fields.Char(string='Komitetas', required=True, states={'valid': [('readonly', True)]},
                       track_visibility='onchange')
    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True,
                                    states={'valid': [('readonly', True)]}, track_visibility='onchange')
    state = fields.Selection([('valid', 'Patvirtinta'),
                              ('invalid', 'Nepatvirtinta')], default='invalid', readonly=True,
                             string='State', track_visibility='onchange')
    date = fields.Date(string='Date', required=True, default=fields.Date.today, states={'valid': [('readonly', True)]},
                       track_visibility='onchange')
    type = fields.Selection([('asset', 'Eksploatacijos aktas')], string='Type', default='asset', required=True,
                            states={'valid': [('readonly', True)]}, track_visibility='onchange')
    member_count = fields.Integer(string='Member Count', compute='_compute_member_count')
    no_of_approve = fields.Integer(string='Required No. of Approves',
                                   help='Needed number of approves by committee members to confirm.',
                                   states={'valid': [('readonly', True)]}, default=1, track_visibility='onchange')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id,
                                 states={'valid': [('readonly', True)]})
    is_valid = fields.Boolean(compute='_compute_is_valid')
    eksploatacijos_aktas_ids = fields.One2many('eksploatacijos.aktas', 'komisija')
    department_id = fields.Many2one('hr.department', string='Department')
    chairman_id = fields.Many2one('hr.employee', string='Chairman of the Committee')
    date_to = fields.Date(string='Date to')

    @api.depends('employee_ids')
    def _compute_member_count(self):
        for rec in self:
            rec.member_count = len(rec.employee_ids)

    @api.depends('state', 'no_of_approve', 'employee_ids')
    def _compute_is_valid(self):
        for rec in self:
            rec.is_valid = rec.state == 'valid' and 1 <= rec.no_of_approve <= rec.member_count

    @api.constrains('state', 'no_of_approve', 'employee_ids')
    def _check_correct_settings_on_validate(self):
        """ When validating a committee, check that there is at least as many members as the minimum number of required approval"""
        min_count = 1
        for rec in self:
            if rec.state != 'valid':
                continue
            if not (min_count <= rec.no_of_approve <= rec.member_count):
                raise exceptions.UserError(_("Tvirtinančiųjų skaičius negali būti didesnis už komiteto narių skaičių "
                                             "arba mažesnis už %s.") % min_count)

    @api.multi
    def invalidate(self):
        """ Invalidate the committee """
        self.write({'state': 'invalid'})

    @api.multi
    def validate(self):
        """ Validate the committee """
        self.write({'state': 'valid'})

    @api.multi
    def unlink(self):
        for rec in self.sudo():
            if rec.eksploatacijos_aktas_ids:
                raise exceptions.UserError(_('Negalima ištrinti komisijų, kurios turi susietų eksploatacijos aktų.'))
            if rec.state == 'valid':
                raise exceptions.UserError(_('Negalima ištrinti komisijų, kurios yra patvirtintos'))
        return super(AlignmentCommittee, self).unlink()
