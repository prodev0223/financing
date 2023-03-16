# -*- coding: utf-8 -*-
#################################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
#################################################################################
{
    'name': 'Amazon S3 cloud Storage',
    'summary': 'Store your Odoo attachment to Amazon S3 cloud Storage',
    'description': """Store your Odoo attachment to Amazon S3 cloud Storage""",
    "category"		: "Website",
    "version" 		: "1.1.0",
    "author" 		: "Webkul Software Pvt. Ltd. -- Updated by Robolabs",
    "maintainer"	: "Saurabh Gupta",
    "website" 		: "https://store.webkul.com/Odoo.html",
    "license":  "Other proprietary",
    'depends': [
        'base_setup',
    ],
    'data': [
        "data/default_data.xml",
        "wizard/base_config_settings_views.xml",
        "views/s3_config_views.xml",
    ],
    "images" 		: ['static/description/banner.png'],
    "application":  True,
    "installable":  True,
    "currency":  "EUR",
    "price": 149,
    "external_dependencies":  {'python': ['boto3',"botocore"]}
}
