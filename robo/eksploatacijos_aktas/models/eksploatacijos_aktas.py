# -*- coding: utf-8 -*-
from odoo import models, fields, _, tools, api, exceptions
from datetime import datetime


class EksploatacijosAktas(models.Model):
    _name = 'eksploatacijos.aktas'
    _inherit = ['mail.thread']
    _order = 'create_date DESC'
    _track = {
        'state': {
            'eksploatacijos_aktas.mt_state': lambda *a: True
        }
    }

    def _default_date(self):
        return datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

    def _company(self):
        return self.env.user.company_id.id

    company_id = fields.Many2one('res.company', default=_company, readonly=True)
    state = fields.Selection([('draft', 'Registering'),
                              ('invitation', 'Waiting'),
                              ('aligned', 'Aligned'),
                              ('cancel', 'Cancelled')], default='draft', track_visibility='onchange')
    name = fields.Char(string='Doc.Nr. (date)', required=True, default=_default_date, readonly=True,
                       states={'draft': [('readonly', False)], 'invitation': [('readonly', False)]})
    komisija = fields.Many2one('alignment.committee', string='Committee (Act nr.)', required=True,
                               domain="[('state','=','valid')]", readonly=True, states={'draft': [('readonly', False)]})
    vizavimas = fields.One2many('alignment.history', 'eks_aktas_id', string='Alignment', required=False,
                                readonly=True, compute='_add_committee_members', store=True, compute_sudo=True)

    introduced_asset_ids = fields.One2many('account.asset.asset', 'ivedimas_id', string='Asset', required=False,
                                           readonly=True, states={'draft': [('readonly', False)]})
    withdrawn_asset_ids = fields.One2many('account.asset.asset', 'isvedimas_id', string='Asset', required=False,
                                          readonly=True, states={'draft': [('readonly', False)]})
    delegate = fields.Boolean(string='Is delegate?', compute='_compute_delegate')

    tipas = fields.Selection([('in', 'Receiving'),
                              ('out', 'Withdrawal')],
                             default='in', required=True, readonly=True, string='Type')
    yra_komentaru = fields.Boolean(string='Has comment?', compute='_yra_komentaru', store=True, readonly=True)
    comments = fields.Char(string='Komentarai', compute='_compute_comments')

    turtas_viz_date = fields.Char(string='Aligned (date)', compute='_compute_turtas_viz_date', store=True)
    sign_id = fields.Many2one('e.document', string='eDokumentas', ondelete='set null', readonly=True)
    signed_by_all = fields.Boolean(compute='_compute_signed_info')
    signed_by_minimum = fields.Boolean(compute='_compute_signed_info')

    @api.multi
    @api.depends('komisija')
    def _add_committee_members(self):
        for act in self:
            alignments = [(5,)]
            alignments.extend((0, 0, {
                'employee_id': member.id,
                'aligned': False,
                'eks_aktas_id': act.id,
                'comment': '',
            }) for member in act.mapped('komisija.employee_ids'))
            act.vizavimas = alignments

    @api.multi
    def confirm(self):
        """ Forcefully mark as aligned """
        # Accountant can bypass the alignment and confirm the act (e.g. agreed with company manager)
        if not self.env.user.is_accountant():
            raise exceptions.AccessError(_('Tik buhalteriai gali atlikti šį veiksmą.'))
        self.write({'state': 'aligned'})

    @api.multi
    def invite_sign(self):
        """
        Creates e-Document from the act and invites committee members to sign
        :return: action to display the edoc (as a dict)
        """
        self.ensure_one()
        user_ids = self.mapped('vizavimas.employee_id.user_id.id')
        action = self.env['e.document'].general_sign_call('eksploatacijos_aktas.report_eksploatacijos_aktas_sl', self,
                                                          user_ids=user_ids)
        if action and 'res_id' in action and action['res_id']:
            self.sign_id = action['res_id']
        return action

    @api.multi
    def invite(self):
        """ Invite to sign: create the edoc, and post a message """
        message = _(u'<p><b>Darbuotojai, pakviesti pasirašyti:</b></p>')
        action = None
        for act in self:
            if act.vizavimas:
                action = act.invite_sign()
                for name in act.mapped('vizavimas.employee_id.name'):
                    message += u'%s<br/>' % name

                post_vars = {'subject': _('Vizavimas'),
                             'body': message, }
                act.message_post(type='email', subtype='mt_comment', **post_vars)
                act.state = 'invitation'

        return action if len(self) == 1 else None

    @api.depends('vizavimas.employee_id')
    def _compute_delegate(self):
        for rec in self:
            employee = self.env['hr.employee'].search([('user_id', '=', rec._uid)])
            delegate = False
            if employee:
                employee_id = employee.id
                for alignment in rec.vizavimas:
                    if alignment.employee_id.id == employee_id and not alignment.aligned:
                        delegate = True
                        break
            rec.delegate = delegate

    @api.depends('vizavimas.comment')
    def _yra_komentaru(self):
        for rec in self.filtered('vizavimas'):
            for alignment in rec.vizavimas:
                if alignment.comment:
                    rec.yra_komentaru = True
                    break
            else:
                rec.yra_komentaru = False

    @api.depends('vizavimas.comment')
    def _compute_comments(self):  #TODO: remove? everything is in edoc now, no more comments
        for rec in self:
            comments = '\n'.join(comment for comment in rec.mapped('vizavimas.comment'))
            if comments:
                rec.comments = comments

    @api.multi
    @api.depends('state')
    def _compute_turtas_viz_date(self):
        now = datetime.now().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        for rec in self:
            rec.turtas_viz_date = now if rec.state == 'aligned' else False

    @api.depends('sign_id.user_ids.state')
    def _compute_signed_info(self):
        for rec in self.filtered(lambda r: r.sign_id and r.sign_id.sudo().active):
            sign_states = [state == 'signed' for state in rec.mapped('sign_id.user_ids.state')]
            rec.signed_by_all = all(sign_states)
            rec.signed_by_minimum = sum(sign_states) >= rec.komisija.no_of_approve

    @api.multi
    def cancel(self):
        """ Resets acts to 'cancel' state """
        self.write({'state': 'cancel'})

    @api.multi
    def reset_to_draft(self):
        """ Resets acts to 'draft' state """
        self.write({'state': 'draft'})

    @api.model
    def create(self, vals):
        """ Extend create method to notify channel on automatic creation """
        res = super(EksploatacijosAktas, self).create(vals)
        channel = self.env.ref('eksploatacijos_aktas.eksploatacijos_aktas_channel', False)
        if channel and self._context.get('automatic_creation'):
            if res.tipas == 'in':
                body = _('Įvedimo į eksploataciją aktas (%s) buvo sukurtas ilgalaikiam turtui %s.') % (
                    res.name, ', '.join(asset.name for asset in res.introduced_asset_ids))
            else:
                body = _('Išvedimo iš eksploatacijos aktas (%s) buvo sukurtas ilgalaikiam turtui %s.') % (
                    res.name, ', '.join(asset.name for asset in res.withdrawn_asset_ids))
            msg = {
                'body': body,
                'subject': _('Buvo sukurtas naujas eksploatacijos aktas') + ' [%s]' % self.env.cr.dbname,
                'message_type': 'comment',
                'subtype': 'mail.mt_comment',
                'author_id': self.env.user.partner_id.id,
            }
            channel.sudo().message_post(**msg)
        return res

    @api.multi
    def unlink(self):
        if any(rec.state not in ['draft', 'cancel'] for rec in self):
            raise exceptions.UserError(_('Negalima ištrinti įrašų. Pirmiau atšaukite.'))
        return super(EksploatacijosAktas, self).unlink()


EksploatacijosAktas()
