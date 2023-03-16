# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions
from odoo.tools import float_is_zero
from odoo.tools.translate import _
from datetime import datetime
from odoo import tools
from dateutil.relativedelta import relativedelta

payroll_parameter_field_identifiers = (
    'sodra_papild_proc', 'gpm_proc', 'gpm_ligos_proc', 'darbuotojo_pensijos_proc', 'darbuotojo_sveikatos_proc',
    'darbdavio_sodra_proc', 'darbdavio_pensiju_draudimo_proc', 'darbdavio_ligos_draudimo_proc',
    'darbdavio_motinystes_draudimo_proc', 'darbdavio_nedarbo_draudimo_proc', 'darbdavio_psd_proc',
    'darbdavio_garantinio_fondo_proc', 'darbdavio_ilgalaikio_darbo_proc', 'darbdavio_nelaimingu_atsitikimu_proc',
    'sodra_lubos_amount', 'gpm_lubos_proc', 'sodra_papild_exponential_proc', 'npd_max', 'npd_0_25_max', 'npd_30_55_max',
    'mma', 'mma_first_day_of_year', 'min_hourly_rate', 'npd_koeficientas', 'dn_coefficient', 'dp_coefficient',
    'vd_coefficient', 'vdn_coefficient', 'vss_coefficient', 'snv_coefficient', 'ligos_koeficientas',
    'term_contract_additional_sodra_proc', 'num_work_days_a_year', 'num_work_days_a_year_6_days_week',
    'gpm_du_unrelated', 'max_overtime_per_year', 'max_7_day_time', 'max_7_day_sumine_apskaita_time',
    'max_7_day_overtime_time', 'max_7_day_including_extra_time', 'employee_tax_fund_foreigner_with_visa_pct',
    'employer_sodra_foreigner_with_visa_pct', 'average_wage', 'under_avg_wage_npd_coefficient',
    'under_avg_wage_npd_max', 'under_avg_wage_minimum_wage_for_npd', 'above_avg_wage_npd_coefficient',
    'above_avg_wage_npd_max', 'above_avg_wage_minimum_wage_for_npd'
)
# Old/unused payroll parameters that are not fields on res.company
other_payroll_parameter_selections = [
    ('darbuotojo_pensijos_proc', 'Darbuotojo mokami mokesčiai į pensijų fondą proc.'),
    ('darbuotojo_sveikatos_proc', 'Darbuotojo mokamas sveikatos draudimas proc.'),
    ('darbdavio_sodra_proc', 'Darbdavio sodros dydis proc.'),
    ('darbdavio_pensiju_draudimo_proc', 'Darbdavio pensijų draudimo dydis proc.'),
    ('darbdavio_ligos_draudimo_proc', 'Darbdavio ligos draudimo dydis proc.'),
    ('darbdavio_motinystes_draudimo_proc', 'Darbdavio motinystės draudimo dydis proc.'),
    ('darbdavio_nedarbo_draudimo_proc', 'Darbdavio nedarbo draudimo dydis proc.'),
    ('darbdavio_psd_proc', 'Darbdavio privalomajo socialinio draudimo dydis proc.'),
    ('darbdavio_garantinio_fondo_proc', 'Darbdavio garantinio fondo dydis proc.'),
    ('darbdavio_ilgalaikio_darbo_proc', 'Darbdavio ilgalaikio darbo dydis proc.'),
    ('darbdavio_nelaimingu_atsitikimu_proc', 'Darbdavio nelaimingų atsitikimų draudimo dydis proc.'),
    ('sodra_lubos_amount', 'Sodros/GPM lubų dydis'),
    ('gpm_lubos_proc', 'GPM viršijus lubas dydis proc.'),
    ('num_work_days_a_year_6_days_week', 'Darbo dienų skaičius metuose dirbant 6 dienas per savaitę'),
]



DEFAULT_ACCOUNT_DOMAIN = [('is_view', '=', False), ('deprecated', '=', False)]


