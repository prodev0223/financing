 robo.define('robo_theme_v10.roboMenu', function(require) {
     'use strict';


     var core = require('web.core');
     var data = require('web.data');
     var localStorage = require('web.local_storage');
     var LogoMenu = require('robo_theme_v10.logo_menu');
     var RoboMenuHelp = require('robo.roboMenuHelp');
     var RoboMenuFit = require('robo.roboMenuFit');
     var Menu = require('web.Menu');
     var Menu_kita = require('robo.menu_kita');
     var Model = require('web.DataModel');
     var Session = require('web.session');


     var QWeb = core.qweb;

      Menu.include({

        init: function(){
            this._super.apply(this, arguments);
            this.$robo_menus = $('.o_main .o_sub_menu');
            var self = this;
            this.on("menu_bound", this, function() {
                // launch the fetch of needaction counters, asynchronous
                var $all_menus = self.$el.parents('.o_web_client').find('.o_sub_menu').find('[data-menu]');
                if ($all_menus.length == 0){
                    $all_menus = self.$robo_menus.find('[data-menu]');
                    var all_menu_ids = _.map($all_menus, function (menu) {return parseInt($(menu).attr('data-menu'), 10);});
                    if (!_.isEmpty(all_menu_ids)) {
                        this.do_load_needaction(all_menu_ids);
                    }
                }
            });
            this.sheduled = false;
            //ROBO: called after url update
            this.getParent().on('state_pushed', this, function(state){
                state = $.deparam($.param(state), true);

                if (state['force_back_menu_id']){
                    Session.robo_front = false;
                    self.open_menu(state['force_back_menu_id']);
                }
                else  if (state['robo_menu_id']){
                    var left_menu = this.$secondary_menus.filter(function(){
                      return $(this).parent().is('.o_main');
                    });
                    var $activate =left_menu.find('[data-menu='+state['robo_menu_id']+']').parent('li');
                    var $current_active = left_menu.find('li.active');

                    if (! $activate.is($current_active)){
                        $current_active.toggleClass('active', false);
                        $activate.toggleClass('active', true);
                    }

                    if (!left_menu.is(":visible")){
                        Session.robo_front = true;
                        self.open_menu(state['robo_menu_id']);
                    }

                }
            })
        },
        bind_menu_fit: function(){
          this.menuFitIcons = new RoboMenuFit(this);
          //parent is webClient
          this.menuFitIcons.setElement(this.getParent().$el.find('div.robo-menu-fit-icons'));
        },
        bind_menu: function() {
            var self = this;
            this.bind_menu_fit();
            this.$secondary_menus = this.$el.parents().find('.o_sub_menu');
            // If jquery did not find sub-menu in Menu widget.
            // This happens if main menu is not available due to security restrictions.
            if (self.$secondary_menus.length === 0) {
                self.$secondary_menus = self.$robo_menus;
            }
            this.$secondary_menus.on('click', '[data-menu]', this.on_menu_click);
            this.$el.on('click', '[data-menu]', function (event) {
                event.preventDefault();
                var menu_id = $(event.currentTarget).data('menu');
                var needaction = $(event.target).is('div#menu_counter');
                core.bus.trigger('change_menu_section', menu_id, needaction);
            });
            // Hide second level submenus
            this.$secondary_menus.find('.oe_menu_toggler').siblings('.oe_secondary_submenu').addClass('o_hidden');
            if (self.current_menu) {
                self.open_menu(self.current_menu);
            }
            this.trigger('menu_bound');
            var lazyreflow = _.debounce(this.reflow.bind(this), 200);
            core.bus.on('resize', this, function() {
                if ($(window).width() < 768 ) {
                    lazyreflow('all_outside');
                } else {
                    lazyreflow();
                }
            });
            core.bus.trigger('resize');

            this.is_bound.resolve();
        },
        start: function(){
            var self = this;
             if (this.$el.length == 0){
                var force_renew_menu = this.$robo_menus.find('[data-menu-name="eDokumentai"],[data-menu-name="Išlaidos"]');
                this.force_renew_menu_ids = _.compact(_.map(force_renew_menu, function (menu) {return parseInt($(menu).attr('data-menu'), 10);}));
            }
            return $.when(this._super.apply(this, arguments)).then(function(){
                    // //If jquery did not find sub-menu in Menu widget.
                    // // This happens if main menu is not available due to security restrictions.
                    // if (self.$secondary_menus.length === 0){
                    //     self.$secondary_menus = $('.o_main .o_sub_menu');
                    //     //The following binding is very important one. Without it hashChange from web_client will
                    //     // do_action without clearing breadcrumbs! So elements can overlap.
                    //     self.$secondary_menus.on('click', 'a[data-menu]', self.on_menu_click);
                    // }

                    var logoMenu = new LogoMenu(self);
                    var $logoMenuPlace = self.$secondary_menus.find('.o_sub_menu_logo');

                    var roboMenuHelp = new RoboMenuHelp(self);
                    var $helpMenuPlace = self.$secondary_menus.parents().find('.o_main_content');

                    // bind help menu action - show help-line
                    self.$secondary_menus.on('click', '.robo-help-menu', function(e){
                        self.do_action('robo.robo_client_ticket_action',{
                          clear_breadcrumbs: true,
                          view_type:'tree',
                       });
                    });

//                    self.$secondary_menus.find('.robo-help-menu').hover(function(e){
//                        var el = $(e.currentTarget).parents().find('.robo-help-line');
//                        if (el.hasClass('super-hide')) {el.removeClass('super-hide');}},
//                        function(e){
//                        var el = $(e.currentTarget).parents().find('.robo-help-line');
//                        if (el.hasClass('super-hide') === false) {el.addClass('super-hide');}}
//                        );

                    //bind kita menu action
                    var $menu_kitas = self.$secondary_menus.find('.robo-kita-menu');
                    $menu_kitas.each(function(indx, el){
                        var menu_kita = new Menu_kita($(el), self);
                        self.$secondary_menus.on('click', '.'+el.className.split(' ').join('.'), function(e){
                            // Activate current menu item
                            self.$secondary_menus.find('.active').removeClass('active');
                            $(e.currentTarget).parent().addClass('active');
                            menu_kita.click();
                        });
                    });

                    self._robo_badges();
                    core.bus.on('click', this, function(e){
                       if ($(e.target).closest('.robo-help-line').length === 0 && $(e.target).closest('.robo-help-menu').length === 0){
                           self.$secondary_menus.parents().find('.robo-help-line').toggleClass('super-hide', true);
                       }
                    });

                    return $.when(logoMenu.appendTo($logoMenuPlace), self.show_hide_menu(),roboMenuHelp.appendTo($helpMenuPlace), self.menuFitIcons.start());
                });
        },
        _robo_badges: function(){
             // click on expenses badge
            var self = this;
            this.$secondary_menus.on('click', '.badge.robo-expenses-badge', function(e){
                e.stopPropagation(); //we must stop bubbling
                e.preventDefault();
                self.do_action('robo.robo_expenses_action_badge',{
                  clear_breadcrumbs: true,
                  view_type:'tree',
               });
            });
            this.$secondary_menus.on('click', '.badge.robo-e_document-badge', function(e){
                e.stopPropagation(); //we must stop bubbling
                e.preventDefault();
                self.do_action('e_document.e_document_action_badge',{
                  clear_breadcrumbs: true,
                  additional_context: {
                    search_default_confirm:1,
                    search_default_draft:1,
                  },
                  view_type:'tree',
               });
            });
        },
        show_hide_menu: function(){
            var $sub_menu_left;
            if (this._no_app_menu()){ //if jquery did not found app menu in parent Menu widget
                $sub_menu_left = this.$secondary_menus.filter(function(){
                     return $(this).parent().is('.o_main');
                });
                $sub_menu_left.toggleClass('super-hide',false);
                this.$secondary_menus.find('.oe_secondary_menu').show();
            }
        },
        _no_app_menu: function(){
            //if jquery did not found app menu in parent Menu widget - official menu does not exist
            if (this.$el.length === 0) return true;
            return false;
        },
        open_menu: function(id){

          //If app menu does not exist
          if (this._no_app_menu()) {
            this.current_menu = id;
            Session.active_id = id;
            Session.robo_front = true;
            localStorage.setItem('active_menu_id', id);

            // Activate current menu item and show parents
            var $clickedRoboMenu = this.$secondary_menus.find('[data-menu=' + id + ']');
            this.$secondary_menus.find('.active').removeClass('active');

            if ($clickedRoboMenu.closest('ul').prev('.robo-kita-menu').length === 0){
                $clickedRoboMenu.parent().toggleClass('active',true);
            }
            else{
               $clickedRoboMenu.parent().toggleClass('active',true);
               $clickedRoboMenu.closest('ul').prev('.robo-kita-menu').parent().toggleClass('active',true);
            }

            return;
          }
          //else
          this.current_menu = id;
          Session.active_id = id;
          localStorage.setItem('active_menu_id', id);
          var isRoboMenu = false;
          var $sub_menu_left, $sub_menu_above, $clicked_menu, $menu_parent, $sub_menu_above_toHide, $clickedRoboMenu, $sub_menu, $current_active;
          var robo_vadovas_app;

          $sub_menu_left = this.$secondary_menus.filter(function(){
              return $(this).parent().is('.o_main');
          });
          $sub_menu_above = this.$secondary_menus.filter(function(){
              return !$(this).parent().is('.o_main');
          });
          $sub_menu_above_toHide = this.$el.parents().find('.navbar.main-nav[role="navigation"]'); //debug=


          if ($sub_menu_left.find('[data-menu=' + id + ']').length > 0){
              isRoboMenu = true;
          }
          else{//maybe its robo Vadovas
              //clicked on app_list or menu.
              $clicked_menu = this.$el.add($sub_menu_above).find('[data-menu=' + id + ']');

              if ($sub_menu_above.has($clicked_menu).length) {
                $menu_parent= $clicked_menu.closest('.oe_secondary_menu[data-menu-parent]');
                if ($menu_parent.length){
                    robo_vadovas_app = !!$menu_parent.find('li.app-name').is('.robo_main_menu')
                }
              }
              else {
                robo_vadovas_app= !!$clicked_menu.is('.robo_main_menu');
              }
          }

          if(isRoboMenu || robo_vadovas_app){
              Session.robo_front = true;
              if (this.is_debug_mode()){
                $sub_menu_above.hide();
                $sub_menu_above_toHide.toggleClass('super-hide', false);
              }
              else{
                $sub_menu_above_toHide.toggleClass('super-hide', true);
              }

              $clickedRoboMenu = $sub_menu_left.find('[data-menu=' + id + ']');
              //special case to show active for robo_extended menu
              if ($clickedRoboMenu.closest('ul').prev('.robo-kita-menu').length !== 0){
                 $clickedRoboMenu.closest('ul').prev('.robo-kita-menu').parent().toggleClass('active',true);
              }
              else
              {
                  $current_active = $sub_menu_left.find('li.active');

                  if (!$clickedRoboMenu.parent('li').is($current_active)) {
                      $current_active.toggleClass('active', false);
                      $clickedRoboMenu.parent('li').toggleClass('active', true);
                  }
              }
              //ROBO menu items unhide
              //robo menu click
              if ($clickedRoboMenu.parents('.oe_secondary_menu').length)
              {
                  $clickedRoboMenu.parents('.oe_secondary_menu').show();
              }
              else // robo app click
              {
                $sub_menu_left.find('.oe_secondary_menu').show();
              }

              $sub_menu_left.toggleClass('super-hide',false);
          }
          else{//backend menu
              Session.robo_front = false;
              if (this.is_debug_mode()){
                $sub_menu_above.show();
              }
              else{
                $sub_menu_above_toHide.show();
              }
              $sub_menu_left.toggleClass('super-hide',true);

              $clicked_menu = this.$el.add($sub_menu_above).find('[data-menu=' + id + ']');
              if ($sub_menu_above.has($clicked_menu).length) {
                    $sub_menu = $clicked_menu.parents('.oe_secondary_menu');
              } else {
                    $sub_menu = $sub_menu_above.find('.oe_secondary_menu[data-menu-parent=' + $clicked_menu.attr('data-menu') + ']');
              }

              $sub_menu_above.find('.oe_secondary_menu').hide();
              $sub_menu.show();

              $sub_menu_above_toHide.toggleClass('super-hide', false);

          }
        },

        is_debug_mode: function(){
          return Session.debug;
        },

        open_action: function (id, robo_context) {
          var self = this;
          var $sub_menu_left = this.$secondary_menus.filter(function(){
              return $(this).parent().is('.o_main');
          });
          var $menu;

          if ($sub_menu_left.length && $sub_menu_left.find('a[data-action-id="' + id + '"]').length){
              $menu = $sub_menu_left.find('a[data-action-id="' + id + '"]').first();
          }
          else {
              $menu = this.$el.add(this.$secondary_menus).find('a[data-action-id="' + id + '"]');
          }

          var menu_id = $menu.data('menu');
          if (menu_id) {
              this.open_menu(menu_id);
          }
          else if (robo_context && robo_context.robo_menu_name){
              id = robo_context.robo_menu_name;
              if (!isNaN(id) && typeof id === 'number') {
                  self.open_menu(robo_context.robo_menu_name);
              } else if (typeof id === 'string') {
                  $.when(new Model('ir.ui.menu').call('get_robo_menu_id', [id])).then(function (robo_menu_id) {
                      self.open_menu(robo_menu_id);
                  });
              }
          }
          else if (localStorage.getItem('active_menu_id')){
              self.open_menu(parseInt(localStorage.getItem('active_menu_id'), 10));
          }
        },
        // destroy: function(){
        //     this._super.apply(this, arguments);
        //     localStorage.removeItem("active_menu_id");
        // },
        do_reload_needaction: function () {
          var self = this;
          if (self.current_menu) {
              self.do_load_needaction(_.union([self.current_menu], self.force_renew_menu_ids)).then(function () {
                  self.trigger("need_action_reloaded");
              });
          }
        },
        on_needaction_loaded: function(data) {
            var self = this;
            this.needaction_data = data;
            _.each(this.needaction_data, function (item, menu_id) {
                var $item = self.$secondary_menus.find('[data-menu="' + menu_id + '"]');
                $item.find('.badge').remove();
                if (item.needaction_counter && item.needaction_counter > 0) {
                    // todo, this is a workaround, but since ROBO only has two languages atm, it's sufficient
                    if ($item.data('menu-name') === 'Išlaidos' || $item.data('menu-name') === 'Expenses'){
                       $item.append(QWeb.render("robo.expense_needaction_counter", { widget : item }));
                    }
                    // todo, this is a workaround, but since ROBO only has two languages atm, it's sufficient
                    else if ($item.data('menu-name') === 'eDokumentai' || $item.data('menu-name') === 'eDocuments'){
                       $item.append(QWeb.render("robo.e_document_needaction_counter", { widget : item }));
                    }
                    else{
                        $item.append(QWeb.render("robo.needaction_counter", { widget : item }));
                    }
                }
            });
        },
        //  ROBO: make sure session value robo_front is updated before we read model context.
        _force_renew_session_robo_front: function(id) {
            var isRoboMenu = false;
            var $sub_menu_left, $sub_menu_above, $clicked_menu, $menu_parent;
            var robo_vadovas_app;

            $sub_menu_left = this.$secondary_menus.filter(function () {
                return $(this).parent().is('.o_main');
            });
            $sub_menu_above = this.$secondary_menus.filter(function () {
                return !$(this).parent().is('.o_main');
            });

            if ($sub_menu_left.find('[data-menu=' + id + ']').length > 0) {
                isRoboMenu = true;
            }
            else {//maybe its robo Vadovas
                //clicked on app_list or menu.
                $clicked_menu = this.$el.add($sub_menu_above).find('[data-menu=' + id + ']');

                if ($sub_menu_above.has($clicked_menu).length) {
                    $menu_parent = $clicked_menu.closest('.oe_secondary_menu[data-menu-parent]');
                    if ($menu_parent.length) {
                        robo_vadovas_app = !!$menu_parent.find('li.app-name').is('.robo_main_menu')
                    }
                }
                else {
                    robo_vadovas_app = !!$clicked_menu.is('.robo_main_menu');
                }
            }
            Session.robo_front = isRoboMenu || robo_vadovas_app;
        },
        on_change_top_menu: function(menu_id, needaction) {
            if (!this._no_app_menu()) {
                this._force_renew_session_robo_front();
            }
            this._super.apply(this, arguments);
        }

      });
 });