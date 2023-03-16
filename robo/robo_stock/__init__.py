# -*- encoding: utf-8 -*-
import model
import wizard


def uninstall_hook(cr, registry):
    cr.execute('''
ALTER TABLE periodic_invoice ALTER COLUMN picking_action DROP NOT NULL;   
    ''')

