# -*- coding: utf-8 -*-
import datetime
from odoo import api, fields, models, _, tools, exceptions
from dateutil.relativedelta import relativedelta


def getQuarterStart(dt=datetime.datetime.utcnow()):
    return datetime.date(dt.year, (dt.month - 1) // 3 * 3 + 1, 1)


class ProductElectronicsWizard(models.TransientModel):
    _name = 'product.electronics.wizard'

    def _date_to_default(self):
        return getQuarterStart(datetime.datetime.utcnow())+relativedelta(months=-1, day=31)

    def _date_from_default(self):
        return getQuarterStart(datetime.datetime.utcnow()) + relativedelta(months=-3, day=1)

    date_from = fields.Date(string="Periodas nuo", required=True, default=_date_from_default)
    date_to = fields.Date(string="Periodas iki", required=True, default=_date_to_default)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.user.company_id)
    package_direction = fields.Selection([('all', 'Visi'),
                                          ('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Pervežimo tipas', default='all')

    @api.multi
    def name_get(self):
        return [(rec.id, _('Elektronikos analitika')) for rec in self]

    @api.multi
    def _open_pivot_report(self, date_from, date_to, package_direction):
        if self._context.get('battery'):
            action = self.env.ref('robo_electronics.open_report_product_batteries')
        else:
            action = self.env.ref('robo_electronics.open_report_product_electronics')

        if action:
            action = action.read()[0]
            action['domain'] = [('date', '>=', date_from), ('date', '<=', date_to)]
            action['context'] = {'search_default_positive': True}
            if package_direction:
                action['context'].update({'search_default_'+package_direction: True})

            return action
        return {}

    @api.multi
    def check_report(self):
        self.ensure_one()

        date_from = self.date_from
        date_to = self.date_to
        package_direction = self.package_direction if self.package_direction != 'all' else False

        if self._context.get('battery'):
            self.env['report.product.batteries'].sudo().refresh_materialised_product_batteries_history()
        else:
            self.env['report.product.electronics'].sudo().refresh_materialised_product_electronics_history()

        return self._open_pivot_report(date_from, date_to, package_direction)

    @api.multi
    def xls_export(self):
        return self.check_report()


ProductElectronicsWizard()
