# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'RoboLabs Server Restart',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Other',
    'description': """
Methods to execute after server restart
========================================
Executes methods/action after the server is restarted (this module reinstalled)
    """,
    'depends': ['e_document', 'robo_scripts'],
    'data': [
        'data/function_calls.xml',
    ],
    'installable': True,
    'auto_install': True,


}