class HrPayrollConfigSettings(models.TransientModel):

    _inherit = 'hr.payroll.config.settings'

    def _default_has_default_company(self):
        return self.env['res.company'].search_count([]) == 1

    has_default_company = fields.Boolean(readonly=True,
                                         default=lambda self: self._default_has_default_company())
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)
    salary_journal_id = fields.Many2one('account.journal', string='Atlyginimų žurnalas',
                                         related='company_id.salary_journal_id')
    advance_journal_id = fields.Many2one('account.journal', string='Avansų žurnalas',
                                         related='company_id.advance_journal_id')
    saskaita_debetas = fields.Many2one('account.account', string='DU sąnaudų sąskaita',
                                        related='company_id.saskaita_debetas')
    saskaita_komandiruotes = fields.Many2one('account.account', string='Komandiruočių sąnaudų sąskaita', related='company_id.saskaita_komandiruotes')
    saskaita_kreditas = fields.Many2one('account.account', string='DU įsipareigojimų sąskaita',
                                       related='company_id.saskaita_kreditas')
    saskaita_gpm = fields.Many2one('account.account', string='GPM įsipareigojimų sąskaita',
                                   related='company_id.saskaita_gpm')
    saskaita_sodra = fields.Many2one('account.account', string='Iš DU mokėtina sodros sąskaita',
                                     related='company_id.saskaita_sodra')
    sodra_papild_proc = fields.Float(string='Papildomo sodros mokesčio dydis proc.',
                                     related='company_id.sodra_papild_proc', readonly=True)
    sodra_papild_exponential_proc = fields.Float(string='Papildomo sodros mokesčio dydis proc.',
                                                 related='company_id.sodra_papild_exponential_proc', readonly=True)
    gpm_proc = fields.Float(string='Gyventojų pajamų mokesčio dydis proc.', related='company_id.gpm_proc', readonly=True)
    gpm_ligos_proc = fields.Float(string='Gyventojų pajamų mokesčio ligų dydis proc.',
                                  related='company_id.gpm_ligos_proc', readonly=True)
    darbuotojo_pensijos_proc = fields.Float(string='Darbuotojo mokami mokesčiai į pensijų fondą proc.',
                                            related='company_id.darbuotojo_pensijos_proc', readonly=True)
    darbuotojo_sveikatos_proc = fields.Float(string='Darbuotojo mokamas sveikatos draudimas proc.',
                                             related='company_id.darbuotojo_sveikatos_proc', readonly=True)
    darbdavio_sodra_proc = fields.Float(string='Darbdavio sodros dydis proc.',
                                        related='company_id.darbdavio_sodra_proc', readonly=True)
    term_contract_additional_sodra_proc = fields.Float(string='Terminuotos sutarties papildomas sodros dydis proc.',
                                                       related='company_id.term_contract_additional_sodra_proc', readonly=True)
    npd_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų dydis',
                           related='company_id.npd_max', readonly=True)
    npd_0_25_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų 0-25% darbingumo dydis',
                                related='company_id.npd_0_25_max', readonly=True)
    npd_30_55_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų 30-55% darbingumo dydis',
                                 related='company_id.npd_30_55_max', readonly=True)
    mma = fields.Float(string='Minimalus mėnesinis atlyginimas', related='company_id.mma', readonly=True)
    mma_first_day_of_year = fields.Float(string='Minimalus mėnesinis atlyginimas pirmąją metų dieną',
                                         related='company_id.mma_first_day_of_year', readonly=True)
    min_hourly_rate = fields.Float(string='Minimalus valandinis atlyginimas', related='company_id.min_hourly_rate', readonly=True)
    npd_koeficientas = fields.Float(string='Koeficiento skaičiuojant pritaikomą NPD dydis',
                                    help="npd=max_npd-kof*(alga-mma_first_day_of_year)", related='company_id.npd_koeficientas', readonly=True)
    # darbdavio_sodra_credit = fields.Many2one('account.account', string='Darbdavio sodros kreditinė sąskaita',
    #                                          related='company_id.darbdavio_sodra_credit')
    darbdavio_sodra_debit = fields.Many2one('account.account', string='Darbdavio sodros debetinė sąskaita',
                                             related='company_id.darbdavio_sodra_debit')

    # advance payments policy
    avansu_politika = fields.Selection([('fixed_sum', 'Fiksuota suma')
                                           # , ('percent', 'Procentas')
                                        ],
                                       string='Avansų politika', related='company_id.avansu_politika',
                                       default='fixed_sum', readonly=True)
    avansu_politika_proc = fields.Float(string='Procentas, %', related='company_id.avansu_politika_proc')

    max_advance_rate_proc = fields.Float(string='Didžiausia leidžiama avanso dalis nuo neto atlyginimo',
                                         related='company_id.max_advance_rate_proc')

    salary_payment_day = fields.Integer(string='Salary payment day', related='company_id.salary_payment_day')
    advance_payment_day = fields.Integer(string='Advance payment day', related='company_id.advance_payment_day')

    dn_coefficient = fields.Float(string='DN koeficientas', related='company_id.dn_coefficient',
                                  help='Darbo naktį koeficientas', readonly=True)
    dp_coefficient = fields.Float(string='DP koeficientas', related='company_id.dp_coefficient',
                                  help='Papildomo darbo koeficientas', readonly=True)
    vd_coefficient = fields.Float(string='VD koeficientas', related='company_id.vd_coefficient',
                                  help='Viršvalandinio darbo koeficientas', readonly=True)
    vdn_coefficient = fields.Float(string='VDN koeficientas', related='company_id.vd_coefficient',
                                  help='Viršvalandinio darbo naktį koeficientas', readonly=True)
    vss_coefficient = fields.Float(string='VSS koeficientas', related='company_id.vss_coefficient',
                                   help='Viršvalandinio darbo savaitgaliais ir švenčių dienomis koeficientas', readonly=True)
    snv_coefficient = fields.Float(string='SNV koeficientas', related='company_id.snv_coefficient',
                                   help='Darbo naktį šventinėmis dienomis koeficientas', readonly=True)
    ligos_koeficientas = fields.Float(string='Ligos koeficientas',
                                      help='Ligos atveju darbdavio apmokamos darbo užmokesčio dalies koeficientas',
                                      related='company_id.ligos_koeficientas', readonly=True)
    payroll_bank_journal_id = fields.Many2one('account.journal', string='Darbo užmokesčio banko žurnalas',
                                              domain="[('type', '=', 'bank')]",
                                              help='Banko žurnalas, naudojamas darbo užmokesčio mokėjimams',
                                              related='company_id.payroll_bank_journal_id')
    atostoginiu_kaupiniai_account_id = fields.Many2one('account.account', string='Atostogų kaupinių sąskaita',
                                                       domain=DEFAULT_ACCOUNT_DOMAIN,
                                                       related='company_id.atostoginiu_kaupiniai_account_id')
    kaupiniai_expense_account_id = fields.Many2one('account.account', string='Atostogų sąnaudų kaupinių sąskaita',
                                                       domain=DEFAULT_ACCOUNT_DOMAIN,
                                                       related='company_id.kaupiniai_expense_account_id')
    saskaita_komandiruotes_credit = fields.Many2one('account.account', string='Dienpinigių kredito sąskaita',
                                        domain=DEFAULT_ACCOUNT_DOMAIN,
                                       related='company_id.saskaita_komandiruotes_credit')
    kiti_atskaitymai_credit = fields.Many2one('account.account', string='Kiti atskaitymai kreditas',
                                              domain=DEFAULT_ACCOUNT_DOMAIN,
                                              related='company_id.kiti_atskaitymai_credit')
    employee_advance_account = fields.Many2one('account.account', string='Employee advance account',
                                              domain=DEFAULT_ACCOUNT_DOMAIN,
                                              related='company_id.employee_advance_account')
    gpm_du_unrelated = fields.Float(string='GPM A klasės išmokoms nesusijusioms su darbo užmokesčiu',
                                    related='company_id.gpm_du_unrelated')
    max_overtime_per_year = fields.Float('Maksimali viršvalandžių trukmė per metus (h.)',
                                         related='company_id.max_overtime_per_year')
    max_7_day_time = fields.Float('Maksimalus darbo laikas per 7 dienas (h.)', related='company_id.max_7_day_time')
    max_7_day_sumine_apskaita_time = fields.Float(
        'Maksimalus darbo laikas per 7 dienas dirbant sumine darbo laiko apskaita (h.)',
        related='company_id.max_7_day_sumine_apskaita_time')
    max_7_day_including_extra_time = fields.Float('Maksimalus darbo laikas per 7 dienas įskaitant papildomą darbą (h.)',
                                                  related='company_id.max_7_day_including_extra_time')
    max_7_day_overtime_time = fields.Float('Maksimalus viršvalandžių laikas per 7 dienas (h.)',
                                           related='company_id.max_7_day_overtime_time')
    employee_tax_fund_foreigner_with_visa_pct = fields.Float(
        string='Darbuotojo užsieniečio su viza mokami mokesčiai į pensijų fondą proc.',
        related='company_id.employee_tax_fund_foreigner_with_visa_pct')
    employer_sodra_foreigner_with_visa_pct = fields.Float(
        string='Darbdavio SoDros dydis, kai darbuotojas yra užsienietis su viza, proc.',
        related='company_id.employer_sodra_foreigner_with_visa_pct')
    average_wage = fields.Float(string='Average wage in Lithuania',
                                related='company_id.average_wage')
    under_avg_wage_npd_coefficient = fields.Float(string='NPD coefficient for wage under average',
                                                  related='company_id.under_avg_wage_npd_coefficient')
    under_avg_wage_npd_max = fields.Float(string='Maximum NPD amount for wage under average',
                                                  related='company_id.under_avg_wage_npd_max')
    under_avg_wage_minimum_wage_for_npd = fields.Float(
        string='Minimum wage used in NPD calculations for wage under average',
        related='company_id.under_avg_wage_minimum_wage_for_npd')
    above_avg_wage_npd_coefficient = fields.Float(string='NPD coefficient for wage above average',
                                                  related='company_id.above_avg_wage_npd_coefficient')
    above_avg_wage_npd_max = fields.Float(string='Maximum NPD amount for wage above average',
                                                  related='company_id.above_avg_wage_npd_max')
    above_avg_wage_minimum_wage_for_npd = fields.Float(
        string='Minimum wage used in NPD calculations for wage above average',
        related='company_id.above_avg_wage_minimum_wage_for_npd')


