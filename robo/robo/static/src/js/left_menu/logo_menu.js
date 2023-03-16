robo.define('robo_theme_v10.logo_menu', function (require) {
"use strict";

    var core = require('web.core');
    var LogoAlarm = require('robo_theme_v10.logo_alarm');
    var Model = require('web.DataModel');
    var Session = require('web.session');
    var UserMenu = require('web.UserMenu');
    var Widget = require('web.Widget');
    var _t = core._t;


    // var chat_manager = require('mail.chat_manager');
    var QWeb = core.qweb;
    var bus = core.bus;
//ROBO: maybe refactor with bootstrap dropdown as logo_alarm.js?
var LogoMenu = UserMenu.extend({
    template: 'LogoMenu',
    events: {
        // 'click .robo-logo-alarm': 'bell_click',
        'click .robo-logo-menu-switch': 'menu_switch_click',
    },
    custom_events:{
      'child_element_clicked' : 'child_element_clicked',
    },

    init: function(){
      this._super.apply(this, arguments);
      this.session = Session;
      this.company_name = '';
      this.show_logo_menu_switch = false;
      this.show_company_settings = false;
    },

    willStart: function(){
      var self = this;
      return $.when(
                Session.is_accountant(),//user_has_group('robo_basic.group_robo_premium_accountant'),
                Session.is_manager(),//user_has_group('robo_basic.group_robo_premium_manager'),
                // Session.user_has_group('robo_basic.group_robo_free_manager'),
                this._super.apply(this, arguments),
                this.get_company_name()
                ).then(function(premium_accountant, manager /*premium_manager, free_manager*/){
                    if (premium_accountant){
                        self.show_logo_menu_switch = true;
                    }
                    if (manager /*premium_manager || free_manager*/){
                        self.show_company_settings = true;
                    }
                });
    },

    get_company_name: function(){
        var self = this;
        var def = $.Deferred();

        var res_company = new Model('res.company');
        res_company.query(['name'])
           .filter([['id', '=', self.session.company_id]])
           .all()
           .then(function (companies){
                self.company_name = companies[0].name;
                // self.company_image_url = self.session.url('/web/image', {model: 'res.company', id: self.session.company_id, field: 'logo',});
                def.resolve();
            });
        return def;
    },

    start: function(){
      var self = this;

      var logoAlarm = new LogoAlarm(this);
      var loadAlarmIcon = logoAlarm.prependTo(this.$el);

      this.showPopover();
      return $.when(this._super.apply(this, arguments), loadAlarmIcon).then(function () {
                  return self.do_update();
              });
    },
    child_element_clicked: function(){
         this.$el.popover('hide');
    },
    showPopover: function(){
        var self = this;
        var options = {
            'content': QWeb.render('LogoPopOver', {widget: this}),
            'html': true,
            'placement': 'right',
            'title': '<div class="title-text">' + _t('Jūs') + '</div>',
            'trigger': 'manual',
            // 'delay': { "show": 0, "hide": 100 },
            'template': '<div class="popover my-Popover"><div class="arrow"></div><div class="popover-title"></div><div class="popover-content"></div></div>',
            'container': self.$el,
        };

        var $toggleIcon = this.$('.robo-logo-toggle-icon');

        this.$el.popover(options).on('click', _.throttle(function(e){
            $(this).popover('toggle');
        }, 200, true));

        bus.on('click', this, function(e){
           var $target = $(e.target);
           //if click outside robo-client-initial, hide popover
           if ($target.closest('.robo-client-initial').length == 0){
               this.$el.popover('hide');
           }
        });

        // this.$el.on('blur', function(){
        //     $(this).popover('hide');
        // });

        this.$el.on('click','.logo-menu-item[data-menu]', function(e){
            e.stopPropagation();
            e.preventDefault();
            var f = self['on_menu_' + $(e.currentTarget).data('menu')];
                if (f) {
                    self.$el.popover('hide');
                    f($(e.currentTarget));
                }
        });

        this.$el.on('shown.bs.popover', function(){
            $toggleIcon.toggleClass('js-turn-icon', true);
        });
        this.$el.on('hidden.bs.popover', function(){
            $toggleIcon.toggleClass('js-turn-icon', false);
        });
    },

    do_update: function(){
        var self = this;
        return $.when(this._super.apply(this, arguments)).then(function(){
            if (!self.session.uid) {
                  $avatar.attr('src', $avatar.data('default-src'));
                  return $.when();
            }
            var $avatar = self.$el.find('.oe_topbar_avatar');
            var avatar_src = self.session.url('/web/image', {model:'res.users', field: 'image_medium', id: self.session.uid});
            $avatar.attr('src', avatar_src);
            self.$('.oe_topbar_company').text(self.company_name);
        });
    },

    // bell_click: function(e){
    //     e.stopPropagation();
    //     alert("bell");
    // },

    menu_switch_click: function(e){
        //todo: In the future make it direct change without bubbling
        e.stopPropagation();
        e.preventDefault();
        this.$el.closest('.o_web_client').find('a.drawer-toggle[accesskey="A"]').trigger('click');
    },

    on_menu_settings: function() {
        var self = this;
        this.trigger_up('clear_uncommitted_changes', {
            callback: function() {
                self.rpc("/web/action/load", { action_id: "robo.action_res_users_my_short" }).done(function(result) {
                    if (_.isObject(result)) {
                        result.res_id = self.session.uid;
                        self.do_action(result, {clear_breadcrumbs: true});
                    }
                });
            },
        });
    },
    on_menu_company_setup: function(){
        var self = this;
        self.rpc("/web/action/load", { action_id: "robo.action_robo_company_settings" }).done(function(result) {
                    if (_.isObject(result)) {
                        self.do_action(result, {clear_breadcrumbs: true});
                    }
        });
    },
    on_menu_mail: function(){
        var self = this;
        self.rpc("/web/action/load", { action_id: "robo.action_mail_channel_subscriptions_wizard_create" }).done(function(result) {
                    if (_.isObject(result)) {
                        self.do_action(result, {clear_breadcrumbs: true});
                    }
        });
    },

});

return LogoMenu;

});
