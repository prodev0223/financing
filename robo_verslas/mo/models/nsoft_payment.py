# -*- coding: utf-8 -*-
from odoo import models, exceptions, api, _


STATIC_ACCOUNT_CODE = '2410'
STATIC_PAYSERA_PARTNER_NAME = 'Gyventojai (bilietai.mo.lt apmokėta per PaySera)'


class NsoftPayment(models.Model):
    """
    Model that holds nSoft payment information
    """
    _inherit = 'nsoft.payment'

    # TODO: IMPORTANT -- METHOD FULLY OVERRIDDEN FROM NSOFT MODULE
    @api.multi
    def create_nsoft_moves(self, partner_id, forced_amount=0):
        """
        Create artificial payment for nsoft.sale.line or nsoft.invoice
        :param partner_id: res.partner that is used to create the move
        :param forced_amount: amount that can be forced to create partial payment move
        :return: None
        """
        forced_paysera_partner = self.env['res.partner'].search([('name', '=', STATIC_PAYSERA_PARTNER_NAME)])
        account = self.env['account.account'].search([('code', '=', STATIC_ACCOUNT_CODE)])
        for payment in self.filtered(lambda x: not x.move_id):
            amount_to_use = forced_amount if forced_amount else payment.residual
            journal = payment.pay_type_id.journal_id
            force_paysera_partner = True if journal.code in ['PSRNS'] else False
            name = 'Mokėjimas ' + payment.payment_date

            move_lines = []
            credit_line = {
                'name': name,
                'date': payment.payment_date,
            }
            debit_line = credit_line.copy()
            if payment.refund:
                debit_line['credit'] = credit_line['debit'] = amount_to_use
                debit_line['debit'] = credit_line['credit'] = 0.0
                debit_line['account_id'] = journal.default_credit_account_id.id
                credit_line['account_id'] = account.id
            else:
                debit_line['debit'] = credit_line['credit'] = amount_to_use
                debit_line['credit'] = credit_line['debit'] = 0.0
                debit_line['account_id'] = journal.default_debit_account_id.id
                credit_line['account_id'] = account.id

            if force_paysera_partner:
                if forced_paysera_partner:
                    debit_line['partner_id'] = forced_paysera_partner.id
                else:
                    raise exceptions.ValidationError(
                        _('Could not find PAYSERA partner to force on nsoft payment move // MO'))

            move_lines.append((0, 0, credit_line))
            move_lines.append((0, 0, debit_line))
            move_vals = {
                'line_ids': move_lines,
                'journal_id': journal.id,
                'date': payment.payment_date,
                'partner_id': partner_id.id,
            }
            move = self.sudo().env['account.move'].create(move_vals)
            move.post()
            payment.move_id = move


NsoftPayment()
