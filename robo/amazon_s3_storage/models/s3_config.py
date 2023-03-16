# -*- encoding: utf-8 -*-
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class S3Config(models.Model):
    _name = 's3.config'
    _description = "Model For Storing S3 Config Values"

    name = fields.Char(string='Name', help="Amazon S3 Cloud Config name", readonly=True)
    amazonS3bucket_name = fields.Char(string='Bucket Name', help="This allows users to store data in Bucket",
                                      inverse='_set_location_parameter')
    amazonS3secretkey = fields.Char(string='Secret key', help="Amazon S3 Cloud Connection",
                                    inverse='_set_location_parameter')
    amazonS3accessKeyId = fields.Char(string='Access Key Id', help="Amazon S3 Cloud Connection access key Id",
                                      inverse='_set_location_parameter')
    bucket_location = fields.Char(string='Bucket Location', help="Amazon S3 Bucket Location",
                                  inverse='_set_location_parameter')
    is_store = fields.Boolean(string='Is Active', default=False, inverse='_set_location_parameter')
    is_cdn = fields.Boolean(string='Is a CDN bucket', help="Used to store the public web assets",
                            inverse='_set_location_parameter')

    def _set_location_parameter(self):
        parameter = ""
        if self.is_store:
            parameter = "s3://%s:%s@%s&s3.%s.amazonaws.com" % (self.amazonS3accessKeyId,
                                                               self.amazonS3secretkey,
                                                               self.amazonS3bucket_name,
                                                               self.bucket_location)
        param_name = 'ir_attachment.location_s3_cdn' if self.is_cdn else 'ir_attachment.location_s3'
        result = self.env['ir.config_parameter'].sudo().set_param(param_name, parameter, ['base.group_system'])

        return result

