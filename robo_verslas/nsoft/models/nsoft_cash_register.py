# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
register_mapper = {
    'web': 'WEB-REGISTER',
    'trans': 'TRANS-REGISTER',
    'gft': 'GIFT-CARD-REGISTER',
    'no_receipt': 'NO-RECEIPT-REGISTER'
}


class NsoftCashRegister(models.Model):
    _name = 'nsoft.cash.register'

    @api.model
    def _default_location_id(self):
        """Returns default location - most recent internal type"""
        return self.env['stock.location'].search(
            [('usage', '=', 'internal')], order='create_date desc', limit=1,
        )

    @api.model
    def _default_journal_id(self):
        """Returns default journal - first occurrence of sale type"""
        return self.env['account.journal'].search([('type', '=', 'sale')], limit=1)

    @api.model
    def _default_cash_journal_id(self):
        """Returns default cash journal - first occurrence of cash type"""
        return self.env['account.journal'].search([('type', '=', 'cash')], limit=1)

    # Identifier fields
    ext_id = fields.Integer(string='External ID')
    cash_register_number = fields.Char(
        required=True, inverse='_set_cash_register_number',
        string='Kasos aparato numeris',
    )
    cash_register_name = fields.Char(
        string='Kasos aparato pavadinimas',
    )

    # Other fields
    state = fields.Selection([
        ('working', 'Kasos aparatas veikiantis'),
        ('failed', 'Trūksta konfigūracijos')],
        string='Būsena', compute='_compute_state'
    )
    spec_register = fields.Selection([
        ('web', 'Internetinių pardavimų kasos aparatas'),
        ('trans', 'Pavedimų kasos aparatas'),
        ('gft', 'Dovanų čekių aparatas'),
        ('no_receipt', 'Mokėjimai be čekio'),
        ('not_used', 'Nenaudojama')],
        string='Specialus kasos aparatas',
        default='not_used', readonly=True
    )

    # Relational fields
    partner_id = fields.Many2one('res.partner', string='Susietas partneris')
    location_id = fields.Many2one(
        'stock.location', default=_default_location_id,
        domain="[('usage','=','internal')]",
        string='Kasos aparato lokacija',
    )
    journal_id = fields.Many2one(
        'account.journal', default=_default_journal_id,
        string='Pagrindinis Žurnalas'
    )

    cash_journal_id = fields.Many2one(
        'account.journal', string='Cash journal',
        domain="[('type', '=', 'cash')]", copy=False,
        default=_default_cash_journal_id
    )

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        domain="[('account_type', 'in', ['income', 'profit'])]",
        string='Default analytic account',
    )
    show_analytic_account_selection = fields.Boolean(
        compute='_compute_show_analytic_account_selection',
    )

    employee_ids = fields.Many2many(
        'hr.employee', string='POS employees',
    )

    # Computes / Inverses / Constraints -------------------------------------------------------------------------------

    @api.multi
    def _compute_show_analytic_account_selection(self):
        """
        Check whether analytic account field should be displayed in the form view
        :return: None
        """
        robo_analytic_installed = self.sudo().env['ir.module.module'].search_count(
            [('name', '=', 'robo_analytic'), ('state', 'in', ['installed', 'to upgrade'])])
        for rec in self:
            rec.show_analytic_account_selection = robo_analytic_installed

    @api.multi
    @api.depends('journal_id', 'location_id', 'cash_register_number', 'partner_id')
    def _compute_state(self):
        """Computes the state for current POS"""
        for rec in self:
            working = rec.journal_id and rec.location_id and rec.cash_register_number and rec.partner_id
            rec.state = 'working' if working else 'failed'

    @api.multi
    def _set_cash_register_number(self):
        """Creates or relates partner record for current POS based on external number"""
        # Ref needed objects
        ResPartner = self.env['res.partner'].sudo()
        ResCountry = self.env['res.country'].sudo()

        # Ref needed accounts
        account_2410 = self.env.ref('l10n_lt.1_account_229')
        account_4430 = self.env.ref('l10n_lt.1_account_378')

        for rec in self.filtered(lambda x: x.cash_register_number):
            partner = ResPartner.search([('kodas', '=', rec.cash_register_number)], limit=1)
            if not partner:
                country_id = ResCountry.sudo().search([('code', '=', 'LT')], limit=1)
                partner_vals = {
                    'name': _('{} Kasos operacijos').format(rec.cash_register_number),
                    'is_company': True,
                    'kodas': rec.cash_register_number,
                    'country_id': country_id.id,
                    'property_account_receivable_id': account_2410.id,
                    'property_account_payable_id': account_4430.id,
                }
                partner = ResPartner.create(partner_vals)
            rec.partner_id = partner

    @api.constrains('cash_register_number')
    def _check_cash_register_number(self):
        """Ensures that cash register number is unique"""
        for rec in self:
            if rec.cash_register_number:
                if self.search_count([('cash_register_number', '=', rec.cash_register_number)]) > 1:
                    raise exceptions.ValidationError(_('Kasos aparatas jau egzistuoja!'))

    @api.constrains('employee_ids')
    def _check_employee_ids(self):
        """Ensure that same partner is not repeated in other registers"""
        for rec in self.filtered('employee_ids'):
            for employee in rec.employee_ids:
                point_of_sale = self.search([
                    ('employee_ids', 'in', employee.id), ('id', '!=', rec.id),
                ])
                if point_of_sale:
                    raise exceptions.ValidationError(
                        _('Employee {} is already assigned to {} point of sale').format(
                            employee.name, point_of_sale.cash_register_number)
                    )

    # Main methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def check_modification_constraints(self):
        """Ensures that non-admin users cannot write nor delete spec cash registers"""
        if not self.env.user.has_group('base.group_system') and any(
                rec.spec_register and rec.spec_register != 'not_used' for rec in self):
            raise exceptions.UserError(_('You cannot modify or delete spec cash registers!'))

    @api.model
    def create_cash_register(self, spec):
        """
        Creates 'special' cash register object
        :param spec: str: Signifies type of special register
        :return: record: Created cash register
        """
        register_name = register_mapper.get(spec)
        values = {
            'cash_register_number': register_name,
            'spec_register': spec,
        }
        # Add special journal to no-receipt cash register
        if spec == 'no_receipt':
            ticket_journal = self.env.ref('nsoft.nsoft_ticket_journal')
            values.update({
                'journal_id': ticket_journal.id,
            })
        res = self.sudo().with_context(allow_write=True).create(values)
        return res

    @api.model
    def find_matching_analytics(self, employee):
        """Finds analytic account based on passed partner"""
        if not employee:
            return None
        register = self.search([('employee_ids', 'in', employee.id)])
        return register.analytic_account_id

    # CRUD ------------------------------------------------------------------------------------------------------------

    @api.multi
    def unlink(self):
        """Check modification constraints on unlink operations"""
        self.check_modification_constraints()
        self.mapped('partner_id').unlink()
        return super(NsoftCashRegister, self).unlink()

    @api.multi
    def write(self, vals):
        """Check modification constraints on write operations"""
        self.check_modification_constraints()
        return super(NsoftCashRegister, self).write(vals)

    # Utility methods -------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        """Custom name get"""
        return [(rec.id, '%s' % rec.cash_register_number) for rec in self]
