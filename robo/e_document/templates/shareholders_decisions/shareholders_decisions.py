# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import models, api, fields, exceptions, _


class EDocument(models.Model):
    _inherit = 'e.document'

    shareholder_ids = fields.Many2many('res.company.shareholder', string='Pasirašinėjantys akcininkai', readonly=True, states={'draft': [('readonly', False)]}, inverse='set_final_document')
    shareholder_sign_footer = fields.Html(compute='_compute_shareholder_sign_footer')

    @api.one
    @api.depends('shareholder_ids')
    def _compute_shareholder_sign_footer(self):
        footer = ''
        single_sign_line = \
            '''<div style="display: flex; justify-content: flex-end; width: 100%; float:right;">
                <table width="55%" align="right" style="float: right; margin-top:25px; border-collapse: separate; 
                    border-spacing: 20px 0;">
                    <tr style="border:none">
                        <td style="border:none; text-align: center; width: 70%;">
                            <span>{0}</span>
                        </td>
                        <td style="border:none;"><span><br/></span></td>
                    </tr>
                    <tr style="border:none;">
                        <td style="border:none; border-top: 1px solid black; text-align:center;" align="center">
                            <span>(vardas, pavardė)</span>
                        </td>
                        <td style="border:none; border-top: 1px solid black; text-align:center;" align="center">
                            <span>(parašas)</span>
                        </td>
                    </tr>
                </table>
            </div>
            '''
        for shareholder_id in self.shareholder_ids:
            footer += single_sign_line.format(shareholder_id.shareholder_name)
        self.shareholder_sign_footer = footer

    @api.multi
    def confirm_shareholders_decision(self):
        is_accountant = self.user_has_groups('robo_basic.group_robo_premium_accountant')
        if not is_accountant:
            raise exceptions.ValidationError(_('Negalite patvirtinti akcininkų sprendimų, nes nesate buhalteris'))
        good_docs = self.filtered(lambda r: r.state == 'confirm' and r.document_type == 'akcininku_sprendimas')
        sign_date = datetime.utcnow()
        for rec in good_docs:
            rec.sudo().workflow_execution()
            rec.sudo().write({'date_signed': sign_date})
            rec.sudo().set_final_document()
            rec.create_pdf()
            rec.write({'state': 'e_signed'})
            self.env['e.document'].accountants_subscribe(rec)

    @api.multi
    def cancel_shareholders_decision(self):
        is_accountant = self.user_has_groups('robo_basic.group_robo_premium_accountant')
        if not is_accountant:
            raise exceptions.ValidationError(_('Negalite atšaukti akcininkų sprendimų, nes nesate buhalteris'))
        good_docs = self.filtered(lambda r: r.state == 'e_signed' and r.document_type == 'akcininku_sprendimas')
        self.cancel_shareholders_decision_workflow()
        self.sudo().write({
            'date_signed': False,
            'signed_user_id': False
        })
        for rec in good_docs:
            rec.sudo().set_final_document()
            rec.create_pdf()
            rec.write({'state': 'confirm'})

    @api.multi
    def cancel_shareholders_decision_workflow(self):
        is_accountant = self.user_has_groups('robo_basic.group_robo_premium_accountant')
        if not is_accountant:
            raise exceptions.ValidationError(_('Negalite atšaukti akcininkų sprendimų, nes nesate buhalteris'))
        if any(doc.document_type != 'akcininku_sprendimas' for doc in self):
            raise exceptions.ValidationError(_('Negalite atšaukti šio dokumento šiuo būdu'))
        if any(doc.state != 'e_signed' or doc.document_type != 'akcininku_sprendimas' for doc in self):
            raise exceptions.ValidationError(_('Nenumatyta klaida, šio dokumento šiuo būdu atšaukti negalite'))
        if not self._context.get('confirming_cancelling_decision', False) and any(doc.cancelled_ids for doc in self):
            raise exceptions.ValidationError(_('Negalite atšaukti kai kurių dokumentų, nes egzistuoja atšaukiantys '
                                               'dokumentai.'))
        # Basic checks, code to be extended in each template

    @api.multi
    def confirm(self):
        res = super(EDocument, self).confirm()
        if any(rec.document_type == 'akcininku_sprendimas' and not rec.shareholder_ids for rec in self):
            raise exceptions.UserError(_('Nenustatyti akcininkai, kurie pasirašinės šį sprendimą'))
        for rec in self.filtered(lambda d: d.document_type == 'akcininku_sprendimas' and (not d.document_number or d.document_number == '-')):
            rec.write({'document_number': self.env['ir.sequence'].next_by_code('AKCININKU_SPRENDIMAS')})
        return res

    @api.multi
    def create_cancelling_shareholders_decision(self):
        self.ensure_one()
        if self.document_type == 'akcininku_sprendimas' and self.state == 'e_signed' and not self.cancelled_ids:
            template_id = self.env.ref('e_document.akcininku_sprendimas_del_sprendimo_panikinimo_template')
            cancel_id = self.create({
                'document_type': 'akcininku_sprendimas',
                'template_id': template_id.id,
                'employee_id': self.env.user.sudo().company_id.vadovas.id,
                'employee_id2': self.env.user.sudo().company_id.vadovas.id,
                'cancel_id': self.id,
                'shareholder_ids': [(6, 0, self.mapped('shareholder_ids.id'))],
                'date_4': datetime.now(),
            })
            ctx = dict(self._context)
            ctx['robo_header'] = {}
            return {
                'name': _('eDokumentai'),
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_model': 'e.document',
                'view_id': template_id.view_id.id,
                'res_id': cancel_id.id,
                'context': ctx,
            }


EDocument()
