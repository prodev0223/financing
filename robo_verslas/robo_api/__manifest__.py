# -*- coding: utf-8 -*-
{
    'name' : 'ROBO API',
    'version' : '1.0',
    'author' : 'Robolabs',
    'website': 'http://www.robolabs.lt',
    'license': 'Other proprietary',
    'depends': ['robo'],
    'data': [
        'data/ir_cron.xml',
        'data/ir_config_parameter.xml',
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'views/robo_api_job.xml',
        'views/robo_company_settings.xml',
        'views/product_category.xml',
    ],
    'qweb': [
    ],
    'demo': [],
    'installable': True,
}
