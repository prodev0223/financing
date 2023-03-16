# -*- encoding: utf-8 -*-
{
    # Theme information
    'name' : 'Robo Theme',
    'category' : 'Theme/Backend',
    'version' : '1.0',
    'summary': 'RoboLabs Theme',
    'description': """
Base on Material Backend Theme v9.
    """,

    # Dependencies
    'depends': [
        'web'
    ],
    'external_dependencies': {},

    # Views
    'data': [
	    'views/backend.xml'
    ],
    'qweb': [
        'static/src/xml/web.xml',
    ],

    # Author
    'author': 'RoboLabs',
    'website': 'http://www.robolabs.lt',

    # Technical
    'installable': False,
    'auto_install': False,
    'application': False,
}
