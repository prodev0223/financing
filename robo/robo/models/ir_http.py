# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super(IrHttp, self).session_info()
        result['robo_is_back_user'] = request.env.user.is_back_user()
        if request.env.user.is_robo_tour_user():
            result['robo_tours'] = request.env['robo.tour'].get_consumed_tours()

            nbr_of_tours = {'manager': 6, 'user': 2}
            nbr = nbr_of_tours['manager']
            if not request.env.user.is_manager():
                nbr = nbr_of_tours['user']

            # the user is not robo_tour_user if all tours are consumed -- currently we have 6 robo tours;
            if len(result['robo_tours']) < nbr:
                result['is_robo_tour_user'] = True
            else:
                result['is_robo_tour_user'] = False
        else:
            result['is_robo_tour_user'] = False
        return result
