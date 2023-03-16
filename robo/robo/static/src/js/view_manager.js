/**
 * Created by Edg on 1/11/2017.
 */
robo.define('robo.ViewManager', function (require) {
    "use strict";


    var config = require('web.config');
    var core = require('web.core');
    var Pager = require('web.Pager');
    var session = require('web.session');
    var utils = require('web.utils');
    var ViewManager = require('web.ViewManager');

    var QWeb = core.qweb;
    var _t = core._t;


    ViewManager.include({

        /**
         * add view id to URL, to find
         *
         * @returns {Object} the default view
         */
        do_push_state: function(state) {
            if (this.action_manager) {
                state.view_type = this.active_view.type;
                if (this.active_view.view_id && _.isNumber(this.active_view.view_id)){
                    state.view_id = this.active_view.view_id;
                }
                this.action_manager.do_push_state(state);
            }
        },
        /**
         * Special case for mobile mode: if there is one, use a mobile-friendly view as default view
         *
         * @returns {Object} the default view
         */
        get_default_view: function () {
            //ROBO: if "Sukurti naują" item clicked -> open form view or 'view' defined in action context!
            var force_view_open;
            if (this.action && this.action.context && this.action.context.default_view){
                if (this.views[this.action.context.default_view]) {
                    this.action.flags.default_view = this.action.context.default_view;
                    force_view_open = true;
                }
            }
            var default_view = this._super.apply(this, arguments);
            if (config.device.size_class <= config.device.SIZES.XS && !default_view.mobile_friendly && !force_view_open) {
                default_view = (_.find(this.views, function (v) { return v.mobile_friendly; })) || default_view;
            }
            return default_view;
        },

        init: function(parent, dataset, views, flags, options){

            this._super.apply(this, arguments);

            this.robo_fit = false;
            if (this.action.context && this.action.context.robo_header) {
                if (this.action.context.robo_header.fit) {
                    this.className += ' robo_header_fit';
                    this.robo_fit = true;
                }
                else {
                    this.className += ' robo_header';
                }
                if (this.action.res_model === 'e.document' && this.action.display_name === undefined) {
                    this.action.display_name = _t('Dokumentai');
                }
            } else if (this.action.res_model === 'e.document' && this.action.context) { //special multiple_form_tree case
                this.action.context.robo_header = {fit: true};
                this.action.display_name = this.action.display_name || _t('Dokumentai');
                this.className += ' robo_header';
            }

            this.robo_front = false;
            if (this.action.context && typeof this.action.context.robo_header === 'object') {
                this.robo_front = true;
            }


        },
        setup_search_view: function(){
            var view_group_by = {};
            var result;
            var context = this.action.context || [];
            _.each(context, function (value, key) {
                var match = /^view_([a-z_]+)_default_group_by$/.exec(key);
                if (match && this.action.view_mode && ~this.action.view_mode.indexOf(match[1])) {
                    if (this.views && this.views[match[1]]) {
                       result  = _.filter(value.split(','),
                            function(v){
                                return this.search_fields_view && this.search_fields_view.fields && this.search_fields_view.fields[v] && true
                        }, this);
                        if (result.length) {
                            view_group_by[match[1]] = result;
                        }
                    }
                }
            }, this);
            _.each(view_group_by, function(v, k){
               if (this.views[k]){
                   this.views[k].group_by = v;
               }
            }, this);

            return $.when(this._super());
        },
        start: function () {
            var def;
            var _super = this._super.bind(this);
            if (this.action && this.action.context && this.action.context.robo_header !==undefined && this.action.display_name) {
                def = this.render_robo_header(this.action.context.robo_header, this.action.display_name);
            }
            return $.when(def).then(function(){
                return _super();
            });
        },
        //if string with LT symbols comes from action context

        _decode_string: function(s){
            if (!s) return '';
            return s
            // var uint8array = new Uint8Array(s.split('').map(function(char) {return char.charCodeAt(0);}));
            // if (window.TextDecode) {
            //     return new TextDecoder().decode(uint8array);
            // }
            // else{//IE case, Safari
            //    //http://stackoverflow.com/questions/14028148/convert-integer-array-to-string-at-javascript
            //    var atos = function(arr) {
            //         for (var i=0, l=arr.length, s='', c; c = arr[i++];)
            //             s += String.fromCharCode(
            //                 c > 0xdf && c < 0xf0 && i < l-1
            //                     ? (c & 0xf) << 12 | (arr[i++] & 0x3f) << 6 | arr[i++] & 0x3f
            //                 : c > 0x7f && i < l
            //                     ? (c & 0x1f) << 6 | arr[i++] & 0x3f
            //                 : c
            //             );
            //         return s
            //     }
            //     return atos(uint8array);
            // }
        },
        render_robo_header: function (robo_header, robo_title) {
            var self = this;
            var requests = [];
            // this.robo_rights = {};
            //
            // if (robo_header.header_button_items && robo_header.header_button_items.length > 0){
            //     _.each(robo_header.header_button_items, function(el){
            //         if (el && el['rights']){
            //             if (typeof session[el['rights']] == 'function' && !self.robo_rights.hasOwnProperty(el['rights'])){
            //                 requests.push(session[el['rights']]());
            //                 self.robo_rights[el['rights']] = requests.length-1;
            //             }
            //         }
            //     })
            // }

            return $.when.apply($,requests).then(function() {

                //reform robo_rights {is_manager: true/false...}
                // var request_results = _.toArray(arguments);
                // _(self.robo_rights).each(function(v,k,list){
                //     list[k] = request_results[v];
                // });

                // robo_header
                var qweb_header_data = {};

                qweb_header_data.title = robo_title;
                qweb_header_data.header_button = robo_header.header_button;
                qweb_header_data.header_button_items = robo_header.header_button_items;
                qweb_header_data.header_help = robo_header.robo_help_header;

                //check if we have some rights to check in items

                qweb_header_data.header_button_class = robo_header.header_button_class;

                qweb_header_data.switcher = robo_header.switcher || false;
                qweb_header_data.switcher_header = robo_header.switcher_header || false;
                if (qweb_header_data.switcher_header) {
                    qweb_header_data.switcher_header_class = 'has-switcher_header'
                }
                else {
                    qweb_header_data.switcher_header_class = ''
                }

                if (qweb_header_data.header_help) {
                    qweb_header_data.help_data = robo_header.help_data
                }

                qweb_header_data.action1 = robo_header.action1 && robo_header.action1.action_id;
                qweb_header_data.menu1 = robo_header.action1 && robo_header.action1.menu_id;
                qweb_header_data.switcher1_name = _t(robo_header.action1 && robo_header.action1.switcher_name);

                qweb_header_data.action2 = robo_header.action2 && robo_header.action2.action_id;
                qweb_header_data.menu2 = robo_header.action2 && robo_header.action2.menu_id;
                qweb_header_data.switcher2_name = _t(robo_header.action2 && robo_header.action2.switcher_name);

                if (qweb_header_data.switcher == 'action1') {
                    qweb_header_data.switcher1_class = 'active';
                    qweb_header_data.switcher2_class = '';
                }
                else {
                    qweb_header_data.switcher2_class = 'active';
                    qweb_header_data.switcher1_class = '';
                }

                qweb_header_data.decoder = self._decode_string;
                qweb_header_data.debug = session.debug;

                // Inner function to render and prepare switch_buttons
                var _render_robo_header = function (qweb_header_data) {
                    var $header = $(QWeb.render('ViewManager.header', qweb_header_data));
                    return $header;
                };
                // Render 2 switch buttons but do not append them to the DOM as this will
                // be done later, simultaneously to all other ControlPanel elements
                self.robo_header = {};
                // self.robo_header.$header = _render_robo_header(_.extend(qweb_header_data, {robo_rights: self.robo_rights}));
                self.robo_header.$header = _render_robo_header(qweb_header_data);

                if (qweb_header_data.header_button_items !== undefined && qweb_header_data.header_button_items.length > 0) {
                    qweb_header_data.header_button_items.forEach(function (el) {
                        self.robo_header.$header.on('click', '.robo_header a.' + el['class'], function (e) {
                            e.stopPropagation();
                            e.preventDefault();
                            //ROBO: default action must open form view
                            var default_view = $(e.currentTarget).data('view') || 'form';
                            //ROBO: add prev action context
                            // self.do_action(el['action'], {additional_context: _.extend((self.action.context || {}), {'default_view': default_view})});
                            self.do_action(el['action'], {'view_type': default_view})
                        });
                    });
                }
            });
        },
        switch_mode_with_id: function(view_type, view_options, view_id){
            var self = this;
            //check if need to generate view
            var view;
            if (this.views[view_type+String(view_id)]){
                view = this.views[view_type+String(view_id)];
            }
            else{
                var view_type = 'form';
                var View = self.registry.get(view_type);
                if (!View) {
                    console.error("View type", "'"+view_type+"'", "is not present in the view registry.");
                    return;
                }
                var view_label = View.prototype.display_name;
                var view_descr = {
                    accesskey: View.prototype.accesskey,
                    button_label: _.str.sprintf(_t('%(view_type)s view'), {'view_type': (view_label || view_type)}),
                    controller: null,
                    // fields_view: view[2] || view.fields_view,
                    icon: View.prototype.icon,
                    label: view_label,
                    mobile_friendly: View.prototype.mobile_friendly,
                    multi_record: View.prototype.multi_record,
                    options: this.views['form'] && this.views['form'].options || view_options || {},
                    require_fields: View.prototype.require_fields,
                    title: self.title,
                    type: view_type,
                    view_id: view_id,
                };
                view = self.views[view_type+String(view_id)] = view_descr;
            }

            var old_view = this.active_view;

            if (!view || this.currently_switching) {
                return $.Deferred().reject();
            } else {
                this.currently_switching = true;  // prevent overlapping switches
            }

            // Ensure that the fields_view has been loaded
            var views_def;
            if (!view.fields_view) {
                views_def = this.load_views(view.require_fields, {pager_view_id: view_id});
            }

            return $.when(views_def).then(function () {
                if (view.multi_record) {
                    self.view_stack = [];
                } else if (self.view_stack.length > 0 && !(_.last(self.view_stack).multi_record)) {
                    // Replace the last view by the new one if both are mono_record
                    self.view_stack.pop();
                }
                self.view_stack.push(view);

                self.active_view = view;

                if (!view.loaded) {
                    if (!view.controller) {
                        view.controller = self.create_view(view, view_options);
                    }
                    view.$fragment = $('<div>');
                    view.loaded = view.controller.appendTo(view.$fragment).done(function () {
                        // Remove the unnecessary outer div
                        view.$fragment = view.$fragment.contents();
                        self.trigger("controller_inited", view.type, view.controller);
                    });
                }

                // Call do_search on the searchview to compute domains, contexts and groupbys
                if (self.search_view_loaded &&
                        self.flags.auto_search &&
                        view.controller.searchable !== false) {
                    self.active_search = $.Deferred();
                    $.when(self.search_view_loaded, view.loaded).done(function() {
                        self.searchview.do_search();
                    });
                }

                return $.when(view.loaded, self.active_search)
                    .then(function() {
                        return self._display_view(view_options, old_view).then(function() {
                            // self.trigger('switch_mode', view_type, view_options);
                        });
                    }).fail(function(e) {
                        if (!(e && e.code === 200 && e.data.exception_type)) {
                            self.do_warn(_t("Klaida"), view.controller.display_name + _t(" nepavyko atidaryti"));
                        }
                        // Restore internal state
                        self.active_view = old_view;
                        self.view_stack.pop();
                    });
            }).always(function () {
                self.currently_switching = false;
            });
        },
        render_view_control_elements: function () {
            if (!this.active_view.control_elements) {
                var elements = this._super();
                if (this.robo_header) {
                    elements.$robo_header = this.robo_header.$header;
                    //robo: turn robo_switch and robo_action button only in tree, kanban modes
                    var re = /kanban|tree|list/;
                    //old: if (this.active_view && this.active_view.type && !(~['kanban', 'tree', 'tree_robo', 'tree_expenses_robo'].indexOf(this.active_view.type))){
                    if (this.active_view && this.active_view.type && !(re.test(this.active_view.type))){
                        if (elements.$robo_header.find('.robo-tabs') !== undefined) elements.$robo_header.find('.robo-tabs').remove();
                        // if (elements.$robo_header.find('.btn-group') !== undefined) elements.$robo_header.find('.btn-group').remove();
                    }
                    if (this.flags.transient) {
                        elements.$buttons = $("<div>");
                        elements.$sidebar = $("<div>");
                        elements.$pager = $("<div>");
                    }

                }

                this.active_view.control_elements = elements;
            }
            return this.active_view.control_elements;
        },
        destroy: function () {
            if (this.active_view && this.active_view.control_elements) {
                if (this.active_view.control_elements.$switch_buttons) { //repaired original robo mistake
                    this.active_view.control_elements.$switch_buttons.off();
                }
                if (this.active_view.control_elements.$robo_header) {
                    this.active_view.control_elements.$robo_header.off();
                }
            }
            return this._super.apply(this, arguments);
        },
    });

});