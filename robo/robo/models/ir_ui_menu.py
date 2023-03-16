# -*- encoding: utf-8 -*-
import operator

from odoo import api, models, tools, _


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def get_robo_menu_id(self, menu_name):
        try:
            return self.env.ref(menu_name).id
        except ValueError:
            menu_name = menu_name.split('.')[-1]
            menu = self.env['ir.ui.menu'].search([('name', '=', menu_name)], limit=1)
            if not menu:
                return False
            return menu.id

    @api.model
    @tools.ormcache_context('self._uid', 'debug', keys=('lang',))
    def load_menus_withTags(self, debug):
        """ Loads all menu items (all applications and their sub-menus).

        :return: the menu root
        :rtype: dict('children': menu_nodes)
        """
        fields = ['name', 'sequence', 'parent_id', 'action', 'web_icon', 'web_icon_data', 'tags', 'searchable',
                  'robo_extended']
        menu_roots = self.get_user_roots()
        menu_roots_data = menu_roots.read(fields) if menu_roots else []
        menu_root = {
            'id': False,
            'name': 'root',
            'parent_id': [-1, ''],
            'children': menu_roots_data,
            'all_menu_ids': menu_roots.ids,
        }
        if not menu_roots_data:
            return menu_root

        # menus are loaded fully unlike a regular tree view, cause there are a
        # limited number of items (752 when all 6.1 addons are installed)
        menus = self.search([('id', 'child_of', menu_roots.ids)])
        menu_items = menus.read(fields)

        # add roots at the end of the sequence, so that they will overwrite
        # equivalent menu items from full menu read when put into id:item
        # mapping, resulting in children being correctly set on the roots.
        menu_items.extend(menu_roots_data)
        menu_root['all_menu_ids'] = menus.ids  # includes menu_roots!

        # make a tree using parent_id
        menu_items_map = {menu_item["id"]: menu_item for menu_item in menu_items}
        start_menu = self.env.ref('robo.menu_start').id
        for menu_item in menu_items:
            parent = menu_item['parent_id'] and menu_item['parent_id'][0]
            parent_is_start_menu = parent == start_menu
            if parent in menu_items_map:
                menu_items_map[parent].setdefault(
                    'children', []).append(menu_item)

            if menu_item.get('searchable'):
                # Get related action to check if it is an eDocument menu
                action = menu_item.get('action') or ''
                action_values = action.split(',') if action else False
                # Menus with a related action only
                if action_values:
                    ActionModel = self.env[action_values[0]]
                    action_record = ActionModel.browse(int(action_values[1])).exists()
                    menu_item_model = action_record.res_model if action_record and 'res_model' in ActionModel._fields \
                        else False
                    edoc_menu = True if menu_item_model and menu_item_model == 'e.document' else False
                    if not parent_is_start_menu:
                        # Append parent menu name to menu name
                        if edoc_menu:
                            menu_item['name'] = _('eDokumentai/{}').format(menu_item['name'])
                        elif parent:
                            parent_menu = self.browse(parent).exists()
                            root_name = parent_menu.name + '/' if parent_menu else ''
                            menu_item['name'] = '{}{}'.format(root_name, menu_item['name'])

        # sort by sequence a tree using parent_id
        for menu_item in menu_items:
            menu_item.setdefault('children', []).sort(key=operator.itemgetter('sequence'))

        return menu_root

    @api.model
    @api.returns('self')
    def get_user_roots(self):
        """ Return all root menu ids visible for the user.
        Fully overridden from base.ir module
        :return: the root menu ids
        :rtype: list(int)
        """
        domain = [('parent_id', '=', False)]
        if self._context.get('skip_root_search_menu'):
            root_search_menu = self.env.ref('robo.menu_search_root')
            if root_search_menu:
                domain += [('id', '!=', root_search_menu.id)]
        return self.search(domain)
