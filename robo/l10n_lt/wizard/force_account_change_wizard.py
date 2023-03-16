# -*- coding: utf-8 -*-
from odoo import models, fields,  api, _


class ForceAccountChangeWizard(models.TransientModel):
    _name = 'force.account.change.wizard'

    def default_journal(self):
        journal_id = self.env['account.journal'].search([('type', '=', 'general')], order='id', limit=1)
        return journal_id or False

    def default_date(self):
        line_date = self.env['account.move.line'].search([('id', 'in', self._context.get('line_ids'))], order='date desc', limit=1)
        return line_date.date or fields.Date.today

    account_id = fields.Many2one('account.account', string='Buhalterinė sąskaita', required=True)
    date = fields.Date(string='Data', default=default_date, required=True)
    journal_id = fields.Many2one('account.journal', string='Žurnalas', default=default_journal, required=True)

    @api.multi
    def change(self):
        self.ensure_one()
        force_account_id = self.account_id
        if not force_account_id:
            return
        if not self._context.get('line_ids', False):
            return
        lines = self.env['account.move.line'].browse(self._context.get('line_ids'))
        ref = _('%s sąskaitos keitimas į %s') % (self.date, self.account_id.display_name)
        move_vals = {
            'ref': ref,
            'journal_id': self.journal_id.id,
            'date': self.date,
        }
        move_id = self.env['account.move'].create(move_vals)
        for line in lines:
            if not line.account_id and force_account_id:
                line.write({'account_id': force_account_id.id})
            new_line_id = line.with_context(unbalanced_entry=True).copy({
                'move_id': move_id.id,
                'credit': line.debit,
                'debit': line.credit,
            })
            if not line.reconciled and line.account_id.reconcile:
                new_line_id |= line
                new_line_id.reconcile()

            line.with_context(unbalanced_entry=True).copy({
                'move_id': move_id.id,
                'account_id': force_account_id.id,
            })
        move_id.post()
        return {
            'name': _('Sąskaitos keitimas'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            'view_id': False,
            'res_id': move_id.id,
        }




