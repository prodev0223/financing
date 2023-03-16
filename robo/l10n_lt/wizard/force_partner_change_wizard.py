# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ForcePartnerChangeWizard(models.TransientModel):
    _name = 'force.partner.change.wizard'

    def default_journal(self):
        journal_id = self.env['account.journal'].search([('type', '=', 'general')], order='id', limit=1)
        return journal_id or False

    def default_date(self):
        line_date = self.env['account.move.line'].search([('id', 'in', self._context.get('line_ids'))], order='date desc', limit=1)
        return line_date.date or fields.Date.today

    partner_id = fields.Many2one('res.partner', string='Partneris', required=True)
    date = fields.Date(string='Data', default=default_date, required=True)
    journal_id = fields.Many2one('account.journal', string='Žurnalas', default=default_journal, required=True)

    @api.multi
    def change(self):
        self.ensure_one()
        force_partner_id = self.partner_id
        if not force_partner_id:
            return
        if not self._context.get('line_ids', False):
            return
        lines = self.env['account.move.line'].browse(self._context.get('line_ids'))
        ref = _('%s partnerio keitimas į %s') % (self.date, self.partner_id.display_name)
        move_vals = {
            'ref': ref,
            'journal_id': self.journal_id.id,
            'date': self.date,
        }
        move_id = self.env['account.move'].create(move_vals)
        for line in lines:
            if not line.partner_id and force_partner_id:
                line.write({'partner_id': force_partner_id.id})
            new_line_id = line.with_context(unbalanced_entry=True).copy({
                'move_id': move_id.id,
                'credit': line.debit,
                'debit': line.credit,
                'amount_currency':  - line.amount_currency if line.amount_currency else False,
            })
            if not line.reconciled and line.account_id.reconcile:
                new_line_id |= line
                new_line_id.reconcile()

            line.with_context(unbalanced_entry=True).copy({
                'move_id': move_id.id,
                'partner_id': force_partner_id.id,
            })
        move_id.post()
        return {
            'name': _('Partnerio keitimas'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            'view_id': False,
            'res_id': move_id.id,
        }
