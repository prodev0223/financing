# -*- coding: utf-8 -*-

from odoo.addons.controller_report_xls.controllers import main as controller
from odoo import models, api, exceptions, fields, _
from dateutil.relativedelta import relativedelta
from datetime import datetime
import logging
import base64

_logger = logging.getLogger(__name__)


class PolisRealTimeFetcher(models.TransientModel):
    """
    Wizard that fetches real-time POLIS data and saves it in XLS file
    without record creation -- used for conserving time
    """
    _name = 'polis.real.time.fetcher'

    @api.model
    def _default_date_from(self):
        """Default date from is two weeks from today"""
        return datetime.utcnow() - relativedelta(days=14)

    @api.model
    def _default_date_to(self):
        """Default date to -- today"""
        return datetime.utcnow()

    # Dates
    date_from = fields.Datetime(default=_default_date_from, string='Data nuo')
    date_to = fields.Datetime(default=_default_date_to, string='Data iki')

    # Filters
    partner_ids = fields.Many2many('res.partner', string='Partneriai', domain="[('gemma_ext_id', '!=', False)]")
    include_canceled_sales = fields.Boolean(string='Įtraukti atšauktus pardavimus')
    include_only_done_sales = fields.Boolean(string='Įtraukti tik atliktus pardavimus')

    @api.multi
    def fetch_temporal_data(self):
        """
        Fetch data from POLIS API, filter it based on criteria, and add the data to the list.
        Fetched data returned and later used for XLS file forming
        :return: fetched POLIS data (list of dicts)
        """

        def format_date(date):
            """Sanitize date to POLIS format"""
            if date:
                return date.replace(' ', 'T')
            return False

        self.ensure_one()
        import_obj = self.env['gemma.data.import'].sudo()
        client, code = import_obj.get_api()
        try:
            data = client.service.RlGetPardavimai(
                code, format_date(self.date_from), format_date(self.date_to)).diffgram.NewDataSet.Pirkimai
        except Exception as e:
            _logger.info(e.args[0])
            data = []

        # Define a new data  set to hold temporal data
        ext_partner_codes = self.partner_ids.mapped('gemma_ext_id')
        data_set = []

        sales = data if isinstance(data, list) else [data]
        sales_list = [dict(x) for x in sales]
        for sale in sales_list:

            # Check whether sale is active if it's not, and user does not want to include
            # cancelled sales -- skip it
            active = import_obj.check_sale_significance(sale, mode='sale_cancel')
            if not active and not self.include_canceled_sales:
                continue
            values = import_obj.get_sale_values(sale)
            values.update({'cancelled': not active})

            # If external sale is not marked as done, and user only wants to include done
            # sales -- skip it
            if not values.get('ext_sale_done') and self.include_only_done_sales:
                continue

            ext_partner_code = values.get('buyer_id')
            # If user wants to fetch specific partners, and sale partner
            # is not in the list -- skip it
            if ext_partner_codes and ext_partner_code not in ext_partner_codes:
                continue

            # Get partner name based on the code
            partner_name = None
            if ext_partner_codes and ext_partner_code in ext_partner_codes:
                partner_name = self.partner_ids.filtered(lambda r: r.gemma_ext_id == ext_partner_code).name

            # If it's not in filtered partners, search for it in the system
            if not partner_name:
                partner = self.env['res.partner'].search([('gemma_ext_id', '=', ext_partner_code)])
                partner_name = partner.name if partner else None

            # If we can't find the partner in the system, fetch it's data from other endpoint
            if not partner_name:
                try:
                    partner_obj = client.service.RlGetASmDuomenys(
                        code, int(ext_partner_code)).diffgram.NewDataSet.Asmenys
                except Exception as e:
                    # On exception use partner code as a name
                    _logger.info(e.args[0])
                    partner_name = ext_partner_code
                else:
                    partner_obj = dict(partner_obj)
                    partner_name = '{} {}'.format(
                        partner_obj.get('ASM_VARDAS', str()), partner_obj.get('ASM_PAVARDE', str()))

            # Update values with fetched partner name and add values to data-set
            values.update({'partner_name': partner_name})
            data_set.append(values)
        if not data_set:
            raise exceptions.UserError(_('Nurodytame periode su pasirinktais filtrais nerasta duomenų!'))

        # Sort data_set
        data_set = sorted(data_set, key=lambda k: (k['buyer_id'], k['sale_date']))
        return data_set

    @api.multi
    def export_excel(self):
        """
        Fetch POLIS data, generate XLS file, and prepare for downloading
        :return: action to download XLS (dict)
        """
        self.ensure_one()

        data_set = self.fetch_temporal_data()
        renderer = self.env['ir.qweb']
        rendered_lines = str()

        for line in data_set:
            # Render table lines and append them to the rendered lines variable
            rendered_lines += renderer.render('gemma.polis_real_time_data_table_line', {
                'partner_name': line['partner_name'],
                'buyer_id': line['buyer_id'],
                'ext_product_code': line['ext_product_code'],
                'qty': line['qty'],
                'price': line['price'],
                'receipt_total': line['receipt_total'],
                'sale_date': line['sale_date'],
                'bed_day_date': line['bed_day_date'],
                'rehabilitation_date': line['rehabilitation_date'],
                'ext_sale_done': line['ext_sale_done'],
                'cancelled': line['cancelled'],
                'cancel_date': line['cancel_date'],
            })

        # Render the table
        rendered_table = renderer.render(
            'gemma.polis_real_time_data_table', {'table_body': rendered_lines})

        # Generate XLS base64
        header_text = 'POLIS EKSPORTAS - {} / {}'.format(self.date_from, self.date_to)
        xls_stream = controller.get_xls(
            rendered_table, self.env.context, decimal_point='.', thousands_sep=str(),
            header_text=header_text, coding='latin-1')
        file_name = '{}.xls'.format(header_text)
        xls_base64 = base64.b64encode(xls_stream)

        attach_id = self.env['ir.attachment'].create({
            'res_model': 'polis.real.time.fetcher',
            'res_id': self.id,
            'type': 'binary',
            'name': file_name,
            'datas_fname': file_name,
            'datas': xls_base64
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/binary/download?res_model=polis.real.time.fetcher&res_id=%s&attach_id=%s' % (
                self.id, attach_id.id),
            'target': 'self',
        }


PolisRealTimeFetcher()
