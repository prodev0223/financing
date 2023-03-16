# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class RKeeperPaymentType(models.Model):
    _name = 'r.keeper.payment.type'
    _description = '''
    Model that stores rKeeper payment types,
    specific account journal and settings
    can be assigned to each type.
    '''

    # Identification
    name = fields.Char(string='Mokėjimo tipo pavadinimas')
    code = fields.Char(string='Mokėjimo tipo kodas')

    journal_id = fields.Many2one('account.journal', string='Susietas žurnalas', copy=False)

    # Other fields
    create_payment = fields.Boolean(string='Kurti mokėjimą', default=True)
    do_reconcile = fields.Boolean(string='Automatiškai dengti sąskaitas', default=True)
    configured = fields.Boolean(string='Sukonfigūruotas', compute='_compute_configured', store=True)
    configured_text = fields.Text(compute='_compute_configured')
    cash_payment_type = fields.Boolean(string='Grynieji pinigai')

    # Refund fields
    create_refund_invoice = fields.Boolean(string='Kurti kreditinę sąskaitą')
    refund_invoice_product = fields.Many2one(
        'product.product', string='Kreditinės sąskaitos produktas',
        domain="[('type', '=', 'service')]"
    )
    refund_invoice_tax = fields.Many2one(
        'account.tax', string='Kreditinės sąskaitos mokestis',
        domain="[('price_include', '=', True), ('type_tax_use', '=', 'sale')]"
    )

    # Computes / Constraints ------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('name', 'code', 'journal_id', 'cash_payment_type')
    def _compute_configured(self):
        """
        Compute //
        Checks whether current payment type is configured
        :return: None
        """
        for rec in self:
            # If current payment type is cash type,
            # it does not require a journal
            configured = rec.name and rec.code
            if not rec.cash_payment_type:
                configured = configured and rec.journal_id

            rec.configured_text = _('Sėkmingai sukonfigūruota') if configured else _('Trūksta konfigūracijos')
            rec.configured = configured

    @api.multi
    @api.constrains('code')
    def _check_code(self):
        """
        Constraints //
        Ensures that payment type code is unique
        :return: None
        """
        for rec in self:
            if self.search_count([('code', '=', rec.code)]) > 1:
                raise exceptions.ValidationError(_('Mokėjimo tipo kodas %s jau egzistuoja sistemoje!') % rec.code)

    # Utility Methods -------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(rec.id, rec.name or _('Mokėjimo tipas #{}').format(rec.id)) for rec in self]

