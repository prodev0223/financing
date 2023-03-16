# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FrontBankStatementMergeWizard(models.TransientModel):
    _name = 'front.bank.statement.merge.wizard'

    front_statement_ids = fields.Many2many(
        'front.bank.statement',
        string='Apjungiami mokėjimai',
    )
    destination_statement_id = fields.Many2one(
        'front.bank.statement', string='Mokėjimas į kurį jungiama',
    )

    @api.multi
    def merge_statements(self):
        """
        Merges statement lines from all of the passed
        statements into one destination statement
        other statements marked as inactive afterwards
        :return: JS reload action (dict)
        """
        self.ensure_one()
        if self.front_statement_ids and self.destination_statement_id:
            # Filter out all of the statements except for the destination one
            other_statements = self.front_statement_ids.filtered(lambda x: x.id != self.destination_statement_id.id)
            # Compose message to post to destination statement
            message_body = '''Mokėjimas sujungtas su:<br/>
            <table width="50%" style="border:1px solid black; border-collapse: collapse; text-align: center;">
                <tr style="border:1px solid black;">
                    <td style="border:1px solid black; padding:5px;"><b>Ruošinio pavadinimas</b></td>
                    <td style="border:1px solid black; padding:5px;"><b>Suma</b></td>
                    <td style="border:1px solid black; padding:5px;"><b>Data</b></td>
                </tr>
            '''
            curr_name = self.env.user.company_id.currency_id.name
            for statement in other_statements:
                message_body += '''
                        <tr style="border:1px solid black;">
                        <td style="border:1px solid black;">%(name)s</td>
                        <td style="border:1px solid black;">%(amount)s</td>
                        <td style="border:1px solid black;">%(date)s</td></tr>''' % {
                    'name': statement.name,
                    'amount': '{} {}'.format(statement.amount, statement.currency_id.name or curr_name),
                    'date': statement.date,
                }
            message_body += """</table><br>"""
            # Write new statement id to all of the other mapped statement lines
            other_statements.mapped('line_ids').write({'statement_id': self.destination_statement_id.id})
            other_statements.write({'active': False})
            # Post the message and reload the view
            self.destination_statement_id.message_post(message_body)
            return {'type': 'ir.actions.act_close_wizard_and_reload_view'}
