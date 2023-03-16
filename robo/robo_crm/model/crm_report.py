# -*- coding: utf-8 -*-
from odoo import fields, models, _


class OpportunityReport(models.Model):
    """ CRM Opportunity Analysis """

    _inherit = "crm.opportunity.report"

    date_deadline = fields.Date(string='Numatomas terminas')
    create_date = fields.Datetime(string='Sukūrimo diena')
    opening_date = fields.Datetime(string='Priskyrimo diena')
    date_closed = fields.Datetime(string='Pabaigos data')
    date_last_stage_update = fields.Datetime(string='Paskutinis etapo atnaujinimas')
    active = fields.Boolean(string='Aktyvus')

    # durations
    delay_open = fields.Float('Priskyrimo trukmė', help="")
    delay_close = fields.Float('Uždarymo trukmė', help="")
    delay_expected = fields.Float('Praėjęs terminas')

    user_id = fields.Many2one(string='User')
    team_id = fields.Many2one(string='Pardavimų komanda')
    nbr_activities = fields.Integer(string='#Žingsnių')
    city = fields.Char(string='Miestas')
    country_id = fields.Many2one(string='Šalis')
    probability = fields.Float(string='Tikimybė')
    total_revenue = fields.Float(string='Viso pajamų')
    expected_revenue = fields.Float(string='Tikėtina apyvarta')
    stage_id = fields.Many2one(string='Etapas')
    stage_name = fields.Char(string='Etapo pavadinimas')
    partner_id = fields.Many2one(string='Klientas')
    company_id = fields.Many2one(string='Kompanija')
    priority = fields.Selection(string='Prioritetas')
    type = fields.Selection([
        ('lead', 'Iniciatyva'),
        ('opportunity', 'Užklausa'),
    ], help="")
    lost_reason = fields.Many2one(string='Praradimo priežastis')
    date_conversion = fields.Datetime(string='Susirašinėjimo diena')


OpportunityReport()


class ActivityReport(models.Model):
    """ CRM Lead Analysis """

    _inherit = "crm.activity.report"

    date = fields.Datetime('Diena')
    author_id = fields.Many2one(string='Sukurta')
    user_id = fields.Many2one(string='Pardavėjas')
    team_id = fields.Many2one(string='Pardavimų komanda')
    lead_id = fields.Many2one(string="Iniciatyva")
    subject = fields.Char(string='Aprašymas')
    subtype_id = fields.Many2one(string='Žingnis')
    country_id = fields.Many2one(string='Šalis')
    company_id = fields.Many2one(string='Kompanija')
    stage_id = fields.Many2one(string='Etapas')
    partner_id = fields.Many2one(string='Partneris/Klientas')
    lead_type = fields.Char(
        string='tipas',
        selection=[('lead', 'Iniciatyva'), ('opportunity', 'Užklausa')],
        help="")
    active = fields.Boolean(string='Aktyvus')
    probability = fields.Float(string='Tikimybė')


ActivityReport()
