# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools.safe_eval import safe_eval


class Team(models.Model):

    _inherit = 'crm.team'

    #TODO JEM : refactor this stuff with xml action, proper customization,
    @api.model
    def action_your_pipeline(self):
        action = self.env.ref('robo_crm.crm_lead_opportunities_tree_view').read()[0]
        user_team_id = self.env.user.sale_team_id.id
        if not user_team_id:
            user_team_id = self.search([], limit=1).id

        action_context = safe_eval(action['context'], {'uid': self.env.uid})
        if user_team_id:
            action_context['default_team_id'] = user_team_id

        action['context'] = action_context
        return action


Team()


class Lead(models.Model):

    _inherit = 'crm.lead'

    name = fields.Char(string='Užklausa')
    partner_id = fields.Many2one('res.partner', string='Klientas', help="")
    active = fields.Boolean(string='Aktyvus', default=True)
    date_action_last = fields.Datetime(string='Buvęs žingsnis')
    date_action_next = fields.Datetime(string='Kitas žingsnis')
    email_from = fields.Char(string='El. paštas', help="")
    team_id = fields.Many2one(string='Pardavimų komanda', help='')
    kanban_state = fields.Selection(
        [('grey', 'Nesuplanuotas joks žingsnis'), ('red', 'Pradelstas kitas žingsnis'), ('green', 'Kitas žingsnis suplanuotas')],
        string='Žingsnio būsena')
    email_cc = fields.Text(string='Bendras CC', help="")
    description = fields.Text(string='Aprašymas')
    create_date = fields.Datetime(string='Sukūrimo diena')
    write_date = fields.Datetime(string='Atnaujinimo diena')
    tag_ids = fields.Many2many(string='Žymės', help="")
    contact_name = fields.Char(string='Kontaktinis asmuo')
    partner_name = fields.Char(string="Kliento pavadinimas", help='')
    opt_out = fields.Boolean(string='Nedalyvauja reklamoje', help="")
    type = fields.Selection([('lead', 'Iniciatyva'), ('opportunity', 'Užklausa')], help="")
    priority = fields.Selection(string='Reitingas')
    date_closed = fields.Datetime(string='Uždarymo diena')

    stage_id = fields.Many2one(string='Etapas')
    user_id = fields.Many2one(string='Pardavėjas')

    # referred = fields.Char('Referred By')
    #
    # date_open = fields.Datetime('Assigned', readonly=True)
    # day_open = fields.Float(compute='_compute_day_open', string='Days to Assign', store=True)
    # day_close = fields.Float(compute='_compute_day_close', string='Days to Close', store=True)
    date_last_stage_update = fields.Datetime(string='Paskutinis etapo pasikeitimas')
    date_conversion = fields.Datetime('Pasikeitimo diena', readonly=True)

    # Messaging and marketing
    # message_bounce = fields.Integer('Bounce', help="Counter of the number of bounced emails for this contact")

    # Only used for type opportunity
    probability = fields.Float(string='Sėkmės tikimybė')
    planned_revenue = fields.Float(string='Planuojamos pajamos')
    date_deadline = fields.Date(string='Planuojamas terminas')

    # CRM Actions
    next_activity_id = fields.Many2one(string="Kitas žingnis")
    date_action = fields.Date(string='Kito žingnio diena')
    title_action = fields.Char(string='Kito žingnio pavadinimas')

    color = fields.Integer(string='Spalvos indeksas')
    partner_address_name = fields.Char(string='Kliento vardas')
    partner_address_email = fields.Char(string='Kliento el. paštas')
    company_currency = fields.Many2one(string='Valiuta')
    user_email = fields.Char(string='Vartotojo el. paštas')
    user_login = fields.Char(string='Vartotojos prisijungimas')

    # Fields for address, due to separation from crm and res.partner
    street = fields.Char(string='Gatvė')
    # street2 = fields.Char('Street2')
    zip = fields.Char(string='Pašto kodas', change_default=True)
    city = fields.Char(string='Miestas')
    state_id = fields.Many2one(string='Būsena')
    country_id = fields.Many2one(string='Šalis')
    phone = fields.Char(string='Telefonas')
    fax = fields.Char(string='Faksas')
    mobile = fields.Char(string='Mobilus telefonas')
    function = fields.Char(string='Pozicija')
    title = fields.Many2one('res.partner.title')
    company_id = fields.Many2one(string='Kompanija')
    meeting_count = fields.Integer(string='# Susitikimai', compute='_compute_meeting_count')
    lost_reason = fields.Many2one('crm.lost.reason', string='Praradimo priežastis')

    _sql_constraints = [
        ('check_probability', 'check(probability >= 0 and probability <= 100)',
         'Užklausos sėkmės tikimybė turi būti tarp 0% ir 100%!')
    ]

    @api.model
    def translate_terms(self):
        ir_model_fields_obj = self.env['ir.model.fields']
        ir_translation_obj = self.env['ir.translation']
        for field in self._fields:
            field_id = ir_model_fields_obj.search([('name', '=', field), ('model', '=', self._name)], limit=1)
            if field_id:
                translation_ids = ir_translation_obj.search([('res_id', '=', field_id.id),
                                                            ('type', '=', 'model'),
                                                            ('name', '=', 'ir.model.fields,field_description')])
                for translation_id in translation_ids:
                    translation_id.write({
                        'value': translation_id.src,
                    })

    @api.multi
    def robo_action_schedule_meeting(self):
        """ Open meeting's calendar view to schedule meeting on current opportunity.
            :return dict: dictionary value for created Meeting view
        """
        self.ensure_one()
        action = self.env.ref('robo_crm.action_calendar_event').read()[0]
        partner_ids = self.env.user.partner_id.ids
        if self.partner_id:
            partner_ids.append(self.partner_id.id)
        # action['view_id'] = 'robo.hr_holidays_calendar_view'
        action['context'] = {
            'search_default_opportunity_id': self.id if self.type == 'opportunity' else False,
            'default_opportunity_id': self.id if self.type == 'opportunity' else False,
            'default_partner_id': self.partner_id.id,
            'default_partner_ids': partner_ids,
            'default_team_id': self.team_id.id,
            'default_name': self.name,
            'robo_menu_name': self.env.ref('robo_crm.menu_robo_crm_pipline').id
        }
        return action

Lead()


class UtmMixin(models.AbstractModel):
    """Mixin class for objects which can be tracked by marketing. """
    _inherit = 'utm.mixin'

    campaign_id = fields.Many2one(string='Kampanija', help="")
    source_id = fields.Many2one(string='Šaltinis', help="")
    medium_id = fields.Many2one(string='Media', help="")

    # @api.model
    # def update_translation(self):
    #     translations = self.env['ir.translation'].search([('module', '=', 'robo_crm')])
    #     for translation in translations:
    #         translation.write({'value': translation.src})


UtmMixin()