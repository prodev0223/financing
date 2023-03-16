# Copyright 2020 VentorTech OU, RoboLabs
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

{
    'name': 'Ventor Two Factor Authentication',
    'summary': '''
        2FA implemented via Google Authenticator. Logging into the system requires
         additional key generated on your mobile device.
        ''',
    'author': 'VentorTech,RoboLabs',
    'website': 'https://ventor.tech',
    'category': 'Uncategorized',
    'license': 'LGPL-3',
    'images': [
        'static/description/Two_factor_authentification.png',
    ],
    'installable': True,
    'depends': ['auth_brute_force', 'sessions', 'passwords'],
    'data': [
        'security/two_factor_otp_auth.xml',
        'data/ir_actions_server_data.xml',
        'views/res_users_view.xml',
        'wizard/transitional_2fa_wizard.xml',
        'templates/assets.xml',
        'templates/verify_code_template.xml',
        'templates/scan_code_template.xml',
    ],
    'external_dependencies': {
        'python': [
            'qrcode',
            'pyotp',
        ],
    },
}
