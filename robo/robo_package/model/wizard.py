# -*- coding: utf-8 -*-
import datetime
from odoo import api, fields, models, _, tools, exceptions
from dateutil.relativedelta import relativedelta
from excel_export import PackagesExcel
from collections import OrderedDict


def getQuarterStart(dt=datetime.datetime.utcnow()):
    return datetime.date(dt.year, (dt.month - 1) // 3 * 3 + 1, 1)


class ProductPackageWizard(models.TransientModel):
    _name = 'product.package.wizard'

    def _date_to_default(self):
        return getQuarterStart(datetime.datetime.utcnow()) + relativedelta(months=2, day=31)

    def _date_from_default(self):
        return getQuarterStart(datetime.datetime.utcnow())

    date_from = fields.Date(string="Periodas nuo", required=True, default=_date_from_default)
    date_to = fields.Date(string="Periodas iki", required=True, default=_date_to_default)
    show_button = fields.Boolean(string='Peržiūrėti važtaraščius', compute='_show_button')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.user.company_id)
    package_direction = fields.Selection([('all', 'Visi'),
                                          ('in_lt', 'Įvežta iš Lietuvos'),
                                          ('in', 'Importas'),
                                          ('out_lt', 'Išleista į Lietuvos rinką'),
                                          ('out_kt', 'Išsiuntimai už Lietuvos ribų'),
                                          ('int', 'Vidiniai')],
                                         string='Pervežimo tipas', default='out_lt')

    @api.one
    @api.depends('date_from', 'date_to')
    def _show_button(self):
        self.show_button = bool(self.env['stock.picking'].search([('review_packages', '=', True)], count=True))

    @api.multi
    def open_pickings(self):
        self.ensure_one()
        action = self.env.ref('robo_stock.open_robo_stock_picking').read()[0]
        action['domain'] = [('review_packages', '=', True)]
        action['context'] = {'clear_breadcrumbs': True, 'robo_header': {}}
        return action

    @api.multi
    def name_get(self):
        return [(rec.id, _('Pakuočių analitika')) for rec in self]

    @api.multi
    def _export_excel(self, date_from, date_to, package_direction):
        self.ensure_one()

        date_dt = datetime.datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)
        date_from_dt = datetime.datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        if abs((date_dt - date_from_dt).days) > 3700:
            raise exceptions.UserError(_('Per ilgas laikotarpis.'))

        selection_dict = dict(self.fields_get(allfields=['package_direction'])['package_direction']['selection'])
        group_column_name = selection_dict.get(package_direction if package_direction else 'all', '')

        excel = PackagesExcel(self, date_from, date_to, group_column_name)

        if package_direction:
            lines = self.env['report.product.packages'] \
                .search([('date', '>=', date_from), ('date', '<=', date_to), ('package_direction', '=', package_direction)], order="date asc")
        else:
            lines = self.env['report.product.packages']\
                .search([('date', '>=', date_from), ('date', '<=', date_to)], order="date asc")

        result = OrderedDict()

        for line in lines:
            if not line.package_category or not line.material_type:
                continue
            id = line.picking_id.id
            if id not in result:
                result[id] = {
                    'partner': line.partner_id.name,
                    'doc_nbr': line.picking_id.name,
                    'date': line.date,
                    'print_line': False
                }
            if (line.package_category+'_'+line.material_type) in result[id]:
                result[id][line.package_category + '_' + line.material_type]['nbr'] += line.qty_of_packages
                result[id][line.package_category + '_' + line.material_type]['weight'] += line.weight_of_packages
            else:
                result[id][line.package_category+'_'+line.material_type] = {
                    'nbr': line.qty_of_packages,
                    'weight': line.weight_of_packages
                }
            if line.qty_of_packages > 0 or line.weight_of_packages > 0:
                result[id]['print_line'] = True

        excel.write_lines(result, non_zero_columns=True)
        base64_file = excel.export()
        filename = 'packages.xls'
        attach_id = self.env['ir.attachment'].create({
            'res_model': 'product.package.wizard',
            'res_id': self.id,
            'type': 'binary',
            'name': filename,
            'datas_fname': filename,
            'datas': base64_file
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=product.package.wizard&res_id=%s&attach_id=%s' % (self.id, attach_id.id),
            'target': 'self',
        }

    @api.multi
    def _open_pivot_report(self, date_from, date_to, package_direction):
        action = self.env.ref('robo_package.open_report_product_packages')
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

        self.env['report.product.packages'].sudo().refresh_materialised_product_packages_history()

        if self._context.get('xls_report', False):
            return self._export_excel(date_from, date_to, package_direction)
        else:
            return self._open_pivot_report(date_from, date_to, package_direction)

    @api.multi
    def xls_export(self):
        return self.check_report()


ProductPackageWizard()
