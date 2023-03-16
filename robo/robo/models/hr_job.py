# -*- coding: utf-8 -*-


from odoo import _, api, fields, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    kodas1 = fields.Many2one('darbo.kodai', string='Profesijos kodas',
                             groups='robo_basic.group_robo_premium_accountant', copy=False)
    kodas2 = fields.Many2one('darbo.kodai', string=' ', groups='robo_basic.group_robo_premium_accountant', copy=False)
    kodas3 = fields.Many2one('darbo.kodai', string=' ', groups='robo_basic.group_robo_premium_accountant', copy=False)
    kodas4 = fields.Many2one('darbo.kodai', string=' ', groups='robo_basic.group_robo_premium_accountant', copy=False)
    domenas1 = fields.Char(string='Domenas', default='zzz', groups='robo_basic.group_robo_premium_accountant',
                           copy=False)
    domenas2 = fields.Char(string='Domenas', default='zzz', groups='robo_basic.group_robo_premium_accountant',
                           copy=False)
    domenas3 = fields.Char(string='Domenas', default='zzz', groups='robo_basic.group_robo_premium_accountant',
                           copy=False)
    name = fields.Char(track_visibility='onchange')
    male_name = fields.Char(string='Vyr. giminės pavadinimas', groups='robo_basic.group_robo_premium_accountant',
                            copy=False, required=False, store=True, track_visibility='onchange')
    female_name = fields.Char(string='Mot. giminės pavadinimas', groups='robo_basic.group_robo_premium_accountant',
                              copy=False, required=False, store=True, track_visibility='onchange')
    work_norm = fields.Float(string=_('Darbo laiko norma (pagal profesiją)'),
                             groups='robo_basic.group_robo_premium_accountant', default=1)
    special_job_type = fields.Selection([
        ('regular', _('Įprasta')),
        ('teachers_and_psychologists', _(
            'Mokyklų, psichologinių, pedagoginių psichologinių tarnybų, vaikų globos įstaigų ir sutrikusio vystymosi kūdikių namų pedagoginiai darbuotojai')),
        ('lecturers_and_study_related', _('Mokslo ir studijų institucijų mokslo darbuotojai')),
        ('art_ppl', _('Profesionaliojo scenos meno įstaigų kūrybiniai darbuotojai')),
        ('nurses', _(
            'Sveikatos priežiūros specialistai, teikiantys sveikatos priežiūros paslaugas, kartu su jais dirbantys darbuotojai, kurie tiesiogiai aptarnauja pacientus arba dirba tomis pačiomis sąlygomis')),
        ('medical_emergency_service_workers',
         _('Sveikatos priežiūros specialistai, teikiantys skubiąją medicinos pagalbą')),
        ('surgeons',
         _('Sveikatos priežiūros specialistai, atliekantys chirurgines operacijas ar dalyvaujantys jas atliekant')),
        ('forced_medical_help_workers', _(
            'Sveikatos priežiūros specialistai, dirbantys asmens sveikatos priežiūros įstaigose su pacientais, kuriems taikoma priverstinė hospitalizacija')),
        ('psychologists_in_special_cases', _('Psichologai ir socialinių paslaugų srities darbuotojai')),
        ('pharmacy_workers', _('Farmacijos specialistai')),
        ('social_workers', _(
            'Socialinių paslaugų srities darbuotojai, dirbantys priverstinio laikymo, švietimo įstaigose ar su socialinės rizikos suaugusiais žmonėmis')),
        ('airplane_pilot_and_navigation_instructors', _(
            'Pilotai instruktoriai, vyriausiasis navigatorius, navigatoriai instruktoriai, skraidantieji inžinieriai instruktoriai')),
        ('pilots_and_navigators', _(
            'Orlaivių vadai, pilotai, navigatoriai, skraidantieji inžinieriai, skraidantieji operatoriai, orlaivių palydovai')),
        ('pilots_testers', _('Pilotai bandytojai')),
        ('lithuanian_air_space_regular_employees', _('Skrydžių vadovai, vyresnieji skrydžių vadovai')),
        ('lithuanian_air_space_senior_employees',
         _('Skrydžių vadovai instruktoriai, skrydžių valdymo centrų pamainų viršininkai')),
        ('seamen', _('Jūrininkai, dirbantys LR jūrų laivų registre įregistruotuose laivuose')),
        ('fishermen', _('Darbuotojai, dirbantys žvejybos laivuose, užsiimančiuose žvejyba')),
        ('biohazard_scientists', _(
            'Darbuotojai, kurie dirba darbą, tiesiogiai susijusį su gyvūnų patologine medžiaga, arba atlieka tyrimus, susijusius su gyvūnais')),
        ('environment_scientists',
         _('LR aplinkos ministerijai pavaldžių įstaigų darbuotojai, atliekantys tyrimus ir matavimus')),
    ], string='Pareigų kategorija', default='regular',
        help='Pagal nustatytą kategoriją - bus priskiriama skirtinga atostogų norma per metus')

    @api.onchange('kodas1')
    def loadsarasas2(self):
        if self.kodas1:
            self.domenas1 = self.kodas1.kodas + '_'
        self.domenas2 = False
        self.domenas3 = False
        self.kodas2 = False
        self.kodas3 = False
        self.kodas4 = False

    @api.onchange('kodas2')
    def loadsarasas3(self):
        if self.kodas2:
            self.domenas2 = self.kodas2.kodas + '_'
        self.domenas3 = False
        self.kodas3 = False
        self.kodas4 = False

    @api.onchange('kodas3')
    def loadsarasas4(self):
        if self.kodas3:
            self.domenas3 = self.kodas3.kodas + '_'
        self.kodas4 = False
