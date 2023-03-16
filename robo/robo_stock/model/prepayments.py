# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, tools
from datetime import datetime


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_prepaid_ready = fields.Boolean(string='Sumokėtas avansas', default=False, copy=False)

    @api.model
    def check_if_prepaid_ready(self):
        quotations_check = self.env['sale.order'].search([('state', 'in', ['draft', 'sent']),
                                                          ('is_prepaid_ready', '=', True)])
        for quot in quotations_check:
            sale_order_amount = 0.0
            for ol in quot.order_line:
                sale_order_amount += ol.price_total
            currency = quot.pricelist_id.currency_id
            orig_sale_order_amount = sale_order_amount
            if currency.id != quot.company_id.currency_id.id:
                sale_order_amount = currency.compute(sale_order_amount, quot.company_id.currency_id)
            available_credit = quot.get_partner_available_credit()
            available_credit_currency = quot.with_context(currency=currency).get_partner_available_credit()
            if available_credit <= 0 or (sale_order_amount > available_credit and orig_sale_order_amount > available_credit_currency) or sale_order_amount <= 0.0:
                quot.is_prepaid_ready = False
        skip_ids = quotations_check.mapped('id')
        quotations = self.env['sale.order'].search([('state', 'in', ['sale']),
                                                    ('is_prepaid_ready', '=', False)])
        for partner_id in quotations.mapped('partner_id'):
            u_available_credit = None
            u_available_credit_currency = None
            for i, quot in enumerate(quotations.filtered(lambda r: r.partner_id.id == partner_id.id).sorted(key=lambda r: r.date_order)):

                if quot.id in skip_ids:
                    continue
                currency = quot.pricelist_id.currency_id
                if i == 0 or (i > 1 and u_available_credit is None):
                    available_credit = quot.get_partner_available_credit()
                    available_credit_currency = quot.with_context(currency=currency).get_partner_available_credit()
                    u_available_credit, u_available_credit_currency = available_credit, available_credit_currency

                sale_order_amount = 0.0
                for ol in quot.order_line:
                    sale_order_amount += ol.price_total

                orig_sale_order_amount = sale_order_amount
                if currency.id != quot.company_id.currency_id.id:
                    sale_order_amount = currency.compute(sale_order_amount, quot.company_id.currency_id)
                precision = currency.rounding
                if tools.float_compare(u_available_credit, 0, precision_rounding=precision) <= 0 \
                        or tools.float_compare(sale_order_amount, 0.0, precision_rounding=precision) <= 0:
                        # or (tools.float_compare(sale_order_amount, u_available_credit, precision_rounding=precision) > 0 and tools.float_compare(orig_sale_order_amount, u_available_credit_currency, precision_rounding=precision) > 0) \

                    quot.is_prepaid_ready = False
                else:
                    quot.is_prepaid_ready = True
                    if quot.company_id.currency_id.id == currency.id:
                        body = _("Yra naujų %s kliento mokėjimų. Bendras prieinamas kreditas: %s %s.") % (quot.partner_id.name, u_available_credit, quot.company_id.currency_id.name)
                    else:
                        body = _("Yra naujų %s kliento mokėjimų. Bendras prieinamas kreditas: %s %s (%s %s).") % (
                            quot.partner_id.name, u_available_credit, quot.company_id.currency_id.name,
                            u_available_credit_currency, currency.name)
                    msg = {
                        'body': body,
                        'robo_chat': True,
                        'client_message': True,
                        'priority': 'high',
                        'front_message': True,
                        'partner_ids': [quot.user_id.partner_id.id],
                        'action_id': self.env.ref('robo_stock.open_robo_sale_orders').id,
                        'rec_model': 'sale.order',
                        'rec_id': quot.id,
                    }
                    quot.with_context(internal_ticketing=True).robo_message_post(**msg)
                    u_available_credit -= sale_order_amount
                    u_available_credit_currency -= sale_order_amount
        return

    def get_partner_available_credit(self):
        # We sum from all the sale orders that are approved, the sale order
        # lines that are not yet invoiced
        forced_currency_id = self._context.get('currency', False)
        domain = [('order_id.partner_id', '=', self.partner_id.id),
                  ('invoice_status', 'not in', ['invoiced']),
                  ('order_id.state', 'not in', ['draft', 'cancel', 'sent']),
                  ('order_id.is_prepaid_ready', '=', True)]
        order_lines = self.env['sale.order.line'].sudo().search(domain)
        none_invoiced_amount = sum(x.currency_id.with_context(date=x.order_id.date_order or datetime.now()).compute(x.price_total, forced_currency_id or x.company_id.currency_id) for x in order_lines)
        # We sum from all the invoices that are in draft the total amount
        domain = [('partner_id', '=', self.partner_id.id),
                  ('state', '=', 'draft'),
                  ('invoice_type', 'in', ['out_invoice', 'out_refund'])]
        draft_invoices = self.env['account.invoice'].sudo().search(domain)
        if not forced_currency_id:
            draft_invoices_amount = sum(x.amount_total_company_signed for x in draft_invoices)
            credit = self.partner_id.sudo().credit
        else:
            draft_invoices_amount = sum(
                x.with_context(date=x.operacijos_date or x.date_invoice or datetime.now()
                               ).currency_id.compute(x.amount_total_signed, forced_currency_id)
                for x in draft_invoices
            )
            # get credit
            tables, where_clause, where_params = self.env['account.move.line']._query_get()
            where_params = [(self.partner_id.id)]
            self._cr.execute("""SELECT l.partner_id, act.type, SUM(l.amount_residual), SUM(l.amount_residual_currency), l.currency_id
                              FROM account_move_line l
                              LEFT JOIN account_account a ON (l.account_id=a.id)
                              LEFT JOIN account_account_type act ON (a.user_type_id=act.id)
                              WHERE act.type IN ('receivable','payable')
                              AND l.partner_id = %s
                              AND l.reconciled IS FALSE
                              """ + where_clause + """
                              GROUP BY l.partner_id, act.type, l.currency_id
                              """, where_params)
            credit_currency = {}
            for pid, type, cval, val, cur in self._cr.fetchall():
                if not cur:
                    cur = self.env.user.sudo().company_id.currency_id.id
                    val = cval
                if cur not in credit_currency:
                    credit_currency[cur] = 0.0
                credit_currency[cur] += val
            if forced_currency_id.id in credit_currency:
                credit = credit_currency[forced_currency_id.id]
                credit_currency.pop(forced_currency_id.id)
            else:
                credit = 0.0
            for key,val in credit_currency.items():
                credit += self.env['res.currency'].browse(key).compute(val, forced_currency_id)
        credit *= -1
        available_credit = credit - draft_invoices_amount - none_invoiced_amount
        return available_credit


SaleOrder()
