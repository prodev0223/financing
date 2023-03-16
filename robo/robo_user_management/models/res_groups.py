# -*- coding: utf-8 -*-

from lxml import etree
from lxml.builder import E

from odoo import api, models, _

rum_group_fields_start_with = 'rum_group_'
rum_group_fields_end_with = '_rights'


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def get_group_from_rum_field(self, field_name):
        if not self.is_rum_field(field_name):
            return False
        group_id = field_name.split(rum_group_fields_start_with)[1].split(rum_group_fields_end_with)[0]
        if group_id:
            try:
                return self.browse(int(group_id))
            except ValueError:
                pass
        return False

    @api.model
    def is_rum_field(self, field_name):
        return field_name.startswith(rum_group_fields_start_with)

    @api.multi
    def get_rum_field_name(self):
        self.ensure_one()
        return rum_group_fields_start_with + str(self.id) + rum_group_fields_end_with

    @api.multi
    def get_rum_help_field_name(self):
        self.ensure_one()
        return self.get_rum_field_name() + '_help'

    @api.multi
    def get_rum_invisible_field_name(self):
        self.ensure_one()
        return self.get_rum_field_name() + '_is_invisible'

    @api.multi
    def get_rum_readonly_field_name(self):
        self.ensure_one()
        return self.get_rum_field_name() + '_is_readonly'

    @api.multi
    def is_disabled_in_rum(self):
        self.ensure_one()

        def get_group_ids(group_ext_ids):
            group_list = []
            for group_ext_id in group_ext_ids:
                group = self.env.ref(group_ext_id, raise_if_not_found=False)
                if group:
                    group_list.append(group.id)
            return group_list

        # Robo stock extended checks
        robo_stock_is_installed = self.sudo().env['ir.module.module'].search_count([
            ('name', '=', 'robo_stock'),
            ('state', '=', 'installed')
        ])
        robo_mrp_is_installed = self.sudo().env['ir.module.module'].search_count([
            ('name', '=', 'robo_mrp'),
            ('state', '=', 'installed')
        ])
        groups_not_to_show = []
        if robo_stock_is_installed:
            if self.env.user.company_id.sudo().politika_sandelio_apskaita == 'simple':
                groups_not_to_show.extend([
                    'robo_stock.group_front_warehouse_manager',
                    'robo_stock.group_robo_front_pricelist',
                    'robo_stock.group_show_avg_cost',
                    'robo_stock.group_robo_landed_costs',
                    'robo_stock.group_robo_serial_numbers',
                    'robo_stock.group_purchase_user_all',
                    'purchase.group_purchase_user',
                    'purchase.group_purchase_manager',
                    'sales_team.group_sale_manager',
                    'sales_team.group_sale_salesman',
                    'sales_team.group_sale_salesman_all_leads',
                    'product.group_product_variant',
                    'robo_stock.robo_stock_pdf_pickings'
                ])
        else:
            groups_not_to_show += [
                'stock_extend.group_robo_stock'
            ]
        if robo_mrp_is_installed:
            if self.env.user.company_id.sudo().politika_gamybos_apskaita == 'off':
                groups_not_to_show.extend([
                    'mrp.group_mrp_user',
                    'mrp.group_mrp_manager',
                    'robo_mrp.group_robo_mrp_bom_readonly',
                    'robo_mrp.group_robo_mrp_bom_manager',
                ])
        return self.id in get_group_ids(groups_not_to_show)

    @api.model
    def _update_user_groups_view(self):
        """ Modify the view with xmlid ``robo_user_management.dynamic_front_end_groups_view``, which inherits
            the res_users_front_end_form_view form view, and introduces the reified group fields.
        """
        # This method extends the existing/default method that populates the user back end view with group checkboxes
        super(ResGroups, self)._update_user_groups_view()

        if self._context.get('install_mode'):
            # use installation/admin language for translatable names in the view
            user_context = self.env['res.users'].context_get()
            self = self.with_context(**user_context)

        invisible_attr = {'invisible': str(True)}
        computed_fields_domain_string = '{"invisible": [("%s", "=", True)], "readonly": [("%s", "=", True)]}'
        computed_invisible_domain_string = '{"invisible": [("%s", "=", True)]}'

        # We have to try-catch this, because at first init the view does not
        # exist but we are already creating some basic groups.
        view = self.env.ref('robo_user_management.dynamic_front_end_groups_view', raise_if_not_found=False)
        if view and view.exists() and view._name == 'ir.ui.view':

            groups = self.env['res.groups'].search([('robo_front', '=', True)])

            category_other = self.env.ref('robo_basic.front_res_groups_category_other')
            group_categories = groups.mapped('front_category_id').sorted(key=lambda c: c.name)
            group_category_ids = group_categories.mapped('id')

            # Moves 'Kita'/'Other' category to the end of the list so it appears at the bottom of the XML
            if category_other.id in group_category_ids:
                group_category_ids.append(group_category_ids.pop(group_category_ids.index(category_other.id)))

            # Re-browse the categories
            group_categories = self.env['front.res.groups.category'].browse(group_category_ids)

            # Start by creating an external group
            group_xmls = E.group(name="dynamic_user_rights_container", colspan="4", col="4")

            # Add the invisible compute/readonly fields at the top
            for category in group_categories:
                group_xmls.append(E.field(name=category.get_invisible_field_name(), **invisible_attr))
                group_xmls.append(E.field(name=category.get_readonly_field_name(), **invisible_attr))
            for group in groups:
                group_xmls.append(E.field(name=group.get_rum_invisible_field_name(), **invisible_attr))
                group_xmls.append(E.field(name=group.get_rum_readonly_field_name(), **invisible_attr))

            # Get only the groups with implied ids (for creating the help text later)
            groups_with_implied_ids = groups.filtered(lambda g: g.implied_ids)

            for category in group_categories:
                category_groups = groups.filtered(lambda g: g.front_category_id == category)

                # Add the ones without a category to category other
                if category == category_other:
                    category_groups |= groups.filtered(lambda g: not g.front_category_id.id)

                group_category_xml = []
                for category_group in category_groups:
                    group_field_xml = []
                    field_name = category_group.get_rum_field_name()  # Gets the shortened field name (based on ID)
                    help_field_name = category_group.get_rum_help_field_name()

                    # Set up the invisible/readonly attributes
                    attrs = {
                        'attrs': computed_fields_domain_string % (category_group.get_rum_invisible_field_name(),
                                                                  category_group.get_rum_readonly_field_name()),
                        'colspan': '2',
                    }

                    help_attrs = {
                        'attrs': computed_invisible_domain_string % category_group.get_rum_invisible_field_name(),
                        'nolabel': '1',
                        'class': 'robo-groups-help-icon',

                    }

                    inner_group_attrs = {
                        'attrs': computed_invisible_domain_string % category_group.get_rum_invisible_field_name(),
                        'col': '4',
                        'class': 'robo-groups-group-container'
                    }

                    # Set up the help attribute
                    groups_that_imply_group = groups_with_implied_ids.filtered(lambda g: category_group.id in g.mapped('implied_ids.id'))
                    if groups_that_imply_group:
                        help_text = _('Ši grupė įgaunama automatiškai turint bent vienas iš šių teisių:\n')
                        help_text += ';\n'.join(groups_that_imply_group.mapped('name'))
                        attrs['help'] = help_text

                    # The attr that specifies which groups can see the field
                    shown_only_to_super = category_group.robo_front_only_shown_to_super
                    if shown_only_to_super:
                        inner_group_attrs['groups'] = 'robo_basic.group_robo_premium_accountant'

                    # Create a new field for each group (in the XML)
                    group_field_xml.append(E.field(name=field_name, **attrs))
                    # Create a help tooltip for each group (in the XML)
                    group_field_xml.append(E.field(name=help_field_name, **help_attrs))
                    group_category_xml.append(E.group(*group_field_xml, **inner_group_attrs))

                # Add the group (with its fields) to the XML
                group_attrs = {
                    'attrs': computed_fields_domain_string % (category.get_invisible_field_name(),
                                                              category.get_readonly_field_name()),
                    'colspan': '4',
                    'col': '2',
                    'string': category.name
                }
                group_xmls.append(E.group(*group_category_xml, **group_attrs))

            # Form the actual XML, add the xml decorator at the top, etc.
            xml_content = '''<?xml version='1.0' encoding='utf-8'?>\n'''
            xml_content += '''<xpath expr="//group[@name='dynamic_user_rights_container']" position="replace">\n'''
            xml_content += etree.tostring(group_xmls, pretty_print=True)  # Get the content as plaintext
            xml_content += '</xpath>'

            # Write to View
            view.sudo().with_context(lang=None).write({'arch': xml_content, 'arch_fs': False})


ResGroups()
