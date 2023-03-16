# -*- coding: utf-8 -*-
{
    "name": """Gantt Native view for Leave HR - Holidays""",
    "summary": """Leave HR - Holidays - Gantt""",
    "category": "Project",
    "images": ['static/description/icon.png'],
    "version": "10.17.1.11.0",
    "description": """
   
    """,
    "author": "Viktor Vorobjov",
    "license": "OPL-1",
    "website": "https://straga.github.io",
    "support": "vostraga@gmail.com",

    "depends": [
        "hr_holidays",
        "web_gantt_native",
    ],
    "external_dependencies": {"python": [], "bin": []},
    "data": [
        'views/hr_holidays_view.xml',
    ],
    "qweb": [],
    "demo": [],

    "post_load": None,
    "pre_init_hook": None,
    "post_init_hook": None,
    "installable": True,
    "auto_install": False,
    "application": False,
}