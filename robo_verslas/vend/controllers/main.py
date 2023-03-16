# -*- coding: utf-8 -*-
from odoo import tools
from odoo import http
from odoo.http import request
from datetime import datetime


class VendController(http.Controller):

    @http.route(['/api/vend/create_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def create_invoice(self, **post):
        '''
                    Sample request:
                    post = {
                            'username': 'vend',
                            'password': 'HKJgg8676578gyyijjvfjgFHGFuf887990hggjvJGVJhk',
                            'date_invoice': '2017-08-28',
                            'number': 'KL00001',
                            'currency': 'EUR',
                            'partner': {
                                'name': 'Client Name',
                                'is_company': True,
                                'company_code': '123456789',
                                'vat_code': 'LT123456715',
                                'street': 'Gatve 1',
                                'city': 'Vilnius',
                                'zip': 'LT-12345',
                                'country': 'LT',
                                'phone': '+370612345678',
                                'email': 'email@email.com',
                            },
                            'invoice_lines':
                            [
                                {
                                    'product': 'Paslaugos',
                                    'price': 100.0,
                                    'qty': 1.0,
                                    'vat': 0.0,
                                },
                            ],
                        }
                    '''
        def response(text, code):
            return {
                'error': text,
                'status_code': code,
            }
        try:
            post = request.jsonrequest
            if 'username' not in post or 'password' not in post:
                return response('Access denied. No login data provided.', 400)
            if post['username'] != u'vend' or post['password'] != u'HKJgg8676578gyyijjvfjgFHGFuf887990hggjvJGVJhk':
                return response('Access denied. Incorrect credentials.', 400)
            user_id = request.env['res.users'].sudo().search([('login', '=', 'karolis.kirkliauskas@gmail.com')], limit=1)
            if not user_id:
                return response('User not found.', 400)
            env = request.env
            invoice_obj = env['account.invoice'].sudo()
            currency_obj = env['res.currency'].sudo()
            partner_obj = env['res.partner'].sudo()
            country_obj = env['res.country'].sudo()
            product_obj = env['product.product'].sudo()
            category_obj = env['product.category'].sudo()
            journal_obj = env['account.journal'].sudo()
            account_obj = env['account.account'].sudo()
            journal_id = journal_obj.search([('code', '=', 'AUTO'), ('type', '=', 'sale')], limit=1)
            invoice_vals = {
                'user_id': user_id.id,
            }
            if journal_id:
                invoice_vals['journal_id'] = journal_id.id
            if 'date_invoice' not in post:
                invoice_vals['date_invoice'] = datetime.utcnow().strftime(tools.DEFAULT_SERVER_DATE_FORMAT)
            else:
                invoice_vals['date_invoice'] = post['date_invoice']
            currency_id = False
            if 'currency' in post:
                currency_id = currency_obj.search([('name', '=', post['currency'])], limit=1)
            if currency_id:
                invoice_vals['currency_id'] = currency_id.id
            else:
                return response('Incorrect currency', 401)
            if 'number' not in post or not post['number']:
                return response('Missing invoice number', 401)
            invoice_vals['number'] = post['number']
            if 'partner' not in post or not post['partner']:
                return response('Missing partner info', 401)
            partner = post['partner']
            partner_code = partner['company_code'] if 'company_code' in partner else False
            partner_vat = partner['vat_code'] if 'vat_code' in partner else False
            partner_name = partner['name'] if 'name' in partner else False
            partner_id = False
            if partner_code:
                partner_id = partner_obj.search([('kodas', '=', partner_code)], limit=1)
            if not partner_id and partner_vat:
                partner_id = partner_obj.search([('vat', '=', partner_vat)], limit=1)
            if not partner_id and partner_name:
                partner_id = partner_obj.search([('name', '=', partner_name)], limit=1)
            if not partner_id:
                if 'country' in partner:
                    country_id = country_obj.search([('code', '=', partner['country'])], limit=1)
                else:
                    country_id = country_obj.search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': partner['name'] if 'name' in partner else False,
                    'is_company': partner['is_company'] if 'is_company' in partner else False,
                    'kodas': partner['company_code'] if 'company_code' in partner else False,
                    'vat': partner['vat_code'] if 'vat_code' in partner else False,
                    'street': partner['street'] if 'street' in partner else False,
                    'city': partner['city'] if 'city' in partner else False,
                    'zip': partner['zip'] if 'zip' in partner else False,
                    'country_id': country_id.id,
                    'phone': partner['phone'] if 'phone' in partner else False,
                    'email': partner['email'] if 'email' in partner else False,
                }
                partner_id = partner_obj.create(partner_vals)
            account_id = account_obj.search([('code', '=', '2410'), ('company_id', '=', env.user.company_id.id)])
            if account_id:
                invoice_vals['account_id'] = account_id.id
            if 'invoice_lines' not in post:
                return response('Missing invoice lines', 401)
            invoice_vals['partner_id'] = partner_id.id
            invoice_lines = []
            invoice_vals['invoice_line_ids'] = invoice_lines
            for line in post['invoice_lines']:
                if 'product' not in line:
                    return response('Missing invoice lines', 401)
                product = line['product']
                if not product:
                    return response('Missing product name', 401)
                category_id = False
                product_id = product_obj.search([('name', '=', product)], limit=1)
                if not product_id:
                    category_id = env.ref('l10n_lt.product_category_2', raise_if_not_found=False)
                    if not category_id:
                        category_id = category_obj.search([('name', '=', 'Parduodamos paslaugos')], limit=1)
                    if not category_id:
                        request.env.cr.rollback()
                        request.env['robo.bug'].sudo().create({'user_id': user_id.id,
                                                               'error_message': 'Missing category',})
                        request.env.cr.commit()
                        return response('Missing product category', 402)
                    product_id = product_obj.create({
                        'name': product,
                        'categ_id': category_id.id,
                        'type': 'service',
                        'sale_ok': True,
                    })
                product_account = product_id.get_product_income_account(return_default=True)
                invoice_lines.append((0, 0, {
                    'product_id': product_id.id,
                    'name': product,
                    'quantity': line['qty'],
                    'price_unit': line['price'],
                    'account_id': product_account.id,
                }))
            invoice_id = invoice_obj.create(invoice_vals)
            invoice_id.partner_data_force()
            invoice_id.write({
                'move_name': post['number'],
            })
            invoice_id.action_invoice_open()
            invoice_id.write({
                'number': post['number'],
                'move_name': post['number'],
                'reference': post['number'],
            })
            return True
        except:
            return response('Unexpected error', 404)
