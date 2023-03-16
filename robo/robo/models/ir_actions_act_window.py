# -*- coding: utf-8 -*-


import logging

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)


class IrActionsActWindow(models.Model):
    _inherit = 'ir.actions.act_window'

    robo_front = fields.Boolean(string='Ar rodyti veiksmą vartotojui?', default=False)
    robo_menu = fields.Many2one('ir.ui.menu', string='Related robo menu', copy=False)
    header = fields.Many2one('robo.header', string='Robo header', copy=False)
    with_settings = fields.Boolean(string='Ieškoti veiksmo nustatymų')

    # # ROBO: naudojamas tik kliento-tiekejo atveju
    # swticher_name = fields.Char(_('Switch mygtuko pavadinimas'))

    # ROBO: kad prie meniu veiksmo nereikėtų nurodyti robo_menu link'o, t.y. jį rastų sistema pati.
    @api.model
    def _robo_default_menu_id(self, action_id):

        menu_start = self.env.ref('robo.menu_start')
        if not self.env.user.is_back_user():
            action_menu = self.env.ref('robo.menu_pagalbininkas')
        else:
            action_menu = self.env['ir.ui.menu']

        if action_id:
            menu_ids = self.env['ir.ui.menu'].search([
                ('robo_front', '=', True),
                ('action', '=', 'ir.actions.act_window,' + str(action_id))
            ])  # action = fields.Reference
            # find menu with parent menu_start
            for menu_id in menu_ids:
                parent_id = menu_id
                while parent_id:
                    if parent_id.parent_id and menu_start and parent_id.parent_id.id == menu_start.id:
                        action_menu = parent_id
                    parent_id = parent_id.parent_id

        return action_menu.id

    def _get_action_settings(self, r):
        values = {}

        # action menu map
        if isinstance(r.get('robo_menu'), tuple):
            robo_menu = r.get('robo_menu')[0]
        else:
            robo_menu = r.get('robo_menu')

        values['robo_menu_name'] = robo_menu or self._robo_default_menu_id(r.get('id'))

        # action settings + header
        if (r.get('with_settings') or r.get('header')) and r.get('id'):

            values['robo_header'] = {}

            fields_context_map = {
                'cards_template': 'robo_template',
                'cards_template_subtype': 'robo_subtype',
                'cards_domain': 'activeBoxDomain',
                'cards_limit': 'limitActive',
                'cards_force_order': 'force_order',
                'search_add_custom': 'search_add_custom',
                'cards_new_action': 'robo_create_new',
                'show_duplicate': 'showDuplicate',
                # 'header': 'robo_header',
            }

            fields_buttons_context_map = {
                'name': 'text',
                'icon': 'icon',
                'action': 'action',
                'item_class': 'class',
                'help': 'title',
            }

            settings = self.sudo().env['ir.actions.act_window.settings'].search([('action', '=', r.get('id'))], limit=1)
            if settings:
                for f in fields_context_map:
                    if isinstance(settings._fields[f], fields.Many2one):
                        values[fields_context_map[f]] = settings[f].id
                    # elif isinstance(settings._fields[f], fields.Many2many):
                    #     values[fields_context_map[f]] = settings[f].mapped(lambda x: (x.xml_id, x.id))
                    elif f in settings:
                        values[fields_context_map[f]] = settings[f]

            # button
            robo_header = {}
            header = r.get('header')
            if isinstance(r.get('header'), tuple):
                header = self.sudo().env['robo.header'].browse(header[0])
            else:
                header = self.sudo().env['robo.header'].browse(header)

            if header:
                if header.fit:
                    robo_header['fit'] = header.fit
                if header.robo_xs_header:
                    robo_header['robo_xs_header'] = header.robo_xs_header
                if header.robo_help_header:
                    robo_header.update(robo_help_header=True,
                                       help_data=self.env['res.company'].robo_help(self.env.user.company_id.id))
                show_buttons = any(group in header.group_ids.ids for
                                   group in self.env.user.groups_id.ids) if header.group_ids.ids else True
                if show_buttons:
                    if header.button_name:
                        robo_header['header_button'] = header.button_name
                    if header.button_class:
                        robo_header['header_button_class'] = header.button_class
                    if header.switch_views_buttons:
                        robo_header['show_switch_buttons'] = header.switch_views_buttons

                    # action switcher?
                    if header.action_switcher_ids and header.active_action_switcher:
                        robo_header['switcher'] = header.active_action_switcher
                        for switcher in header.action_switcher_ids:
                            robo_header[switcher['priority']] = {
                                'action_id': switcher['action_id'].id,
                                'menu_id': switcher['menu_id'].id,
                                'switcher_name': switcher['name'],
                            }

                    items = header.header_items_ids
                    robo_header['header_button_items'] = []
                    items = items.filtered(
                        lambda item: (set(item.group_ids.ids) & set(self.env.user.groups_id.ids)) or not item.group_ids)
                    for item in items:
                        button_values = {}
                        for f in fields_buttons_context_map:
                            if isinstance(item._fields[f], fields.Many2one):
                                button_values[fields_buttons_context_map[f]] = item[f].id
                            # elif isinstance(item._fields[f], fields.Many2many):
                            #     button_values[fields_buttons_context_map[f]] = item[f].ids
                            elif item[f]:
                                button_values[fields_buttons_context_map[f]] = item[f]

                        robo_header['header_button_items'].append(button_values)

            values['robo_header'] = robo_header

        return values

    # ROBO:  For front_users:
    #       1) remove views which do not have robo_front id
    #       2) remove view_id if it does not have robo_front id

    @api.multi
    def read(self, fields=None, load='_classic_read'):
        """ call the method get_empty_list_help of the model and set the window action help message
        """
        result = super(IrActionsActWindow, self).read(fields, load=load)

        if not self.env.user.is_back_user():
            for r in result:
                new_views = []
                # check if list of views is correct
                for view in r.get('views') or []:
                    if view[0] and isinstance(view[0], tuple([int, long])):
                        robo_front = self.env['ir.ui.view'].browse(view[0]).robo_front
                        if not robo_front:
                            res_model = r.get('res_model', self.sudo().browse(r['id']).res_model)
                            if self.env[res_model].is_transient():
                                robo_front = True
                        if robo_front:
                            new_views.append(view)
                        else:
                            _logger.info(
                                "{ROBO_VIEW_INFO}{Error} xml_id=%s is not robo_front." % self.env['ir.ui.view'].browse(
                                    view[0]).xml_id)

                # remove view id
                if isinstance(r.get('view_id'), tuple) and len(r['view_id']) == 2 \
                        and isinstance(r['view_id'][0], (int, long)) and not self.env['ir.ui.view'].browse(
                    r['view_id'][0]).robo_front:
                    res_model = r.get('res_model', self.sudo().browse(r['id']).res_model)
                    if not self.env[res_model].is_transient():
                        _logger.info(
                            "{ROBO_VIEW_INFO}{Error} xml_id=%s is not robo_front." % self.env['ir.ui.view'].browse(
                                r['view_id'][0]).xml_id)
                        r['view_id'] = (False, r['view_id'][1])
                r.update({'views': new_views})

        for r in result:
            if r.get('context'):
                try:
                    r['context'] = tools.safe_eval(r.get('context'), tools.UnquoteEvalContext(), nocopy=True)
                except:
                    continue
                else:
                    action_settings = self._get_action_settings(r)
                    r['context'].update(action_settings)
                    r['context'] = unicode(r.get('context'))

        return result
