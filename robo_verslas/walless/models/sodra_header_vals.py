# -*- coding: utf-8 -*-

from odoo import models, api


def get_sodra_parameters(env):
    PARAM_OBJ = env['ir.config_parameter'].sudo()
    gatve = PARAM_OBJ.get_param('walless.force_gatve', '')
    namas = PARAM_OBJ.get_param('walless.force_namas', '')
    miestas = PARAM_OBJ.get_param('walless.force_miestas', '')
    pasto_kodas = PARAM_OBJ.get_param('walless.force_pasto_kodas', '')
    adresas = gatve + ' ' + namas + ', ' + miestas + ' ' + pasto_kodas
    return {
        'name': PARAM_OBJ.get_param('walless.force_company_name', ''),
        'draudejo_kodas': PARAM_OBJ.get_param('walless.force_draudejo_kodas', ''),
        'imones_kodas': PARAM_OBJ.get_param('walless.force_imones_kodas', ''),
        'telefonas': PARAM_OBJ.get_param('walless.force_telefonas', ''),
        'gatve': gatve,
        'namas': namas,
        'miestas': miestas,
        'pasto_kodas': pasto_kodas,
        'adresas': adresas,
    }


class SAM(models.TransientModel):
    _inherit = 'e.sodra.sam'

    @api.multi
    def sam(self):
        params = get_sodra_parameters(self.env)
        return super(SAM, self.with_context(
            force_company_name=params['name'],
            force_draudejo_kodas=params['draudejo_kodas'],
            force_imones_kodas=params['imones_kodas'],
            force_telefonas=params['telefonas'],
            force_adresas=params['adresas'],
        )).sam()

    @api.multi
    def sam_new(self):
        params = get_sodra_parameters(self.env)
        return super(SAM, self.with_context(
            force_company_name=params['name'],
            force_draudejo_kodas=params['draudejo_kodas'],
            force_imones_kodas=params['imones_kodas'],
            force_telefonas=params['telefonas'],
            force_adresas=params['adresas'],
        )).sam_new()


SAM()


class DarbuotojuParametraiSD1(models.TransientModel):
    _inherit = 'sodra.darbuotojai'

    def generuoti(self):
        params = get_sodra_parameters(self.env)
        return super(DarbuotojuParametraiSD1, self.with_context(
            force_company_name=params['name'],
            force_draudejo_kodas=params['draudejo_kodas'],
            force_imones_kodas=params['imones_kodas'],
            force_telefonas=params['telefonas'],
            force_gatve=params['gatve'],
            force_namas=params['namas'],
            force_miestas=params['miestas'],
        )).generuoti()


DarbuotojuParametraiSD1()


class DarbuotojuParametraiSD2(models.TransientModel):
    _inherit = 'sodra.darbuotojai.sd2'

    def generuoti(self):
        params = get_sodra_parameters(self.env)
        return super(DarbuotojuParametraiSD2, self.with_context(
            force_company_name=params['name'],
            force_draudejo_kodas=params['draudejo_kodas'],
            force_imones_kodas=params['imones_kodas'],
            force_telefonas=params['telefonas'],
            force_gatve=params['gatve'],
            force_namas=params['namas'],
            force_miestas=params['miestas'],
        )).generuoti()


DarbuotojuParametraiSD2()


class SD9(models.TransientModel):
    _inherit = 'e.sodra.sd9'

    @api.multi
    def sd9_generate(self, leave, child_birthdate, child_person_code):
        params = get_sodra_parameters(self.env)
        return super(SD9, self.with_context(
            force_company_name=params['name'],
            force_draudejo_kodas=params['draudejo_kodas'],
            force_imones_kodas=params['imones_kodas'],
            force_telefonas=params['telefonas'],
            force_adresas=params['adresas'],
        )).sd9_generate(leave, child_birthdate, child_person_code)


SD9()


class SD12(models.TransientModel):
    _inherit = 'e.sodra.sd12'

    @api.multi
    def sd12_generate(self):
        params = get_sodra_parameters(self.env)
        return super(SD12, self.with_context(
            force_company_name=params['name'],
            force_draudejo_kodas=params['draudejo_kodas'],
            force_imones_kodas=params['imones_kodas'],
            force_telefonas=params['telefonas'],
            force_adresas=params['adresas'],
        )).sd12_generate()


SD12()


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.multi
    def get_registry(self):
        return self.sudo().env['ir.config_parameter'].get_param('walless.force_imones_kodas',
                                                         self.env.user.company_id.company_registry)


ResUsers()
