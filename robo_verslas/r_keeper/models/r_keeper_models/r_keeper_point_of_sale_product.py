# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, tools, _

TRIGGER_FIELDS = [
    'price_unit', 'vat_rate', 'product_state', 'product_state', 'is_weighed',
    'point_of_sale_id', 'product_id', 'category_id', 'uom_id', 'related_product_id', 'related_product_uom_id'
]
M2O_TRIGGER_FIELDS = [
    'point_of_sale_id', 'product_id', 'category_id', 'uom_id', 'related_product_id', 'related_product_uom_id'
]


class RKeeperPointOfSaleProduct(models.Model):
    _name = 'r.keeper.point.of.sale.product'
    _description = '''
    Model that stores rKeeper point of sale product
    lines, each line acts as a product variant for
    corresponding point of sale.
    '''

    # Fields that are used in CSV
    # export, rKeeper data fields
    point_of_sale_id = fields.Many2one('r.keeper.point.of.sale', string='Pardavimo taškas')
    product_id = fields.Many2one(
        'product.template', string='Produktas',
        domain="[('categ_id.r_keeper_category', '=', True)]"
    )
    category_id = fields.Many2one('product.category', string='Produkto kategorija')
    uom_id = fields.Many2one('product.uom', string='Matavimo vienetas')
    price_unit = fields.Float(string='Kaina')
    price_unit_exportable = fields.Integer(compute='_compute_price_unit_exportable')
    vat_rate = fields.Selection(
        [('0', '0 %'),
         ('9', '9 %'),
         ('21', '21 %')
         ], string='PVM Procentas', required=1,
    )
    product_state = fields.Selection(
        [('active', 'Aktyvus'),
         ('inactive', 'Neaktyvus'),
         ('deleted', 'Ištrintas')
         ], string='Produkto statusas', default='active', required=1,
    )
    is_weighed = fields.Boolean(string='Sveriama prekė')
    related_product_id = fields.Many2one('product.template', string='Susijusi prekė')
    related_product_uom_id = fields.Many2one('product.uom', string='Susijusios prekės matavimo vienetas')

    # Export status and revision identifiers
    r_keeper_export_revision_ids = fields.One2many(
        'r.keeper.data.export.revision',
        'point_of_sale_product_id', copy=False,
        string='Duomenų eksporto versijos'
    )

    # Revision number
    r_keeper_revision_number = fields.Integer(string='Įrašo versija', copy=False)
    r_keeper_revision_number_display = fields.Char(
        compute='_compute_r_keeper_revision_number_display',
        string='Įrašo versija'
    )

    # Revision text and state
    r_keeper_revision_text = fields.Char(
        string='Įrašo statusas rKeeper serveryje',
        compute='_compute_export_revision_data',
        store=True
    )
    r_keeper_export_state = fields.Selection(
        [('waiting', 'Eksportuota, laukiama atsakymo'),
         ('rejected', 'Paskutinis įrašo eksportas atmestas'),
         ('out_dated', 'Reikia atnaujinti įrašą'),
         ('up_to_date', 'Įrašo versija naujausia'),
         ('not_tried', 'Neeksportuota')
         ], string='rKeeper eksportavimo būsena',
        compute='_compute_export_revision_data',
        store=True
    )
    r_keeper_update = fields.Boolean(
        string='Reikia atnaujinti',
        compute='_compute_export_revision_data',
        store=True
    )

    # Computes / Inverses ---------------------------------------------------------------------------------------------

    @api.multi
    @api.depends('price_unit')
    def _compute_price_unit_exportable(self):
        """
        Compute //
        Calculates exportable price unit
        in rKeeper accepted format,
        without decimal separator
        :return: None
        """
        for rec in self:
            rec.price_unit_exportable = tools.float_round(rec.price_unit * 100, precision_digits=0)

    @api.multi
    @api.depends('r_keeper_revision_number')
    def _compute_r_keeper_revision_number_display(self):
        """
        Compute //
        Compose revision number display
        :return: None
        """
        for rec in self:
            rec.r_keeper_revision_number_display = '#{0}'.format(rec.r_keeper_revision_number)

    @api.multi
    @api.depends(
        'r_keeper_export_revision_ids',
        'r_keeper_export_revision_ids.data_export_id.state',
        'r_keeper_revision_number',
        'product_id.r_keeper_product'
    )
    def _compute_export_revision_data(self):
        """
        Computes export revision data:
        1. Checks whether current product line should
        be updated -- If it belongs to rKeeper category
        and it was never exported OR if last export
        revision number is smaller than current revision
        number.
        2. Computes the state for the current record --
        state of last export.
        3. Computes the revision display text for the
        current record.
        :return: None
        """
        for rec in self:
            revision = rec.r_keeper_revision_number

            # Base values
            r_keeper_update = False
            r_keeper_revision_text = _('Įrašas nebandytas importuoti')
            r_keeper_export_state = 'not_tried'

            revisions = rec.r_keeper_export_revision_ids
            if revisions:
                last_revision = revisions.sorted(lambda x: x.id, reverse=True)[0]

                # Get latest export and it's revision number
                last_export = last_revision.data_export_id
                last_revision_number = last_revision.revision_number
                if last_revision_number < revision:
                    r_keeper_update = True

                # Check last export state
                if last_export.state == 'accepted':
                    # If last export state is accepted, check whether it's revision differs from current record
                    if last_revision_number < revision:
                        # If it does, mark current record as outdated
                        r_keeper_revision_text = \
                            _('Įrašo versija rKeeper serveryje yra senesnė: #{0} < #{1}').format(
                                last_revision_number, revision)
                        r_keeper_export_state = 'out_dated'

                    else:
                        # Otherwise rKeeper server data matches current data
                        r_keeper_revision_text = \
                            _('Įrašo versija rKeeper serveryje yra naujausia: #{0}').format(last_revision_number)
                        r_keeper_export_state = 'up_to_date'
                else:
                    # Filter out only accepted revisions
                    accepted_revisions = revisions.filtered(lambda x: x.data_export_id.state == 'accepted')
                    last_accepted_revision = last_a_revision_number = None
                    if accepted_revisions:
                        last_accepted_revision = accepted_revisions.sorted(lambda x: x.id, reverse=True)[0]
                        last_a_revision_number = last_accepted_revision.revision_number

                    # If state is waiting, update the export state
                    if last_export.state in ['waiting', 'no_action']:
                        r_keeper_export_state = 'waiting'
                        r_keeper_revision_text = _('Laukiama atsakymo iš rKeeper serverio #{0} įrašui.').format(
                            last_revision_number)
                        # If we have last successful export, keep the last revision number in the text
                        if last_accepted_revision:
                            r_keeper_revision_text = _(
                                '{0} Paskutinė sėkmingai įkelta versija #{1}').format(
                                r_keeper_revision_text, last_a_revision_number)
                    # Lastly, the export state is rejected
                    else:
                        r_keeper_export_state = 'rejected'
                        r_keeper_revision_text = _('Paskutinis įkėlimas #{0} įrašui buvo atmestas').format(
                            last_revision_number)
                        # If we have last successful export, keep the last revision number in the text
                        if last_accepted_revision:
                            r_keeper_revision_text = _(
                                '{0} Paskutinė sėkmingai įkelta versija #{1}').format(
                                r_keeper_revision_text, last_accepted_revision.revision_number)
                        # If state is rejected, it needs to be updated again
                        r_keeper_update = True
            else:
                r_keeper_update = rec.product_id.categ_id.r_keeper_category

            rec.r_keeper_update = r_keeper_update
            rec.r_keeper_revision_text = r_keeper_revision_text
            rec.r_keeper_export_state = r_keeper_export_state

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        Onchange //
        On product change, change default UOM
        and product category
        :return: None
        """
        self.category_id = self.product_id.categ_id
        self.uom_id = self.product_id.uom_id

    # CRUD Methods ----------------------------------------------------------------------------------------------------

    @api.multi
    def write(self, vals):
        for rec in self:
            # Prevent modification of records in waiting state
            if rec.r_keeper_export_state == 'waiting':
                raise exceptions.ValidationError(
                    _('Negalima keisti produkto informacijos iki kol negautas atsakymas '
                      'paskutiniam eksportui į rKeeper serverį. Palaukite keletą minučių')
                )
            # If line was exported to rKeeper once, do not let
            # user to change the related product
            if rec.r_keeper_export_state != 'not_tried':
                if 'product_id' in vals:
                    raise exceptions.ValidationError(
                        _('Negalima keisti produkto jei produktas bent kartą buvo importuotas į rKeeper serverį. '
                          'Jeigu pageidaujate keisti produktą, deaktyvuokite esamą eilutę ir sukurkite naują')
                    )
                # Collect the fields that have unchanged values
                fields_to_pop = []
                for field, value in vals.items():
                    if field in TRIGGER_FIELDS:
                        current_value = getattr(rec, field)
                        if field in M2O_TRIGGER_FIELDS:
                            current_value = current_value.id
                        if current_value == value:
                            fields_to_pop.append(field)
                # Pop the fields
                for field in fields_to_pop:
                    vals.pop(field)

                # If any of the trigger fields is written to the line increase revision number as well
                if any(x in vals for x in TRIGGER_FIELDS):
                    vals['r_keeper_revision_number'] = rec.r_keeper_revision_number + 1
        return super(RKeeperPointOfSaleProduct, self).write(vals)

    @api.multi
    def unlink(self):
        for rec in self:
            # Prevent deletion of records in waiting state
            if rec.r_keeper_export_state == 'waiting':
                raise exceptions.ValidationError(
                    _('Negalima keisti produkto informacijos iki kol negautas atsakymas '
                      'paskutiniam eksportui į rKeeper serverį. Palaukite keletą minučių')
                )
            # Deny product unlinking that have exported revisions, unless
            # product state is deleted and rKeeper server is up to date
            if rec.r_keeper_export_revision_ids and (
                    rec.r_keeper_export_state != 'up_to_date' or rec.product_state != 'deleted'):
                raise exceptions.ValidationError(
                    _('Negalite ištrinti eilutės kuri buvo eksportuota į rKeeper serverį. '
                      'Deaktyvuokite produktą ir atnaujinkite informaciją rKeeper serveryje')
                )
        return super(RKeeperPointOfSaleProduct, self).unlink()

    # Utility methods -------------------------------------------------------------------------------------------------

    @api.multi
    def name_get(self):
        return [(rec.id, rec.product_id.display_name) for rec in self]
