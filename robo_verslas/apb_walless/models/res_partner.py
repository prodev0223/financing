# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):

    _inherit = 'res.partner'

    vsd_with_royalty = fields.Boolean(string='VSD Pervesti su honoraru')

    # We specify it here, in res_partner, because walless employees aren't employed in the system,
    # thus they don't have the contract
    sodra_royalty_percentage = fields.Selection([('0', 'Nekaupiama'),
                                                 ('1.8', '2.7%'),
                                                 ('3', '3%')],
                                                string='Sodros kaupimo procentas (honorarams)', default='0')


ResPartner()
