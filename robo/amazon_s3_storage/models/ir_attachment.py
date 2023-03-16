# -*- encoding: utf-8 -*-
import base64
import hashlib
from odoo import api, models, fields, _, tools
from six import iteritems
from . import s3_tool
import re
import logging

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'
    _s3_bucket = False
    _s3_encryption_enabled = False

    @api.model
    def _storage(self):
        """ Return the attachment location for CDN """
        s3_enabled = tools.config.get('s3_storage_enabled')
        storage = False
        if s3_enabled:
            if self._context.get('cdn') and not self._context.get('skip_cdn'):
                storage = 's3://cdn'
            else:
                storage = 's3://data'
        return storage or super(IrAttachment, self)._storage()

    def _get_S3_bucket(self, storage):
        """ Get the S3 bucket from config parameters """
        access_key_id = tools.config.get('s3_storage_access_key_id')
        secret_key = tools.config.get('s3_storage_secret_key')
        s3_storage_url = tools.config.get('s3_storage_url')
        if storage == 's3://data':
            bucket_name = tools.config.get('s3_storage_data_bucket_name')
        elif storage == 's3://cdn':
            bucket_name = tools.config.get('s3_storage_cdn_bucket_name')
        else:
            bucket_name = None
        s3 = s3_tool.get_resource(access_key_id, secret_key, s3_storage_url)
        self._s3_bucket = s3.Bucket(bucket_name)

    @api.model
    def _file_read(self, fname, bin_size=False):
        storage = self._storage()
        if storage[:5] == 's3://':
            if not self._s3_bucket:
                self._get_S3_bucket(storage)
            try:
                s3path = self._get_s3_full_path(fname)
                s3_key = self._s3_bucket.Object(s3path)
                read = base64.b64encode(s3_key.get()['Body'].read())
                return read
            except Exception as e:
                _logger.info("ERROR 404: File %s not found on AWS S3...%r", fname, e)
        return super(IrAttachment, self)._file_read(fname, bin_size)

    @api.model
    def _get_s3_full_path(self, path):
        # sanitize path
        dbname = hashlib.md5(self._cr.dbname).hexdigest() if self._context.get('cdn') else self._cr.dbname
        s3path = re.sub('[.]', '', path)
        s3path = s3path.strip('/\\')
        return '/'.join([dbname, s3path])

    def _get_s3_key(self, sha):
        dbname = hashlib.md5(self._cr.dbname).hexdigest() if self._context.get('cdn') else self._cr.dbname
        fname = sha[:2] + '/' + sha
        return fname, '/'.join([dbname, fname])

    @api.model
    def _file_write(self, value, checksum, mimetype=None):
        storage = self._storage()
        if storage[:5] == 's3://':
            if not self._s3_bucket:
                self._get_S3_bucket(storage)
            bin_value = value.decode('base64')
            fname, s3path = self._get_s3_key(checksum)
            if self._s3_encryption_enabled:
                _logger.info("-------------Encryption----enable--")
                self._s3_bucket.Object(s3path).put(Body=bin_value, ServerSideEncryption='AES256')
            else:
                self._s3_bucket.Object(s3path).put(Body=bin_value, ContentType=mimetype or 'octet-stream')
                if self._context.get('cdn') and not self._context.get('skip_cdn'):
                    self._s3_bucket.Object(s3path).Acl().put(ACL='public-read')
        else:
            fname = super(IrAttachment, self)._file_write(value, checksum, mimetype)
        return fname

    def _mark_for_gc(self, fname):
        storage = self._storage()
        if storage[:5] == 's3://':
            try:
                if not self._s3_bucket:
                    self._get_S3_bucket(storage)
                new_key = self._get_s3_full_path('checklist/%s' % fname)
                s3_key = self._s3_bucket.Object(new_key)
                s3_key.put(Body='')
                _logger.debug('S3: _mark_for_gc key:%s marked for GC', new_key)
            except Exception as e:
                _logger.error('S3: File mark as GC, Storage %r,Exception %r', (storage, e))
        else:
            _logger.info('Using file store SUPER _mark_for_gc able to save key')
            return super(IrAttachment, self)._mark_for_gc(fname)

    @api.model
    def _file_gc(self):
        """ Perform the garbage collection of the filestore. """
        # TODO: Check how to pass context
        storage = self._storage()
        if storage[:5] == 's3://':
            return
            cr = self._cr
            cr.commit()
            cr.execute("LOCK ir_attachment IN SHARE MODE")
            checklist = {}
            whitelist = set()
            removed = 0
            try:
                if not self._s3_bucket:
                    self._get_S3_bucket(storage)

                for gc_key in self._s3_bucket.objects.filter(Prefix=self._get_s3_full_path('checklist')):
                    key = self._get_s3_full_path(gc_key.key[1 + len(self._get_s3_full_path('checklist/')):])
                    checklist[key] = gc_key.key

                for names in cr.split_for_in_conditions(checklist):
                    cr.execute("SELECT store_fname FROM ir_attachment WHERE store_fname IN %s", [names])
                    whitelist.update(row[0] for row in cr.fetchall())

                for key, value in iteritems(checklist):
                    if key not in whitelist:
                        s3_key = self._s3_bucket.Object(key)
                        s3_key.delete()
                        s3_key_gc = self._s3_bucket.Object(value)
                        s3_key_gc.delete()
                        removed += 1
                        _logger.info('S3: _file_gc_s3 deleted key:%s successfully', key)
            except Exception as e:
                _logger.error('S3: _file_gc_ method deleted key:EXCEPTION %r', tools.ustr(e))
            cr.commit()
            _logger.debug("S3: filestore gc %d checked, %d removed", len(checklist), removed)
        else:
            return super(IrAttachment, self)._file_gc()
