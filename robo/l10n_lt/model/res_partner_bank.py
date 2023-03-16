# -*- coding: utf-8 -*-
import re
from odoo import fields, models, api, exceptions, _
from odoo.addons.base_iban.models.res_partner_bank import validate_iban


def sanitize_account_number(acc_number):
    if acc_number:
        return re.sub(r'\W+', '', acc_number).upper()
    return False


class ResPartnerBank(models.Model):
    _inherit = 'res.partner.bank'

    acc_number = fields.Char(inverse='_inv_acc_number')
    active = fields.Boolean(string='Active', default=True)
    partner_id = fields.Many2one('res.partner', required=True)

    @api.model_cr
    def init(self):
        try:
            self._cr.execute('''
            ALTER TABLE res_partner_bank DROP CONSTRAINT res_partner_bank_unique_number;

            ALTER TABLE res_partner_bank ADD CONSTRAINT res_partner_bank_unique_number UNIQUE (sanitized_acc_number,currency_id)
            ''')
        except:
            pass

    @api.onchange('acc_number')
    def onchange_acc_number(self):
        self.acc_number = sanitize_account_number(self.acc_number)
        if self.acc_number and len(self.acc_number) >= 9:
            bank_code = self.acc_number[4:9]
            bank_id = self.env['res.bank'].search([('kodas', '=', bank_code)], limit=1)
            if not bank_id:
                bank_id = self.env['res.bank'].search([('kodas', '=like', bank_code[:3] + '%')], limit=1)
            if bank_id:
                self.bank_id = bank_id.id

    @api.one
    def _inv_acc_number(self):
        if self.acc_number and len(self.acc_number) >= 9 and not self.bank_id:
            bank_code = self.acc_number[4:9]
            bank_id = self.env['res.bank'].search([('kodas', '=', bank_code)], limit=1)
            if not bank_id:
                bank_id = self.env['res.bank'].search([('kodas', '=like', bank_code[:3] + '%')], limit=1)
            if bank_id:
                self.bank_id = bank_id.id
            elif self.acc_number.startswith('LT'):
                raise exceptions.ValidationError(
                    _('Account {} does not have related bank set. '
                      'Please create corresponding bank record or contact your accountant').format(self.acc_number)
                )

    @api.model
    def create(self, vals):
        if 'acc_number' in vals:
            vals['acc_number'] = sanitize_account_number(vals['acc_number'])
        return super(ResPartnerBank, self).create(vals)

    @api.multi
    def write(self, vals):
        if 'acc_number' in vals:
            vals['acc_number'] = sanitize_account_number(vals['acc_number'])
        return super(ResPartnerBank, self).write(vals)

    @api.multi
    @api.constrains('acc_number')
    def _check_iban(self):
        force_iban_country_codes = ['LT']
        for rec in self:
            if rec.acc_type == 'iban' or rec.acc_number and rec.acc_number[:2].upper() in force_iban_country_codes:
                validate_iban(rec.acc_number)

    @api.model
    def default_get(self, field_list):
        res = super(ResPartnerBank, self).default_get(field_list)
        res.update({
            'acc_number': self._context.get('default_name', ''),
        })
        return res
