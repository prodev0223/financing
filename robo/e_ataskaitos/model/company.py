# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions
from odoo.tools.sql import drop_view_if_exists
from ..e_vmi_tools import SKYRIAI


class EVRKKodai(models.Model):

    _name = 'evrk.kodai'

    name = fields.Char(string='Pavadinimas')
    code = fields.Char(string='Kodas')
    active = fields.Boolean(string='Aktyvus')

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            if record.code:
                result.append((record.id, "[%s] %s" % (record.code, record.name)))
            else:
                result.append((record.id, "%s" % record.name))

        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not args:
            args = []
        args = args[:]
        if name:
            recs = self.search(
                ['|', ('code', operator, name), ('name', operator, name)] + args,
                limit=limit)
        else:
            recs = self.search(args, limit=limit)
        return recs.name_get()

EVRKKodai()


class EVRKCompany(models.Model):

    _inherit = 'res.company'

    evrk = fields.Many2one('evrk.kodai', string='EVRK kodas')
    savivaldybe = fields.Selection(SKYRIAI, string='Savivaldybė', default='13', required=True)

    substitute_report_partner = fields.Many2one('res.partner')

    @api.multi
    def get_report_company_data(self):
        """
        Returns name, code and vat_code of
        the current company, or if set, of the
        substitute partner
        :return: company data (dict)
        """
        self.ensure_one()
        # If substitute partner is set, use it's data

        partner = self.substitute_report_partner or self.partner_id
        data = {
            'code': partner.kodas or str(),
            'name': (partner.name or str()).replace('&', '&amp;'),
            'vat_code': partner.vat or str(),
            'fax': partner.fax or str(),
            'street': partner.street or str(),
            'city': partner.city or str(),
            'phone': partner.phone or str(),
            'email': partner.email or str(),
            'full_address': '{}, {}'.format(partner.street, partner.city)[:45] if partner.street else ' ',
        }
        return data


EVRKCompany()


class DarbuotojaiSavivaldybe(models.Model):

    _inherit = 'hr.employee'

    savivaldybe = fields.Selection(SKYRIAI, string='Savivaldybė')

    @api.constrains('savivaldybe')
    def _check_savivaldybe(self):
        for rec in self:
            if not rec.is_non_resident and not rec.savivaldybe:
                raise exceptions.ValidationError(_('It is required to set declared place of residence if employee '
                                                   'is a resident.'))


DarbuotojaiSavivaldybe()
