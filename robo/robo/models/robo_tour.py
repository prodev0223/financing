# -*- coding: utf-8 -*-

from odoo import api, fields, models


class RoboTour(models.Model):
    _name = 'robo.tour'
    _description = "Robo Tours"
    _log_access = False

    name = fields.Char(string="Robo Tour name", required=True)
    user_id = fields.Many2one('res.users', string='Consumed by')

    @api.model
    def consume(self, tour_names):
        """ Sets given tours as consumed, meaning that
            these tours won't be active anymore for that user """
        # ROBO: Why I need sudo!?
        for name in tour_names:
            self.sudo().create({'name': name, 'user_id': self.env.uid})

    @api.model
    def get_consumed_tours(self):
        """ Returns the list of consumed tours for the current user """
        # ROBO: Why I need sudo!?
        return [t.name for t in self.sudo().search([('user_id', '=', self.env.uid)])]
