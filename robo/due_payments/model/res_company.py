# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    apr_send_reminders = fields.Boolean(string='Aktyvuoti automatinius priminimus',
                                        help=('Jei užstatyta, klientai su įjungtu priminimų siuntimu gaus el. laiškus.'
                                              ' Jei neužstatyta, nei vienas klientas negaus automatinių priminimų.'),
                                        default=False)

    apr_enabled_by_default = fields.Boolean(string='Aktyvuoti visiems naujai sukurtiems partneriams pagal nutylėjimą',
                                            default=False,
                                            help='Aktyvuoti automatinius priminimus visiems naujai sukurtiems partneriams pagal nutylėjimą')

    apr_send_before = fields.Boolean(string='Siųsti automatinius priminimus prieš mokėjimo terminą',
                                     help='Jei užstatyta, klientas gaus automatinius mokėjimo priminimus prieš mokėjimo terminą',
                                     default=False)
    apr_send_before_ndays = fields.Integer(string='Dienų skaičius iki mokėjimo termino',
                                           help='Priminimas bus siunčiamas ... dienų iki mokėjimo termino',
                                           default=3)

    apr_send_on_date = fields.Boolean(string='Siųsti priminimą termino dieną',
                                      help='Jei užstatyta, klientas gaus automatinius mokėjimo priminimus',
                                      default=False)
    apr_send_after = fields.Boolean(string='Siųsti automatinius priminimus po mokėjimo termino',
                                    help='Jei užstatyta, klientas gaus automatinius mokėjimo priminimus',
                                    default=False)
    apr_send_after_ndays = fields.Integer(string='Dienų skaičius nuo mokėjimo termino',
                                          default=3)
    apr_min_amount_to_send = fields.Float(string='Mažiausia suma, nuo kurios siųsti mokėjimo priminimus',
                                          default=10)
    apr_email_cc = fields.Text(string='Siųsti laiškų kopijas el. paštu')
    apr_email_reply_to = fields.Text(string='Priminimų laiškai atsakomi \'reply-to\'')


ResCompany()
