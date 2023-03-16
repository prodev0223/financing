# -*- coding: utf-8 -*-
from odoo import models, api, _, exceptions, fields, tools, http
import operator
from odoo.http import request
from odoo.addons.web.controllers.main import ensure_db
from datetime import datetime
from dateutil.relativedelta import relativedelta
import random
import odoo


class MailComposeMessage(models.TransientModel):

    _inherit = 'mail.compose.message'

    @api.multi
    def send_mail_action(self):
        raise exceptions.UserError(_('Demonstracinėje versijoje negalima siųsti el. sąskaitų.'))

MailComposeMessage()


class RoboCompanySettings(models.TransientModel):

    _inherit = 'robo.company.settings'

    @api.model
    def demo_install(self):
        self.env['res.partner'].search([]).write({
            'notify_email': 'none',
        })

    @api.model
    def deactivate_demo_accounts(self):
        date_expiration = (datetime.utcnow() - relativedelta(minutes=30)).strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        self.env['res.users'].search([('login', '=like', 'demo%'), ('login_date', '<=', date_expiration)]).write({
            'active': False
        })

    @api.model
    def default_get(self, field_list):
        return


RoboCompanySettings()


class RoboMenuEnterprice(models.Model):
    _inherit = 'ir.ui.menu'

    web_enterprice_icon = fields.Char(string='Web Enterprice Icon File')

    @api.model
    @tools.ormcache_context('self._uid', 'debug', keys=('lang',))
    def load_menus(self, debug):
        """ Loads all menu items (all applications and their sub-menus).

        :return: the menu root
        :rtype: dict('children': menu_nodes)
        """
        fields = ['name', 'sequence', 'parent_id', 'action', 'web_icon', 'web_icon_data', 'robo_extended', 'web_enterprice_icon', 'robo_main_menu']
        menu_roots = self.with_context(skip_root_search_menu=True).get_user_roots()
        menu_roots_data = menu_roots.read(fields) if menu_roots else []
        menu_root = {
            'id': False,
            'name': 'root',
            'parent_id': [-1, ''],
            'children': menu_roots_data,
            'all_menu_ids': menu_roots.ids,
        }
        if not menu_roots_data:
            return menu_root

        # menus are loaded fully unlike a regular tree view, cause there are a
        # limited number of items (752 when all 6.1 addons are installed)
        menus = self.search([('id', 'child_of', menu_roots.ids)])
        menu_items = menus.read(fields)

        # add roots at the end of the sequence, so that they will overwrite
        # equivalent menu items from full menu read when put into id:item
        # mapping, resulting in children being correctly set on the roots.
        menu_items.extend(menu_roots_data)
        menu_root['all_menu_ids'] = menus.ids  # includes menu_roots!

        # make a tree using parent_id
        menu_items_map = {menu_item["id"]: menu_item for menu_item in menu_items}
        for menu_item in menu_items:
            parent = menu_item['parent_id'] and menu_item['parent_id'][0]
            if parent in menu_items_map:
                menu_items_map[parent].setdefault(
                    'children', []).append(menu_item)

        # sort by sequence a tree using parent_id
        for menu_item in menu_items:
            menu_item.setdefault('children', []).sort(key=operator.itemgetter('sequence'))

        return menu_root


RoboMenuEnterprice()


def random_pass():
    letters = 'qwertyuiopasdfghjklzxcvbnm'
    digits = '1234567890'
    caps = 'QWERTYUIOPASDFGHJKLZXCVBNM'
    token = ''.join(random.SystemRandom().choice(letters) for i in xrange(20))
    token += ''.join(random.SystemRandom().choice(digits) for i in xrange(20))
    token += ''.join(random.SystemRandom().choice(caps) for i in xrange(20))

    return token


