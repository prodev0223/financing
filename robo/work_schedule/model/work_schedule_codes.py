# -*- coding: utf-8 -*-

from odoo import models, fields


class WorkScheduleCodes(models.Model):
    _name = 'work.schedule.codes'

    tabelio_zymejimas_id = fields.Many2one('tabelio.zymejimas', string='Tabelio Žymėjimas')
    is_overtime = fields.Boolean(string='Naudojamas žymėti papildomus darbus')
    is_holiday = fields.Boolean(string='Naudojamas žymėti atostogas')
    is_absence = fields.Boolean(string='Naudojamas žymėti neatvykimus')
    is_whole_day = fields.Boolean(string='Žymima visa diena')
    can_only_be_set_by_accountants = fields.Boolean(string='Gali būti nustatoma tik buhalterio')
    code = fields.Char(string='Tabelio žymėjimo kodas', related='tabelio_zymejimas_id.code')
    name = fields.Char(string='Tabelio žymėjimo pavadinimas', related='tabelio_zymejimas_id.name')


WorkScheduleCodes()