HrPayrollConfigSettings()


class ResCompany(models.Model):

    _inherit = 'res.company'

    def default_salary_journal(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', 'ATLY')], limit=1)

    def default_advance_journal(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', 'ATLY')], limit=1)

    def default_saskaita_kreditas(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', '4480')], limit=1)

    def default_saskaita_debetas(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', '62031')], limit=1)

    def default_darbdavio_sodra_debit(self):
        return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', '62031')], limit=1)

    def default_saskaita_gpm(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', '4481')], limit=1)

    def default_saskaita_sodra(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', '4482')], limit=1)

    def _default_saskaita_komandiruotes(self):
        if self.id:
            return self.env['account.account'].search([('company_id', '=', self.id), ('code', '=', '62032')], limit=1)

    def default_saskaita_komandiruotes_credit(self):
        return self.env['account.account'].search([('code', '=', '4483')], limit=1)

    def default_kiti_atskaitymai_credit(self):
        return self.env['account.account'].search([('code', '=', '4484')], limit=1)

    def default_employee_advance_account(self):
        return self.env['account.account'].search([('code', '=', '4489')], limit=1)

    def default_atostoginiu_kaupiniai_account_id(self):
        return self.env['account.account'].search([('code', '=', '4485')], limit=1)

    def default_atostoginiu_kaupiniai_sanaudos_account_id(self):
        return self.env['account.account'].search([('code', '=', '62034')], limit=1)

    salary_journal_id = fields.Many2one('account.journal', string='Atlyginimų žurnalas', default=default_salary_journal)
    advance_journal_id = fields.Many2one('account.journal', string='Avansų žurnalas', default=default_advance_journal)
    saskaita_debetas = fields.Many2one('account.account', string='DU sąnaudų sąskaita', default=default_saskaita_debetas,
                                        domain=DEFAULT_ACCOUNT_DOMAIN, inverse='set_salary_rule_debit_accounts')
    saskaita_kreditas = fields.Many2one('account.account', string='DU įsipareigojimų sąskaita', default=default_saskaita_kreditas,
                                       domain=DEFAULT_ACCOUNT_DOMAIN, inverse='set_salary_rule_mok_accounts' )
    saskaita_gpm = fields.Many2one('account.account', string='GPM įsipareigojimų sąskaita', default=default_saskaita_gpm,
                                   domain=DEFAULT_ACCOUNT_DOMAIN, inverse='set_salary_rule_gpm_accounts')
    saskaita_sodra = fields.Many2one('account.account', string='Iš DU mokėtina sodros sąskaita', default=default_saskaita_sodra,
                                     domain=DEFAULT_ACCOUNT_DOMAIN, inverse='set_salary_rule_sodra_accounts')
    sodra_papild_proc = fields.Float(string='Papildomo sodros mokesčio dydis proc.', compute='_sodra_papild_proc')
    sodra_papild_exponential_proc = fields.Float(string='Papildomo sodros mokesčio dydis proc.', compute='_sodra_papild_exponential_proc')
    saskaita_komandiruotes_credit = fields.Many2one('account.account', string='Dienpinigių kredito sąskaita', default=default_saskaita_komandiruotes_credit,
                                    domain=DEFAULT_ACCOUNT_DOMAIN)
    gpm_proc = fields.Float(string='Gyventojų pajamų mokesčio dydis proc.', compute='_gpm_proc')
    gpm_ligos_proc = fields.Float(string='Gyventojų pajamų mokesčio ligų dydis proc.', compute='_gpm_ligos_proc')
    darbuotojo_pensijos_proc = fields.Float(string='Darbuotojo mokami mokesčiai į pensijų fondą proc.', compute='_darbuotojo_pensijos_proc')
    darbuotojo_sveikatos_proc = fields.Float(string='Darbuotojo mokamas sveikatos draudimas proc.', compute='_darbuotojo_sveikatos_proc')
    darbdavio_sodra_proc = fields.Float(string='Darbdavio sodros dydis proc.', compute='_darbdavio_sodra_proc')
    term_contract_additional_sodra_proc = fields.Float(string='Terminuotos sutarties papildomas sodros dydis proc.', compute='_additional_sodra_proc')
    npd_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų dydis', compute='_npd_max')
    npd_0_25_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų 0-25% darbingumo dydis',
                                compute='_npd_0_25_max')
    npd_30_55_max = fields.Float(string='Maksimalus mėnesinių neapmokestinamų pajamų 30-55% darbingumo dydis',
                                 compute='_npd_30_55_max')
    mma = fields.Float(string='Minimalus mėnesinis atlyginimas', compute='_mma')
    num_work_days_a_year = fields.Float(string='Darbo dienų skaičius metuose', compute='_num_work_days_a_year')
    mma_first_day_of_year = fields.Float(string='Minimalus mėnesinis atlyginimas pirmąją metų dieną',
                                         compute='_mma_first_day_of_year')
    min_hourly_rate = fields.Float(string='Minimalus valandinis atlyginimas', compute='_min_hourly_rate')
    npd_koeficientas = fields.Float(string='Koeficiento skaičiuojant pritaikomą NPD dydis',
                                    help="npd=max_npd-kof*(alga-mma_first_day_of_year)", compute='_npd_koeficientas')
    # darbdavio_sodra_credit = fields.Many2one('account.account', string='Darbdavio sodros kreditinė sąskaita')
    darbdavio_sodra_debit = fields.Many2one('account.account', string='Darbdavio sodros debetinė sąskaita', default=default_darbdavio_sodra_debit)

    avansu_politika = fields.Selection([('fixed_sum', 'Fiksuota suma')
                                        ], string='Avansų politika', default='fixed_sum', readonly=True)
    avansu_politika_proc = fields.Float(string='Pagrindinis avansų procentas')
    max_advance_rate_proc = fields.Float(string='Didžiausia leidžiama avanso dalis nuo neto atlyginimo', default=50.0)

    salary_payment_day = fields.Integer(string='Salary payment day', default=14)
    advance_payment_day = fields.Integer(string='Advance payment day', default=20)

    dn_coefficient = fields.Float(string='DN koeficientas', help='Darbo naktį koeficientas', compute='_dn_coefficient')
    dp_coefficient = fields.Float(string='DP koeficientas', help='Papildomo darbo koeficientas',
                                  compute='_dp_coefficient')
    vd_coefficient = fields.Float(string='VD koeficientas', help='Viršvalandinio darbo koeficientas', compute='_vd_coefficient')
    vdn_coefficient = fields.Float(string='VDN koeficientas', help='Viršvalandinio darbo naktį koeficientas',
                                   compute='_vdn_coefficient')
    vss_coefficient = fields.Float(string='VSS koeficientas', compute='_vss_coefficient',
                                   help='Viršvalandinio darbo savaitgaliais ir švenčių dienomis koeficientas')
    snv_coefficient = fields.Float(string='SNV koeficientas', compute='_snv_coefficient',
                                   help='Darbo naktį šventinėmis dienomis koeficientas')
    ligos_koeficientas = fields.Float(string='Ligos koeficientas',
                                      help='Ligos atveju darbdavio apmokamos darbo užmokesčio dalies koeficientas',
                                      compute='_ligos_koeficientas')
    payroll_bank_journal_id = fields.Many2one('account.journal', string='Darbo užmokesčio banko žurnalas',
                                              domain="[('type', '=', 'bank')]",
                                              help='Banko žurnalas, naudojamas darbo užmokesčio mokėjimams')
    atostoginiu_kaupiniai_account_id = fields.Many2one('account.account', string='Atostogų kaupinių sąskaita',
                                                       default=default_atostoginiu_kaupiniai_account_id)
    kaupiniai_expense_account_id = fields.Many2one('account.account', string='Atostogų kaupinių sąnaudų sąskaita',
                                                   default=default_atostoginiu_kaupiniai_sanaudos_account_id)
    saskaita_komandiruotes = fields.Many2one('account.account', string='Komandiruočių sąnaudų sąskaita',
                                             default=_default_saskaita_komandiruotes)
    payroll_param_history_ids = fields.One2many('payroll.parameter.history', 'company_id', string='Darbo apskaitos paramentrų istorija')
    kiti_atskaitymai_credit = fields.Many2one('account.account', string='Kiti atskaitymai kreditas',
                                              domain=DEFAULT_ACCOUNT_DOMAIN,
                                              default=default_kiti_atskaitymai_credit)
    employee_advance_account = fields.Many2one('account.account', string='Employee advance account',
                                              domain=DEFAULT_ACCOUNT_DOMAIN,
                                              default=default_employee_advance_account)
    gpm_du_unrelated = fields.Float(string='GPM A klasės išmokoms nesusijusioms su darbo užmokesčiu', compute='gpm_du_unrelated_proc')
    max_overtime_per_year = fields.Float('Maksimali viršvalandžių trukmė per metus (h.)',
                                         compute='_compute_max_overtime_per_year')
    max_7_day_time = fields.Float('Maksimalus darbo laikas per 7 dienas (h.)', compute='_compute_max_7_day_time')
    max_7_day_sumine_apskaita_time = fields.Float(
        'Maksimalus darbo laikas per 7 dienas dirbant sumine darbo laiko apskaita (h.)',
        compute='_compute_max_7_day_sumine_apskaita_time')
    max_7_day_including_extra_time = fields.Float('Maksimalus darbo laikas per 7 dienas įskaitant papildomą darbą (h.)',
                                                  compute='_compute_max_7_day_including_extra_time')
    max_7_day_overtime_time = fields.Float('Maksimalus viršvalandžių laikas per 7 dienas (h.)',
                                           compute='_compute_max_7_day_overtime_time')
    employee_tax_fund_foreigner_with_visa_pct = fields.Float(string='Darbuotojo užsieniečio su viza mokami mokesčiai į pensijų fondą proc.',
                                                             compute='_compute_employee_tax_fund_foreigner_with_visa_pct')
    employer_sodra_foreigner_with_visa_pct = fields.Float(string='Darbdavio SoDros dydis, kai darbuotojas yra užsienietis su viza, proc.',
                                                          compute='_compute_employer_sodra_foreigner_with_visa_pct')
    average_wage = fields.Float(string='Average wage in Lithuania', compute='_compute_average_wage')
    under_avg_wage_npd_coefficient = fields.Float(string='NPD coefficient for wage under average',
                                                  compute='_compute_under_avg_wage_npd_coefficient')
    under_avg_wage_npd_max = fields.Float(string='Maximum NPD amount for wage under average',
                                                  compute='_compute_under_avg_wage_npd_max')
    under_avg_wage_minimum_wage_for_npd = fields.Float(
        string='Minimum wage used in NPD calculations for wage under average',
        compute='_compute_under_avg_wage_minimum_wage_for_npd')
    above_avg_wage_npd_coefficient = fields.Float(string='NPD coefficient for wage above average',
                                                  compute='_compute_above_avg_wage_npd_coefficient')
    above_avg_wage_npd_max = fields.Float(string='Maximum NPD amount for wage above average',
                                                  compute='_compute_above_avg_wage_npd_max')
    above_avg_wage_minimum_wage_for_npd = fields.Float(
        string='Minimum wage used in NPD calculations for wage above average',
        compute='_compute_above_avg_wage_minimum_wage_for_npd')

    @api.one
    def set_salary_rule_debit_accounts(self):
        salary_rules_mok = self.env['hr.salary.rule'].search([('code', 'in', ['M']), ('company_id', '=', self.id)])
        for rule in salary_rules_mok:
            rule.account_debit = self.saskaita_debetas.id
        gpm_rules = self.env['hr.salary.rule'].search([('code', 'in', ['GPM']), ('company_id', '=', self.id)])
        for rule in gpm_rules:
            rule.account_debit = self.saskaita_debetas.id
        sodra_rules = self.env['hr.salary.rule'].search([('code', 'in', ['SDD', 'SDB', 'SDP']), ('company_id', '=', self.id)])
        for rule in sodra_rules:
            rule.account_debit = self.saskaita_debetas.id

    @api.one
    def set_salary_rule_mok_accounts(self):
        mok_rules = self.env['hr.salary.rule'].search([('code', 'in', ['M']), ('company_id', '=', self.id)])
        for rule in mok_rules:
            if not rule.account_credit:
                rule.account_credit = self.saskaita_kreditas.id

    @api.one
    def set_salary_rule_gpm_accounts(self):
        gpm_rules = self.env['hr.salary.rule'].search([('code', 'in', ['GPM']), ('company_id', '=', self.id)])
        for rule in gpm_rules:
            rule.account_credit = self.saskaita_gpm.id

    @api.one
    def set_salary_rule_sodra_accounts(self):
        sodra_rules = self.env['hr.salary.rule'].search([('code', 'in', ['SDD', 'SDB', 'SDP']), ('company_id', '=', self.id)])
        for rule in sodra_rules:
            rule.account_credit = self.saskaita_sodra.id

    def get_historical_field_value(self, date, field_name):
        rec = self.env['payroll.parameter.history'].search([('company_id', '=', self.id), ('field_name', '=', field_name),
                                                            ('date_from', '<=', date)], order='date_from desc', limit=1)
        if not rec:
            rec = self.env['payroll.parameter.history'].search(
                [('company_id', '=', self.id), ('field_name', '=', field_name)], order='date_from desc', limit=1)
        if rec:
            return rec.value
        else:
            return 0.0

    @api.one
    def _sodra_papild_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        employee_id = self._context.get('employee_id')
        if datetime.strptime(date,tools.DEFAULT_SERVER_DATE_FORMAT) >= datetime(2019,1,1) and employee_id \
                and self.env['hr.employee'].browse(employee_id).contract_id.with_context(date=date).appointment_id.sodra_papildomai_type == 'exponential':
            self.sodra_papild_proc = self.get_historical_field_value(date, 'sodra_papild_exponential_proc')
        else:
            self.sodra_papild_proc = self.get_historical_field_value(date, 'sodra_papild_proc')

    @api.one
    def _sodra_papild_exponential_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.sodra_papild_exponential_proc = self.get_historical_field_value(date, 'sodra_papild_exponential_proc')

    @api.one
    def _num_work_days_a_year(self):
        six_day_work_week = self._context.get('six_day_work_week', False)
        weekend = [5,6] if not six_day_work_week else [6]
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
        year_start = datetime(date_dt.year, 1, 1)
        year_end = datetime(date_dt.year+1, 1, 1)-relativedelta(days=1)
        holidays = self.env['sistema.iseigines'].search([
            ('date', '<=', year_end.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
            ('date', '>=', year_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT)),
        ]).mapped('date')
        num_work_days = 0
        while year_start <= year_end:
            if year_start.weekday() not in weekend and not year_start.strftime(tools.DEFAULT_SERVER_DATE_FORMAT) in holidays:
                num_work_days += 1
            year_start += relativedelta(days=1)
        self.num_work_days_a_year = num_work_days

    @api.one
    def _gpm_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        check_is_tax_free = not self._context.get('dont_check_is_tax_free')
        if not check_is_tax_free or not self.is_tax_free():
            self.gpm_proc = self.get_historical_field_value(date, 'gpm_proc')
        else:
            self.gpm_proc = self.get_historical_field_value(date, 'gpm_lubos_proc')

    @api.one
    def gpm_du_unrelated_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.gpm_du_unrelated = self.get_historical_field_value(date, 'gpm_du_unrelated')

    @api.one
    def _gpm_ligos_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.gpm_ligos_proc = self.get_historical_field_value(date, 'gpm_ligos_proc')

    @api.one
    def _darbuotojo_pensijos_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        check_is_tax_free = not self._context.get('dont_check_is_tax_free')
        if not check_is_tax_free or not self.is_tax_free():
            self.darbuotojo_pensijos_proc = self.get_historical_field_value(date, 'darbuotojo_pensijos_proc')
        else:
            self.darbuotojo_pensijos_proc = 0.0

    @api.one
    def _darbuotojo_sveikatos_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.darbuotojo_sveikatos_proc = self.get_historical_field_value(date, 'darbuotojo_sveikatos_proc')

    @api.one
    def _darbdavio_sodra_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        sodra_proc = [
            self.get_historical_field_value(date, 'darbdavio_pensiju_draudimo_proc'),
            self.get_historical_field_value(date, 'darbdavio_ligos_draudimo_proc'),
            self.get_historical_field_value(date, 'darbdavio_motinystes_draudimo_proc'),
            self.get_historical_field_value(date, 'darbdavio_nedarbo_draudimo_proc'),
            self.get_historical_field_value(date, 'darbdavio_psd_proc'),
            self.get_historical_field_value(date, 'darbdavio_garantinio_fondo_proc'),
            self.get_historical_field_value(date, 'darbdavio_ilgalaikio_darbo_proc'),
            self.get_historical_field_value(date, 'darbdavio_nelaimingu_atsitikimu_proc')
        ]
        check_is_tax_free = not self._context.get('dont_check_is_tax_free')
        # Tax free is not applied to employer taxes beginning January 1st 2021
        if not check_is_tax_free or not self.is_tax_free() or date >= '2021-01-01':
            self.darbdavio_sodra_proc = sum(sodra_proc)
        else:
            self.darbdavio_sodra_proc = 0.0

    @api.one
    def _additional_sodra_proc(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.term_contract_additional_sodra_proc = self.get_historical_field_value(date, 'term_contract_additional_sodra_proc')

    @api.one
    def _npd_max(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.npd_max = self.get_historical_field_value(date, 'npd_max')

    @api.one
    def _npd_0_25_max(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.npd_0_25_max = self.get_historical_field_value(date, 'npd_0_25_max')

    @api.one
    def _npd_30_55_max(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.npd_30_55_max = self.get_historical_field_value(date, 'npd_30_55_max')

    @api.one
    def _mma(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.mma = self.get_historical_field_value(date, 'mma')

    @api.one
    def _mma_first_day_of_year(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.mma_first_day_of_year = self.get_historical_field_value(date, 'mma_first_day_of_year')

    @api.one
    def _min_hourly_rate(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.min_hourly_rate = self.get_historical_field_value(date, 'min_hourly_rate')

    @api.one
    def _npd_koeficientas(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.npd_koeficientas = self.get_historical_field_value(date, 'npd_koeficientas')

    @api.one
    def _dn_coefficient(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.dn_coefficient = self.get_historical_field_value(date, 'dn_coefficient')

    @api.one
    def _dp_coefficient(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.dp_coefficient = self.get_historical_field_value(date, 'dp_coefficient')

    @api.one
    def _vd_coefficient(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.vd_coefficient = self.get_historical_field_value(date, 'vd_coefficient')

    @api.one
    def _vdn_coefficient(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.vdn_coefficient = self.get_historical_field_value(date, 'vdn_coefficient')

    @api.one
    def _vss_coefficient(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.vss_coefficient = self.get_historical_field_value(date, 'vss_coefficient')

    @api.one
    def _snv_coefficient(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.snv_coefficient = self.get_historical_field_value(date, 'snv_coefficient')

    @api.one
    def _ligos_koeficientas(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.ligos_koeficientas = self.get_historical_field_value(date, 'ligos_koeficientas')

    @api.one
    def _compute_max_overtime_per_year(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.max_overtime_per_year = self.get_historical_field_value(date, 'max_overtime_per_year')

    @api.one
    def _compute_max_7_day_time(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.max_7_day_time = self.get_historical_field_value(date, 'max_7_day_time')

    @api.one
    def _compute_max_7_day_sumine_apskaita_time(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.max_7_day_sumine_apskaita_time = self.get_historical_field_value(date, 'max_7_day_sumine_apskaita_time')

    @api.one
    def _compute_max_7_day_including_extra_time(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.max_7_day_including_extra_time = self.get_historical_field_value(date, 'max_7_day_including_extra_time')

    @api.one
    def _compute_max_7_day_overtime_time(self):
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.max_7_day_overtime_time = self.get_historical_field_value(date, 'max_7_day_overtime_time')

    @api.multi
    def _compute_employee_tax_fund_foreigner_with_visa_pct(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.employee_tax_fund_foreigner_with_visa_pct = self.get_historical_field_value(
            date, 'employee_tax_fund_foreigner_with_visa_pct')

    @api.multi
    def _compute_employer_sodra_foreigner_with_visa_pct(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.employer_sodra_foreigner_with_visa_pct = self.get_historical_field_value(
            date, 'employer_sodra_foreigner_with_visa_pct')

    @api.multi
    def _compute_average_wage(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.average_wage = self.get_historical_field_value(date, 'average_wage')

    @api.multi
    def _compute_under_avg_wage_npd_coefficient(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.under_avg_wage_npd_coefficient = self.get_historical_field_value(date, 'under_avg_wage_npd_coefficient')

    @api.multi
    def _compute_under_avg_wage_npd_max(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.under_avg_wage_npd_max = self.get_historical_field_value(date, 'under_avg_wage_npd_max')

    @api.multi
    def _compute_under_avg_wage_minimum_wage_for_npd(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.under_avg_wage_minimum_wage_for_npd = self.get_historical_field_value(
            date, 'under_avg_wage_minimum_wage_for_npd'
        )

    @api.multi
    def _compute_above_avg_wage_npd_coefficient(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.above_avg_wage_npd_coefficient = self.get_historical_field_value(date, 'above_avg_wage_npd_coefficient')

    @api.multi
    def _compute_above_avg_wage_npd_max(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.above_avg_wage_npd_max = self.get_historical_field_value(date, 'above_avg_wage_npd_max')

    @api.multi
    def _compute_above_avg_wage_minimum_wage_for_npd(self):
        self.ensure_one()
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        self.above_avg_wage_minimum_wage_for_npd = self.get_historical_field_value(date, 'above_avg_wage_minimum_wage_for_npd')

    def is_tax_free(self):
        '''
            Don't forget to pass date and employee_id as context!
        :return: True/False - the wage sum of payslips from whole year is larger than sodra ceiling
        '''
        date = self._context.get('date') or datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
        employee_id = self._context.get('employee_id', False)
        sodra_lubos = self.get_historical_field_value(date, 'sodra_lubos_amount')
        if not float_is_zero(sodra_lubos, precision_digits=2) and employee_id and self.env['hr.employee'].browse(employee_id).no_taxes_sodra_lubos:
            date_strptime = datetime.strptime(date, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_from = (date_strptime + relativedelta(day=1, month=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to = (date_strptime + relativedelta(day=31, month=12)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            payslips = self.env['hr.payslip'].search([
                ('employee_id', '=', employee_id),
                ('date_from', '>=', date_from),
                ('date_to', '<=', date_to),
                ('state', '=', 'done')
            ])
            return sum(payslips.mapped('bruto')) > sodra_lubos
        else:
            return False

    @api.multi
    def get_employee_advance_account(self):
        """Returns employee advance account. Separate method due to dependency issues"""
        self.ensure_one()
        return self.employee_advance_account


class PayrollParameterHistory(models.Model):

    _name = 'payroll.parameter.history'

    _order = 'date_from desc'
    _sql_constraints = [('unique_date_field', 'unique(date_from, field_name)', _('Tas pats parametras negali įgyti dviejų reikšmių tą pačią dieną'))]

    def _company_id(self):
        return self.env.user.company_id

    @api.model
    def _get_payroll_parameter_selection(self):
        company_fields = self.env.user.company_id._fields
        fields_in_company = [field for field in payroll_parameter_field_identifiers if field in company_fields]
        return [
            (field, company_fields[field].string) for field in fields_in_company
        ] + other_payroll_parameter_selections

    company_id = fields.Many2one('res.company', string='Kompanija', required=True, default=_company_id)
    field_name = fields.Selection(_get_payroll_parameter_selection, string='Laukelis', required=True)
    value = fields.Float(string='Reikšmė', required=True)
    date_from = fields.Date(string='Data nuo', required=True)


PayrollParameterHistory()


class HrDepartment(models.Model):

    _inherit = 'hr.department'

    saskaita_debetas = fields.Many2one('account.account', string='DU sąnaudų sąskaita',
                                       domain=DEFAULT_ACCOUNT_DOMAIN,
                                       groups='account.group_account_user')
    saskaita_kreditas = fields.Many2one('account.account', string='DU įsipareigojimų sąskaita',
                                        domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    saskaita_gpm = fields.Many2one('account.account', string='GPM įsipareigojimų sąskaita',
                                   domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    saskaita_sodra = fields.Many2one('account.account', string='Iš DU mokėtina sodros sąskaita',
                                     domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    saskaita_komandiruotes_credit = fields.Many2one('account.account', string='Dienpinigių kredito sąskaita',
                                                    domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    darbdavio_sodra_debit = fields.Many2one('account.account', string='Darbdavio sodros debetinė sąskaita',
                                            domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    # darbdavio_sodra_credit = fields.Many2one('account.account', string='Darbdavio sodros kreditinė sąskaita')
    atostoginiu_kaupiniai_account_id = fields.Many2one('account.account', string='Atostogų kaupinių sąskaita',
                                                       domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    kaupiniai_expense_account_id = fields.Many2one('account.account', string='Atostogų kaupinių sąnaudų sąskaita',
                                                   domain=DEFAULT_ACCOUNT_DOMAIN,
                                                   groups='account.group_account_user')
    saskaita_komandiruotes = fields.Many2one('account.account', string='Komandiruočių sąnaudų sąskaita',
                                             domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    kiti_atskaitymai_credit = fields.Many2one('account.account', string='Kiti atskaitymai kreditas',
                                              domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')
    employee_advance_account = fields.Many2one('account.account', string='Employee advance account',
                                              domain=DEFAULT_ACCOUNT_DOMAIN, groups='account.group_account_user')


HrDepartment()


class ZeroNPDPeriod(models.Model):
    _name = 'zero.npd.period'
    _order = 'date_end DESC'

    date_start = fields.Date(string='Nuo', required=True)
    date_end = fields.Date(string='Iki', required=True)

    @api.multi
    @api.constrains('date_start', 'date_end')
    def constraint_intersection(self):
        for rec in self:
            if self.search_count([
                ('date_end', '>=', rec.date_start),
                ('date_start', '<=', rec.date_end)],
            ) > 1:
                raise exceptions.ValidationError(_('Negali persidengti periodai'))
            if rec.date_start > rec.date_end:
                raise exceptions.ValidationError(_('Pradžios data negali būti vėlesnė už pabaigos datą.'))
            first_day_month = (datetime.strptime(rec.date_start, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            last_day_month = (datetime.strptime(rec.date_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if rec.date_start != first_day_month:
                raise exceptions.ValidationError(_('Pradžios data turi būti mėnesio pirma diena'))
            if rec.date_end != last_day_month:
                raise exceptions.ValidationError(_('Pabaigos data turi būti mėnesio paskutinė diena'))

    @api.multi
    @api.onchange('date_start')
    def make_date_start_first_day_month(self):
        for period in self:
            if period.date_start:
                first_day_month = (datetime.strptime(period.date_start, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                    day=1)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                period.date_start = first_day_month

    @api.multi
    @api.onchange('date_end')
    def make_date_end_last_day_month(self):
        for period in self:
            if period.date_end:
                last_day_month = (datetime.strptime(period.date_end, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                    day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
                period.date_end = last_day_month


ZeroNPDPeriod()
