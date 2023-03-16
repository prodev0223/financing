# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools, _, exceptions
from odoo.addons.queue_job.job import job, identity_exact
from odoo.addons.queue_job.exception import RetryableJobError
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dateutil.parser import parse
import pytz
from odoo.tools import ustr
from collections import deque
from odoo.tools.misc import xlwt
import StringIO
from copy import deepcopy
import logging

_logger = logging.getLogger(__name__)
XLS_EXT = 'xls'

def zero_quant_cleanup(report, value_field_list):
    new_prod_dict = {}
    report_copy = deepcopy(report)
    for row in report_copy:
        if row['product_id'][0] not in new_prod_dict:
            new_prod_dict[row['product_id'][0]] = row
        else:
            key_id = row['product_id'][0]
            for value in value_field_list:
                new_prod_dict[key_id][value] += row[value]
    remove_ids = []
    for key, value in new_prod_dict.items():
        to_remove = True
        for col_value in value_field_list:
            if value[col_value]:
                to_remove = False
                break
        if to_remove:
            remove_ids.append(key)
    report = [x for x in report if x['product_id'][0] not in remove_ids]
    return report


def convert_to_dt_str(date_str, offset):
    dt = parse(date_str + ' 00:00:00 ' + offset)
    dt = dt.astimezone(pytz.utc)
    return dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)


