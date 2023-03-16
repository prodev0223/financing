# -*- coding: utf-8 -*-
from odoo import api, fields, models, exceptions, _, tools


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    selling_asset = fields.Boolean(string='Selling asset', compute='_selling_asset', store=True)
    has_assets = fields.Boolean(string='Yra ilgalaikis turtas', compute='_compute_has_assets')

    @api.multi
    @api.depends('invoice_line_ids.asset_id')
    def _selling_asset(self):
        for rec in self:
            rec.selling_asset = bool(rec.invoice_line_ids.filtered(lambda r: r.asset_id))

    @api.multi
    def _compute_has_assets(self):
        assets = self.env['account.asset.asset'].sudo().search([('invoice_id', 'in', self.ids)])
        for rec in self:
            if assets.filtered(lambda a: a.invoice_id == rec):
                rec.has_assets = True

    @api.multi
    def finalize_invoice_move_lines(self, move_lines):
        move_lines = super(AccountInvoice, self).finalize_invoice_move_lines(move_lines)
        invoice_id = False
        for line in move_lines:
            if line[0] == 0:
                invoice_id = self.browse(line[2]['invoice_id'])
                break
        if invoice_id:
            assets = invoice_id.mapped('invoice_line_ids.asset_id')

            if any(not asset.category_id.account_asset_id for asset in assets):
                raise exceptions.UserError(_('Ilgalaikio turto kategorijoje nenustatyta ilgalaikio turto sąskaita'))

            asset_account_ids = assets.mapped('category_id.account_asset_id')
            asset_account_ids |= self.sudo().env.user.company_id.account_asset_transfer_profit
            asset_account_ids |= self.sudo().env.user.company_id.account_asset_transfer_loss
            move_lines = [move_line for move_line in move_lines if
                          move_line[2].get('account_id', False) not in asset_account_ids.ids]

            for asset in assets:
                if asset.written_off_or_sold:
                    raise exceptions.UserError(_('Ilgalaikis turtas %s jau buvo parduotas.') % asset.name)

                invoice_asset_quant = sum(invoice_line.quantity for invoice_line in
                                          invoice_id.invoice_line_ids.filtered(lambda l: l.asset_id.id == asset.id))
                if tools.float_compare(invoice_asset_quant, asset.residual_quantity, precision_digits=2) > 0:
                    raise exceptions.UserError(
                        _('Ilgalaikio turto {0} turima {1} vnt., o norima parduoti {2} vnt.').format(asset.name,
                                                                                                     asset.residual_quantity,
                                                                                                     invoice_asset_quant))
                asset.ensure_lines_not_posted(invoice_id.date_invoice)
                move_lines = asset.perform_asset_sale(invoice_id, move_lines)

        return move_lines

    @api.multi
    def action_invoice_open(self):
        res = super(AccountInvoice, self).action_invoice_open()
        for rec in self:
            assets = rec.mapped('invoice_line_ids.asset_id')
            if assets and not self.env.user.is_accountant():
                raise exceptions.AccessError(_('Confirming asset-related invoice is not available. '
                                               'Please contact your accountant.'))
            for asset in assets:
                asset.compute_depreciation_board()
        return res

    @api.multi
    def action_cancel(self):
        # ASSET SALE INVOICE BEING CANCELLED (Asset id in invoice line ids)
        assets = self.mapped('invoice_line_ids.asset_id')
        for rec in self:
            for asset in self.mapped('invoice_line_ids.asset_id'):
                asset.ensure_lines_not_posted(rec.date_invoice)
        assets.write({
            'written_off_or_sold': False,
            'state': 'open',
        })
        assets.mapped('sell_move_id').button_cancel()
        assets.mapped('sell_move_id').unlink()
        AccountAssetAsset = self.env['account.asset.asset']
        all_assets = AccountAssetAsset
        all_assets |= assets
        for asset in all_assets:
            asset.compute_depreciation_board()

        # ASSET PURCHASE INVOICE BEING CANCELLED (Asset has invoice id of one of these invoices)
        assets = AccountAssetAsset.sudo().search([('invoice_id', 'in', self.ids)])
        all_assets |= assets
        for asset in assets:
            lines_posted = self.env['account.asset.depreciation.line'].search(
                [('asset_id', '=', asset.id), ('move_posted_check', '=', True)])
            if not lines_posted and asset.state != 'close' and not asset.written_off_or_sold:
                asset.set_to_draft()
                asset.unlink()
            else:
                body = _('Sąskaita (%s) buvo atšaukta, tačiau turtas %s vis dar egzistuoja.') % (
                    asset.invoice_id.document_name, asset.name)
                asset.invoice_id.message_post(body=body)
                try:
                    ticket_obj = self.env['mail.thread']._get_ticket_rpc_object()
                    subject = _('[{}] Atšaukus sąskaita, susijęs turtas nebuvo ištrintas'.format(self.env.cr.dbname))
                    vals = {
                        'ticket_dbname': self.env.cr.dbname,
                        'ticket_model_name': self._name,
                        'ticket_record_id': asset.invoice_id.id,
                        'name': subject,
                        'ticket_user_login': self.env.user.login,
                        'ticket_user_name': self.env.user.name,
                        'description': body,
                        'ticket_type': 'accounting',
                        'user_posted': self.env.user.name
                    }
                    res = ticket_obj.create_ticket(**vals)
                    if not res:
                        raise exceptions.UserError(_('The distant method did not create the ticket.'))
                except Exception as exc:
                    message = 'Failed to create ticket informing about an invoice cancelled, ' \
                              'but longterm asset not deleted. Exception: %s \nAsset ID: %s \nInvoice ID: %s' % (
                                  str(exc.args), asset.id, asset.invoice_id.id)
                    self.env['robo.bug'].sudo().create({
                        'user_id': self.env.user.id,
                        'error_message': message,
                    })
        res = super(AccountInvoice, self).action_cancel()
        return res

    @api.multi
    def show_related_assets(self):
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.asset.asset',
            'name': _('Ilgalaikis turtas'),
            'view_id': False,
            'domain': [('invoice_id', 'in', self.ids)],
        }


AccountInvoice()
