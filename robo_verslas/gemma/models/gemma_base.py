# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
from suds.client import Client
from suds.xsd.doctor import Import, ImportDoctor
import logging

_logger = logging.getLogger(__name__)


class GemmaBase(models.AbstractModel):

    _name = 'gemma.base'

    @api.model
    def get_partner_base(self, ext_partner_id):
        if ext_partner_id:
            partner_id = self.env['res.partner'].search([('gemma_ext_id', '=', ext_partner_id)])
            if not partner_id:
                client, code = self.env['gemma.data.import'].get_api()
                country_id = self.env['res.country'].sudo().search([('code', '=', 'LT')], limit=1)
                try:
                    partner_obj = client.service.RlGetASmDuomenys(code, int(ext_partner_id)).diffgram.NewDataSet.Asmenys
                except Exception as e:
                    _logger.info("Gemma partner import: Failed to get partner %s | error %s" % (str(ext_partner_id), e))
                    return
                partner_obj = dict(partner_obj)
                code = partner_obj.get('ASM_AK', '')
                partner_id = self.env['res.partner'].search([('kodas', '=', code)])
                if not partner_id:
                    name = partner_obj.get('ASM_VARDAS', '')
                    surname = partner_obj.get('ASM_PAVARDE', '')
                    if code and name and surname:
                        partner_vals = {
                            'name': name.capitalize() + ' ' + surname.capitalize(),
                            'is_company': False,
                            'kodas': code,
                            'gemma_ext_id': ext_partner_id,
                            'country_id': country_id.id,
                            'property_account_receivable_id': self.env['account.account'].sudo().search(
                                [('code', '=', '2410')],
                                limit=1).id,
                            'property_account_payable_id': self.env['account.account'].sudo().search(
                                [('code', '=', '4430')],
                                limit=1).id,
                        }
                        partner_id = self.env['res.partner'].create(partner_vals)
                    else:
                        body = _('Importuojant partnerį nepateiktas '
                                 'kodas/vardas. Partnerio ID: %s') % (str(ext_partner_id))
                        self.post_message(i_body=body, state='warning')
                        return
                else:
                    if partner_id.gemma_ext_id != ext_partner_id:
                        partner_id.write({'gemma_ext_id': ext_partner_id})
            self.partner_id = partner_id


GemmaBase()

