# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from datetime import datetime
from six import iteritems


class Statistics(http.Controller):
    @http.route('/statistics/get_statistics', type='json', auth='user')
    def get_statistics(self, data):
        if request.env.user.accumulate_statistics():  # change to new statistics group for write rights
            model = request.env['robo.company.statistics']
            for k, v in iteritems(data['tags']):
                model.sudo().create({
                    'tag': k,
                    'duration': v,
                    'user': request.env.user.id,
                })
            for k, v in iteritems(data['models']):
                model.sudo().create({
                    'model': k,
                    'duration': v,
                    'user': request.env.user.id,
                })
        return True


Statistics()
