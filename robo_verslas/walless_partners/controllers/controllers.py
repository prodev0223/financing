from odoo.addons.robo_api.controllers.api_controller import ApiController
from odoo import http
from odoo.http import request
import logging
_logger = logging.getLogger(__name__)


class ApiControllerWalless(ApiController):

    @http.route(['/api/check_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def check_invoice(self, **post):

        try:
            post = request.jsonrequest
            env = request.env
            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            invoice_obj = env['account.invoice'].sudo()
            ext_id = post.get('walless_main_ext_id', False)
            if not ext_id:
                return self.response(request, 403, 'Ext ID is not provided.')
            invoice_id = invoice_obj.search([('walless_main_ext_id', '=', ext_id)])
            if invoice_id:
                return self.response(request, 200)
            else:
                return self.response(request, 205, 'Invoice not found')

        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)

    @http.route(['/api/cancel_invoice'], type='json', auth='public', methods=['POST'], csrf=False)
    def cancel_invoice(self, **post):
        try:
            post = request.jsonrequest
            env = request.env
            # Check credentials
            res = self.check_credentials(request)
            if res:
                return self.response(request, **res)

            invoice_obj = env['account.invoice'].sudo()
            ext_id = post.get('walless_main_ext_id', False)
            if not ext_id:
                return self.response(request, 403, 'Ext ID is not provided.')
            invoice_id = invoice_obj.search([('walless_main_ext_id', '=', ext_id)])
            if invoice_id:
                if invoice_id.state in ['open']:
                    invoice_id.action_invoice_cancel()
                elif invoice_id.state in ['paid']:
                    for line in invoice_id.mapped('move_id.line_ids'):
                        if line.account_id == invoice_id.account_id:
                            line.remove_move_reconcile()
                    invoice_id.action_invoice_cancel()
                return self.response(request, 200)
            else:
                return self.response(request, 205, 'Invoice not found')
        except Exception as exc:
            # Format the message on exception
            return self.format_api_exception(request, exc)
