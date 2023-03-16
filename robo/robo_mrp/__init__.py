# -*- coding: utf-8 -*-
from . import models
from . import report
from . import wizard
from . import robo_mrp_tools


def uninstall_hook(cr, registry):
    cr.execute('''
ALTER TABLE robo_company_settings ALTER COLUMN production_lot_series DROP NOT NULL;
ALTER TABLE robo_company_settings ALTER COLUMN production_lot_number DROP NOT NULL;
ALTER TABLE robo_company_settings ALTER COLUMN production_lot_length DROP NOT NULL;
ALTER TABLE robo_company_settings ALTER COLUMN serial_num_series DROP NOT NULL;
ALTER TABLE robo_company_settings ALTER COLUMN serial_num_number DROP NOT NULL;
ALTER TABLE robo_company_settings ALTER COLUMN serial_num_length DROP NOT NULL;      
    ''')
