# -*- coding: utf-8 -*-
from odoo import models, fields, _, api, exceptions
from datetime import datetime


def guess_partner_code_type(s):
    if not s or not isinstance(s, basestring):
        return ''
    if len(s) == 11 and s[0] in ['3', '4', '5', '6']:
        return 'mmak'
    if len(s) == 6 and s.isdigit():
        return 'ivvpn'
    if s and s[0] not in ['(', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'] and s.isalnum() and not s.isdigit():
        return 'vlm'
    return 'atpdsin'


class StockPicking(models.Model):

    _inherit = 'stock.picking'

    customer_name = fields.Char(string="Customer Name", compute='_customer_compute')
    customer_code = fields.Char(string='Customer Code', compute='_customer_compute')
    customer_street = fields.Char(string='Customer Street', compute='_customer_compute')
    customer_city = fields.Char(string='Customer City', compute='_customer_compute')
    customer_zip = fields.Char(string='Customer Zip', compute='_customer_compute')
    customer_country = fields.Char(string='Customer Country', compute='_customer_compute')
    customer_email = fields.Char(string='Customer Email', compute='_customer_compute')

    partner_id_carrier = fields.Many2one('res.partner', string='Carrier Company', states={'done': [('readonly', True)]},
                                         sequence=100,
                                         )
    transport_id = fields.Many2one('transport', string='Mašina', states={'done': [('readonly', True)]},
                                   lt_string='Mašina', sequence=100,
                                   )

    warehouse_address_id = fields.Many2one('res.partner', string='Source Location Address',
                                       compute='_warehouse_address_id_compute')
    warehouse_address_id_text = fields.Char(string='Source Location Address', compute='_warehouse_address_id_compute')
    dest_address_id = fields.Many2one('res.partner', string='Destination Location Address',
                                      compute='_dest_address_id')
    dest_address_id_text = fields.Char(string='Pristatymo adresas', compute='_dest_address_id')

    @api.one
    @api.depends('partner_id', 'location_dest_id')
    def _dest_address_id(self):
        if self.location_dest_id and self.location_dest_id.partner_id:
            self.dest_address_id = self.location_dest_id.partner_id.id
        elif self.location_dest_id and self.location_dest_id.warehouse_id and self.location_dest_id.warehouse_id.partner_id:
            self.dest_address_id = self.location_dest_id.warehouse_id.partner_id.id
        elif self.partner_id:
            self.dest_address_id = self.partner_id.id
        else:
            self.dest_address_id = self.company_id.partner_id.id if self.company_id.partner_id else False
        if self.dest_address_id:
            self.dest_address_id_text = self.dest_address_id.contact_address_line

    @api.one
    @api.depends('location_id')
    def _warehouse_address_id_compute(self):
        if self.location_id.usage != 'view':
            parent = self.location_id
            while parent and parent.usage != 'view':
                parent = parent.location_id
            if parent:
                warehouse = self.env['stock.warehouse'].search([('view_location_id', '=', parent.id)], limit=1)
                if warehouse and warehouse.partner_id:
                    self.warehouse_address_id = warehouse.partner_id.id
                    self.warehouse_address_id_text = self.warehouse_address_id.contact_address_line
                    return
        self.warehouse_address_id = self.company_id.partner_id.id if self.company_id.partner_id else False
        if self.warehouse_address_id:
            self.warehouse_address_id_text = self.warehouse_address_id.contact_address_line

    @api.one
    @api.depends('partner_id', 'location_dest_id')
    def _customer_compute(self):
        if self.partner_id and self.partner_id.parent_id:
            parent = self.partner_id.parent_id
            while parent.parent_id:
                parent = parent.parent_id
            self.customer_name = parent.name
            self.customer_code = parent.kodas
            self.customer_street = parent.street
            self.customer_city = parent.city
            self.customer_zip = parent.zip
            self.customer_country = parent.country_id.name
            self.customer_email = parent.email
        elif self.partner_id:
            self.customer_name = self.partner_id.name
            self.customer_code = self.partner_id.kodas
            self.customer_street = self.partner_id.street
            self.customer_city = self.partner_id.city
            self.customer_zip = self.partner_id.zip
            self.customer_country = self.partner_id.country_id.name
            self.customer_email = self.partner_id.email
        else:
            self.customer_name = self.location_dest_id.company_id.partner_id.name
            self.customer_code = self.location_dest_id.company_id.partner_id.kodas
            self.customer_street = self.location_dest_id.company_id.partner_id.street
            self.customer_city = self.location_dest_id.company_id.partner_id.city
            self.customer_zip = self.location_dest_id.company_id.partner_id.zip
            self.customer_country = self.location_dest_id.company_id.partner_id.country_id.name
            self.customer_email = self.location_dest_id.company_id.email

    @api.onchange('carrier_id')
    def onchange_carrier_id_set_delivery_agent(self):
        if self.carrier_id:
            self.partner_id_carrier = self.carrier_id.partner_id.id
        else:
            self.partner_id_carrier = False
        self.transport_id = False


StockPicking()


class Transport(models.Model):

    _name = 'transport'

    delivery_agent_id = fields.Many2one('res.partner', string='Pervežimo kompanija', required=True)
    model = fields.Char(string='Mašinos modelis', required=True, lt_string='Mašinos modelis')
    license_plate = fields.Char(string='Mašinos numeriai', required=True, lt_string='Mašinos numeriai')

    @api.multi
    def name_get(self):
        return [(rec.id, rec.model + ' ' + rec.license_plate) for rec in self]

    @api.multi
    @api.constrains('license_plate')
    def constraint_license_plate(self):
        for rec in self:
            if rec.license_plate and len(rec.license_plate) > 10:
                raise exceptions.ValidationError(_('Valstybinių numerių ilgis negali viršyti 10 simbolių.'))


Transport()


class ResPartner(models.Model):

    _inherit = 'res.partner'

    delivery_agent = fields.Boolean(string='Delivery agent', default=False)
    contact_address_line = fields.Char(string='Contact address line', compute='_contact_address_line')
    partner_code_type = fields.Selection([('mmak', 'mokesčių mokėtojo asmens kodas'),
                                          ('vlm', 'verslo liudijimo numeris'),
                                          ('PVMmk', 'PVM mokėtojo kodas'),
                                          ('ivvpn', 'individualios veiklos vykdymo pažymos numeris'),
                                          ('atpdsin', 'asmens tapatybę patvirtinančio dokumento serija ir numeris')],
                                         string='Kodo tipas')

    @api.onchange('kodas')
    def onch_guess_partner_code_type(self):
        if not self.is_company:
            guess_type = guess_partner_code_type(self.kodas)
            if guess_type:
                self.partner_code_type = guess_type

    @api.one
    @api.depends(lambda self: self._display_address_depends())
    def _contact_address_line(self):
        if self._context.get('skip_name', False):
            address_line = ''
        else:
            address_line = self.commercial_company_name or self.name or ''
        if self.street:
            if not self._context.get('skip_name', False):
                address_line += ", "
            address_line += self.street
        if self.street2:
            address_line += ", " + self.street2
        if self.city:
            address_line += ", " + self.city
        if self.zip:
            address_line += ", " + self.zip
        if self.country_id:
            address_line += ", " + self.country_id.name
        address_line = address_line.strip(', ')
        self.contact_address_line = address_line

    @api.model
    def create(self, vals):
        if vals.get('kodas') and not vals.get('is_company'):
            guess_type = guess_partner_code_type(vals['kodas'])
            if guess_type:
                vals['partner_code_type'] = guess_type
        return super(ResPartner, self).create(vals)


ResPartner()


class DeliveryCarrier(models.Model):  # todo remove somehow

    _inherit = 'delivery.carrier'

    partner_id = fields.Many2one('res.partner', string='Partner')


DeliveryCarrier()
