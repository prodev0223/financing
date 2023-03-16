# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import api, fields, models, _, tools
import logging
_logger = logging.getLogger(__name__)


class Report(models.Model):
    _inherit = 'report'

    @api.model
    def get_pdf(self, docids, report_name, html=None, data=None):
        """
        This method generates and returns pdf version of a report.
        :param docids: list of record ids
        :param report_name: name of the report (str)
        :param html:
        :param data:
        :return: pdf content as a str
        """
        res = super(Report, self).get_pdf(docids, report_name, html, data)
        if report_name == 'saskaitos.report_invoice' and len(docids) == 1 and self.env.user.company_id.embed_einvoice_xml:
            invoice = self.env['account.invoice'].browse(docids[0])
            try:
                if invoice.type in ('out_invoice', 'out_refund') and invoice.state in ['open', 'paid'] and not invoice.partner_id.do_not_embed_einvoice_xml:
                    res = invoice.insert_xml_content_into_pdf(res)
            except Exception as e:
                name = invoice.number or 'ID:%s' % invoice.id
                message = 'Failed to embed invoice XML inside PDF (invoice %s). Error message:\n%s' % (name, str(e))
                self.env['robo.bug'].sudo().create({
                    'user_id': self.env.user.id,
                    'error_message': message,
                })
                _logger.info('Invoice XML embedding failed. Exception message: %s', str(e))
        return res


Report()