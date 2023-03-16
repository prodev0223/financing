robo.define('robo.FormView', function (require) {
    "use strict";

    var config = require('web.config');
    var core = require('web.core');
    var FormRenderingEngineMobile = require('robo.FormRenderingEngineMobile');
    var FormView = require('web.FormView');
    var Pager = require('web.Pager');
    var session = require('web.session');
    var Sidebar = require('web.Sidebar');
    var Model = require('web.DataModel');
    var Dialog = require('web.Dialog');

    var _t = core._t;
    var QWeb = core.qweb;

    FormView.include({
        defaults: _.extend({}, FormView.prototype.defaults, {
            disable_autofocus: config.device.touch,
        }),
        events: {
            "click .robo_group_collapsable > tbody tr:first-of-type": "toggle_collapsable_group",
            "click div.robo_group_collapsable > div.o_horizontal_separator": "toggle_collapsable_group",
        },
        init: function () {
            this._super.apply(this, arguments);
            this.robo_front = this.ViewManager.robo_front;
            if (true){ // if (config.device.size_class <= config.device.SIZES.XS) {
                if (this.robo_front) {
                    this.rendering_engine = new FormRenderingEngineMobile(this, {
                        // additional_buttons: _.compact(
                        //     [this.is_action_enabled('delete') && {label: _t('Delete'), $el: $(QWeb.render('FormRendering.button.delete', {label: _t('Delete')}))
                        //     }]
                        // ),
                        robo_front: this.robo_front,
                    });
                }
                else{
                    this.rendering_engine = new FormRenderingEngineMobile(this);
                }
            }

        },
        // start: function(){
        //     var self = this;
        //     //veiksmas additional buttons: delete
        //     this.$el.on('click','.remove_item', function(e){
        //         e.stopPropagation();
        //         e.preventDefault();
        //         self.on_button_delete();
        //         //close dropdown
        //         $(e.currentTarget).closest(".dropdown-menu").prev().dropdown("toggle");
        //     });
        //     return this._super.apply(this, arguments);
        // },
        toggle_sidebar: function(){
          //we removed delete button from sidebar and added to buttons, but we should keep toggle rules on these buttons
            if (this.robo_front) this.trigger('update_robo_buttons');
            return this._super();
        },
        render_sidebar: function($node) {
            if (!this.sidebar && this.options.sidebar) {
                this.sidebar = new Sidebar(this, {editable: this.is_action_enabled('edit'), robo_front: this.robo_front});
                if (this.fields_view.toolbar && !(this.robo_front)) {
                    this.sidebar.add_toolbar(this.fields_view.toolbar);
                }
                this.sidebar.add_items('other', _.compact([
                    !(this.robo_front) && this.is_action_enabled('delete') && { label: _t('Delete'), callback: this.on_button_delete, icon: 'icon-trash2', title: 'Išrinti'},
                    !(this.robo_front) && this.is_action_enabled('create') && { label: _t('Duplicate'), callback: this.on_button_duplicate, icon: 'icon-copy', title: 'Kurti kopiją'}
                ]));

                this.sidebar.appendTo($node);

                // Show or hide the sidebar according to the view mode
                this.toggle_sidebar();
            }
        },
        // render_buttons: function($node){
        //     this._super.apply(this, arguments);
        //     this.$buttons.on('click', '.o_form_button_create', this.on_button_create);
        // }
        toggle_buttons: function(){
            this._super();
            if (!!this.$buttons){
                this.$buttons.find('.o_form_button_create').toggle(!this.robo_front);
            }
        },
        display_translation_alert: function(){
            if (session.is_superuser){
                this._super.apply(this, arguments);
            }
        },
        do_show: function() {
            var self = this;
            return $.when(this._super.apply(this, arguments)).then(function(){
                if (self.$el.find('.robo-mail-compose-body').length > 0) {
                    var the_modal = $(self.getParent().getParent().$modal).find('.modal-dialog')
                    if (the_modal.length > 0) {
                        the_modal.toggleClass('robo-wizard-wide', true);
                    }
                }
                if (self.$el.find('.robo-form-xwide').length > 0) {
                    var the_modal = $(self.getParent().getParent().$modal).find('.modal-dialog')
                    if (the_modal.length > 0) {
                        the_modal.toggleClass('robo-wizard-xwide', true);
                    }
                }
                var collapsable_groups = self.$el.find('.robo_group_collapsable');
                $(collapsable_groups).each(function (index) {
                    var collapsable_group = this;
                    var is_collapsed = $(collapsable_group).hasClass('robo_group_collapsed');
                    var is_table = $(collapsable_group).is('table');
                    if (is_table) {
                        var rows = $(collapsable_group).find('tbody tr');
                        $(rows).each(function (index) {
                            if (index === 0) {
                                $(this).find("td").css("width", "auto");
                                if (is_collapsed) {
                                    $(this).append($('<i class="fa fa-chevron-down robo_collapsable_group_indicator"></i>'));
                                } else {
                                    $(this).append($('<i class="fa fa-chevron-up robo_collapsable_group_indicator"></i>'));
                                }
                            } else {
                                $(this).toggleClass('robo_collapsable_group_invisible_row', is_collapsed);
                            }
                        });
                    } else {
                        var title_div = $(collapsable_group).find('div.o_horizontal_separator');
                        if (title_div.length > 1) {
                            title_div = title_div[0];
                        }
                        $(title_div).css("width", "auto");
                        if (is_collapsed) {
                            $(title_div).append($('<i class="fa fa-chevron-down robo_collapsable_group_indicator" style="top: 0;"></i>'));
                        } else {
                            $(title_div).append($('<i class="fa fa-chevron-up robo_collapsable_group_indicator" style="top: 0;"></i>'));
                        }
                        var tables = $(collapsable_group).find('table');
                        $(tables).each(function (index) {
                            $(this).toggleClass('robo_collapsable_group_invisible_row', is_collapsed);
                        });
                    }
                });
            });
        },
        toggle_collapsable_group: function(event) {
            var collapsable_group = event.target.closest('.robo_group_collapsable');
            var is_collapsed = $(collapsable_group).hasClass('robo_group_collapsed');
            $(collapsable_group).toggleClass('robo_group_collapsed');
            var is_table = $(collapsable_group).is('table');
            if (is_table) {
                var rows = $(collapsable_group).find('tbody tr');
                if (rows.length > 0) {
                    var header_row = rows[0];
                    var collapsable_indicator = $(collapsable_group).find('.robo_collapsable_group_indicator');
                    if (collapsable_indicator.length > 0) {
                        collapsable_indicator.toggleClass('fa-chevron-up');
                        collapsable_indicator.toggleClass('fa-chevron-down');
                    }
                    $(rows).each(function (index) {
                        if (index !== 0) {
                            $(this).toggleClass('robo_collapsable_group_invisible_row', !is_collapsed);
                        }
                    });
                }
            } else {
                var title_div = $(collapsable_group).find('div.o_horizontal_separator');
                if (title_div.length > 1) {
                    title_div = title_div[0];
                }
                var collapsable_indicator = $(title_div).find('.robo_collapsable_group_indicator');
                if (collapsable_indicator.length > 0) {
                    collapsable_indicator.toggleClass('fa-chevron-up');
                    collapsable_indicator.toggleClass('fa-chevron-down');
                }
                var tables = $(collapsable_group).find('table');
                $(tables).each(function (index) {
                    $(this).toggleClass('robo_collapsable_group_invisible_row', !is_collapsed);
                });
            }
        },
        on_button_save: function() {
              if (this.dataset.model == "res.partner"){
                    var ids = this.datarecord.id;
                    var parent = this._super;
                    var parent_this = this
                    $.when(session.is_accountant()).then(function(is_accountant){
                      if (! is_accountant){
                      new Model('res.partner').call('get_lock_status_js', [ids]).then(function(response){
                          if (response[0]){
                                var message = _t(response[1]);
                                var self = this;
                                var def = $.Deferred();
                                var options = {
                                    title: _t("Warning"),
                                    confirm_callback: function() {
                                        this.on('closed', null, function() {
                                            parent.apply(parent_this);
                                            def.resolve();
                                        });
                                    },
                                    cancel_callback: function() {
                                        def.reject();
                                    },
                                };
                                var dialog = Dialog.confirm(this, message, options);
                                dialog.$modal.on('hidden.bs.modal', function() {
                                    def.reject();
                                });
                                return def;
                          }else{parent.apply(parent_this);}
                      });
                      }else{
                      parent.apply(parent_this);}
                 });
              }else{this._super.apply(this);}

        },
        /**
         * Instantiate and render the pager and add listeners on it.
         * Set this.pager
         * @param {jQuery} [$node] a jQuery node where the pager should be inserted
         * $node may be undefined, in which case the FormView inserts the pager into this.options.$pager
         */
        render_pager: function($node) {
            if (this.options.pager) {
                var self = this;
                var options = {
                    validate: _.bind(this.can_be_discarded, this),
                };

                this.pager = new Pager(this, this.dataset.ids.length, this.dataset.index + 1, 1, options);
                this.pager.on('pager_changed', this, function (new_state) {
                    // if (new_state && new_state.action_pager){
                    //     var action;
                    //     if (action = self.dataset.context.pager_actions) {
                    //         self.dataset.context.pager_actions.current_id = action.element_ids[new_state.current_min-1];
                    //         self.do_action({
                    //             type: 'ir.actions.act_window',
                    //             res_model: action.model,
                    //             res_id: action.element_ids[new_state.current_min-1],
                    //             views: [[action.element_views[new_state.current_min-1], 'form']],
                    //             target: 'current',
                    //             context: self.dataset.context,
                    //         }, {
                    //             additional_context: {
                    //                 clear_breadcrumbs: true,
                    //             }
                    //         });
                    //     }
                    // }
                    var action, view_id;
                    if (action = self.dataset.context.pager_actions){
                        this.pager.disable();
                        this.dataset.index = new_state.current_min - 1;
                        view_id = action.element_views[this.dataset.ids[this.dataset.index]];
                        var def = this.trigger('switch_mode_with_id', 'form', {pager: true}, view_id);
                        $.when(def).then(function () {
                            self.pager.enable();
                        });
                    }
                    else {
                        this.pager.disable();
                        this.dataset.index = new_state.current_min - 1;
                        this.trigger('pager_action_executed');
                        $.when(this.reload()).then(function () {
                            self.pager.enable();
                        });
                    }
                });

                this.pager.appendTo($node = $node || this.options.$pager);

                // Hide the pager in create mode
                if (this.get("actual_mode") === "create") {
                    this.pager.do_hide();
                }
            }
        },
    });

});