class InventorySummaryWizard(models.TransientModel):

    _name = 'inventory.summary.wizard'

    def _default_date_to(self):
        return datetime.utcnow() + relativedelta(day=31)

    def _default_date_from(self):
        return datetime.utcnow() - relativedelta(day=1)

    def default_locations(self):
        ids = self.env['stock.location'].search([('usage', 'in', ['internal']), ('active', '=', True)])
        return [(4, loc.id) for loc in ids]

    select_all_products = fields.Boolean(string='Pasirinkti visus produktus', default=True)
    select_all_locations = fields.Boolean(string='Pasirinkti visus sandėlius')
    group_by_location = fields.Boolean(string='Grupuoti duomenis pagal sandėlį')
    location_ids = fields.Many2many('stock.location', string='Sandėliai', default=default_locations,
                                    domain=[('usage', '=', 'internal')])
    product_ids = fields.Many2many('product.product', string='Produktai')
    date_from = fields.Date(string='Nuo', default=_default_date_from)
    date_to = fields.Date(string='Iki', default=_default_date_to)
    category_ids = fields.Many2many('product.category', string='Produktų kategorijos')
    select_all_categories = fields.Boolean(string='Pasirinkti visas produktų kategorijas')
    selection_type = fields.Selection([('product', 'Produktus'), ('category', 'Produktų kategorijas')],
                                      string='Filtruoti pagal', default='product', required=True)

    @api.multi
    def name_get(self):
        return [(rec.id, _('Atsargų analizė')) for rec in self]

    def refresh_materialised_stock_history(self):
        self._cr.execute('''
        REFRESH MATERIALIZED VIEW stock_move_report;
        REFRESH MATERIALIZED VIEW stock_history_delayed''')

    def xls_export(self, domain, obj_domain):
        product_ids = self.env['product.product'].with_context(active_test=False).search(obj_domain)
        main_field_list = ['product_id', 'location_id', 'date']
        value_field_list = [
            'start_stock', 'start_value',
            'qty_supplied', 'value_supplied',
            'qty_produced', 'value_produced',
            'qty_in_reverse', 'value_in_reverse',
            'qty_in_other', 'value_in_other',
            'qty_delivered', 'value_delivered',
            'qty_consumed', 'value_consumed',
            'qty_out_reverse', 'value_out_reverse',
            'qty_scrap', 'value_scrap',
            'qty_out_other', 'value_out_other',
            'end_stock', 'end_value'
        ]
        field_list = main_field_list + value_field_list
        measures = [_('Pradinis likutis, vnt.'), _('Vertė, EUR'),
                    _('Gauta iš tiekėjų, vnt.'), _('Vertė, EUR'),
                    _('Pagamintas kiekis, vnt.'), _('Vertė, EUR'),
                    _('Grąžintas kiekis klientams, vnt.'), _('Vertė, EUR'),
                    _('Kitas gautas kiekis, vnt.'), _('Vertė, EUR'),
                    _('Parduotas kiekis, vnt.'),_('Vertė, EUR'),
                    _('Suvartotas kiekis, vnt.'), _('Vertė, EUR'),
                    _('Grąžintas kiekis tiekėjams, vnt.'), _('Vertė, EUR'),
                    _('Subrokuotas kiekis, vnt.'), _('Vertė, EUR'),
                    _('Kitas išsiųstas kiekis, vnt.'), _('Vertė, EUR'),
                    _('Pabaigos likutis, vnt.'), _('Vertė, EUR'),
                    ]
        measure_count = len(measures)
        report = self.env['stock.move.report'].with_context(skip_computations=True).read_group(
            domain, field_list, ['date:date', 'product_id', 'location_id'], lazy=False)
        if report:
            report = zero_quant_cleanup(report, value_field_list)
            dates = list(set([d['date:date'] for d in report]))
            if not self.date_from and dates:
                self.date_from = datetime.strptime(dates[0], '%Y-%m').strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            if not self.date_to and dates:
                self.date_to = (datetime.strptime(dates[-1], '%Y-%m') + relativedelta(day=31)).strftime(tools.DEFAULT_SERVER_DATE_FORMAT)

            date_from_dt = datetime.strptime(self.date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
            date_to_dt = datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT)

            mediate_date_from_dct = {}
            mediate_date_to_dct = {}
            # check middle of the month
            if date_from_dt.day != 1:
                mediate_date_from_dct[date_from_dt.strftime('%Y-%m')] = date_from_dt.day
            if (date_to_dt + relativedelta(days=1)).month == date_to_dt.month:
                mediate_date_to_dct[date_to_dt.strftime('%Y-%m')] = date_to_dt.day

            # check if populated
            while date_from_dt < date_to_dt:
                date = date_from_dt.strftime('%Y-%m')
                if date not in dates:
                    dates.append(date)
                date_from_dt += relativedelta(months=1)

            locations = self.location_ids if not self.select_all_locations else \
                self.env['stock.location'].search([('usage', 'in', ['internal']), ('active', '=', True)])
            # Set a list for looping through subsets of locations depending on grouping settings
            location_ids_list = [[location_id] for location_id in locations.ids] \
                if self.group_by_location else [locations.ids]
            dates = sorted(dates, key=lambda key: datetime.strptime(key, '%Y-%m'))
            report_sums = []
            history_domain = [('location_id', 'in', locations.ids)]
            if product_ids:
                history_domain.append(('product_id', 'in', product_ids.ids))
            headers = [[], [], [], [], []]
            top_row_totals = []
            for date in dates:
                if mediate_date_from_dct.get(date, False):
                    stock_from_date = (datetime.strptime(date, '%Y-%m') -
                                       relativedelta(day=mediate_date_from_dct.get(date) - 1, hour=21, minute=00, second=00)
                                       ).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                else:
                    stock_from_date = (datetime.strptime(date, '%Y-%m') -
                                       relativedelta(day=31, hour=21, minute=0, second=0, months=1)
                                       ).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

                if mediate_date_to_dct.get(date, False):
                    stock_to_date = (datetime.strptime(date, '%Y-%m') +
                                     relativedelta(day=mediate_date_to_dct.get(date), hour=21, minute=1, second=1)
                                     ).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
                else:
                    stock_to_date = (datetime.strptime(date, '%Y-%m') +
                                     relativedelta(day=31, hour=20, minute=59, second=59)
                                     ).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

                final_domain_from = history_domain + [('date', '<=', stock_from_date)]
                final_domain_to = history_domain + [('date', '<=', stock_to_date)]
                stock_from_data = self.sudo().env['stock.history'].read_group(final_domain_from, [],
                                                                              ['product_id', 'location_id'], lazy=False)
                stock_to_data = self.sudo().env['stock.history'].read_group(final_domain_to, [],
                                                                            ['product_id', 'location_id'], lazy=False)
                prods_list = []
                partials = filter(lambda x: x['date:date'] == date, report)
                partials_prod = list(set([d['product_id'][0] for d in partials]))
                for prod in partials_prod:
                    for location_ids in location_ids_list:
                        prods = filter(lambda x: x['product_id'][0] == prod and x['location_id'][0] in location_ids,
                                       partials)
                        if not prods:
                            continue
                        prod_dict = dict([(f, round(sum(prod[f] for prod in prods), 2)) for f in value_field_list])
                        start_vals = [x for x in stock_from_data if x['product_id'][0] == prod and
                                      x['location_id'][0] in location_ids]
                        end_vals = [x for x in stock_to_data if x['product_id'][0] == prod and
                                    x['location_id'][0] in location_ids]

                        prod_dict['start_stock'] = round(sum(x['quantity'] for x in start_vals), 2)
                        prod_dict['end_stock'] = round(sum(x['quantity'] for x in end_vals), 2)
                        prod_dict['start_value'] = round(sum(x['total_value'] for x in start_vals), 2)
                        prod_dict['end_value'] = round(sum(x['total_value'] for x in end_vals), 2)
                        prod_dict['product_id'] = prods[0]['product_id']
                        prod_dict['location_ids'] = location_ids
                        prod_dict['date:date'] = date
                        prods_list.append(prod_dict)
                non_moved_quants = [x for x in product_ids if x.id not in partials_prod]
                for product in non_moved_quants:
                    for location_ids in location_ids_list:
                        product_stock = [x for x in stock_to_data if x['product_id'][0] == product.id and
                                         x['location_id'][0] in location_ids]
                        non_moved_quantity = round(sum(x['quantity'] for x in product_stock) if product_stock else 0, 2)
                        non_moved_value = round(sum(x['total_value'] for x in product_stock) if product_stock else 0, 2)
                        empty_dict = dict([(f, 0.0) for f in value_field_list])
                        empty_dict['product_id'] = product.name_get()[0]
                        empty_dict['location_ids'] = location_ids
                        empty_dict['date:date'] = date
                        empty_dict['start_stock'] = empty_dict['end_stock'] = non_moved_quantity
                        empty_dict['start_value'] = empty_dict['end_value'] = non_moved_value
                        prods_list.append(empty_dict)
                report_sums += prods_list

                headers[4].append({
                    'width': measure_count,
                    'title': date,
                    'expanded': False,
                    'height': 1,
                })
                total_dict = {}
                for f in value_field_list:
                    total_dict[f] = sum(item[f] for item in prods_list)
                top_row_totals.append(total_dict)
            report_sums = zero_quant_cleanup(report_sums, value_field_list)

            measure_row = []
            headers[0].append({
                'width': measure_count * len(dates),
                'title': self.env.user.sudo().company_id.name,
                'expanded': True,
                'height': 1,
            })
            headers[1].append({
                'width': measure_count * len(dates),
                'title': _('Data: {} - {}').format(self.date_from or str(), self.date_to or str()),
                'expanded': True,
                'height': 1,
            })
            location_codes = locations.mapped('warehouse_id.code')
            headers[2].append({
                'width': measure_count * len(dates),
                'title': _('Sandėliai: {}').format(', '.join(x for x in location_codes)),
                'expanded': True,
                'height': 1,
            })

            headers[3].append({
                'width': measure_count * len(dates),
                'title': _('Viso'),
                'expanded': True,
                'height': 1,
            })
            if len(dates) > 1:
                date_length = len(dates) + 1
                headers[3].append({
                    'width': measure_count,
                    'title': _('Viso'),
                    'height': 2,
                })
            else:
                date_length = len(dates)
            for x in range(date_length):
                for measure in measures:
                    if x == date_length and date_length > 1:
                        bold = True
                    else:
                        bold = False
                    measure_row.append({
                        'is_bold': bold,
                        'measure': measure,
                    })
            field_list.pop(0)
            field_list.pop(0)
            field_list.pop(0)
            workbook = xlwt.Workbook(encoding='utf-8')
            worksheet = workbook.add_sheet(_('Atsargų analizė'))
            xlwt.add_palette_colour('robo_background', 0x21)
            workbook.set_colour_RGB(0x21, 236, 240, 241)
            header_bold = xlwt.easyxf("font: bold on; pattern: pattern solid, fore_colour robo_background;")
            header_plain = xlwt.easyxf("pattern: pattern solid, fore_colour robo_background;")
            header_bold_brd = xlwt.easyxf("font: bold on; pattern: pattern solid, "
                                          "fore_colour robo_background; borders: left thick")
            header_plain_brd = xlwt.easyxf("pattern: pattern solid, fore_colour robo_background; borders: left thick")
            header_bold_b = xlwt.easyxf("font: bold on; pattern: pattern solid, "
                                        "fore_colour robo_background; borders: bottom thick")
            header_plain_b = xlwt.easyxf("pattern: pattern solid, fore_colour robo_background; borders: bottom thick")
            header_bold_brd_b = xlwt.easyxf("font: bold on; pattern: pattern solid, "
                                            "fore_colour robo_background; borders: left thick, bottom thick")
            header_plain_brd_b = xlwt.easyxf("pattern: pattern solid, fore_colour "
                                             "robo_background; borders: left thick, bottom thick")
            column_bold = xlwt.easyxf("borders: left thick")
            bold = xlwt.easyxf("font: bold on;")

            worksheet.write(0, 1, '', header_plain)
            worksheet.write(1, 1, '', header_plain)
            worksheet.write(2, 1, '', header_plain)
            worksheet.write(3, 1, '', header_plain)
            worksheet.write(4, 1, '', header_plain)
            y, carry = 0, deque()
            x = 3 if self.group_by_location else 2
            iteration = 0
            for i, header_row in enumerate(headers):
                worksheet.write(i, 0, '', header_plain)
                if self.group_by_location:
                    worksheet.write(i, 2, '', header_plain)
                for header in header_row:
                    while carry and carry[0]['x'] == x:
                        cell = carry.popleft()
                        for i in range(measure_count):
                            worksheet.write(y, x + i, '', header_plain)
                        if cell['height'] > 1:
                            carry.append({'x': x, 'height': cell['height'] - 1})
                        x = x + measure_count
                    style = 'plain' if 'expanded' in header else 'bold'
                    for i in range(header['width']):
                        if i % measure_count == 0:
                            style = header_plain_brd if style in ['plain'] else header_bold_brd
                        else:
                            style = header_plain if style in ['plain'] else header_bold
                        try:
                            worksheet.write(y, x + i, header['title'] if i == 0 else '', style)
                        except ValueError:
                            raise exceptions.Warning(_('Pasirinktas per didelis periodas!'))  # todo, just a workaround
                    if header['height'] > 1:
                        carry.append({'x': x, 'height': header['height'] - 1})
                    x = x + header['width']
                while carry and carry[0]['x'] == x:
                    cell = carry.popleft()
                    for i in range(measure_count):
                        if not i:
                            worksheet.write(y, x + i, '', header_plain_brd)
                        else:
                            worksheet.write(y, x + i, '', header_plain)
                    if cell['height'] > 1:
                        carry.append({'x': x, 'height': cell['height'] - 1})
                    x = x + measure_count
                if iteration < 4:
                    x = 3 if self.group_by_location else 2
                    y = y + 1
                else:
                    x, y = 1, y + 1
                iteration += 1

            if measure_count > 1:
                worksheet.write(y, 0, '', header_plain)
                worksheet.write(y, x, 'Produkto kodas', header_bold)
                x += 1
                if self.group_by_location:
                    worksheet.write(y, x, 'Lokacija', header_bold)
                    x += 1
                for c, measure in enumerate(measure_row):
                    if c % measure_count == 0:
                        style = header_bold_brd_b if measure['is_bold'] else header_plain_brd_b
                    else:
                        style = header_bold_b if measure['is_bold'] else header_plain_b
                    worksheet.write(y, x, measure['measure'], style)
                    x = x + 1
                y = y + 1

            total_row = y
            worksheet.write(total_row, 0, ustr(_('Viso')), header_bold)
            worksheet.write(total_row, 1, ustr(_('')), header_bold)
            x = 2 if self.group_by_location else 1
            if self.group_by_location:
                worksheet.write(total_row, 2, ustr(_('')), header_bold)
            for dates in top_row_totals:
                for en, col in enumerate(field_list):
                    x += 1
                    if not en:
                        worksheet.write(y, x, dates[col], xlwt.easyxf("borders: left thick; font: bold on"))
                    else:
                        worksheet.write(y, x, dates[col], bold)
            y += 1
            total_col = x
            x = 0
            end_line_totals = []

            for location_ids in location_ids_list:
                for product in product_ids:
                    prod_group = [val for val in report_sums if val['product_id'][0] == product.id and val['location_ids'] == location_ids]
                    if not prod_group:
                        continue
                    prod_group = sorted(prod_group, key=lambda key: datetime.strptime(key['date:date'], '%Y-%m'))
                    prod_obj = self.env['product.product'].browse(prod_group[0]['product_id'][0])
                    worksheet.write(y, x, ustr(prod_obj.name), header_plain)
                    x += 1
                    worksheet.write(y, x, ustr(prod_obj.default_code or ''), header_plain)
                    if self.group_by_location:
                        x += 1
                        warehouse_code = self.env['stock.location'].browse(location_ids).warehouse_id.code or str()
                        worksheet.write(y, x, ustr(warehouse_code), header_plain)
                    prod_total = {}
                    start_stock = start_value = None
                    end_stock = end_value = 0
                    field_count = 0
                    for prod in prod_group:
                        for col in field_list:
                            x = x + 1
                            if not field_count:
                                worksheet.write(y, x, prod[col], column_bold)
                            else:
                                worksheet.write(y, x, prod[col])
                            field_count += 1
                            if col == 'end_stock':
                                end_stock = prod[col]
                            elif col == 'start_stock' and start_stock is None:
                                start_stock = prod[col]
                            elif col == 'end_value':
                                end_value = prod[col]
                            elif col == 'start_value' and start_value is None:
                                start_value = prod[col]
                            else:
                                if prod_total.get(col, False):
                                    prod_total[col] += prod[col]
                                else:
                                    prod_total[col] = prod[col]
                        field_count = 0
                    prod_total['start_stock'] = start_stock
                    prod_total['end_stock'] = end_stock
                    prod_total['start_value'] = start_value
                    prod_total['end_value'] = end_value
                    end_line_totals.append(prod_total)
                    if date_length > 1:
                        for c, col in enumerate(field_list):
                            x = x + 1
                            if not c:
                                worksheet.write(y, x, prod_total[col], xlwt.easyxf("borders: left thick; font: bold on"))
                            else:
                                worksheet.write(y, x, prod_total[col], bold)
                    x, y = 0, y + 1

            if date_length > 1:
                for x, col in enumerate(field_list):
                    total_col += 1
                    if not x:
                        worksheet.write(total_row, total_col, sum(item[col] for item in end_line_totals),
                                        xlwt.easyxf("borders: left thick; font: bold on"))
                    else:
                        worksheet.write(total_row, total_col, sum(item[col] for item in end_line_totals), bold)

            worksheet.set_panes_frozen(True)
            worksheet.set_horz_split_pos(3)
            worksheet.set_vert_split_pos(2)

            f = StringIO.StringIO()
            workbook.save(f)
            base64_file = f.getvalue().encode('base64')

            attach_id = self.env['ir.attachment'].create({
                'res_model': 'inventory.summary.wizard',
                'res_id': self[0].id,
                'type': 'binary',
                'name': 'name.xls',
                'datas_fname': _('Atsargų_analizė_' + self.date_from + '_' + self.date_to + '.xls'),
                'datas': base64_file
            })
            return attach_id
        else:
            raise exceptions.Warning(_('Nerasta produktų judėjimų pasirinktam periodui. Pasirinkite platesnį periodą.'))

    @api.multi
    def show_report(self):
        # Check if threading is enabled
        threaded = self.sudo().env.user.company_id.activate_threaded_front_reports
        if self._context.get('xls_export', False) and threaded:
            return self.action_background_report()
        return self._action_report(threaded=False)

    @api.multi
    def action_background_report(self):
        user_id = self.env.user.id
        report_name = self.display_name
        now = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        report_job = self.env['robo.report.job'].create({
            'report_name': report_name,
            'execution_start_date': now,
            'state': 'in_progress',
            'user_id': user_id,
            'job_type': 'export'
        })

        context = self._context.copy()

        # Start export job
        job = self.with_delay(eta=5, channel='root', identity_key=identity_exact).perform_xlsx_export_job(
            report_job.id, additional_context=context
        )
        self.with_delay(eta=600, channel='root', identity_key=identity_exact).check_failed_job_status(job.uuid, report_job.id)

        # Return the action which displays information on where to find the report
        action = self.env.ref('robo.action_open_robo_report_job').read()[0]
        action.update({
            'view_mode': 'form', 'res_id': report_job.id,
            'view_id': self.env.ref('robo.form_robo_report_job').id
        })  # Force form view of the created import job
        return action

    @job
    @api.multi
    def perform_xlsx_export_job(self, import_job_id, additional_context=None):
        context = self._context.copy()
        if additional_context:
            context.update(additional_context)

        # Re-browse import object
        report_job = self.env['robo.report.job'].browse(import_job_id)
        if not report_job.exists():
            return

        try:
            if not context.get('active_ids'):
                context['active_ids'] = [self.id]
            res = self.with_context(context)._action_report(threaded=True)

            base64_file = res.get('base64_file')
            exported_file_name = res.get('exported_file_name')
            exported_file_type = XLS_EXT
        except Exception as exc:
            report_job.write({
                'state': 'failed',
                'fail_message': str(exc.args[0] if exc.args else exc),
                'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            })
            _logger.error('Background task failed to export the report for the stock analysis: %s' % str(exc.args[0]))
        else:
            report_job.write({
                'state': 'succeeded',
                'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'exported_file': base64_file,
                'exported_file_name': exported_file_name,
                'exported_file_type': exported_file_type
            })

        report_job.post_message()

    @job
    def check_failed_job_status(self, uuid, job_id):
        job = self.env['queue.job'].sudo().search([('uuid', '=', uuid)])
        if job.state in ['pending', 'enqueued', 'started']:
            raise RetryableJobError('Job still in progress', 600, True)
        report_job = self.env['robo.report.job'].browse(job_id)
        if job.state in ['done', 'failed'] and report_job.state != 'in_progress':
            report_job.write({
                'state': 'failed',
                'fail_message': _('Background tasks failed to complete'),
                'execution_end_date': datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            })
            report_job.post_message()

    @api.multi
    def _action_report(self, threaded=False):
        if not self._context.get('do_not_refresh_stock_history'):
            self.refresh_materialised_stock_history()
        domain = []
        obj_domain = []
        offset = self.env.user.tz_offset
        if self.date_from:
            domain.append(('date', '>=', convert_to_dt_str(self.date_from, offset)))
        if self.date_to:
            date_to = (datetime.strptime(self.date_to, tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(
                days=1)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            domain.append(('date', '<', convert_to_dt_str(date_to, offset)))
        if not self.select_all_locations:
            if not self.location_ids:
                raise exceptions.Warning(_('Privaloma pasirinkti bent vieną sandėlį.'))
            domain.append(('location_id', 'in', self.location_ids.ids))
        else:
            loc_ids = self.env['stock.location'].search([('usage', 'in', ['internal']), ('active', '=', True)])
            domain.append(('location_id', 'in', loc_ids.ids))
        if self.selection_type == 'product':
            if not self.select_all_products:
                if not self.product_ids:
                    raise exceptions.Warning(_('Privaloma pasirinkti bent vieną produktą.'))
                domain.append(('product_id', 'in', self.product_ids.mapped('id')))
                obj_domain = [('id', 'in', self.product_ids.mapped('id')), ('type', '=', 'product')]
            else:
                obj_domain = [('type', '=', 'product')]
        elif self.selection_type == 'category':
            if not self.select_all_categories:
                category_ids = []
                if not self.category_ids:
                    raise exceptions.Warning(_('Privaloma pasirinkti bent vieną produkto kategoriją.'))
                for category in self.category_ids:
                    categories = self.env['product.category'].search([('id', 'child_of', category.id)])
                    category_ids.extend(categories.mapped('id'))
                category_ids = list(set(category_ids))
                domain.append(('product_category', 'in', category_ids))
                obj_domain = [('categ_id', 'in', category_ids), ('type', '=', 'product')]
            else:
                obj_domain = [('type', '=', 'product')]
        obj_domain += ['|', ('active', '=', True), ('active', '=', False)]
        if self._context.get('xls_export', False):
            attach_id = self.xls_export(domain, obj_domain)
            if threaded:
                exported_file_name = attach_id.datas_fname
                base64_file = attach_id.datas

                return {
                    'exported_file_name': exported_file_name,
                    'base64_file': base64_file
                }
            else:
                return {
                    'type': 'ir.actions.act_url',
                    'url': '/web/binary/download?res_model=inventory.summary.wizard&res_id=%s&attach_id=%s' % (
                        self[0].id, attach_id.id),
                    'target': 'self',
                }
        else:
            return {
                'context': self._context,
                'view_type': 'form',
                'view_mode': 'pivot',
                'res_model': 'stock.move.report',
                'view_id': False,
                'domain': domain,
                'type': 'ir.actions.act_window',
                'id': self.env.ref('stock_move_report.action_stock_move_summary_pivot').id,
            }


InventorySummaryWizard()
