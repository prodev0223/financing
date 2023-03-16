# -*- coding: utf-8 -*-

{
    'name': "Odoo debranding Kit",
    'version': '1.0',
    'author': 'ITROOTS ODOO',
    'category': 'Debranding',
    'price': 40.00,
    'currency': 'EUR',
    'depends': [
        'web',
        'mail',
        'robo_depend',
        # 'web_planner',
        # 'access_apps',
        # 'access_settings_menu',
    ],
    'data': [
        'views/data.xml',
        'views/views.xml',
        'views/js.xml',
        'pre_install.yml',
        ],
    'qweb': [
        'static/src/xml/web.xml',
    ],
    'images': ['static/description/main.jpg'],
    'auto_install': False,
    'uninstall_hook': 'uninstall_hook',
    'installable': True
}