robo.define('robo.FormRenderingEngine', function (require) {
    "use strict";

    var config = require('web.config');
    var core = require('web.core');
    var FormRenderingEngine = require('web.FormRenderingEngine');

    var _t = core._t;
    var QWeb = core.qweb;

    FormRenderingEngine.include({
        init: function(view, options){
            this._super(view);
            if (options && options.robo_front){
                this.robo_front = true;
            }
            if (this.view && this.view.ViewManager && this.view.ViewManager.action) {
                if ((this.view.ViewManager.action.target === "new")) {
                    this.new_target = true;
                }
                if (this.view.ViewManager.action.transient) {
                    this.transient = true;
                }

                if (this.view.ViewManager.action.context.showDuplicate) {
                    this.show_duplicate = true;
                }
            }
        },
        process: function($tag) {
            var self = this;
            // Add button box post rendering when window resize and record loaded events
            if($tag.attr("name") === 'button_box') {
                this.view.is_initialized.then(function() {
                    var $buttons = $tag.children();
                    self.organize_button_box($tag, $buttons);

                    self.view.on('view_content_has_changed', self, function() {
                        this.organize_button_box($tag, $buttons);
                    });
                    core.bus.on('size_class', self, function() {
                        this.organize_button_box($tag, $buttons);
                    });
                });
            }
            if (($tag[0].nodeName.toLowerCase() == 'form') && this.robo_front && !this.new_target){
                if (!$tag.children('header').length){
                    $tag.prepend("<header/>");
                }

                if (this.show_duplicate) {
                    $tag.children('header').append($(QWeb.render('FormRendering.button.duplicate', {label: _t('Duplicate')})));
                }
                if (!this.transient) {
                    $tag.children('header').append($(QWeb.render('FormRendering.button.delete', {label: _t('Delete')})));
                }
            }
            return this._super($tag);
        },
        organize_button_box: function($button_box, $buttons) {
            var $visible_buttons = $buttons.not('.o_form_invisible');
            var $invisible_buttons = $buttons.filter('.o_form_invisible');

            // Get the unfolded buttons according to window size
            var nb_buttons = [2, 4, 6, 7][config.device.size_class];
            var $unfolded_buttons = $visible_buttons.slice(0, nb_buttons).add($invisible_buttons);

            // Get the folded buttons
            var $folded_buttons = $visible_buttons.slice(nb_buttons);
            if($folded_buttons.length === 1) {
                $unfolded_buttons = $buttons;
                $folded_buttons = $();
            }

            // Empty button box and toggle class to tell if the button box is full (LESS requirement)
            $buttons.detach();
            $button_box.empty();
            var full = ($visible_buttons.length > nb_buttons);
            $button_box.toggleClass('o_full', full).toggleClass('o_not_full', !full);

            // Add the unfolded buttons
            $unfolded_buttons.each(function(index, elem) {
                $(elem).appendTo($button_box);
            });

            // Add the dropdown with unfolded buttons if any
            if($folded_buttons.length) {
                $button_box.append($("<button/>", {
                    type: 'button',
                    'class': "btn btn-sm oe_stat_button o_button_more dropdown-toggle",
                    'data-toggle': "dropdown",
                    text: _t("Daugiau"),
                }));

                var $ul = $("<ul/>", {'class': "dropdown-menu o_dropdown_more", role: "menu"}).appendTo($button_box);
                $folded_buttons.each(function(i, elem) {
                    $('<li/>').appendTo($ul).append(elem);
                });
            }
        },
        process_header: function($statusbar) {
            if ($statusbar.parent().hasClass('extended_form')){
                $statusbar.addClass('extend_statusbar');
            }
            var $new_statusbar = this.render_element('FormRenderingStatusBar', $statusbar.getAttributes());
            this.handle_common_properties($new_statusbar, $statusbar);
            $statusbar.find('button').addClass('o_in_statusbar');
            //add also robo_front delete_button if exists
            this.fill_statusbar_buttons($new_statusbar.find('.o_statusbar_buttons'), $statusbar.contents('button').add($statusbar.contents('button_d')).add($statusbar.contents('button_dupl')));
            $new_statusbar.append($statusbar.find('field'));
            $statusbar.before($new_statusbar).remove();
            this.process($new_statusbar);
        },
        fill_statusbar_buttons: function($statusbar_buttons, $buttons) {
            $statusbar_buttons.append($buttons);
        },
        process_button: function ($button) {
            $button = this._super($button);
            if ($button.hasClass('oe_highlight')) {
                $button.addClass('btn-primary');
            } else if ($button.hasClass('o_in_statusbar')) {
                $button.addClass('btn-default');
            }
            $button.removeClass('o_in_statusbar oe_highlight');
            return $button;
        }
    });

    });

