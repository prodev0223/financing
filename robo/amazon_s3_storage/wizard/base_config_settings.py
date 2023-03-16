from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)
import ast


def _getExpireValue(attr, value):
    dic = {
        'second': value,
        'minute': value * 60,
        'hour'  : value * 60 * 60,
        'day'   : value * 24 * 60 *60,
        'month' : value * 30 * 24 *60 *60,
        'year'  : value * 365 *30 * 24 *60 *60
    }
    return dic.get(attr)


class BaseConfigSettings(models.TransientModel):
    _inherit = 'base.config.settings'

    @api.multi
    def open_s3_conf(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Amazon S3 Configuration',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 's3.config',
            'target': 'current',
        }