class MultiDatabaseAccess(http.Controller):

    @http.route('/token', type='http', auth="public")
    def AccessByToken(self, token=None, uid=None, **kw):
        ensure_db()
        if token and uid:
            users_obj = request.env['res.users']
            users_obj.env.uid = odoo.SUPERUSER_ID
            user_id = users_obj.search([('id', '=', uid)])
            password = random_pass()
            if user_id and user_id.partner_id.signup_token == token and user_id.partner_id.signup_valid:
                values = {
                    'db': request.session.db,
                    'token': token,
                    'name': user_id.name,
                    'email': user_id.email,
                    'login': user_id.login,
                    'password': password,
                }
                db, login, password = request.env['res.users'].sudo().signup(values, token)
                request.env.cr.commit()
                uid = request.session.authenticate(db, login, password)
                if not uid:
                    values['error'] = _("Authentication failed.")
                    return request.render('web.login', values)
                user = request.env.user
                self.save_session(
                    user.tz,
                    request.httprequest.session.sid)
        return http.redirect_with_hash('/web')

    def save_session(
            self,
            tz,
            sid,
            unsuccessful_message='',
    ):
        now = fields.datetime.now()
        session_obj = request.env['ir.sessions']
        cr = request.registry.cursor()

        # Get IP, check if it's behind a proxy
        ip = request.httprequest.headers.environ['REMOTE_ADDR']
        forwarded_for = ''
        if 'HTTP_X_FORWARDED_FOR' in request.httprequest.headers.environ and request.httprequest.headers.environ[
            'HTTP_X_FORWARDED_FOR']:
            forwarded_for = request.httprequest.headers.environ['HTTP_X_FORWARDED_FOR'].split(', ')
            if forwarded_for and forwarded_for[0]:
                ip = forwarded_for[0]

        # for GeoIP
        geo_ip_resolver = None
        ip_location = ''
        try:
            import GeoIP
            geo_ip_resolver = GeoIP.open(
                '/usr/share/GeoIP/GeoIP.dat',
                GeoIP.GEOIP_STANDARD)
        except ImportError:
            geo_ip_resolver = False
        if geo_ip_resolver:
            ip_location = (str(geo_ip_resolver.country_name_by_addr(ip)) or '')

        # autocommit: our single update request will be performed atomically.
        # (In this way, there is no opportunity to have two transactions
        # interleaving their cr.execute()..cr.commit() calls and have one
        # of them rolled back due to a concurrent access.)
        cr.autocommit(True)
        user = request.env.user
        logged_in = True
        uid = user.id
        if unsuccessful_message:
            uid = odoo.SUPERUSER_ID
            logged_in = False
            sessions = False
        else:
            sessions = session_obj.search([('session_id', '=', sid),
                                           ('ip', '=', ip),
                                           ('user_id', '=', uid),
                                           ('logged_in', '=', True)],
                                          )
        if not sessions:
            date_expiration = (now + relativedelta(seconds=user.session_default_seconds)).strftime(
                tools.DEFAULT_SERVER_DATETIME_FORMAT)
            values = {
                'user_id': uid,
                'logged_in': logged_in,
                'session_id': sid,
                'session_seconds': user.session_default_seconds,
                'multiple_sessions_block': user.multiple_sessions_block,
                'date_login': now.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT),
                'date_expiration': date_expiration,
                'ip': ip,
                'ip_location': ip_location,
                'remote_tz': tz or 'GMT',
                'unsuccessful_message': unsuccessful_message,
            }
            session_obj.sudo().create(values)
            cr.commit()
        cr.close()


MultiDatabaseAccess()


class ClientSupportTicketWizard(models.TransientModel):
    _inherit = 'client.support.ticket.wizard'

    @api.multi
    def create_ticket(self):
        raise exceptions.UserError(_('Demonstracinėje versijoje negalite kurti užklausų.'))


ClientSupportTicketWizard()


class ClientSupportTicket(models.Model):
    _inherit = 'client.support.ticket'

    @api.multi
    @api.returns('self', lambda value: value.id)
    def robo_message_post(self, **kwargs):
        return super(ClientSupportTicket, self.with_context(internal_ticketing=True)).robo_message_post(**kwargs)


ClientSupportTicket()
