robo.define('robo.ControlPanel', function (require) {
    "use strict";

    var config = require('web.config');
    var ControlPanel = require('web.ControlPanel');
    var core = require('web.core');
    var session = require('web.session');
    var data = require('web.data');

    ControlPanel.include({
        MAX_LINK_LENGTH: 4,
        init: function(){
          this._super.apply(this,arguments);
          this.wasRoboHeader = false;
          this.robo_fit = false;
          this.robo_show_switch_buttons = false;
          this.robo_xs_header = false;
        },
        start: function () {
            var self = this;
            var $header = this.$('.o_cp_robo_header');
            var $breadcrumbs = this.$('.breadcrumb:not(.robo_breadcrumb)'); //change back
            var $robo_breadcrumbs = this.$('.robo_breadcrumb');
            return $.when(this._super()).then(function () {
                self.nodes.$robo_header = $header;
                self.nodes.$breadcrumbs = $breadcrumbs;
                self.nodes.$robo_breadcrumbs = $robo_breadcrumbs;
            });
        },
        _contains_robo_header: function(breadcrumbs){
            var has_robo_header = false;
            var index = breadcrumbs.length-1;
            has_robo_header = breadcrumbs.length > 0
                && breadcrumbs[index].action
                && breadcrumbs[index].action.action_descr
                && breadcrumbs[index].action.action_descr.context
                && breadcrumbs[index].action.action_descr.context.robo_header;

            if (has_robo_header){
                this.robo_fit = !!breadcrumbs[index].action.action_descr.context.robo_header.fit;
                this.robo_show_switch_buttons = !!breadcrumbs[index].action.action_descr.context.robo_header.show_switch_buttons || breadcrumbs[index].action.action_descr.context.force_show_switch_buttons;
                this.robo_xs_header = !!breadcrumbs[index].action.action_descr.context.robo_header.robo_xs_header;
                this.small_screen = config.device.size_class <= config.device.SIZES.XS;
                // this.transient = !!breadcrumbs[0].action.action_descr.transient;
                return true;
            }

            return false;
        },
         /**
         * Private function that renders a breadcrumbs' li Jquery element
         */
        _render_robo_breadcrumbs_li: function (bc, index, length) {
            var self = this;
            var is_last = (index === length-1);
            var li_content = bc.title && _.escape(bc.title.trim()) || data.noDisplayContent;
            var $bc = $('<li>')
                .append(is_last ? li_content : $('<a>').html(li_content))
                .toggleClass('active', is_last);
            if (!is_last) {
                $bc.click(function () {
                    self.trigger("on_breadcrumb_click", bc.action, bc.index);
                });
            }
            return $bc;
        },
        _prepare_front_link: function(elements){
          if (elements.length){
              if (elements.length == 1){
                  return []
              }
              else if (elements.length > this.MAX_LINK_LENGTH){
                 var last_actions = _.last(elements, this.MAX_LINK_LENGTH);
                 last_actions.unshift($('<li>').html('...'));
                 return last_actions;
              }
              else{
                  return elements;
              }
          }
        },
        _render_breadcrumbs: function (breadcrumbs) {

            if (this._contains_robo_header(breadcrumbs)){
                var self = this;

                // this.$('.breadcrumb:not(.robo_breadcrumb)').toggleClass('super-hide', true);
                // this.$('.robo_breadcrumb').toggleClass('super-hide', false);

                if (!this.robo_fit || this.robo_form_view){
                    this.$el.toggleClass('container', true);
                }
                else{
                    this.$el.toggleClass('container', false);
                }

                this.$('.o_cp_robo_header').attr('id', 'cp_header');
                if (!this.robo_form_view) {
                    if (this.robo_fit) {
                        if (this.robo_xs_header){
                            this.$('#cp_header').toggleClass('robo_xs_header', true);
                            this.$('#cp_header').toggleClass('robo_cp_header_fit', false);
                            this.$('#cp_header').toggleClass('o_cp_robo_header', false);
                        }else{
                            this.$('#cp_header').toggleClass('o_cp_robo_header', true);
                            this.$('#cp_header').toggleClass('robo_cp_header_fit', true);
                            this.$('#cp_header').toggleClass('robo_xs_header', false);
                        }
                    }
                    else {
                        this.$('#cp_header').toggleClass('o_cp_robo_header', true);
                        this.$('#cp_header').toggleClass('robo_cp_header_fit', false);
                        this.$('#cp_header').toggleClass('robo_xs_header', false);
                    }
                }

                if (!this.wasRoboHeader) {
                    core.bus.trigger('roboHeaderScollBar', true);
                    this.wasRoboHeader = true;
                }

                return {
                        value: this.session.show_history_links && !this.small_screen && this._prepare_front_link(breadcrumbs.map(function (bc, index) {
                                return self._render_robo_breadcrumbs_li(bc, index, breadcrumbs.length);
                                }), 4) || $(),
                        front: true
                    };
            }else{
                if (this.wasRoboHeader){
                    // this.$('.breadcrumb:not(.robo_breadcrumb)').toggleClass('super-hide', false);
                    // this.$('.robo_breadcrumb').toggleClass('super-hide', true);

                    this.$el.toggleClass('container',false);//catch if we need to fit controlPanel in container; maybe not the best place;
                    core.bus.trigger('roboHeaderScollBar', false);
                    this.wasRoboHeader = false;
                }
            }
            return {
                        value: !this.small_screen && this._super.apply(this, arguments) || $(),
                        front: false,
                    };
        },
         /**
         * Updates the content and displays the ControlPanel
         * ROBO: hides swicth buttons in front if not robo_fit
         * @param {Object} [status.active_view] the current active view
         * @param {Array} [status.breadcrumbs] the breadcrumbs to display (see _render_breadcrumbs() for
         * precise description)
         * @param {Object} [status.cp_content] dictionnary containing the new ControlPanel jQuery elements
         * @param {Boolean} [status.hidden] true if the ControlPanel should be hidden
         * @param {openerp.web.SearchView} [status.searchview] the searchview widget
         * @param {Boolean} [status.search_view_hidden] true if the searchview is hidden, false otherwise
         * @param {Boolean} [options.clear] set to true to clear from control panel
         * elements that are not in status.cp_content
         */
        update: function(status, options) {
            this.robo_form_view = false;
            if (status && status.active_view === 'form' || options.view_type === 'form'){
                this.robo_form_view = true;
            }
            this._update(status, options);
            // this._super.apply(this, arguments);//here we render
            if (status && status.breadcrumbs){
                if (this._contains_robo_header(status.breadcrumbs) && (!this.robo_show_switch_buttons || this.small_screen)){
                    this.nodes.$switch_buttons.hide();
                }
                else{
                    this.nodes.$switch_buttons.show();
                }
            }

        },
        _clear_breadcrumbs_handlers: function(){
            this._super.apply(this, arguments);
            if (this.$robo_breadcrumbs) {
                _.each(this.$robo_breadcrumbs, function ($bc) {
                    $bc.off();
                });
            }
        },
        _update: function(status, options) {
            this._toggle_visibility(!status.hidden);

            // Don't update the ControlPanel in headless mode as the views have
            // inserted themselves the buttons where they want, so inserting them
            // again in the ControlPanel will remove them from where they should be
            if (!status.hidden) {
                options = _.defaults({}, options, {
                    clear: true, // clear control panel by default
                });
                var new_cp_content = status.cp_content || {};

                // Render the breadcrumbs
                if (status.breadcrumbs) {
                    var breadcrumbs_type;
                    this._clear_breadcrumbs_handlers();
                    breadcrumbs_type = this._render_breadcrumbs(status.breadcrumbs);
                    if (breadcrumbs_type.front){
                        this.$robo_breadcrumbs = breadcrumbs_type.value;
                        new_cp_content.$robo_breadcrumbs = this.$robo_breadcrumbs;
                        this.$breadcrumbs = $();
                    }
                    else{
                        this.$breadcrumbs = breadcrumbs_type.value;
                        new_cp_content.$breadcrumbs = this.$breadcrumbs;
                        this.$robo_breadcrumbs = $();
                    }

                }

                // Detach control_panel old content and attach new elements
                if (options.clear) {
                    this._detach_content(this.nodes);
                    // Show the searchview buttons area, which might have been hidden by
                    // the searchview, as client actions may insert elements into it
                    this.nodes.$searchview_buttons.show();
                } else {
                    this._detach_content(_.pick(this.nodes, _.keys(new_cp_content)));
                }
                this._attach_content(new_cp_content);

                // Update the searchview and switch buttons
                this._update_search_view(status.searchview, status.search_view_hidden);
                if (status.active_view_selector) {
                    this._update_switch_buttons(status.active_view_selector);
                }
            }
        },
        _update_search_view: function(searchview, is_hidden){
            this._super.apply(this, arguments);
            this.nodes.$robo_header.children().first().toggleClass('cp_header_mb', !is_hidden);
            this.nodes.$searchview.css("min-height","0px");
            if (! this.robo_xs_header){
                this.nodes.$robo_header.children().first().css("margin-bottom","20px");
            }
        }
    });

});