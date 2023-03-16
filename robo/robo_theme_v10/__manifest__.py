# -*- coding: utf-8 -*-
# (c) 2021 Robolabs

{
    'name' : 'RoboLabs Theme v10',
    'version' : '1.0',
    'author' : 'Robolabs',
    'sequence': 5,
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'category' : 'Reporting',
    'description':
        """
         """,
	'images':[
        'images/screen.png'
	],
    "installable": True,
    'application': False,
    "depends": [
        'robo_basic',
    ],
    "data": [
        'views/assets.xml',
        'views/web.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],

}