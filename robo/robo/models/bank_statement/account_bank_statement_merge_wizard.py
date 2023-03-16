# -*- coding: utf-8 -*-
from six import iteritems
from odoo import models, fields, _, api, exceptions


class AccountBankStatementMergeWizard(models.TransientModel):
    _name = 'account.bank.statement.merge.wizard'

    @api.model
    def default_get(self, field_list):
        res = super(AccountBankStatementMergeWizard, self).default_get(field_list)
        active_ids = self.env.context.get('active_ids')
        if not active_ids:
            raise exceptions.UserError(_('Nėra sujungtinu ruosiniu'))
        if self.env.context.get('active_model') == 'account.bank.statement' and active_ids:
            res['statement_ids'] = active_ids
            res['destination_statement_id'] = active_ids[0]
        return res

    statement_ids = fields.Many2many('account.bank.statement', string='Mokėjimo ruošiniai')
    destination_statement_id = fields.Many2one('account.bank.statement', string='Sujungti į')
    merge_same_partner = fields.Boolean(string='Sujungti eilutes su tuo pačiu partneriu', default=True)
    show_warning_sepa_imported = fields.Boolean(string='Rodyti įspėjimą',
                                                compute='_compute_show_warning_sepa_imported')

    @api.one
    @api.depends('statement_ids.sepa_imported')
    def _compute_show_warning_sepa_imported(self):
        if any(self.mapped('statement_ids.sepa_imported')):
            self.show_warning_sepa_imported = True

    @api.multi
    def merge_selected_bank_statements(self):
        self.ensure_one()
        if any(self.mapped('statement_ids.sepa_imported')):
            raise exceptions.UserError(_('Negalima sujungti importuotų mokėjimo ruošinių'))
        if any(state == 'confirm' for state in self.mapped('statement_ids.state')):
            raise exceptions.UserError(_('Negalima sujungti patvirtintų mokėjimo ruošinių'))
        if len(self.statement_ids.mapped('journal_id')) > 1:
            raise exceptions.UserError(_('Negalima sujungti ruošinių iš skirtingų banko sąskaitų.'))

        if not self.merge_same_partner:
            statements_to_merge = self.statement_ids - self.destination_statement_id
            statements_to_merge.mapped('line_ids').write({'statement_id': self.destination_statement_id.id})
            self.env['ir.attachment'].search([
                ('res_model', '=', 'account.bank.statement'),
                ('res_id', 'in', statements_to_merge.ids)
            ]).write({'res_id': self.destination_statement_id.id})
            statements_to_merge.unlink()
        else:
            lines_grouping = {}
            for line in self.statement_ids.mapped('line_ids'):
                key = (line.partner_id.id, False, line.info_type, line.currency_id.id, line.bank_account_id.id)
                if key in lines_grouping:
                    lines_grouping[key] |= line
                else:
                    lines_grouping[key] = line
            destination_id = self.destination_statement_id
            new_statement_id = self.env['account.bank.statement'].create({
                'date': destination_id.date,
                'name': destination_id.name,
                'journal_id': destination_id.journal_id.id
            })
            line_obj = self.env['account.bank.statement.line']
            for key, lines in iteritems(lines_grouping):
                if key[2] == 'structured':
                    structured_codes = list(set(lines.mapped('name')))
                    for structured_code in structured_codes:
                        slines = lines.filtered(lambda r: r.name == structured_code)
                        line_obj.create({
                            'date': new_statement_id.date,
                            'name': structured_code,
                            'currency_id': key[3],
                            'info_type': key[2],
                            'partner_id': key[0],
                            'ref': structured_code,
                            'bank_account_id': key[4],
                            'amount': sum(slines.mapped('amount')),
                            'amount_currency': sum(slines.mapped('amount_currency')),
                            'statement_id': new_statement_id.id
                        })
                else:
                    line_obj.create({
                        'date': new_statement_id.date,
                        'name': ', '.join(lines.filtered(lambda r: r.name).mapped('name')),
                        'currency_id': key[3],
                        'info_type': key[2],
                        'partner_id': key[0],
                        'ref': ', '.join(lines.filtered(lambda r: r.ref).mapped('ref')),
                        'bank_account_id': key[4],
                        'amount': sum(lines.mapped('amount')),
                        'amount_currency': sum(lines.mapped('amount_currency')),
                        'statement_id': new_statement_id.id
                    })
            self.env['ir.attachment'].search([
                ('res_model', '=', 'account.bank.statement'),
                ('res_id', 'in', self.statement_ids.ids)
            ]).write({'res_id': new_statement_id.id})
            self.statement_ids.unlink()
            self.destination_statement_id = new_statement_id.id

        action = self.env.ref('account.action_bank_statement_tree')
        return {
            'name': action.name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.bank.statement',
            'res_id': self.destination_statement_id.id,
            'context': action.context,
            'type': 'ir.actions.act_window',
        }


AccountBankStatementMergeWizard()
