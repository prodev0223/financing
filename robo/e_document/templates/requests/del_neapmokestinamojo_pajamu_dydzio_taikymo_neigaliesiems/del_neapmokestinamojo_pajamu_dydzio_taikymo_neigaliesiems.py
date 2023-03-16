# -*- coding: utf-8 -*-
from odoo import models, api, _


class EDocument(models.Model):
    _inherit = 'e.document'

    @api.multi
    def prasymas_del_neapmokestinamojo_pajamu_dydzio_taikymo_neigaliesiems_workflow(self):
        self.ensure_one()
        try:
            subject = _('[{}] Pasirašytas prašymas dėl neapmokestinamojo pajamų dydžio taikymo neįgaliesiems').format(
                self._cr.dbname
            )
            body = _("Sveiki,\ndarbuotojas {} pasirašė prašymą taikyti neįgalumo NPD. \n\nReikėtų patikrinti, ar prie "
                     "pasirašyto prašymo yra prisegtas atitinkamas dokumentas ir pakoreguoti esamą arba sukurti naują "
                     "darbo sutarties priedą su atitinkamu atostogų dienų skaičiumi ir nedarbingumo parametru.").format(
                self.employee_id1.name)
            self.create_internal_ticket(subject, body)
        except Exception:
            message = _('[{}] Failed to create a ticket informing about need for manual fixes. Document ID: {}').format(
                self._cr.dbname, self.id
            )
            self.env['robo.bug'].sudo().create({'user_id': self.env.user.id, 'error_message': message, })


EDocument()
