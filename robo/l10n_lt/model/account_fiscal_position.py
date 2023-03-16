# -*- coding: utf-8 -*-
from odoo import models, fields, _, api


class AccountFiscalPosition(models.Model):
    _inherit = 'account.fiscal.position'

    not_country_id = fields.Many2one('res.country', string='Netaikyti valstybėms',
                                     help='Netaikyti šioms valstybėms')
    not_country_group_id = fields.Many2one('res.country.group', string='Netaikyti valstybių grupėms',
                                           help='Netaikyti šioms valstybių grupėms.')

    @api.model
    def _get_fpos_by_region(self, country_id=False, state_id=False, zipcode=False, vat_required=False):
        if not country_id:
            return False
        base_domain = [('auto_apply', '=', True), ('vat_required', '=', vat_required)]
        if self.env.context.get('force_company'):
            base_domain.append(('company_id', '=', self.env.context.get('force_company')))
        null_state_dom = state_domain = [('state_ids', '=', False)]
        null_zip_dom = zip_domain = [('zip_from', '=', 0), ('zip_to', '=', 0)]
        null_country_dom = [('country_id', '=', False), ('country_group_id', '=', False)]

        if zipcode and zipcode.isdigit():
            zipcode = int(zipcode)
            zip_domain = [('zip_from', '<=', zipcode), ('zip_to', '>=', zipcode)]
        else:
            zipcode = 0

        if state_id:
            state_domain = [('state_ids', '=', state_id)]

        domain_country = base_domain + [('country_id', '=', country_id)]
        domain_group = base_domain + [('country_group_id.country_ids', '=', country_id)]

        # Build domain to search records with exact matching criteria
        fpos = self.search(domain_country + state_domain + zip_domain, limit=1)
        # return records that fit the most the criteria, and fallback on less specific fiscal positions if any can be found
        if not fpos and state_id:
            fpos = self.search(domain_country + null_state_dom + zip_domain, limit=1)
        if not fpos and zipcode:
            fpos = self.search(domain_country + state_domain + null_zip_dom, limit=1)
        if not fpos and state_id and zipcode:
            fpos = self.search(domain_country + null_state_dom + null_zip_dom, limit=1)

        # fallback: country group with no state/zip range
        if not fpos:
            fpos = self.search(domain_group + null_state_dom + null_zip_dom, limit=1)

        # Extra: try additional domains
        domain_extra = base_domain + [('not_country_id', '!=', country_id),
                                      ('not_country_group_id.country_ids', '!=', country_id)]
        if not fpos:
            fpos = self.search(domain_extra + null_state_dom + null_zip_dom, limit=1)

        if not fpos:
            # Fallback on catchall (no country, no group)
            fpos = self.search(base_domain + null_country_dom, limit=1)
        return fpos or False

    @api.model
    def get_fiscal_position(self, partner_id, delivery_id=None):
        """
        Get fiscal position for partner
        :param partner_id: id of the partner record
        :param delivery_id: id of the res.partner record for delivery address, if any
        :return: id of fiscal position if found, False otherwise
        """
        # Override the base Odoo method
        if not partner_id:
            return False
        # This can be easily overriden to apply more complex fiscal rules
        PartnerObj = self.env['res.partner']
        partner = PartnerObj.browse(partner_id)

        # if no delivery use invoicing
        if delivery_id:
            delivery = PartnerObj.browse(delivery_id)
        else:
            delivery = partner

        # partner manually set fiscal position always win
        if delivery.property_account_position_id or partner.property_account_position_id:
            return delivery.property_account_position_id.id or partner.property_account_position_id.id
        fp = False
        # First search only matching VAT positions
        vat_required = bool(partner.vat)
        if vat_required:
            # Try to find the country by VAT code instead of
            vat_country_code = partner.vat[:2]
            country = self.env['res.country'].search([('code', '=', vat_country_code)])
            if country:
                fp = self._get_fpos_by_region(country.id, False, False, True)
            if country and not fp:
                fp = self._get_fpos_by_region(country.id, False, False, False)
        if not fp:
            fp = self._get_fpos_by_region(delivery.country_id.id, delivery.state_id.id, delivery.zip, vat_required)

        # Then if VAT required found no match, try positions that do not require it
        if not fp and vat_required:
            fp = self._get_fpos_by_region(delivery.country_id.id, delivery.state_id.id, delivery.zip, False)

        return fp.id if fp else False

    @api.multi
    def map_tax(self, taxes, product=None, partner=None):
        if self.env.context.get('creation_from_purchase_order'):
            return taxes
        result = self.env['account.tax'].browse()
        if self._context.get('product_type', False):
            product_type = self._context['product_type']
        else:
            product_type = 'product'
        for tax in taxes:
            tax_count = 0
            for t in self.tax_ids:
                if t.tax_src_id == tax and t.product_type == product_type:
                    tax_count += 1
                    if t.tax_dest_id:
                        result |= t.tax_dest_id
            if not tax_count:
                for t in self.tax_ids:
                    if t.tax_src_id == tax and t.product_type == 'all':
                        tax_count += 1
                        if t.tax_dest_id:
                            result |= t.tax_dest_id
            if not tax_count:
                result |= tax
        return result