robo.define('robo.FormRenderingEngineMobile', function (require) {
    "use strict";

    var FormRenderingEngine = require('web.FormRenderingEngine');

    return FormRenderingEngine.extend({
        fill_statusbar_buttons: function ($statusbar_buttons, $buttons) {
            if(!$buttons.length) {
                return;
            }
            var $statusbar_buttons_dropdown = this.render_element('FormRenderingStatusBar_DropDown', {});
            $buttons.each(function(i, el) {
                $statusbar_buttons_dropdown.find('.dropdown-menu').append($('<li/>').append(el));
            });
            //add additional robo_front delete button to o_statusbar_buttons btn-group
            //Form view has an event handler
            // if (this.robo_front){
            //     $statusbar_buttons_dropdown.find('.dropdown-menu').append($('<li/>').append(this.button));
            // }
            $statusbar_buttons.append($statusbar_buttons_dropdown);
        },
    });

});

// robo.define('robo.FormRendering_buttonDelete', function (require) {
//     "use strict";
//
//     var Widget = require('web.Widget');
//
//     var VeiksmasButtonDelete = Widget.extend({
//         template: 'FormRendering.button.delete',
//         init: function(parent, callback){
//             this._super(parent);
//             this.callback = callback;
//         },
//         start: function(){
//             var self = this;
//             this.$el.on('click', function(){
//                 self.callback();
//             });
//             return this._super();
//         }
//
//     });
//
//     return VeiksmasButtonDelete;
//
// });




