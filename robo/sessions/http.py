# -*- encoding: utf-8 -*-
import logging

import odoo
import werkzeug.contrib.sessions
import werkzeug.datastructures
import werkzeug.exceptions
import werkzeug.local
import werkzeug.routing
import werkzeug.wrappers
import werkzeug.wsgi
from odoo.http import request
from odoo.tools.func import lazy_property
import sys
from odoo import http, tools
if sys.version_info > (3,):
    import _pickle as cPickle
    unicode = str
else:
    import cPickle


_logger = logging.getLogger(__name__)
SESSION_TIMEOUT = 60 * 60 * 24 * 7  # 1 week in seconds, rolling session expiration


def is_redis_session_store_activated():
    return tools.config.get('enable_redis')


try:
    import redis
except ImportError:
    if is_redis_session_store_activated():
        raise ImportError(
            'Please install package python3-redis: '
            'apt install python3-redis')


class RedisSessionStore(werkzeug.contrib.sessions.SessionStore):

    def __init__(self, *args, **kwargs):
        super(RedisSessionStore, self).__init__(*args, **kwargs)
        self.expire = kwargs.get('expire', SESSION_TIMEOUT)
        self.key_prefix = kwargs.get('key_prefix', '')
        self.redis = redis.Redis(
            host=tools.config.get('redis_host', 'localhost'),
            port=int(tools.config.get('redis_port', 6379)),
            db=int(tools.config.get('redis_dbindex', 1)),
            password=tools.config.get('redis_pass', None))
        self._is_redis_server_running()

    def save(self, session):
        key = self._get_session_key(session.sid)
        data = cPickle.dumps(dict(session))
        self.redis.setex(name=key, value=data, time=self.expire)

    def delete(self, session):
        key = self._get_session_key(session.sid)
        self.redis.delete(key)

    def _get_session_key(self, sid):
        key = self.key_prefix + sid
        if isinstance(key, unicode):
            key = key.encode('utf-8')
        return key

    def get(self, sid):
        key = self._get_session_key(sid)
        data = self.redis.get(key)
        if data:
            self.redis.setex(name=key, value=data, time=self.expire)
            data = cPickle.loads(data)
        else:
            data = {}
        return self.session_class(data, sid, False)

    def _is_redis_server_running(self):
        try:
            self.redis.ping()
        except redis.ConnectionError:
            raise redis.ConnectionError('Redis server is not responding')


class OpenERPSession(odoo.http.OpenERPSession):
    def logout(self, keep_db=False, logout_type=None, env=None):
        try:
            env = env or request.env
        except:
            pass
        if env and hasattr(
                env,
                'registry') and env.registry.get('ir.sessions'):
            session = env['ir.sessions'].sudo().search(
                [('session_id', '=', self.sid),
                 ('logged_in', '=', True), ])
            if session:
                session._on_session_logout(logout_type)
        return super(OpenERPSession, self).logout(keep_db=keep_db)

# Patch methods of openerp.http to use Redis instead of filesystem

@lazy_property
def session_store(self):
    # Override to use Redis instead of filestystem
    if is_redis_session_store_activated():
        _logger.debug('HTTP sessions stored in Redis')
        return RedisSessionStore(session_class=OpenERPSession)
    else:
        path = odoo.tools.config.session_dir
        _logger.debug('HTTP sessions stored in: %s', path)
        return werkzeug.contrib.sessions.FilesystemSessionStore(
            path, session_class=OpenERPSession)

if is_redis_session_store_activated():

    def session_gc(session_store):
        # Override to ignore file unlink
        # because sessions are not stored in files
        pass

    http.session_gc = session_gc

http.Root.session_store = session_store
