robo.define('robo.web_client', function (require) {
    "use strict";

    var config = require('web.config');
    var core = require('web.core');
    var Model = require('web.DataModel');
    var session = require('web.session');
    var WebClient = require('web.WebClient');

    WebClient.include({
        get_scrollTop: function () {
            if (config.device.size_class <= config.device.SIZES.XS) {
                return this.el.scrollTop;
            } else {
                return this.action_manager.el.scrollTop;
            }
        },
        bind_events: function(){
          var self = this;
          this._super.apply(this, arguments);

          core.bus.on('roboHeaderScollBar',null, function(roboScroll){
            if (roboScroll){
                self.$el.find('.o_main_content').css('overflow', 'auto');
                self.$el.find('.o_content').css('overflow', 'initial');
                //action manager in abstract_web_client binded to scroll event, why?? Do I need here?
                self.$el.find('.o_main_content').on('scroll',core.bus.trigger.bind(core.bus, 'scroll'));

            }else{
                self.$el.find('.o_main_content').css('overflow', '');
                self.$el.find('.o_content').css('overflow', '');
                //action manager in abstract_web_client binded to scroll event, why?? Do I need here?
                self.$el.find('.o_main_content').off('scroll',core.bus.trigger.bind(core.bus, 'scroll'));
            }
          });
        },
        load_robo_menu: function(action){
            var robo_menu_name;
            if (action && action.action_descr){
                if (action.action_descr.robo_menu){
                    robo_menu_name = action.action_descr.robo_menu[0]
                }
                else if (action.action_descr.context){
                    robo_menu_name  = action.action_descr.context.robo_menu_name
                }
            }
            // if (action && action.action_descr && action.action_descr.context){
            //     if (!action.action_descr.context.robo_menu_name){
            //         if (action.action_descr.res_model === 'e.document'){
            //            action.action_descr.context.robo_menu_name = 'e_document.e_document_root';//TODO: change to e.document menu
            //            action.action_descr.context.robo_header = {fit: true};
            //         }else {
            //             action.action_descr.context.robo_menu_name = 'robo.menu_start';
            //         }
            //     }
            // }
            return {robo_menu_name: robo_menu_name};
        },
        // overridden just for the case if only robo menu available (for front users). In that case
        // self.menu.$el is empty and we need to find first menu_id from "robo_menu".
        bind_hashchange: function() {
            var self = this;
            $(window).bind('hashchange', this.on_hashchange);
            if (!session.URL_link) {
                $(window).bind('popstate', this.on_popstatechange);
            }

            var state = $.bbq.getState(true);
            if (_.isEmpty(state) || state.action === "login") {
                self.menu.is_bound.done(function() {
                    new Model("res.users").call("read", [[session.uid], ["action_id"]]).done(function(result) {
                        var data = result[0];
                        if(data.action_id) {
                            self.action_manager.do_action(data.action_id[0]);
                            self.menu.open_action(data.action_id[0]);
                        } else {
                            var first_menu_id = self.menu.$el.find("a:first").data("menu") || self.$el.find('.o_main .oe_secondary_menu').find("a:first").data("menu"); //actual change
                            if(first_menu_id) {
                                self.menu.menu_click(first_menu_id);
                            }
                        }
                    });
                });
            } else {
                $(window).trigger('hashchange');
            }
        },
        on_popstatechange: function(event){
            if (session.URL_link) {
                return;
            }
            if (this._ignore_hashchange) {
                this._ignore_hashchange = false;
                return;
            }

            var self = this;
            this.clear_uncommitted_changes().then(function () {
                var stringstate = $.deparam($.param(history.state||{}));
                if (!_.isEqual(self._current_state, stringstate)) {
                    var state = history.state||{};
                    if(!state.action && state.menu_id) {
                        self.menu.is_bound.done(function() {
                            self.menu.menu_click(state.menu_id);
                        });
                    } else {
                        state._push_me = false;  // no need to push state back...
                        self.action_manager.do_load_state(state, !!self._current_state).then(function () {
                            var action = self.action_manager.get_inner_action();
                            if (action) {
                                self.menu.open_action(action.action_descr.id, self.load_robo_menu(action)); //load aditional menu_id if found in path
                            }
                        });
                    }
                }
                self._current_state = stringstate;
            }, function () {
                if (event) {
                    self._ignore_hashchange = true;
                    window.location = '#';
                }
            });
        },
        _isStateEqual: function(obj1, obj2){
            if (!obj1 || !obj2){
                return false;
            }
            if (obj1.menu_id && obj2.menu_id && obj1.menu_id != obj2.menu_id){
                return false;
            }
            if (obj1.robo_menu_id && obj2.robo_menu_id && obj1.robo_menu_id != obj2.robo_menu_id){
                return false;
            }
            var rm = ['menu_id', 'robo_menu_id', '_push_me' ];
            return _.isEqual(_.omit(obj1, rm) , _.omit(obj2, rm));

        },
        on_hashchange: function(event) {
            if (this._ignore_hashchange) {
                this._ignore_hashchange = false;
                return;
            }

            var self = this;
            this.clear_uncommitted_changes().then(function () {
                var stringstate = event.getState(false);
                if (!self._isStateEqual(self._current_state, stringstate)) {
                    var state = event.getState(true);
                    if(!state.action && state.menu_id) {
                        self.menu.is_bound.done(function() {
                            self.menu.menu_click(state.menu_id);
                        });
                    } else {
                        state._push_me = false;  // no need to push state back...
                        self.action_manager.do_load_state(state, !!self._current_state).then(function () {
                            var action = self.action_manager.get_inner_action();
                            if (action) {
                                self.menu.open_action(action.action_descr.id, self.load_robo_menu(action)); //load aditional menu_id if found in path
                            }
                        });
                    }
                }
                self._current_state = stringstate;
            }, function () {
                if (event) {
                    self._ignore_hashchange = true;
                    window.location = event.originalEvent.oldURL;
                }
            });
        },
    });
});

