# -*- coding: utf-8 -*-

from odoo import models, fields, api, _, tools, exceptions
from datetime import datetime
from dateutil.relativedelta import relativedelta
from suds.client import Client
from suds.xsd.doctor import Import, ImportDoctor
import logging
import gemma_tools
import ssl


_logger = logging.getLogger(__name__)


def format_date(date):
    if date:
        return date.replace(' ', 'T')
    return False


def parse_date(date):
    if date:
        temp = date.replace('T', ' ').split('+')[0]
        if temp and '.' in temp:
            temp = temp.split('.')[0]
        return temp
    return ''


def sp_dt(date_string):
    """Convert string to datetime format"""
    return datetime.strptime(date_string, tools.DEFAULT_SERVER_DATETIME_FORMAT)


def sp_d(date_string):
    """Convert string to date format"""
    return datetime.strptime(date_string, tools.DEFAULT_SERVER_DATE_FORMAT)


class GemmaDataImport(models.TransientModel):
    _name = 'gemma.data.import'

    def date_from_default(self):
        return datetime.utcnow() - relativedelta(months=1)

    def date_to_default(self):
        return datetime.utcnow()

    use_date = fields.Boolean(string='Leisti naudoti pasirinktas datas', default=False)
    date_from = fields.Datetime(string='Duomenys nuo', default=date_from_default)
    date_to = fields.Datetime(string='Duomenys iki', default=date_to_default)

    # Processing methods ------------------------------------------------------------------------------------------

    @api.model
    def process_payment_cancels(self, payments_cancels):
        if type(payments_cancels) != list:
            payments_cancels = [payments_cancels]
        cancels = self.env['gemma.payment']

        # Comparing lock date without using check_locked_accounting so it's not fetched on each loop
        lock_date = self.env.user.company_id.get_user_accounting_lock_date()
        for cancel in payments_cancels:
            cancel = dict(cancel)
            ext_id = int(cancel.get('MokID', 0))
            if ext_id:
                payment_obj = self.env['gemma.payment'].search([('ext_payment_id', '=', ext_id)])
                if payment_obj and payment_obj.state not in ['canceled']:
                    cancel_date = parse_date(cancel.get('AnuliavimoData', ''))
                    payment_obj.cancel_date = cancel_date

                    # Check if period is not locked
                    if not payment_obj.payment_date or payment_obj.payment_date <= lock_date:
                        payment_obj.write({'state': 'cancel_locked'})
                        continue
                    cancels += payment_obj
        cancels.with_context(use_cancel_date=True).reverse_moves()

    @api.model
    def process_cash_operations(self, cash_ops, threshold_date_dt):
        cash_ops = cash_ops if isinstance(cash_ops, list) else [cash_ops]
        cash_ops_list = [dict(x) for x in cash_ops]
        for en, cash_op in enumerate(cash_ops_list, 1):
            if en % 10 == 0:
                _logger.info("Gemma cash operation import: %s/%s" % (en, len(cash_ops_list)))
            ext_id = int(cash_op.get('ID', 0))
            operation_sum = float(cash_op.get('SUMA', 0))
            date = parse_date(cash_op.get('Created', ''))

            # Skip cash operation if one of the mandatory fields is not present
            if not operation_sum or not ext_id or not date:
                continue

            # Skip cash operation if it's already in the system or it's older than threshold date
            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if self.env['gemma.payment'].search_count(
                    [('ext_payment_id', '=', ext_id)]) or date_dt < threshold_date_dt:
                continue

            values = {
                'ext_payment_id': ext_id,
                'payment_date': parse_date(cash_op.get('Created', '')),
                'cash_operation_code': str(cash_op.get('TIPAS', '').lower()),
                'department_id': int(cash_op.get('SKYRIUS', 0)),
                'payment_sum': operation_sum,
            }
            payment_id = self.env['gemma.payment'].sudo().create(values)
            if not payment_id.journal_id:
                payment_id.message_post(body='Mokėjimas importuotas su įspėjimais, sukonfigūruokite mokėjimo tipą!')

    @api.model
    def process_payments(self, payments, threshold_date_dt):
        payments = payments if isinstance(payments, list) else [payments]
        payment_list = [dict(x) for x in payments]
        for en, payment in enumerate(payment_list, 1):
            if en % 100 == 0:
                _logger.info("Gemma payment import: %s/%s" % (en, len(payment_list)))
            ext_id = int(payment.get('MokID', 0))
            cancelled = payment.get('ANULIUOTA', True)
            date = parse_date(payment.get('MokejimoData', ''))
            if type(cancelled) != bool:
                cancelled = False if cancelled.lower() in ['false', '0'] else True
            if not ext_id or not date or cancelled:
                continue

            date_dt = datetime.strptime(date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if date_dt < threshold_date_dt:
                continue

            payment_id = self.env['gemma.payment'].search([('ext_payment_id', '=', ext_id)])
            if payment_id:
                do_create = self.check_payment_changes(payment_id, payment)
                if not do_create:
                    continue

            values = self.get_payment_values(payment)
            payment_id = self.env['gemma.payment'].sudo().create(values)
            body = str()
            if not payment_id.journal_id:
                body += _('Mokėjimas importuotas su įspėjimais, sukonfigūruokite mokėjimo tipą!')
            if payment_id.type != 'cash_operations' and not payment_id.partner_id:
                body += _('Mokėjimas importuotas su įspėjimais, nerastas partneris!')
            if body:
                payment_id.message_post(body=body)

    @api.model
    def process_sale_cancels(self, sale_cancels):
        sale_cancels = sale_cancels if isinstance(sale_cancels, list) else [sale_cancels]
        cancel_list = [dict(x) for x in sale_cancels]
        cancelled_sales = self.env['gemma.sale.line']

        # Comparing lock date without using check_locked_accounting so it's not fetched on each loop
        lock_date = self.env.user.company_id.get_user_accounting_lock_date()
        for cancel in cancel_list:
            cancel_date = parse_date(cancel.get('AnuliavimoData', ''))
            if self.check_sale_significance(cancel, mode='sale_cancel'):
                continue
            sale_obj = self.sale_matcher(cancel)
            if sale_obj and sale_obj.state not in ['canceled']:
                sale_obj.cancel_date = cancel_date

                # Check whether period is locked
                if not sale_obj.sale_day or sale_obj.sale_day <= lock_date:
                    sale_obj.write({'state': 'cancel_locked'})
                    continue
                cancelled_sales += sale_obj
        cancelled_sales.credit_sales()
        if cancelled_sales:
            body = str()
            for sale in cancelled_sales.filtered(lambda r: r.refund_id):
                message = 'Pardavimas {} / Partneris {} / Pardavimo data {} / Atšaukimo data {} / ' \
                          'Kredituojama sąskaita {} / Kreditinė sąskaita {} \n\n'.format(
                           sale.ext_sale_db_id, sale.partner_id.display_name or '', sale.sale_date or '',
                           sale.cancel_date or '', sale.invoice_id.display_name or '', sale.refund_id.display_name)
                body += message
            if body:
                body = 'Atšaukti pardavimai atėję iš Polio (Tikrinimo data {}): \n\n'.format(
                        datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)) + body
                self.inform_findir(message=body, inform_type='email')

    @api.model
    def process_sales(self, sales):
        sales = sales if isinstance(sales, list) else [sales]
        sales_list = [dict(x) for x in sales]
        for en, sale in enumerate(sales_list, 1):
            if en % 100 == 0:
                _logger.info("Gemma sale import: %s/%s" % (en, len(sales_list)))
            if not self.check_sale_significance(sale, mode='sale_dates'):
                continue
            if not self.check_sale_significance(sale, mode='sale_cancel'):
                continue
            price = float(sale.get('PardavimoSuma', 0))
            sale_line = self.sale_matcher(sale)
            matched = False  # we do it like this, because we unlink sale_line if changes are present
            if sale_line:
                matched = True
                if not self.check_sale_significance(sale, mode='duplicate_check', sales_list=sales_list):
                    continue
                if not self.check_sale_changes(sale_line, sale):
                    continue
                # We reinitialize the sale_line object, since it was deleted
                # Not to cause missing error on some checks
                sale_line = self.env['gemma.sale.line']
            if not price and not matched:
                continue
            values = self.get_sale_values(sale, sale_line)
            sale_line = self.env['gemma.sale.line'].sudo().create(values)
            sale_line.force_sale_state()

    @api.model
    def process_invoices(self, invoices):
        invoices = invoices if isinstance(invoices, list) else [invoices]
        invoice_list = [dict(x) for x in invoices]
        for en, invoice in enumerate(invoice_list, 1):
            if en % 100 == 0:
                _logger.info("Gemma invoice import: %s/%s" % (en, len(invoices)))
            ext_id = int(invoice.get('Saskaitos_ID', 0))
            if not ext_id or self.env['gemma.invoice'].search_count([('ext_invoice_id', '=', ext_id)]):
                continue

            values = {
                'ext_invoice_id': ext_id,
                'payment_numbers': invoice.get('SaskaitosEilutes', ''),
                'date_invoice': parse_date(invoice.get('saskaitos_data', '')),
                'company_id': int(invoice.get('IMONES_ID', 0)),
                'buyer_id': int(invoice.get('ASM_ID', 0)),
                'name': invoice.get('SASKAITOS_NR', ''),
                'partner_code': invoice.get('AsmensKodas', ''),
                'partner_name': invoice.get('AsmensVardas', ''),
                'partner_surname': invoice.get('AsmensPavarde', ''),
                'partner_birthday': parse_date(invoice.get('AsmensGimimoData', '')),
            }
            invoice_id = self.env['gemma.invoice'].sudo().create(values)
            body = str()
            if not invoice_id.sale_line_ids:
                body += _('Importuota su ispėjimais, nerastos sąskaitos eilutės!\n')
            if invoice_id.sale_line_ids and 'warning' in invoice_id.sale_line_ids.mapped('state'):
                body += _('Rasta įspėjimų, patikrinkite sąskaitos eilutes!\n')
            if invoice_id.sale_line_ids:
                for line in invoice_id.sale_line_ids:
                    if not line.payment_id.payment_type_id.journal_id:
                        body += _('Rasta įspėjimų, patikrinkite sąskaitos eilutes!\n')
            if any(line.invoice_id or line.invoice_line_id or
                   line.state == 'created' for line in invoice_id.sale_line_ids):
                message = 'Gauta tėvinė sąskaita {} eilutėms kurios jau turi ' \
                          'padienines sąskaitas. Sąskaitos suma - {} // ' \
                          'Eilučių periodas {} - {} // Partneris - {}'.format(
                           invoice_id.name, invoice_id.invoice_total,
                           min(invoice_id.sale_line_ids.mapped('sale_day')),
                           max(invoice_id.sale_line_ids.mapped('sale_day')),
                           invoice_id.partner_id.name or invoice_id.sale_line_ids.mapped('partner_id').name)
                self.inform_findir(message=message, obj_id=invoice_id)
            if body:
                self.post_message(invoice=invoice_id, i_body=_(body), state='warning')

    # Value fetchers ---------------------------------------------------------------------------------------------

    @api.model
    def get_sale_values(self, sale, system_sale=None):
        """
        Prepare dictionary that is suitable for gemma.sale.line
        :param sale: gemma sale object (dict)
        :param system_sale: gemma.sale.line record
        :return: value dict that is ready to be passed to gemma.sale.line create method
        """
        system_sale = system_sale if system_sale else self.env['gemma.sale.line']
        ext_product_code = sale.get('PaslaugosKodas', False) or sale.get('PrekesKodas', False)
        batch_excluded = True if gemma_tools.universal_product_tax_mapping.get(ext_product_code, False) else False
        ext_sale_done = self.process_bool_value(sale.get('Atlikta'))
        values = {
            'ext_id_second': sale.get('_id', False),
            'ext_sale_id': int(sale.get('PardavimoId', 0)),
            'ext_sale_db_id': int(sale.get('DB_ID', 0)),
            'ext_product_name': sale.get('PaslaugosPavadinimas', ''),
            'price_list': sale.get('Kianorastis', ''),
            'price_list_text': sale.get('KianorastisText', ''),
            'qty': float(sale.get('KIEKIS', 0)),
            'price': float(sale.get('PardavimoSuma', 0)),
            'receipt_total': float(sale.get('CekioSuma', 0)),
            'sale_date': parse_date(sale.get('PardavimoData', '')),
            'receipt_id': int(sale.get('CekNr', 0) if type(sale.get('CekNr', 0)) == int else 0),
            'ext_payment_id': int(sale.get('MokID', 0)),
            'vat_code': sale.get('PAS_PVM_KODAS', ''),
            'batch_excluded': batch_excluded,
            'ext_sale_done': ext_sale_done,
            'cancel_date': parse_date(sale.get('AnuliavimoData', str())),
        }
        if not system_sale.ext_sale_done:
            values.update({
                'buyer_id': sale.get('ASM_ID', '0'),
                'ext_product_code': sale.get('PaslaugosKodas') or sale.get('PrekesKodas'),
                'bed_day_date': parse_date(
                    sale.get('LovadienioStacionareData', '')) or parse_date(sale.get('STAC_GULD_DATA', '')),
                'rehabilitation_date': parse_date(sale.get('DATA_NUO', ''))
            })
        return values

    @api.model
    def get_payment_values(self, payment):
        """
        Prepare dictionary that is suitable for gemma.payment
        :param payment: gemma payment object (dict)
        :return: value dict that is ready to be passed to gemma.payment create method
        """
        try:
            receipt_id = int(payment.get('CekNr', 0))
        except (UnicodeEncodeError, ValueError):
            receipt_id = 0
        values = {
            'ext_payment_type_id': int(payment.get('AtsiskaitymoTipas', 0)),
            'payment_type_text': payment.get('AtsiskaitymoTipasText', ''),
            'receipt_id': receipt_id,
            'payer_id': int(payment.get('ASM_ID', 0)) or int(payment.get('MOK_ASM_ID', 0)),
            'ext_payment_id': int(payment.get('MokID', 0)),
            'payment_date': parse_date(payment.get('MokejimoData', '')),
            'vat_rate': float(payment.get('PVMReiksme', 0)),
            'vat_class': float(payment.get('PVMklasif', 0)),
            'department_id': int(payment.get('SKYRIUS', 0)),
            'department_desc': payment.get('SkyriusText', ''),
            'payment_sum': float(payment.get('SUMA', 0)),
        }
        return values

    # Cron Jobs ---------------------------------------------------------------------------------------------------

    @api.multi
    def data_import_cron(self):

        # todo for the future: If we start accounting at certain threshold, for example 2019,
        # we can miss some credit sales, e.g: item is sold on 2018-12, and is credited on 2019-01, we do not have
        # the initial sale thus we don't credit anything

        sync_date = self.env.user.company_id.gemma_db_sync
        cron_job = self._context.get('cron_job', False)
        threshold_date_dt = datetime(2019, 1, 1)
        # dates
        if self.use_date:
            date_from = self.date_from
            if self.date_to:
                date_to = self.date_to
            else:
                date_to = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if date_to < date_from:
                raise exceptions.Warning(_('Data iki turi būti didesnė negu data nuo'))
        else:
            date_to = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            if sync_date:
                date_from = sync_date
            else:
                date_from = '2019-01-01'

        client, code = self.get_api()

        #
        # Get dated data
        if not self.env.user.company_id.gemma_db_sync:
            date_from = '2018-12-01'
            date_to = '2019-01-01'
            try:
                data = client.service.RlGetPardavimai(code, format_date(date_from),
                                                      format_date(date_to)).diffgram.NewDataSet.Pirkimai
            except Exception as e:
                _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
                data = []
            self.process_sales(data)
            self.env.cr.commit()

        #
        # Get canceled payments
        try:
            data = client.service.RlGetApmokejimai(code, format_date(gemma_tools.date_from_initial),
                                                   format_date(date_to),
                                                   date_from, date_to).diffgram.NewDataSet.Mokejimai
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_payment_cancels(data)
        self.env.cr.commit()

        #
        # Get cash operations
        try:
            data = client.service.RlGetKasosOperacijos(code, format_date(date_from),
                                                       format_date(date_to)).diffgram.NewDataSet.KasosOperacijos
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_cash_operations(data, threshold_date_dt)
        self.env.cr.commit()

        #
        # Get payments
        try:
            data = client.service.RlGetApmokejimai(code, format_date(date_from),
                                                   format_date(date_to)).diffgram.NewDataSet.Mokejimai
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_payments(data, threshold_date_dt)
        self.env.cr.commit()

        #
        # Get canceled sales
        try:
            data = client.service.RlGetPardavimai(code, format_date(gemma_tools.date_from_initial),
                                                  format_date(date_to),
                                                  date_from, date_to).diffgram.NewDataSet.Pirkimai
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_sale_cancels(data)
        self.env.cr.commit()

        #
        # Get sales
        try:
            data = client.service.RlGetPardavimai(code, format_date(date_from),
                                                  format_date(date_to)).diffgram.NewDataSet.Pirkimai
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_sales(data)
        self.env.cr.commit()

        #
        # Get previous sales and check changes
        try:
            date_from_past_period = (datetime.strptime(date_from, tools.DEFAULT_SERVER_DATETIME_FORMAT) -
                                     relativedelta(months=3)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
            data = client.service.RlGetPardavimai(code, format_date(date_from_past_period),
                                                  format_date(date_from)).diffgram.NewDataSet.Pirkimai
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_sales(data)
        self.env.cr.commit()

        #
        # Get invoices
        try:
            data = client.service.RlGetSaskaitos(code, format_date(date_from),
                                                 format_date(date_to)).diffgram.NewDataSet.Saskaitos
        except Exception as e:
            _logger.info('POLIS API Error: %s', e.args[0] if e.args else 'No message provided')
            data = []
        self.process_invoices(data)

        if cron_job:
            self.env['res.company'].search(
                [('id', '=', self.env.user.company_id.id)], limit=1).write({'gemma_db_sync': datetime.utcnow()})
            to_return = None
        else:
            to_return = {
                'name': _('Pardavimai'),
                'view_type': 'form',
                'view_mode': 'tree',
                'view_id': self.env.ref('gemma.gemma_sale_line_tree').id,
                'res_model': 'gemma.sale.line',
                'type': 'ir.actions.act_window',
                'target': 'current',
            }
        self.env.cr.commit()
        self.env['gemma.sale.line'].cron_recreate()
        return to_return

    @api.model
    def cron_delete_sales(self):
        potentially_deletable = self.env['gemma.sale.line']
        deletable = self.env['gemma.sale.line']
        client, code = self.get_api()

        if self._context.get('force_date_from', False):
            date_from = self._context.get('force_date_from')
            date_from_dt = datetime.strptime(date_from, tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            date_from_dt = datetime.utcnow() - relativedelta(months=2, day=1)
            date_from = date_from_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

        if self._context.get('force_threshold_date', False):
            threshold_date = self._context.get('force_threshold_date')
            threshold_date_dt = datetime.strptime(threshold_date, tools.DEFAULT_SERVER_DATE_FORMAT)
        else:
            threshold_date_dt = datetime(2019, 04, 01)

        date_to_dt = datetime.utcnow()
        date_to = date_to_dt.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        try:
            sales = client.service.RlGetPardavimai(code, format_date(date_from),
                                                  format_date(date_to)).diffgram.NewDataSet.Pirkimai
        except Exception as e:
            body = _('Gemma deletion fail - SUDS access. Exception: %s') % e
            _logger.info(body)
            self.send_bug(body)
            return

        gsl = self.env['gemma.sale.line'].search([])
        gsl = gsl.filtered(lambda r: date_to_dt >= datetime.strptime(r.sale_day,
                                                                     tools.DEFAULT_SERVER_DATE_FORMAT) >= date_from_dt)
        db_ids = [int(dict(x).get('DB_ID', 0)) for x in sales]
        for line in gsl:
            if line.ext_sale_db_id not in db_ids:
                potentially_deletable += line

        if potentially_deletable:
            dates = sorted(list(set([x.sale_date[:10] for x in potentially_deletable])),
                           key=lambda r: datetime.strptime(r, tools.DEFAULT_SERVER_DATE_FORMAT))

            widest_gap = (
                (datetime.strptime(dates[0], tools.DEFAULT_SERVER_DATE_FORMAT) - relativedelta(days=1)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT),
                (datetime.strptime(dates[-1], tools.DEFAULT_SERVER_DATE_FORMAT) + relativedelta(days=1)).strftime(
                    tools.DEFAULT_SERVER_DATE_FORMAT)
            )

            # Second call, because RlGetPardavimai returns sales BY modification date,
            # however we can only see sale date, so sale date like 2019-01-01 can occur in gap 2019-06-01 -- 2019-06-30,
            # we need wider filter. Also add one day for safety
            try:
                sales = client.service.RlGetPardavimai(code, widest_gap[0] + 'T00:00:00',
                                                       widest_gap[1] + 'T23:59:59').diffgram.NewDataSet.Pirkimai
            except Exception as e:
                body = _('Gemma deletion fail - SUDS access / wider gap. Exception: %s') % e
                _logger.info(body)
                self.send_bug(body)
                return

            db_ids = [int(dict(x).get('DB_ID', 0)) for x in sales]
            for line in potentially_deletable:
                if line.ext_sale_db_id not in db_ids:
                    deletable += line

            no_id = deletable.filtered(lambda r: not r.ext_sale_db_id)
            if no_id:
                body = 'Gemma deletion - %s records skipped due to ambiguity, ' \
                       'no DB ID found - gap - %s' % (len(no_id), str(widest_gap))
                self.send_bug(body)

            deletable = deletable.filtered(lambda r: r.ext_sale_db_id and datetime.strptime(
                r.sale_day, tools.DEFAULT_SERVER_DATE_FORMAT) >= threshold_date_dt)

            _logger.info('Gemma Deletion: Total deletable sales %s ' % len(deletable))
            invoices = deletable.mapped('invoice_id')
            for invoice in invoices:
                corresponding_sales = deletable.filtered(lambda x: x.invoice_id.id == invoice.id)
                dummy = self.env['gemma.invoice']
                self.env['gemma.sale.line'].with_context(correction=True).create_invoices(
                    line_ids=corresponding_sales, ext_invoice=dummy)
            deletable.write({'invoice_id': False, 'invoice_line_id': False})
            deletable.unlink()

    # Matchers ----------------------------------------------------------------------------------------------------

    @api.model
    def sale_matcher(self, sale_dict):
        ext_sale_db_id = int(sale_dict.get('DB_ID', 0))
        dummy = self.env['gemma.sale.line']
        return self.env['gemma.sale.line'].search(
            [('ext_sale_db_id', '=', ext_sale_db_id), ('active', '=', True)]) if ext_sale_db_id else dummy

    # Change Checkers ---------------------------------------------------------------------------------------------

    @api.model
    def check_sale_significance(self, sale, mode='bed_dates', sales_list=None):
        sales_list = [] if sales_list is None else sales_list
        if mode in ['bed_dates', 'rehab_dates', 'sale_dates']:
            threshold_accounting = datetime(2019, 1, 1)
            bed_date = parse_date(sale.get('LovadienioStacionareData', '')) or parse_date(
                sale.get('STAC_GULD_DATA', ''))
            spec_date = parse_date(sale.get('DATA_NUO', '')) if mode in ['rehab_dates'] else bed_date
            sale_date = parse_date(sale.get('PardavimoData', ''))
            if sale_date:
                if mode != 'sale_dates' and not spec_date:
                    return False
                sale_date_dt = datetime.strptime(sale_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                if sale_date_dt < threshold_accounting:
                    return False
                if spec_date:
                    spec_date_dt = datetime.strptime(spec_date, tools.DEFAULT_SERVER_DATETIME_FORMAT)
                    if spec_date_dt < threshold_accounting:
                        return False
                return True if mode == 'sale_dates' else spec_date
            else:
                return False
        elif mode in ['sale_cancel']:
            cancelled = sale.get('PardAnuliuotas', False)
            if type(cancelled) != bool:
                cancelled = False if cancelled.lower() in ['false', '0'] else True
            if cancelled:
                return False
            return True
        elif mode in ['payment_cancel']:
            cancelled_payment = sale.get('MokAnuliuotas', False)
            if type(cancelled_payment) != bool:
                cancelled_payment = False if cancelled_payment.lower() in ['false', '0'] else True
            return cancelled_payment
        elif mode in ['duplicate_check']:
            potential_duplicates = filter(lambda r: r['DB_ID'] == sale.get('DB_ID'), sales_list)
            if len(potential_duplicates) > 1:
                not_cancelled_count = 0
                statuses_unfixed = [x.get('MokAnuliuotas', False) for x in potential_duplicates]
                for x in statuses_unfixed:
                    if type(x) != bool:
                        x = False if x.lower() in ['false', '0'] else True
                    if not x:
                        not_cancelled_count += 1
                if not_cancelled_count > 1 or self.check_sale_significance(sale, mode='payment_cancel'):
                    return False
            return True

    @api.model
    def check_sale_changes(self, sale_id, sale):
        """
        Checks changes between gemma.sale.line object in the system, and newly modified object
        from POLIS. If system sale is not in created/canceled/cancel_locked state - write all of the changes
        otherwise check for specific column changes
        :param sale_id: gemma.sale.line object in the system
        :param sale: newly fetched gemma sale data
        :return: True if new sale needs to be created, False if not
        """
        if sale_id.state not in ['created', 'cancel', 'cancel_locked']:
            values = self.get_sale_values(sale, sale_id)
            sale_id.write(values)
            sale_id.force_sale_state()
        else:
            bed_date = self.get_bet_date(sale)
            if sale_id.partner_id:
                lock_date = sale_id.partner_id.gemma_lock_date
                if lock_date:
                    lock_date_dt = sp_d(lock_date)
                    if sp_d(sale_id.sale_day) < lock_date_dt:
                        return True

            sale_bed_date_dt = sp_dt(sale_id.bed_day_date) if sale_id.bed_day_date else False
            bed_date_dt = sp_dt(bed_date) if bed_date else False
            to_change = {}
            buyer_id = str(sale.get('ASM_ID', 0))
            price = float(sale.get('PardavimoSuma', 0))
            if tools.float_compare(sale_id.price, price, precision_digits=2) != 0:
                to_change['price'] = price
            if (bed_date_dt and sale_bed_date_dt and bed_date_dt != sale_bed_date_dt) or \
                    (not sale_bed_date_dt and bed_date_dt):
                to_change['bed_day_date'] = bed_date
                to_change['state'] = 'imported'
            if buyer_id and sale_id.buyer_id != buyer_id and not sale_id.partner_id \
                    and sale_id.state not in ['canceled']:
                to_change['buyer_id'] = buyer_id
            if to_change:
                if sale_id.state in ['created']:
                    if self.env.user.company_id.check_locked_accounting(sale_id.sale_day):
                        sale_id.write({'state': 'cancel_locked'})
                        return False
                    if not sale_id.refund_id and not sale_id.correction_id and sale_id.invoice_id:
                        sale_id.credit_sales()
                    sale_id.write({'invoice_line_id': False, 'invoice_id': False})
                    sale_id.unlink()
                    self.env.cr.commit()
                    return True
        return False

    @api.model
    def check_payment_changes(self, payment_id, payment):
        """
        Checks changes between gemma.payment object in the system, and newly modified object
        from POLIS. If system payment is not in created/canceled/cancel_locked state - write all of the changes
        otherwise check for specific column changes
        :param payment_id: gemma.payment object in the system
        :param payment: newly fetched gemma payment data
        :return: True if new payment needs to be created, False if not
        """
        payment_sum = float(payment.get('SUMA', 0))
        payer_id = str(payment.get('MOK_ASM_ID', 0))
        to_change = {}
        if payment_id.state in ['active', 'warning', 'failed']:
            values = self.get_payment_values(payment)
            payment_id.write(values)
        elif payment_id.state not in ['canceled', 'cancel_locked']:
            if tools.float_compare(payment_id.payment_sum, payment_sum, precision_digits=2) != 0 and \
                    payment_id.state not in ['canceled']:
                to_change['payment_sum'] = payment_sum
            if payer_id and payment_id.payer_id != payer_id and not payment_id.partner_id \
                    and payment_id.state not in ['canceled']:
                to_change['payer_id'] = payer_id
            if to_change:
                if self.env.user.company_id.check_locked_accounting(payment_id.payment_date):
                    payment_id.write({'state': 'cancel_locked'})
                    return False
                payment_id.reverse_moves()
                payment_id.write({'move_id': False})
                payment_id.unlink()
                self.env.cr.commit()
                return True
        return False

    # Misc Methods ------------------------------------------------------------------------------------------------

    @api.model
    def inform_findir(self, message, obj_id=None, inform_type='post'):
        if inform_type in ['post'] and obj_id is not None:
            obj_id.robo_message_post(subtype='mt_comment', body=message,
                                     partner_ids=self.env.user.company_id.findir.partner_id.ids,
                                     priority='high')
        elif inform_type in ['email']:
            findir_email = self.sudo().env.user.company_id.findir.partner_id.email
            database = self._cr.dbname
            subject = '{} // [{}]'.format('Polis Alert', database)
            self.env['script'].send_email(emails_to=[findir_email],
                                          subject=subject,
                                          body=message)

    @api.model
    def post_message(self, lines=None,
                     l_body=None, state=None, invoice=None, i_body=None):
        if lines is None:
            lines = self.env['gemma.sale.line']
        if invoice is None:
            invoice = self.env['gemma.invoice']
        if lines:
            msg = {'body': l_body}
            for line in lines:
                line.message_post(**msg)
            if state is not None:
                lines.write({'state': state})
        if invoice:
            msg = {'body': i_body}
            invoice.message_post(**msg)
            if state is not None:
                invoice.state = state

    @api.model
    def send_bug(self, body):
        """
        Send bug to Robolabs support
        :param body: bug body
        :return: None
        """
        self.env['robo.bug'].sudo().create({
            'user_id': self.env.user.id,
            'error_message': body,
        })

    @api.model
    def get_bet_date(self, sale):
        """Fetch bed date from ext gemma sale object"""
        bed_date = parse_date(sale.get('LovadienioStacionareData', '')) or parse_date(
            sale.get('STAC_GULD_DATA', ''))
        return bed_date

    @api.model
    def process_bool_value(self, value):
        """
        Check whether passed value can be converted to pythonic boolean, if not, return False
        otherwise converted value
        :param value: Value to be tested for boolean
        :return: True / False
        """
        if not isinstance(value, bool):
            if isinstance(value, int) and value in [1, 0]:
                return bool(value)
            if isinstance(value, basestring):
                return True if value.lower() in ['true', '1'] else False
            return False
        return value

    @api.model
    def get_api(self):
        """
        Read systems' config parameters, create ssl context and connect
        to external POLIS api using suds library.
        :return: suds client object, external POLIS login code
        """
        config_obj = self.sudo().env['ir.config_parameter']
        url = config_obj.get_param('gemma_url')
        code = config_obj.get_param('gemma_code')
        if hasattr(ssl, '_create_unverified_context'):
            ssl._create_default_https_context = ssl._create_unverified_context
        imp = Import(
            'https://www.w3.org/2009/XMLSchema/XMLSchema.xsd',
            location='https://www.w3.org/2009/XMLSchema/XMLSchema.xsd'
        )
        imp.filter.add('http://medsystem.lt/md')
        client = Client(url, plugins=[ImportDoctor(imp)], timeout=100)
        return client, code


GemmaDataImport()
